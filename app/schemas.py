"""The shapes the HTTP layer accepts and returns.

These models exist only at the edge. The contract itself lives in
json_validator.SupportResponse and is embedded here untouched, which is the
point: the API must publish the same four fields the CLI prints, not a variant
of them.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from src.json_validator import SupportResponse
from src.prompt_builder import DEFAULT_TEMPLATE

# Trimmed and bounded. The upper limit is a support ticket's worth of text: past
# that the input is not a query, and an unbounded body is free tokens for
# anyone who finds the port.
QueryText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]

# Spelled out rather than read from the prompts directory, because this is a
# security boundary before it is a convenience: an arbitrary string here would
# be client-directed file reading. FastAPI also renders it as a dropdown in the
# generated docs, which the dynamic version could not do.
TemplateName = Literal["main_prompt.md", "zero_shot_prompt.md"]


class QueryRequest(BaseModel):
    """One support query, as the console sends it."""

    query: QueryText = Field(
        ...,
        description="The customer support query to answer.",
        examples=["Un cliente reporta que la aplicación se cierra al abrir reportes."],
    )
    template: TemplateName = Field(
        default=DEFAULT_TEMPLATE,
        description=(
            "Prompt template to use. Exists so the few-shot versus zero-shot "
            "comparison in the report can be reproduced from the browser."
        ),
    )


class QueryMetrics(BaseModel):
    """What the call cost, as the API itself reported it.

    Token counts come from response.usage, never from an estimate, which is
    what makes the cost auditable.
    """

    tokens_prompt: int
    tokens_completion: int
    total_tokens: int
    latency_ms: int
    estimated_cost_usd: float


class SafetyDecision(BaseModel):
    """What the safety layers decided, and on what grounds.

    layer and reason are null when nothing blocked: an empty string would read
    as a layer named "".
    """

    blocked: bool
    layer: str | None = None
    reason: str | None = None


class QueryResponse(BaseModel):
    """The envelope: the contract, plus what it cost to produce it.

    response is nested rather than flattened on purpose. SupportResponse
    declares extra="forbid" and is the contract the report and the tests
    describe; folding latency_ms into it would make it a different object, and
    the API would then publish a shape the CLI does not.

    metrics is null for a blocked query. It was never sent, so it has no
    tokens, no latency and no cost, and a zero would be a fabricated number.
    """

    response: SupportResponse
    metrics: QueryMetrics | None = None
    safety: SafetyDecision
    template: str
