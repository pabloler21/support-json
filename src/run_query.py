"""Command-line entry point: answers a support query and prints the result.

Run it from the project root:

    uv run python -m src.run_query "the support query"

The validated JSON goes to stdout and the usage summary to stderr, so the
output can be redirected to a file and stay valid JSON.

Exit codes, so a calling script can tell the failures apart:

    0   the answer satisfies the contract, or the query was safely blocked
    1   the API call failed: network, credentials, quota, or a missing template
    2   the call succeeded but the answer violates the contract

The steps themselves live in pipeline.py, shared with the HTTP entry point in
app/main.py. What stays here is the translation into the vocabulary of a
terminal: arguments in, text out, exit codes. Anything that decides something
about the problem domain belongs in a module, not here.
"""

import argparse
import sys

from src.json_validator import ContractViolationError
from src.pipeline import QueryOutcome, answer_query
from src.prompt_builder import DEFAULT_TEMPLATE


def _parse_args() -> argparse.Namespace:
    """Read the command line."""
    parser = argparse.ArgumentParser(
        description="Answer a customer support query and return it as JSON.",
        epilog="The JSON goes to stdout; token usage, latency and cost go to stderr.",
    )
    parser.add_argument("query", help="The support query to answer.")
    # The default is imported rather than repeated, so the two files cannot
    # disagree about which template is the standard one.
    parser.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        help=(
            "Prompt template to use, from prompts/. Defaults to "
            f"{DEFAULT_TEMPLATE}. Exists so the few-shot versus zero-shot "
            "comparison in the report can be reproduced."
        ),
    )
    return parser.parse_args()


def _usage_line(outcome: QueryOutcome) -> str:
    """Summarise what the query cost, for stderr.

    A blocked query has no usage to report: it was never sent. Saying so is the
    honest line, and it keeps the CLI consistent with metrics.csv, which has no
    row for it either.
    """
    if outcome.usage is None:
        return (
            f"blocked by {outcome.verdict.layer}: {outcome.verdict.reason} "
            "| no API call was made"
        )

    return (
        f"tokens: {outcome.usage.tokens_prompt} prompt "
        f"+ {outcome.usage.tokens_completion} completion "
        f"= {outcome.usage.total_tokens} total "
        f"| latency: {outcome.usage.latency_ms} ms "
        f"| cost: ${outcome.cost.total_usd:.8f}"
    )


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = _parse_args()

    try:
        outcome = answer_query(args.query, args.template, source="cli")
    except (RuntimeError, FileNotFoundError) as error:
        # A failed call and a misspelled template are both configuration
        # problems, which is what exit code 1 already means.
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
    except ContractViolationError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)

    # The validated object, never the raw string: publishing the string would
    # hand the consumer text nobody checked, which would make validating it
    # pointless. model_dump_json writes accents as UTF-8 rather than escaping
    # them, which json.dumps would do unless told otherwise.
    print(outcome.response.model_dump_json(indent=2))
    print(_usage_line(outcome), file=sys.stderr)


if __name__ == "__main__":
    main()
