"""Counts tokens locally, without spending an API call.

Useful for measuring a prompt after editing it, for comparing the few-shot and
zero-shot templates, and for offline tests that assert the prompt did not grow
unexpectedly. None of that needs the network or a key.

This module never feeds metrics/metrics.csv. Those numbers come from the usage
field the API returns, because that is what gets billed: if the server-side
message framing ever changes, the arithmetic here would drift out of sync
silently, and the report asks for auditable costs rather than reconstructed
ones.
"""

import tiktoken

from src.config import MODEL

# Loaded once per process: the vocabulary is 200k entries and is fetched from
# disk, or downloaded on first use. Resolving it from MODEL rather than naming
# an encoding means switching models moves the encoding along with it.
try:
    _ENCODING = tiktoken.encoding_for_model(MODEL)
except KeyError:
    # encoding_for_model only knows model names, so the fallback has to go
    # through get_encoding. o200k_base is what the gpt-4o family uses, and it
    # is what a model too new for this tiktoken release would most likely want.
    _ENCODING = tiktoken.get_encoding("o200k_base")

# A chat request is not the concatenation of its messages: each one is wrapped
# in <|im_start|>{role}\n{content}<|im_end|>\n, and the request ends with
# <|im_start|>assistant to prime the answer. Both constants were verified
# against the API's own usage field on four real calls, with zero difference.
TOKENS_PER_MESSAGE = 3
TOKENS_PER_REPLY = 3


def count_tokens(text: str) -> int:
    """Count the tokens in a plain string.

    Args:
        text: Any text, such as the contents of a prompt template.

    Returns:
        How many tokens the model would see.
    """
    return len(_ENCODING.encode(text))


def count_message_tokens(messages: list[dict[str, str]]) -> int:
    """Count the tokens a chat request would bill for.

    Mirrors how the API frames a conversation, so the result matches the
    prompt_tokens it reports rather than undercounting it.

    Args:
        messages: The list built by prompt_builder.build_messages.

    Returns:
        The estimated value of prompt_tokens for that request.
    """
    total = 0
    for message in messages:
        total += TOKENS_PER_MESSAGE
        # Every value, not just the content: the role name is billed too, and
        # each one costs a token. Counting only "content" undercounts a
        # two-message request by exactly two tokens.
        for value in message.values():
            total += count_tokens(value)
    return total + TOKENS_PER_REPLY
