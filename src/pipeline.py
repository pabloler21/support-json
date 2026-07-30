"""The steps one support query goes through, in order, with no entry point.

This module holds the sequence and nothing else: no argument parsing, no
printing, no exit codes and no HTTP. That separation is what lets the CLI and
the API share one code path instead of keeping two copies of the order in step.
Two copies of a rule is how the second one ends up subtly wrong, which is the
same reason safety.py reuses append_row rather than writing its own CSV.

The order carries two decisions that cost real money to get wrong:

    check_query before build_messages   blocking is pointless if the call was
                                        already paid for
    log_metrics before validate_response an answer that breaks the contract
                                        still cost money, and how often that
                                        happens measures the prompt

Nothing here catches exceptions. RuntimeError, FileNotFoundError and
ContractViolationError travel up untouched, and each entry point translates
them into its own vocabulary: exit codes for the CLI, status codes for the API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.json_validator import SupportResponse, validate_response
from src.metrics import Cost, estimate_cost, log_metrics
from src.prompt_builder import DEFAULT_TEMPLATE, build_messages
from src.safety import (
    SafetyVerdict,
    blocked_response,
    check_query,
    log_safety_decision,
)

if TYPE_CHECKING:
    # Only for the annotation below. openai_client raises at import time without
    # an API key, and `from __future__ import annotations` keeps every
    # annotation a string, so this import never runs. Importing it for real
    # would cost the project its offline test suite.
    from src.openai_client import CompletionResult


@dataclass(frozen=True)
class QueryOutcome:
    """Everything one query produced: the answer, what it cost, and why.

    usage and cost are None rather than zero when the query was blocked. The
    query was never sent, so it has no tokens, no latency and no cost, and a
    zero would be a fabricated number that poisons any average computed later.
    It is the same reason blocked queries live in safety_log.csv instead of
    metrics.csv.
    """

    response: SupportResponse
    verdict: SafetyVerdict
    usage: CompletionResult | None
    cost: Cost | None
    template: str


def answer_query(
    query: str,
    template: str = DEFAULT_TEMPLATE,
    source: str = "cli",
) -> QueryOutcome:
    """Answer one support query, recording the safety decision and the cost.

    Args:
        query: The support query, as the user wrote it.
        template: Which prompt file to use, from prompts/. Exists so the
            few-shot versus zero-shot comparison in the report stays
            reproducible from either entry point.
        source: Which entry point is calling, "cli" or "api". Passed in rather
            than inferred: the caller is the one who knows, and working it out
            from sys.argv would couple this module back to the transport it was
            extracted from.

    Returns:
        The validated response together with its usage, cost and verdict.

    Raises:
        RuntimeError: The moderation or chat call failed.
        FileNotFoundError: The template does not exist.
        ContractViolationError: The model answered, but not to the contract.
    """
    # Ahead of build_messages, because the whole point of blocking is to not
    # spend the call.
    verdict = check_query(query)
    log_safety_decision(verdict, query)

    if verdict.blocked:
        # Returns the same four fields as any other answer: a block is a normal
        # outcome, not an error, and downstream consumers expect that shape.
        return QueryOutcome(
            response=blocked_response(),
            verdict=verdict,
            usage=None,
            cost=None,
            template=template,
        )

    messages = build_messages(query, template)

    # Imported here, after the blocked branch has already returned, for the
    # reason given at the top of the module and in safety.py: openai_client
    # raises at import time when the key is missing. Deferring it this far means
    # a heuristics block never touches it at all.
    from src.openai_client import create_chat_completion

    usage = create_chat_completion(messages)

    # Recorded before validating, on purpose. A call that breaks the contract
    # still cost money and still took time. Logging only the successes would
    # hide exactly the rows worth counting.
    log_metrics(
        usage.tokens_prompt,
        usage.tokens_completion,
        usage.total_tokens,
        usage.latency_ms,
        template,
        source,
    )

    response = validate_response(usage.content)

    return QueryOutcome(
        response=response,
        verdict=verdict,
        usage=usage,
        cost=estimate_cost(usage.tokens_prompt, usage.tokens_completion),
        template=template,
    )
