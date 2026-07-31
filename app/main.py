"""HTTP entry point: the same pipeline the CLI runs, reachable from a browser.

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

Holds no logic of its own. Its whole job is translation: a JSON body into the
pipeline's arguments, and the pipeline's exceptions into status codes. The
steps themselves live in src/pipeline.py, shared with src/run_query.py, so the
two entry points cannot drift apart.

The API key never leaves this process. The browser only ever knows /api/query.
"""

import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import QueryMetrics, QueryRequest, QueryResponse, SafetyDecision
from src.json_validator import ContractViolationError
from src.pipeline import QueryOutcome, answer_query

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Asistente de soporte al cliente",
    version="1.0.0",
    # Without this openapi.json carries no host, and a client generated from it
    # -- Postman, or any codegen -- builds its base URL as an empty string and
    # every request comes out as http:///api/query. The absolute entry goes
    # first because that is the one such a client picks up. The relative one is
    # second so /docs still works when the server was started on another port,
    # which happens whenever 8000 is already taken.
    servers=[
        {"url": "http://127.0.0.1:8000", "description": "Local, el puerto por defecto"},
        {"url": "/", "description": "El mismo origen, para cualquier otro puerto"},
    ],
    description=(
        "Recibe una consulta de soporte y devuelve el contrato JSON de cuatro "
        "campos, junto con lo que costó producirlo.\n\n"
        "El esquema de `response` se genera desde `src/json_validator.py`, que "
        "es el mismo módulo que valida la salida del modelo: lo que se ve acá "
        "es la especificación ejecutable, no una copia escrita a mano."
    ),
)


# A rate limit is the one guard that belongs in the transport rather than in
# the pipeline. safety.py reads the query; this reads a clock. It also cannot
# apply to the CLI, where one command is one query typed by a person.
#
# What it protects is money: every call to /api/query spends about $0.00027 and
# nothing else in the system counts how often that happens. 30 per minute is
# roughly ten times what a person clicking through the console reaches and a
# hundredth of what a loop does, which caps the damage at ~$0.008 per minute.
RATE_LIMIT = 30
WINDOW_S = 60

# ponytail: one global bucket, not one per client. The server binds to
# 127.0.0.1, so every request already comes from the same address and a dict
# keyed by IP would hold exactly one entry. Move to dict[str, deque] the day
# this is exposed beyond localhost.
_hits: deque[float] = deque()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Cap how often /api/query can be called, in a sliding one-minute window.

    Only that path. Static files and /docs cost nothing to serve, and a 429
    there would break the console without protecting anything.

    No lock is needed, which is worth being explicit about because the route
    below deliberately is not async. This function is, so it runs on the event
    loop, and there is no await between reading the deque and appending to it:
    no other request can interleave. The route runs in a threadpool instead,
    which is why metrics.py needs its own lock and this does not.
    """
    if request.url.path == "/api/query":
        now = time.monotonic()

        # Drop what has aged out. A sliding window rather than a fixed one:
        # a fixed window is two lines shorter but lets 2x the limit through at
        # the boundary between windows, which is the burst worth stopping.
        while _hits and now - _hits[0] > WINDOW_S:
            _hits.popleft()

        if len(_hits) >= RATE_LIMIT:
            # Retry-After says when the oldest hit expires, which is the
            # earliest moment a slot actually frees up.
            retry_after = int(WINDOW_S - (now - _hits[0])) + 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"Límite de {RATE_LIMIT} consultas por minuto alcanzado. "
                        f"Reintentá en {retry_after} segundos."
                    )
                },
                headers={"Retry-After": str(retry_after)},
            )

        _hits.append(now)

    return await call_next(request)


def _to_response(outcome: QueryOutcome) -> QueryResponse:
    """Turn what the pipeline produced into what the HTTP layer publishes."""
    metrics = None
    if outcome.usage is not None:
        metrics = QueryMetrics(
            tokens_prompt=outcome.usage.tokens_prompt,
            tokens_completion=outcome.usage.tokens_completion,
            total_tokens=outcome.usage.total_tokens,
            latency_ms=outcome.usage.latency_ms,
            estimated_cost_usd=outcome.cost.total_usd,
        )

    return QueryResponse(
        response=outcome.response,
        metrics=metrics,
        safety=SafetyDecision(
            blocked=outcome.verdict.blocked,
            layer=outcome.verdict.layer or None,
            reason=outcome.verdict.reason or None,
        ),
        template=outcome.template,
    )


# Declared with def rather than async def, deliberately. The chat call blocks
# for well over a second; inside a coroutine it would stall the event loop and
# the whole server with it. Starlette runs a sync route in a threadpool, which
# is the correct behaviour here. Writing async without awaiting the I/O would
# be worse than not writing it.
@app.post(
    "/api/query",
    response_model=QueryResponse,
    summary="Responder una consulta de soporte",
    responses={
        200: {
            "description": (
                "La respuesta cumple el contrato, **o** la consulta fue "
                "bloqueada por la capa de seguridad. Un bloqueo no es un error: "
                "devuelve los mismos cuatro campos, lo señala en `safety.blocked` "
                "y trae `metrics` en null porque nunca se hizo la llamada."
            )
        },
        422: {"description": "El cuerpo del pedido no cumple el esquema."},
        429: {
            "description": (
                f"Se superaron las {RATE_LIMIT} consultas por minuto. La cabecera "
                "`Retry-After` indica en cuántos segundos se libera un lugar."
            )
        },
        500: {"description": "El modelo respondió, pero violando el contrato."},
        502: {"description": "Falló la llamada a la API de OpenAI."},
    },
)
def create_query(request: QueryRequest) -> QueryResponse:
    """Run one query through the pipeline and report what it cost.

    A block returns 200, not 403, because the CLI returns exit code 0 for the
    same case. Two entry points disagreeing about what counts as a failure is
    exactly what sharing the pipeline was meant to prevent.
    """
    try:
        outcome = answer_query(request.query, request.template, source="api")
    except ContractViolationError as error:
        # The call worked; what failed is this project's own prompt.
        raise HTTPException(status_code=500, detail=str(error)) from error
    except FileNotFoundError as error:
        # Unreachable while template is a Literal, kept so a widened type
        # cannot turn into a 500.
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        # The service upstream failed, which is what 502 means.
        raise HTTPException(status_code=502, detail=str(error)) from error

    return _to_response(outcome)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the console."""
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
