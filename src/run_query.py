"""Command-line entry point: answers a support query and prints the result.

Run it from the project root:

    uv run python -m src.run_query "the support query"

The JSON answer goes to stdout and the usage metrics to stderr, so the output
can be redirected to a file and stay valid JSON.
"""

import argparse
import sys

from src.prompt_builder import build_messages
from src.openai_client import create_chat_completion


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Answer a customer support query and return it as JSON.",
        epilog="The JSON goes to stdout; token usage and latency go to stderr.",
    )
    parser.add_argument("query", help="The support query to answer.")
    args = parser.parse_args()

    messages = build_messages(args.query)
    try:
        result = create_chat_completion(messages)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(result.content)
    print(
        f"tokens: {result.tokens_prompt} prompt + {result.tokens_completion} completion "
        f"= {result.total_tokens} total | latency: {result.latency_ms} ms",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
