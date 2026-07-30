"""HTTP entry point: the same pipeline the CLI runs, reachable from a browser.

    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

Holds no logic of its own. Its whole job is translation: a JSON body into the
pipeline's arguments, and the pipeline's exceptions into status codes. The
steps themselves live in src/pipeline.py, shared with src/run_query.py, so the
two entry points cannot drift apart.

The API key never leaves this process. The browser only ever knows /api/query.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import QueryMetrics, QueryRequest, QueryResponse, SafetyDecision
from src.json_validator import ContractViolationError
from src.pipeline import QueryOutcome, answer_query

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Asistente de soporte al cliente",
    version="1.0.0",
    description=(
        "Recibe una consulta de soporte y devuelve el contrato JSON de cuatro "
        "campos, junto con lo que costó producirlo.\n\n"
        "El esquema de `response` se genera desde `src/json_validator.py`, que "
        "es el mismo módulo que valida la salida del modelo: lo que se ve acá "
        "es la especificación ejecutable, no una copia escrita a mano."
    ),
)


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
