"""Builds the message list sent to the OpenAI Chat Completions API."""

from pathlib import Path

# Resolved from this file's location, not from the current working directory,
# so it works no matter where the process is launched from.
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DEFAULT_TEMPLATE = "main_prompt.md"


def load_template(name: str = DEFAULT_TEMPLATE) -> str:
    """
    Read a prompt template from the prompts/ directory.

    The file is read on every call so that edits to the template take effect
    without restarting the process.

    Args:
        name (str): File name of the template, e.g. "main_prompt.md".

    Returns:
        str: The full content of the template.

    Raises:
        FileNotFoundError: If the template does not exist. The message includes
                           the absolute path that was attempted.
    """
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Prompt template not found: {path}") from error


def build_messages(
    question: str, template_name: str = DEFAULT_TEMPLATE
) -> list[dict[str, str]]:
    """
    Build the two-message list expected by the Chat Completions API.

    The template goes into the system message and the user question into its
    own user message. Keeping them apart is what lets the model treat the
    query as data instead of as instructions.

    Args:
        question (str): The support query to be answered.
        template_name (str): Which template to load from prompts/.

    Returns:
        list: Exactly two messages, system first and user second.
    """
    return [
        {"role": "system", "content": load_template(template_name)},
        {"role": "user", "content": question.strip()},
    ]
