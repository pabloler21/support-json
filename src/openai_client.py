"""Single point of contact with the OpenAI API."""

from dataclasses import dataclass
from time import perf_counter

from openai import OpenAI, OpenAIError

from src.config import MAX_TOKENS, MODEL, OPENAI_API_KEY, TEMPERATURE

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
