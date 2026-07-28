"""Enforces the JSON contract on the model output.

The contract is specified in reports/contrato_json.md; this module is the single
place where it is enforced. It must stay importable without an API key so the
tests can run offline, which is why it imports nothing from openai_client.

Definitions run from the inside out: the exception first, then the vocabularies,
then the model, and the public entry point last, once everything it uses exists.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StringConstraints,
    ValidationError,
    field_validator,
)


class ContractViolationError(Exception):
    """The model returned something that does not satisfy the JSON contract.

    Deliberately distinct from the RuntimeError raised by openai_client: that
    one means the call failed, this one means the call succeeded and the answer
    is unusable. Only the second is a signal about the quality of the prompt.
    """


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


def validate_response(content: str) -> SupportResponse:
    """Parse and validate the raw text the model returned.

    Takes the string as it came back from the API, not a dict: parsing and
    schema validation are one job and pydantic reports both as the same error,
    so splitting them would spread one concern across two modules.

    Args:
        content: The raw response body, expected to be a JSON object.

    Returns:
        The validated response.

    Raises:
        ContractViolationError: If the text is not valid JSON, or is valid JSON
            that breaks the contract. Callers never need to import pydantic.
    """
    try:
        return SupportResponse.model_validate_json(content)
    except ValidationError as error:
        raise ContractViolationError(
            f"The model output does not satisfy the JSON contract: {error}"
        ) from error
