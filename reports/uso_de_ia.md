# Uso de herramientas de IA en el desarrollo

El enunciado pide documentar el uso de herramientas de IA **y cómo influyó en
las decisiones técnicas**. Lo segundo es lo que tiene valor: decir *"usé un
asistente para el código"* no informa nada sobre el proceso.

Este documento registra qué hizo cada parte, dónde el asistente se equivocó,
dónde acertó algo que el autor no había visto, y —lo más importante— **qué
método hizo que la colaboración produjera decisiones defendibles en vez de
código plausible.**

La herramienta fue **Claude (Anthropic), usado desde Claude Code**, a lo largo de
todo el desarrollo.

---

## 1. La división del trabajo

| Tarea | Quién |
|---|---|
| Escribir el código de los módulos | El autor, línea por línea |
| Revisar ese código y señalar errores | El asistente |
| Proponer estructura y decisiones de diseño | El asistente, con decisión final del autor |
| Diseñar el contrato JSON | El asistente, a pedido explícito |
| Ejecutar las llamadas y recolectar mediciones | Ambos |
| Redactar la bitácora, el contrato y los informes | El asistente |
| Decidir la técnica de prompting, la librería de validación y los parámetros | El autor |

El pedido inicial fue explícito: *"no quiero que vos hagas cambios, lo quiero ir
codeando yo mismo, entendiendo la lógica y la estructura"*. Esa condición
determinó el modo de trabajo: el asistente explicaba, el autor escribía, el
asistente revisaba. Los archivos que el asistente escribió completos fueron los
de documentación y algunos módulos donde el autor lo pidió tras dos intentos
propios.

---

## 2. Dónde el asistente se equivocó, y qué lo corrigió

**Esta es la sección más importante del documento.** Un asistente de IA produce
afirmaciones con el mismo tono de confianza esté en lo cierto o no, y el registro
de dónde falló es lo que muestra que el proceso no consistió en aceptarlas.

| Afirmación del asistente | Qué la desmintió |
|---|---|
| El system prompt ocupa "entre 850 y 1000 tokens" | La API devolvió **1104**. Lección adoptada: si la API devuelve el número, se usa el número |
| El completion ocupará "200 a 250 tokens" | Fueron **79** |
| Los finales de línea CRLF contaminarían el conteo de tokens | **Falso.** Python normaliza `\r\n` a `\n` al leer en modo texto |
| Acortar el `answer` bajaría la latencia | Los datos lo desmintieron: la corrida con más tokens de salida fue la más rápida |
| Hay dos regímenes de latencia claramente separados | Se cayó con n=24: **cinco de siete** llamadas "frías" caen dentro del rango de las "tibias" |
| El zero-shot rompería el formato JSON | **30 de 30 válidas.** El formato lo sostiene un parámetro de la API, no el prompt |
| La técnica few-shot cuesta "+34%" | Mal calculado. Los números reales son +39,5% de participación, +65,3% de input y **+51,3% de costo total** |

A eso se suman dos errores de diseño, no de dato:

- **Un contrato que se contradecía a sí mismo.** La banda baja de `confidence`
  incluía "está fuera de alcance", mientras la sección 6 usaba confianza alta
  para un caso fuera de alcance. Confundía *"la consulta es rara"* con *"la
  respuesta no es confiable"*.
- **Una regla con justificación débil.** La precedencia
  `billing > account > technical > other` se justificaba con "billing va primero
  porque involucra dinero". No llegó al modelo en dos intentos, y al revisarla el
  argumento no se sostenía. Se reemplazó por una regla de intención principal.

---

## 3. Dónde el asistente atrapó errores del autor

| Error | Por qué era difícil de ver |
|---|---|
| `from pydantic import json` | El import **funciona**: trae un módulo de compatibilidad que no tiene `load()`. Falla después y lejos |
| Una clase llamada `ChatCompletion` | Colisiona con `openai.types.chat.ChatCompletion`. Renombrada a `CompletionResult` |
| `try/except AttributeError` para detectar `content=None` | **`None` no es un error.** Acceder a un atributo que vale `None` no lanza nada. Se detecta con `if ... is None` |
| `response_format` pasado al constructor del dataclass en vez de a la llamada a la API | El módulo importaba sin error; fallaba recién al ejecutar |
| `convert_to_list(messages)` partiendo el prompt en N mensajes por salto de línea | Malentendido de la estructura de `messages`, que son exactamente dos |
| `encoding="utf-8"` faltante | En Windows el default es cp1252, y el bug aparece en la máquina de quien clone el repo |
| `git add .` parado dentro de `src/` | Dejó un commit cuyo mensaje no describe su contenido. Pasó dos veces |

---

## 4. El método, que es lo que hizo que sirviera

Cuatro reglas, adoptadas después de que las primeras mediciones resultaran
inutilizables:

1. **Un cambio por iteración.** Cambiar el prompt y la temperatura a la vez
   impide atribuir la diferencia a algo.
2. **La expectativa se escribe antes de correr.** Convierte *"¿anduvo?"* en un
   conteo en lugar de una opinión, y evita acomodar el criterio al resultado.
3. **Verificar la variable de control.** `tokens_prompt` tiene que cambiar el
   número previsto cuando se toca el prompt. Si no cambió, el prompt nuevo no se
   cargó y el resto de la corrida no es interpretable.
4. **Nunca concluir con n=1.**

> **La regla que las une: las afirmaciones del asistente se trataron como
> hipótesis a medir, no como hechos.** Cada una de las siete de la tabla anterior
> habría entrado al informe como verdad si no se hubiera medido. Tres de ellas
> —la latencia, los dos regímenes, el formato del zero-shot— llegaron a estar
> escritas antes de caerse.

Vale registrar también un caso donde la regla 4 funcionó **antes** de escribir la
conclusión y no después: en la iteración 8, la primera corrida de C2 devolvió
`confidence: 0.50` y el asistente señaló que, de sostenerse, debilitaría la
evidencia de calibración. Con n=4 la media resultó **0,325**, por debajo del
valor previo. La alarma no sobrevivió y la conclusión nunca se escribió.

---

## 5. Verificar en vez de recordar

Un modelo de lenguaje tiene fecha de corte y afirma con confianza cosas
desactualizadas. La práctica adoptada fue **comprobar empíricamente el
comportamiento de las librerías** en vez de aceptar la descripción del asistente.
Todo esto se verificó ejecutándolo:

| Afirmación | Cómo se comprobó | Resultado |
|---|---|---|
| Un `float` de pydantic acepta `True` | Se instanció el modelo con `True` | **Confirmado**: lo convierte en `1.0`, y agregar `ge`/`le` no lo evita. Por eso el campo usa `StrictFloat` |
| `datetime.utcnow()` está deprecada en 3.12 | Se elevó `DeprecationWarning` a error | **Confirmado**, con el mensaje del intérprete |
| `csv.writer` sin `newline=""` produce `\r\r\n` | Se escribió a disco y se leyeron los bytes | **Confirmado**, y además se descubrió que escribiendo a mano con `f.write` el bug **no** aparece |
| `omni-moderation-latest` existe | Se leyó el `Literal` de tipos del SDK instalado | **Confirmado** |
| La moderación detecta prompt injection | Se llamó al endpoint con C5 | **Refutado**: vuelve sin marcar. Confirmado después contra la documentación oficial |
| La fórmula de tokens del chat | Se comparó contra `prompt_tokens` real | Contando solo `content` erraba **−2 constante**; incluyendo los nombres de rol, **exacto en 7 de 7** |

---

## 6. Qué se puede concluir

El asistente aceleró el trabajo y produjo la mayor parte de la documentación,
pero **no fue una fuente confiable de hechos sobre el sistema**. Siete
afirmaciones suyas fueron desmentidas por mediciones, y tres de ellas ya estaban
escritas cuando se cayeron.

Lo que hizo que la colaboración produjera un proyecto defendible no fue la
calidad de las respuestas, sino **la disciplina de medición aplicada encima de
ellas**: escribir la expectativa antes, verificar la variable de control, repetir
antes de concluir, y ejecutar la librería en vez de creerle al asistente lo que
la librería hace.

Esa disciplina también dejó su propio rastro de errores registrados en
[`iteraciones.md`](iteraciones.md), que es lo que permite auditar el proceso en
lugar de tener que confiar en él.
