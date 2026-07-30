"""Single point of contact with the OpenAI API."""

from dataclasses import dataclass
from time import perf_counter

from openai import OpenAI, OpenAIError

from src.config import (
    MAX_TOKENS,
    MODEL,
    MODERATION_MODEL,
    OPENAI_API_KEY,
    TEMPERATURE,
)

if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is missing. Copy .env.example to .env and fill in the key."
    )

client = OpenAI(api_key=OPENAI_API_KEY)


@dataclass(frozen=True)
class CompletionResult:
    """A completed API call: the model output plus its token cost and latency.

    Field names match the columns of metrics/metrics.csv, so the mapping from
    the OpenAI field names happens once, here, at the edge of the system.
    """

    content: str
    tokens_prompt: int
    tokens_completion: int
    total_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class ModerationResult:
    """The moderation endpoint's verdict on one piece of text.

    Carries the flagged category names as well as the boolean, so the safety
    log can record why something was rejected and not merely that it was.
    """

    flagged: bool
    categories: tuple[str, ...]


def create_chat_completion(messages: list[dict[str, str]]) -> CompletionResult:
    """
    Create a chat completion using the configured model.

    Args:
        messages (list): A list of message dictionaries, where each message
                         has a role and its content.

    Returns:
        CompletionResult: The model output together with its token usage and
                          the latency of the API call in milliseconds.

    Raises:
        RuntimeError: If the API call fails (network, rate limit, auth, etc.),
                      if the response carries no choices, if the model refused
                      to answer, or if the response carries no usage data.
    """
    start = perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_TOKENS,
            response_format={"type": "json_object"},
        )
    except OpenAIError as error:
        raise RuntimeError(f"OpenAI API call failed: {error}") from error

    latency_ms = int((perf_counter() - start) * 1000)

    if not response.choices or not response.choices[0].message:
        raise RuntimeError(f"OpenAI API returned no choices: {response}")

    elif response.choices[0].message.content is None:
        raise RuntimeError(
            "OpenAI API returned a choice with no content. Refusal: "
            f"{response.choices[0].message.refusal}"
        )

    try:
        return CompletionResult(
            content=response.choices[0].message.content,
            tokens_prompt=response.usage.prompt_tokens,
            tokens_completion=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens,
            latency_ms=latency_ms,
        )
    except (AttributeError, IndexError) as error:
        raise RuntimeError(
            f"Unexpected response format from OpenAI API: {response}"
        ) from error


def moderate(text: str) -> ModerationResult:
    """Ask the moderation endpoint whether a piece of text is harmful.

    Lives here rather than in safety.py because this module is the project's
    only point of contact with the network. Two clients would mean two places
    to look when the network misbehaves, and two configurations that can drift.

    Measured limitation, and the reason safety.py needs a second layer: this
    endpoint does not detect prompt injection. The injection used as test case
    C5 comes back unflagged, with no category set.

    Moderation calls are not billed, so nothing here is recorded in
    metrics.csv.

    Args:
        text: The customer query, before it reaches the chat model.

    Returns:
        Whether the text was flagged, and the names of the categories that
        triggered it.

    Raises:
        RuntimeError: If the API call fails, or the response carries no result.
            Left to propagate rather than resolved into a decision here: if the
            network is down the chat call cannot succeed either, so there is no
            gap to fail open or closed about.
    """
    try:
        response = client.moderations.create(model=MODERATION_MODEL, input=text)
    except OpenAIError as error:
        raise RuntimeError(f"OpenAI moderation call failed: {error}") from error

    if not response.results:
        raise RuntimeError(f"OpenAI moderation returned no results: {response}")

    result = response.results[0]
    # by_alias=True yields the API's own category names and, unlike the default,
    # does not repeat a category under both its alias and its field name.
    flagged_categories = tuple(
        name
        for name, is_set in result.categories.model_dump(by_alias=True).items()
        if is_set
    )
    return ModerationResult(flagged=result.flagged, categories=flagged_categories)
