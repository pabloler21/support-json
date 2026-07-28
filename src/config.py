"""Project configuration: loads environment variables and exposes constants.

This module does NOT create clients or run any logic, it only reads values.
That keeps it importable from anywhere (tests included) without an API key.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # Load environment variables from the .env file

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL = os.getenv("MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "100"))

# Prices in USD per 1M tokens (gpt-4o-mini).
# Input and output are billed at different rates, so they are kept apart:
# metrics.py needs both to compute estimated_cost_usd.
INPUT_COST_PER_1M_TOKENS = float(os.getenv("INPUT_COST_PER_1M_TOKENS", "0.15"))
OUTPUT_COST_PER_1M_TOKENS = float(os.getenv("OUTPUT_COST_PER_1M_TOKENS", "0.60"))
