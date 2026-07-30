# Asistente de soporte al cliente

Proyecto Integrador del Módulo 1 de AI Engineering (Soy Henry).

Entra una consulta de soporte en texto libre, sale un JSON de cuatro campos que
la consola de un agente usa para mostrar la respuesta sugerida, su confianza y
las acciones recomendadas.

**Una sola llamada al modelo resuelve tres trabajos** —clasificar, redactar y
recomendar— y eso es lo que sostiene el nombre *Multitasking Text Utility* del
enunciado: no es multi-tarea concurrente, es una tarea que devuelve tres cosas.

---

## El contrato de salida

```json
{
  "category": "billing",
  "answer": "Confirmá primero la identidad del cliente y revisá en el panel de facturación qué plan quedó registrado. Si el cargo no coincide, corresponde iniciar la devolución de la diferencia.",
  "confidence": 0.85,
  "actions": ["verify_identity", "issue_refund_request"]
}
```

Los cuatro campos son obligatorios y el objeto es **cerrado**: una clave de más
significa que el modelo se desvió del prompt, y se rechaza en vez de ignorarse.

| Campo | Tipo | Reglas |
|---|---|---|
| `category` | `str` | Del vocabulario de abajo |
| `answer` | `str` | No vacío tras recortar, máximo 500 caracteres, texto plano, en el idioma de la consulta |
| `confidence` | `float` | Entre 0.0 y 1.0. **Nunca `bool`** |
| `actions` | `list[str]` | Entre 0 y 3, sin repetir, del vocabulario de abajo |

**`category`:** `billing` · `technical` · `account` · `other`

**`actions`:** `request_more_information` · `verify_identity` · `open_ticket` ·
`escalate_to_supervisor` · `send_help_article` · `issue_refund_request`

`confidence` califica **cuán confiable es el contenido del `answer`**, no cuán
rara fue la consulta ni qué tan segura está la clasificación.

La especificación completa —con las reglas de desambiguación, la semántica de
cada banda de confianza y los casos de prueba— está en
[`reports/contrato_json.md`](reports/contrato_json.md).

---

## Instalación

Requiere **Python 3.12+** y una clave de la API de OpenAI.

```bash
git clone <url-del-repo>
cd support_json
uv sync
```

Sin `uv`:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Después, la clave:

```bash
cp .env.example .env
```

y completá `OPENAI_API_KEY` en `.env`.

> ⚠️ **`.env` está en `.gitignore` y no debe commitearse nunca.** `.env.example`
> es la plantilla y no lleva credenciales.

---

## Uso

**Siempre desde la raíz del proyecto y siempre con `-m`:**

```bash
uv run python -m src.run_query "Un cliente reporta que la aplicación se cierra sola al abrir reportes."
```

### Dos trampas de ejecución

- `uv run src/run_query.py` falla con `ModuleNotFoundError: No module named 'src'`.
  Ejecutar el archivo directo pone `src/` en el `sys.path` en lugar de la raíz.
- Ejecutar parado **dentro** de `src/` da el mismo error, porque `-m` resuelve
  contra el directorio actual. Verificá dónde estás parado antes.

### Salida

**El JSON va a stdout y las métricas a stderr**, así que redirigir produce JSON
puro y parseable:

```bash
uv run python -m src.run_query "la consulta" > salida.json
```

### Elegir la plantilla de prompt

```bash
uv run python -m src.run_query --template zero_shot_prompt.md "la consulta"
```

Existe para que la comparación few-shot contra zero-shot del informe se pueda
reproducir. El default es `main_prompt.md`.

### La interfaz web

Además de la CLI, el proyecto se puede usar desde el navegador:

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

| URL | Qué es |
|---|---|
| <http://127.0.0.1:8000/> | La consola: se pega un ticket y se ve el veredicto con sus métricas |
| <http://127.0.0.1:8000/docs> | El contrato, navegable y ejecutable, **generado desde `json_validator.py`** |

La consola tiene dos pestañas. La segunda corre la misma consulta contra las dos
plantillas en paralelo y muestra el delta de tokens y de costo, así la
comparación few-shot contra zero-shot del informe se reproduce con un click.

> `/docs` no es documentación escrita a mano: FastAPI la deriva del mismo modelo
> pydantic que valida la salida del modelo. Los vocabularios, los rangos de
> `confidence` y el máximo de tres acciones aparecen ahí porque están en el
> código que los hace cumplir.

**La clave de la API nunca sale del proceso servidor.** El navegador solo conoce
`/api/query`. El servidor bindea a `127.0.0.1`, no a `0.0.0.0`.

Las dos entradas comparten `src/pipeline.py`, así que no pueden divergir: una
consulta bloqueada devuelve los mismos cuatro campos y **HTTP 200**, igual que la
CLI sale con código 0 en ese caso.

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | La respuesta cumple el contrato, **o** la consulta fue bloqueada por seguridad |
| `1` | Falló la llamada a la API: red, credenciales, cuota, o plantilla inexistente |
| `2` | La llamada funcionó pero la respuesta viola el contrato |

Un bloqueo de seguridad **no es un fallo**: el sistema devuelve los mismos cuatro
campos y sale con 0. Los bloqueos se cuentan en el log de seguridad.

---

## Qué produce

### `metrics/metrics.csv`

Una fila por llamada a la API. Las seis primeras columnas y su orden son las que
pide el enunciado; las tres últimas se agregaron.

```
timestamp, tokens_prompt, tokens_completion, total_tokens, latency_ms,
estimated_cost_usd, input_cost_usd, output_cost_usd, template, source
```

`source` vale `cli` o `api` según de qué entrada vino la consulta. Sin esa
columna, las filas de las mediciones del informe y las que genera cualquiera
probando la interfaz quedan indistinguibles, y los números publicados dejan de
poder recalcularse. El informe cita **las filas con `source=cli`**.

Los conteos de tokens salen de `response.usage`, que es lo que factura OpenAI,
**nunca de una estimación**. Es lo que hace que los costos sean auditables.

### `metrics/safety_log.csv`

Una fila por decisión de seguridad, **incluidas las consultas permitidas**: sin
ellas no hay denominador, y *"dos bloqueadas"* es una anécdota donde *"dos
bloqueadas de cuarenta y siete"* es una medición.

```
timestamp, blocked, layer, reason, query_preview
```

Solo se guardan los primeros 80 caracteres de la consulta. Un log de seguridad
es donde terminan acumulándose los datos personales de un cliente, y la primera
línea alcanza para auditar la decisión.

Va en un archivo aparte y no en `metrics.csv` por un motivo concreto: una
consulta bloqueada **nunca se envió**, así que no tiene tokens, ni latencia, ni
costo. Ponerla ahí obligaría a llenar esas columnas con ceros, y el promedio de
latencia incluiría filas que jamás hicieron una llamada.

---

## Tests

```bash
uv run pytest
```

**88 tests, y todos corren sin API key y sin red.** Esa propiedad no es
casualidad: ningún módulo con lógica importa `openai_client` a nivel de módulo, y
ese archivo exige la clave al importarse. Es lo que hace barata toda la fase de
pruebas.

| Archivo | Qué cubre |
|---|---|
| `tests/test_core.py` | 61 · los cuatro módulos con lógica: contrato, métricas, prompts, tokens |
| `tests/test_pipeline.py` | 12 · **el orden de los pasos**, que hasta ahora vivía dentro de `main()` y no lo verificaba nadie |
| `tests/test_api.py` | 15 · la traducción de excepciones a códigos HTTP, con el pipeline sustituido |

Los casos de rechazo del contrato son los de la sección 8 de
[`contrato_json.md`](reports/contrato_json.md), uno por regla, así que la salida
de pytest se lee como la especificación.

---

## Arquitectura

```
run_query.py  ─┐                CLI:  argumentos, stdout, códigos de salida
app/main.py   ─┤                HTTP: cuerpo JSON, códigos de estado
               │
               └──> pipeline.py     el orden de los pasos, compartido
                      ├── safety.py         capas 1 y 2, antes de gastar la llamada
                      ├── prompt_builder.py lee prompts/*.md
                      ├── openai_client.py  ÚNICO que sale a la red ──> config.py
                      ├── json_validator.py el contrato, con pydantic
                      └── metrics.py        costo y CSV             ──> config.py

token_estimator.py              fuera del camino de producción: tiktoken,
                                para medir prompts sin gastar llamadas
```

**Las dos entradas son traductores y nada más.** Reciben una consulta en el
vocabulario de su transporte, llaman a `answer_query()` y traducen de vuelta:
`RuntimeError` es exit 1 para la CLI y HTTP 502 para la API; una violación del
contrato es exit 2 y HTTP 500. El orden de los pasos existe una sola vez, así
que las dos entradas no pueden contradecirse.

Cada archivo es una frontera que recibe algo menos confiable y devuelve algo más
confiable. Después de `validate_response`, `response.category` **no puede** valer
un string arbitrario: no es improbable, es imposible.

### Invariantes

| Regla | Qué se rompe si no se cumple |
|---|---|
| Solo `openai_client.py` hace llamadas **salientes** | Dos clientes, dos lugares donde mirar cuando la red falla. FastAPI recibe conexiones entrantes, que es otra cosa |
| Nadie importa `openai_client` a nivel de módulo | Caen los 88 tests offline. `safety.py` y `pipeline.py` lo importan **dentro de la función**, y hay un test que lo verifica |
| Solo `metrics.py` escribe CSVs | Filas con formatos distintos y un encabezado que deja de describir el contenido |
| `config.py` no crea clientes ni ejecuta lógica | Deja de importarse sin API key, y con él caen los tests |
| `log_metrics` recibe valores sueltos, no el dataclass | Testear una multiplicación exigiría credenciales |
| El orden de los pasos vive solo en `pipeline.py` | Dos copias de la secuencia, y la segunda termina sutilmente mal |
| Las entradas no tienen lógica propia | La lógica queda donde no se puede testear sin red |

---

## Seguridad

Tres capas, sobre amenazas **disjuntas**. El enunciado descarta explícitamente
una sola línea de defensa.

| Capa | Dónde | Qué ataja |
|---|---|---|
| 1 | Heurísticas locales en `safety.py` | Prompt injection |
| 2 | Endpoint de moderación de OpenAI | Contenido dañino |
| 3 | El bloque `RESTRICCIONES` del prompt | La red de contención de lo que las dos anteriores no vean |

**Las capas 1 y 2 no son redundantes, y está medido:** la inyección que el
proyecto usa como caso C5 vuelve del endpoint de moderación **sin marcar**,
porque su contenido no es dañino — solo intenta cambiar lo que el programa hace.
A la inversa, un mensaje de acoso no contiene ningún patrón de inyección.

La capa 1 **normaliza antes de comparar** —minúsculas, descomposición Unicode
para quitar tildes, y colapso de espacios—, que es lo que la hace resistente a
variaciones triviales. Medido: bloquea **16 de 16** variantes del ataque
(mayúsculas, sin tildes, con tildes descompuestas, espaciado, inglés) y **0 de 6**
consultas legítimas.

---

## Limitaciones conocidas

Están medidas y documentadas, no escondidas.

- **C2 falla parcialmente.** En la consulta ambigua *"necesito ayuda con lo de
  siempre"*, el modelo reconoce en el `answer` que falta información pero a veces
  emite `escalate_to_supervisor` en lugar de `request_more_information`.
  Acumulado sobre las mediciones: **5 de 7 correctas**.
- **Alucinación blanda.** El modelo referencia información que no tiene:
  *"departamento de recursos humanos"*, *"las políticas de reembolso"*. No inventa
  datos duros —montos, plazos, saldos— pero presupone áreas y documentos.
  Siete apariciones registradas.
- **Registro y destinatario inconsistentes.** El prompt establece que la salida la
  lee el agente, no el cliente final, y aun así algunas respuestas están
  redactadas hacia el cliente. También alterna voseo y tuteo.
- **Las heurísticas tienen falsos positivos por diseño.** Una capa heurística
  cambia cobertura por precisión y no puede minimizar las dos. Una consulta
  legítima que diga *"actuá como si el cliente ya hubiera verificado su
  identidad"* puede bloquearse. La capa 3 es la contención.
- **El vocabulario está duplicado.** Vive en el prompt (`.md`) y en las
  constantes de `json_validator.py`, porque el prompt es texto y no código. Si
  uno se edita y el otro no, el modelo devolvería valores que el validador
  rechaza. Mejora futura: generar esa sección del prompt desde las constantes.

---

## Dónde está el registro de las decisiones

Este README explica **cómo se usa**. Lo que se probó, qué falló y por qué se
eligió cada versión está en otro lado, sin duplicarse:

| Documento | Contenido |
|---|---|
| [`reports/PI_report_es.md`](reports/PI_report_es.md) | El informe. También en [inglés](reports/PI_report_en.md) |
| [`reports/iteraciones.md`](reports/iteraciones.md) | La bitácora: **10 iteraciones** con mediciones, hipótesis que se cayeron y decisiones |
| [`reports/contrato_json.md`](reports/contrato_json.md) | El contrato completo. Fuente del prompt, del validador y de los tests |
| [`reports/consultas_de_prueba.md`](reports/consultas_de_prueba.md) | Las 5 consultas fijas con su resultado esperado escrito **antes** de correr |
| [`reports/uso_de_ia.md`](reports/uso_de_ia.md) | Cómo se usaron herramientas de IA y cómo influyeron en las decisiones técnicas |
