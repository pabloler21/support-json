"""Único punto de contacto con la API de OpenAI."""

from openai import OpenAI, OpenAIError

from src.config import MAX_TOKENS, MODEL, OPENAI_API_KEY, TEMPERATURE

if not OPENAI_API_KEY:
    raise RuntimeError(
        "Falta OPENAI_API_KEY. Copiá .env.example a .env y completá la clave."
    )

client = OpenAI(api_key=OPENAI_API_KEY)


def create_chat_completion(messages: list[dict[str, str]]) -> str:
    """
    Crea una respuesta de chat utilizando el modelo especificado.

    Args:
        messages (list): Una lista de mensajes en formato de diccionario,
                         donde cada mensaje tiene un rol y contenido.

    Returns:
        str: La respuesta generada por el modelo.

    Raises:
        RuntimeError: Si la llamada a la API falla (red, rate limit, auth, etc.).
    """
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=TEMPERATURE,
            max_completion_tokens=MAX_TOKENS,
        )
    except OpenAIError as error:
        raise RuntimeError(f"Falló la llamada a la API de OpenAI: {error}") from error

    return response.choices[0].message.content
