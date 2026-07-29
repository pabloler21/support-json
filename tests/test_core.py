"""Offline tests for the four modules that hold the project's logic.

Every test here runs with no API key and no network. That is the payoff of
keeping json_validator, metrics, prompt_builder and token_estimator free of any
import from openai_client, which raises at import time when the key is missing.
openai_client and run_query are therefore not covered here: exercising them
would require credentials, and neither holds logic of its own.

The rejected cases mirror reports/contrato_json.md, section 8.
"""

import csv
import json

import pytest

from src import metrics
from src.config import INPUT_COST_PER_1M_TOKENS, OUTPUT_COST_PER_1M_TOKENS
from src.json_validator import (
    Action,
    Category,
    ContractViolationError,
    validate_response,
)
from src.metrics import COLUMNS, estimate_cost, log_metrics
from src.prompt_builder import build_messages, load_template
from src.token_estimator import (
    TOKENS_PER_MESSAGE,
    TOKENS_PER_REPLY,
    count_message_tokens,
    count_tokens,
)

# The canonical example from contrato_json.md, section 1. Every rejected case
# below is a mutation of this one object, so a failure points at the mutation
# instead of at some unrelated difference between two hand-written payloads.
VALID = {
    "category": "billing",
    "answer": "Verificá la identidad del cliente y confirmá que ambos cargos coincidan.",
    "confidence": 0.75,
    "actions": ["verify_identity", "issue_refund_request"],
}


def mutate(**changes) -> str:
    """Serialise the canonical example with some fields replaced or added."""
    return json.dumps({**VALID, **changes})


# --------------------------------------------------------------------------
# The contract: what must be accepted
# --------------------------------------------------------------------------


def test_the_canonical_example_is_accepted():
    response = validate_response(json.dumps(VALID))

    assert response.category is Category.BILLING
    assert response.actions == [Action.VERIFY_IDENTITY, Action.ISSUE_REFUND_REQUEST]
    assert response.confidence == 0.75


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"actions": []}, id="an empty action list is allowed"),
        pytest.param({"confidence": 1}, id="an integer confidence is allowed"),
        pytest.param({"confidence": 0.0}, id="the lower bound is inclusive"),
        pytest.param({"confidence": 1.0}, id="the upper bound is inclusive"),
    ],
)
def test_accepted_variants(changes):
    validate_response(mutate(**changes))


def test_the_answer_is_stripped():
    response = validate_response(mutate(answer="  con espacios de sobra  "))

    assert response.answer == "con espacios de sobra"


# --------------------------------------------------------------------------
# The contract: what must be rejected
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(json.dumps(VALID)[:-1] + ",}", id="a trailing comma is not JSON"),
        pytest.param(
            json.dumps({k: v for k, v in VALID.items() if k != "confidence"}),
            id="a required key is missing",
        ),
        pytest.param(mutate(reasoning="..."), id="the contract is closed"),
        pytest.param(mutate(confidence=1.5), id="confidence is out of range"),
        pytest.param(mutate(confidence=True), id="bool is not an accepted type"),
        pytest.param(mutate(answer=""), id="the answer is empty"),
        pytest.param(mutate(answer="   "), id="the answer is empty once stripped"),
        pytest.param(mutate(answer="a" * 501), id="the answer is over 500 characters"),
        pytest.param(
            mutate(category="billin"), id="the category is not in the vocabulary"
        ),
        pytest.param(
            mutate(actions=["send_discount"]), id="an action is not in the vocabulary"
        ),
        pytest.param(
            mutate(actions=["open_ticket", "open_ticket"]), id="actions are duplicated"
        ),
        pytest.param(
            mutate(
                actions=[
                    "open_ticket",
                    "verify_identity",
                    "send_help_article",
                    "issue_refund_request",
                ]
            ),
            id="more than three actions",
        ),
    ],
)
def test_contract_violations_are_rejected(raw):
    with pytest.raises(ContractViolationError):
        validate_response(raw)


def test_the_original_error_is_chained():
    """`raise ... from error` is what keeps the pydantic detail reachable."""
    with pytest.raises(ContractViolationError) as caught:
        validate_response(mutate(confidence=1.5))

    assert caught.value.__cause__ is not None


# --------------------------------------------------------------------------
# Cost arithmetic
# --------------------------------------------------------------------------


def test_a_million_tokens_costs_the_listed_rate():
    cost = estimate_cost(1_000_000, 1_000_000)

    assert cost.input_usd == pytest.approx(INPUT_COST_PER_1M_TOKENS)
    assert cost.output_usd == pytest.approx(OUTPUT_COST_PER_1M_TOKENS)


def test_input_and_output_are_priced_apart():
    """Output is billed at a higher rate, so the two cannot share one number."""
    only_input = estimate_cost(1_000_000, 0)
    only_output = estimate_cost(0, 1_000_000)

    assert only_input.output_usd == 0
    assert only_output.input_usd == 0
    assert only_output.total_usd > only_input.total_usd


def test_the_total_is_the_sum_of_its_parts():
    cost = estimate_cost(1484, 95)

    assert cost.total_usd == pytest.approx(cost.input_usd + cost.output_usd)


def test_a_single_query_survives_the_stored_precision():
    """One query costs about $0.00026; two decimals would flatten it to zero."""
    cost = estimate_cost(1484, 95)

    assert float(metrics.COST_FORMAT.format(cost.total_usd)) > 0


# --------------------------------------------------------------------------
# The CSV
# --------------------------------------------------------------------------


@pytest.fixture
def csv_path(tmp_path, monkeypatch):
    """Point log_metrics at a throwaway file for the duration of one test.

    Without this the tests would append to the real metrics/metrics.csv, which
    is a deliverable: its rows are the evidence behind the report, and inventing
    some would defeat the point of recording real usage.
    """
    path = tmp_path / "metrics.csv"
    monkeypatch.setattr(metrics, "METRICS_PATH", path)
    return path


def test_the_header_is_written_once(csv_path):
    log_metrics(1484, 95, 1579, 3606)
    log_metrics(1400, 90, 1490, 2100)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    assert len(rows) == 2
    assert list(rows[0]) == list(COLUMNS)


def test_the_row_records_what_it_was_given(csv_path):
    log_metrics(1484, 95, 1579, 3606)

    row = next(csv.DictReader(csv_path.open(encoding="utf-8")))

    assert int(row["tokens_prompt"]) == 1484
    assert int(row["tokens_completion"]) == 95
    assert int(row["total_tokens"]) == 1579
    assert int(row["latency_ms"]) == 3606
    assert float(row["estimated_cost_usd"]) == pytest.approx(
        estimate_cost(1484, 95).total_usd
    )


def test_the_timestamp_is_utc(csv_path):
    log_metrics(1, 1, 2, 3)

    row = next(csv.DictReader(csv_path.open(encoding="utf-8")))

    assert row["timestamp"].endswith("+00:00")


def test_rows_are_not_separated_by_blank_lines(csv_path):
    """csv.writer emits \\r\\n itself; without newline="" it would become \\r\\r\\n."""
    log_metrics(1, 1, 2, 3)
    log_metrics(1, 1, 2, 3)

    assert b"\r\r\n" not in csv_path.read_bytes()


# --------------------------------------------------------------------------
# Prompt assembly
# --------------------------------------------------------------------------


def test_build_messages_returns_a_system_then_a_user_message():
    messages = build_messages("la consulta")

    assert [message["role"] for message in messages] == ["system", "user"]
    assert messages[1]["content"] == "la consulta"


def test_the_query_is_stripped():
    messages = build_messages("   la consulta   ")

    assert messages[1]["content"] == "la consulta"


def test_an_unknown_template_fails_loudly():
    with pytest.raises(FileNotFoundError):
        load_template("no_existe.md")


def test_the_templates_differ_only_by_the_examples_block():
    """Any instruction added to one template must be added to the other.

    If they drift, the few-shot versus zero-shot comparison measures two changes
    at once and the number reported for the technique is not attributable.
    """
    few_shot = load_template("main_prompt.md")
    zero_shot = load_template("zero_shot_prompt.md")

    assert few_shot.split("EJEMPLOS")[0].strip() == zero_shot.strip()


# --------------------------------------------------------------------------
# Token counting
# --------------------------------------------------------------------------


def test_role_names_are_counted_too():
    """Counting only "content" undercounts every message by its role name."""
    messages = [{"role": "user", "content": "hola"}]

    assert count_message_tokens(messages) == (
        TOKENS_PER_MESSAGE
        + count_tokens("user")
        + count_tokens("hola")
        + TOKENS_PER_REPLY
    )


def test_the_framing_grows_with_the_number_of_messages():
    one = count_message_tokens([{"role": "user", "content": "hola"}])
    two = count_message_tokens(
        [{"role": "user", "content": "hola"}, {"role": "user", "content": "hola"}]
    )

    assert two - one == TOKENS_PER_MESSAGE + count_tokens("user") + count_tokens("hola")


def test_spanish_costs_more_tokens_than_english():
    """The vocabulary was built mostly on English, which is why the Spanish
    prompt was accepted as a deliberate ~15% overhead."""
    assert count_tokens("aplicación") > count_tokens("app")
