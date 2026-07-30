"""Command-line entry point: answers a support query and prints the result.

Run it from the project root:

    uv run python -m src.run_query "the support query"

The validated JSON goes to stdout and the usage summary to stderr, so the
output can be redirected to a file and stay valid JSON.

Exit codes, so a calling script can tell the failures apart:

    0   the answer satisfies the contract, or the query was safely blocked
    1   the API call failed: network, credentials, quota
    2   the call succeeded but the answer violates the contract

This module orchestrates and owns no logic of its own: it calls in order and
routes errors. Anything that decides something about the problem domain belongs
in a module, not here.
"""

import argparse
import sys

from src.json_validator import ContractViolationError, validate_response
from src.metrics import estimate_cost, log_metrics
from src.openai_client import create_chat_completion
from src.prompt_builder import DEFAULT_TEMPLATE, build_messages
from src.safety import blocked_response, check_query, log_safety_decision


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
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
    args = parser.parse_args()

    # Ahead of build_messages, because the whole point of blocking is to not
    # spend the call. A block is a normal outcome, not a failure: it returns the
    # same four fields as any answer and exits 0. Blocks are counted in
    # safety_log.csv, which is why they need no exit code of their own.
    try:
        verdict = check_query(args.query)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    log_safety_decision(verdict, args.query)

    if verdict.blocked:
        print(blocked_response().model_dump_json(indent=2))
        print(
            f"blocked by {verdict.layer}: {verdict.reason} | no API call was made",
            file=sys.stderr,
        )
        return

    try:
        messages = build_messages(args.query, args.template)
    except FileNotFoundError as error:
        # A misspelled template name is a configuration problem, which is what
        # exit code 1 already means.
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    try:
        result = create_chat_completion(messages)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Recorded before validating, on purpose. A call that breaks the contract
    # still cost money and still took time, and how often that happens is a
    # measure of the prompt. Logging only the successes would hide exactly the
    # rows worth counting.
    log_metrics(
        result.tokens_prompt,
        result.tokens_completion,
        result.total_tokens,
        result.latency_ms,
        args.template,
    )

    try:
        response = validate_response(result.content)
    except ContractViolationError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(2)

    # The validated object, never result.content: publishing the raw string
    # would hand the consumer text nobody checked, which would make validating
    # it pointless. model_dump_json writes accents as UTF-8 rather than
    # escaping them, which json.dumps would do unless told otherwise.
    print(response.model_dump_json(indent=2))

    cost = estimate_cost(result.tokens_prompt, result.tokens_completion)
    print(
        f"tokens: {result.tokens_prompt} prompt + {result.tokens_completion} completion "
        f"= {result.total_tokens} total | latency: {result.latency_ms} ms "
        f"| cost: ${cost.total_usd:.8f}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
