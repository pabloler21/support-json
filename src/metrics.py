"""Records what each API call cost, one row per run.

metrics/metrics.csv is the auditable record behind every number in the report,
which is why the token counts come from the API's own usage field and never
from an estimate. This module is the only one that writes that file.

It stays importable without an API key because it takes loose integers instead
of a CompletionResult: importing that dataclass would pull in openai_client,
which raises at import time when the key is missing, and testing a
multiplication would then require credentials.
"""

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from src.config import INPUT_COST_PER_1M_TOKENS, OUTPUT_COST_PER_1M_TOKENS

# Resolved from this file's location, not from the current working directory,
# so it works no matter where the process is launched from.
METRICS_PATH = Path(__file__).resolve().parent.parent / "metrics" / "metrics.csv"

# Single source of truth for the header and for the order of every row, so the
# two can never drift apart. The first six names and their order come from the
# assignment; the last two are the breakdown this project chose to add.
COLUMNS = (
    "timestamp",
    "tokens_prompt",
    "tokens_completion",
    "total_tokens",
    "latency_ms",
    "estimated_cost_usd",
    "input_cost_usd",
    "output_cost_usd",
)

# Enough decimals to keep a single query visible. One costs about $0.00026, and
# the output column alone lands near $0.00005, which str() would write in
# scientific notation and round(x, 2) would flatten to zero.
COST_FORMAT = "{:.8f}"


class Cost(NamedTuple):
    """The price of one call, split the way the CSV reports it."""

    input_usd: float
    output_usd: float
    total_usd: float


def estimate_cost(tokens_prompt: int, tokens_completion: int) -> Cost:
    """Price one call from its token counts.

    Pure arithmetic: no I/O, and nothing imported beyond the two prices. That is
    what lets the test suite exercise it in a single line, with no API key and
    no files on disk.

    Input and output are billed at different rates, so they are computed apart
    and reported apart.

    Args:
        tokens_prompt: Tokens sent, as reported by the API.
        tokens_completion: Tokens generated, as reported by the API.

    Returns:
        The input, output and total cost in USD.
    """
    input_usd = tokens_prompt / 1_000_000 * INPUT_COST_PER_1M_TOKENS
    output_usd = tokens_completion / 1_000_000 * OUTPUT_COST_PER_1M_TOKENS
    return Cost(input_usd, output_usd, input_usd + output_usd)


def log_metrics(
    tokens_prompt: int,
    tokens_completion: int,
    total_tokens: int,
    latency_ms: int,
) -> None:
    """Append one run to metrics/metrics.csv, writing the header if it is new.

    The cost is computed here rather than received, so callers stay free of
    arithmetic. Timestamps are ISO 8601 in UTC, which keeps rows comparable
    across machines and makes each batch of runs reconstructable.

    Args:
        tokens_prompt: Tokens sent, as reported by the API.
        tokens_completion: Tokens generated, as reported by the API.
        total_tokens: The API's own total, stored rather than recomputed.
        latency_ms: Wall-clock duration of the call.
    """
    cost = estimate_cost(tokens_prompt, tokens_completion)
    row = (
        datetime.now(UTC).isoformat(),
        tokens_prompt,
        tokens_completion,
        total_tokens,
        latency_ms,
        COST_FORMAT.format(cost.total_usd),
        COST_FORMAT.format(cost.input_usd),
        COST_FORMAT.format(cost.output_usd),
    )

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Asked before opening: append mode creates the file, so checking afterwards
    # would always find it there and the header would never be written.
    is_new = not METRICS_PATH.exists()

    # newline="" is required with csv.writer on Windows. The writer emits \r\n
    # itself, and text mode would translate that \n again, producing \r\r\n and
    # a blank line between every row.
    with open(METRICS_PATH, "a", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(row)
