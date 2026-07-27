from config import client, MODEL, TEMPERATURE, MAX_TOKENS

def create_chat_completion(messages) -> str:
    """
    Crea una respuesta de chat utilizando el modelo especificado.

    Args:
        messages (list): Una lista de mensajes en formato de diccionario, 
                         donde cada mensaje tiene un rol y contenido.

    Returns:
        str: La respuesta generada por el modelo.
    """
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS
    )
    return response.choices[0].message.content
