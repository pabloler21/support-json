"""Enforces the JSON contract on the model output.

The contract is specified in reports/contrato_json.md; this module is the single
place where it is enforced. It must stay importable without an API key so the
tests can run offline, which is why it imports nothing from openai_client.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StringConstraints,
    field_validator,
)


class Category(StrEnum):
    """What the query is about. Vocabulary from contrato_json.md, section 3."""

    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    OTHER = "other"


class Action(StrEnum):
    """A step the agent should take. Vocabulary from contrato_json.md, section 4."""

    REQUEST_MORE_INFORMATION = "request_more_information"
    VERIFY_IDENTITY = "verify_identity"
    OPEN_TICKET = "open_ticket"
    ESCALATE_TO_SUPERVISOR = "escalate_to_supervisor"
    SEND_HELP_ARTICLE = "send_help_article"
    ISSUE_REFUND_REQUEST = "issue_refund_request"


# The contract asks for a non-empty answer of at most 500 characters. Stripping
# first is what makes a whitespace-only answer fail instead of passing as a str.
AnswerText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]


class SupportResponse(BaseModel):
    """One validated answer to a support query: the four fields of the contract.

    The contract is closed. A key the prompt never asked for means the model
    drifted, so extra keys are rejected rather than silently dropped, which is
    pydantic's default.
    """

    model_config = ConfigDict(extra="forbid")

    category: Category = Field(..., description="The category of the support request.")
    answer: AnswerText = Field(..., description="The answer to the support request.")
    # StrictFloat, not float: a plain float accepts True and coerces it to 1.0,
    # and the ge/le bounds do not catch it either. StrictFloat still accepts an
    # int, which the contract allows, and rejects bool, which it does not.
    confidence: StrictFloat = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="How reliable the answer is for this case, from 0 to 1.",
    )
    actions: list[Action] = Field(
        ...,
        max_length=3,
        description="Recommended next steps, in the order the agent should run them.",
    )

    @field_validator("actions")
    @classmethod
    def _reject_duplicate_actions(cls, actions: list[Action]) -> list[Action]:
        """The contract allows up to three actions and all must be distinct."""
        if len(actions) != len(set(actions)):
            raise ValueError("actions must not contain duplicate values")
        return actions
