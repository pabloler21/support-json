# Endpoint HTTP e interfaz web

*Diseño. 2026-07-30. Rama `feat/web-interface`, sobre el tag `entrega-m1`.*

---

## 1. Qué se agrega y qué no

Se agrega un endpoint FastAPI y una interfaz web estática, para que el proyecto
se pueda probar desde un navegador en vez de una terminal.

**No cubre ningún requisito faltante.** La fila *"Aplicación o script ejecutable"*
de la consigna es un OR entre `src/run_query.py`, `app/endpoint.py` y un notebook;
`run_query.py` ya la cumple entera, incluidas sus cuatro cláusulas de contenido
mínimo. El *"contrato estable para integraciones posteriores"* también está
cubierto: la CLI separa stdout de stderr justamente para que `> salida.json`
produzca JSON puro.

Lo que este trabajo agrega es concreto y limitado:

| Aporte | |
|---|---|
| El evaluador prueba sin abrir una terminal | ✅ |
| El contrato se navega en `/docs`, generado desde `json_validator.py` | ✅ |
| Demuestra servir un LLM detrás de un contrato HTTP | ✅ |
| Cumplimiento de la consigna | ❌ ninguno, ya estaba completo |

**Criterio de éxito:** al terminar, todo lo que hoy funciona funciona igual, y
además existe una URL local donde se pega un ticket y se ve la respuesta.

**Criterio de fracaso, que obliga a revertir:** cualquier regresión en los 61
tests offline o en la salida de `run_query.py`.

---

## 2. Alternativas descartadas

| Opción | Motivo |
|---|---|
| **Streamlit / Gradio** | Menos código —unas 15 líneas contra ~260—, pero **Streamlit no expone endpoints REST de forma nativa** (issue [#1135](https://github.com/streamlit/streamlit/issues/1135)); la recomendación de su comunidad es poner FastAPI al lado. No produce nada consumible por otro sistema, que es la premisa del proyecto. Además impone su propia UI, lo que cancela el objetivo de diseñar la interfaz |
| **Typer en vez de `argparse`** | La CLI tiene un posicional y una opción. Typer ahorraría ~10 líneas a cambio de una dependencia y de reescribir un entregable calificado |
| **`pydantic-settings` en vez de `config.py`** | Valida al instanciarse. Con `OPENAI_API_KEY` requerida, importar `config.py` sin `.env` levantaría `ValidationError` y **caerían los 61 tests offline**. Declararla opcional para evitarlo desactiva la razón de adoptarla |
| **Flask** | Funcionaría, pero sin pydantic nativo habría que escribir a mano la validación y la documentación que FastAPI deriva del contrato, que ya es pydantic |
| **React / Vue** | Exigen npm y un build en un repo que hoy se instala con `uv sync`. Rompe *"autocontenido"* por comodidad innecesaria para cuatro interacciones |
| **`http.server` de stdlib** | Sin dependencias, pero routing, parseo de body y content-types a mano: más código que FastAPI y peor |

---

## 3. Arquitectura

### El problema que se resuelve primero

`run_query.py` declara no tener lógica propia, y es cierto, pero la **secuencia de
pasos** vive dentro de `main()`, mezclada con `argparse`, `print` y `sys.exit`.
FastAPI no puede reutilizarla: `sys.exit` mataría el servidor.

La evidencia de que eso ya cuesta algo está en el script del experimento del
informe, que para correr 30 llamadas levantó un proceso por consulta con
`subprocess.run` y recuperó los tokens con un regex sobre stderr.

### La separación

**El pipeline** —qué pasos, en qué orden— se separa del **mecanismo de entrega**
—cómo entra la consulta y cómo sale la respuesta—.

```
                    ┌──────────────────┐
  CLI ──────────────►                  │
  (run_query.py)    │  src/pipeline.py │──► safety · prompt_builder
                    │  answer_query()  │    openai_client · metrics
  HTTP ─────────────►                  │    json_validator
  (app/main.py)     └──────────────────┘
```

Un solo camino, dos traductores. La CLI y la API **no pueden divergir** porque
ejecutan la misma función.

Es el mismo argumento que el proyecto ya aplicó a `append_row`: resolver dos
veces el mismo problema es como la segunda copia termina sutilmente mal. Acá lo
que se duplicaría es el **orden de los pasos**, donde viven las dos invariantes
más caras:

- `check_query` antes de `build_messages`, porque el punto de bloquear es no
  gastar la llamada.
- `log_metrics` antes de `validate_response`, porque una respuesta que rompe el
  contrato igual costó dinero.

**Ningún test verifica hoy ese orden.** Vive en `main()`, que solo se ejercita
por subprocess. Extraerlo lo vuelve testeable por primera vez.

### Archivos

```
app/                      NUEVO — la capa HTTP y nada más
   __init__.py
   main.py                rutas + montaje de estáticos
   schemas.py             modelos pydantic de request y response
   static/index.html
   static/app.js
   static/styles.css

src/
   pipeline.py            NUEVO — la orquestación compartida
   run_query.py           ADELGAZA — argparse + print + exit codes
   metrics.py             + parámetro y columna `source`
   config.py              sin cambios
   json_validator.py      sin cambios
   openai_client.py       sin cambios
   prompt_builder.py      sin cambios
   safety.py              sin cambios
   token_estimator.py     sin cambios
```

Seis de los ocho módulos existentes de `src/` quedan intactos; `run_query.py` y
`metrics.py` se tocan, y `pipeline.py` es nuevo.

---

## 4. `src/pipeline.py`

```python
@dataclass(frozen=True)
class QueryOutcome:
    response: SupportResponse          # el contrato validado, o el de bloqueo
    verdict:  SafetyVerdict
    usage:    CompletionResult | None  # None si nunca se llamó a la API
    cost:     Cost | None
    template: str

def answer_query(query: str,
                 template: str = DEFAULT_TEMPLATE,
                 source: str = "cli") -> QueryOutcome: ...
```

**`usage` y `cost` son `| None`, no ceros.** Mismo razonamiento por el que
`safety_log.csv` es un archivo aparte: una consulta bloqueada nunca se envió, así
que no tiene tokens, latencia ni costo. Un `0` sería un número falso que después
contamina cualquier promedio.

**`source` es un parámetro, no algo que el pipeline infiera.** Quien sabe desde
dónde se llamó es el llamador. Inferirlo (mirando `sys.argv`, por ejemplo)
volvería a acoplar el pipeline al transporte.

**El pipeline no atrapa excepciones.** Deja pasar `RuntimeError`,
`FileNotFoundError` y `ContractViolationError` tal como las levantan los módulos
de hoy. Cada entry point las traduce a su propio vocabulario: la CLI a códigos de
salida, la API a status HTTP.

### Import diferido, obligatorio

```python
def answer_query(...):
    from src.openai_client import create_chat_completion   # dentro de la función
```

`openai_client.py` levanta `RuntimeError` al importarse si falta la API key. Un
import a nivel de módulo haría que cualquier test que importe el pipeline falle
sin `.env`, y con él caería la propiedad *"61 tests sin API key y sin red"*, que
el README y ambos informes afirman.

Es el mismo patrón que `safety.py` ya usa para `moderate`, con el mismo motivo
documentado en su comentario.

---

## 5. `src/run_query.py` después del cambio

Queda como traductor: parsear argumentos, llamar al pipeline, imprimir, salir.

```python
def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = _parse_args()
    try:
        outcome = answer_query(args.query, args.template, source="cli")
    except (RuntimeError, FileNotFoundError) as error:
        print(f"Error: {error}", file=sys.stderr); sys.exit(1)
    except ContractViolationError as error:
        print(f"Error: {error}", file=sys.stderr); sys.exit(2)

    print(outcome.response.model_dump_json(indent=2))
    print(_usage_line(outcome), file=sys.stderr)
```

**Contrato de no regresión, verificable:** para la misma consulta y plantilla, el
comando de hoy produce el mismo stdout, el mismo formato de stderr y el mismo
código de salida que antes del cambio. Los tres códigos (0, 1, 2), el flag
`--template` y el comportamiento de bloqueo se conservan. Si no se cumple, la
refactorización está mal y se revierte.

---

## 6. El contrato HTTP

### Rutas

| Ruta | Método | Qué hace |
|---|---|---|
| `/api/query` | POST | Procesa una consulta |
| `/` | GET | Sirve `static/index.html` |
| `/docs` | GET | OpenAPI, generado por FastAPI |

### Request

```json
{ "query": "texto del ticket", "template": "main_prompt.md" }
```

`query` obligatoria, no vacía tras recortar, máximo 2000 caracteres. `template`
opcional, con `DEFAULT_TEMPLATE` como default y restringida por un `Literal` a
las plantillas existentes: una ruta arbitraria acá sería lectura de archivos
dirigida por el cliente.

### Response

```json
{
  "response": { "category": "...", "answer": "...", "confidence": 0.85, "actions": [] },
  "metrics":  { "tokens_prompt": 1104, "tokens_completion": 79, "total_tokens": 1183,
                "latency_ms": 1709, "estimated_cost_usd": 0.00021300 },
  "safety":   { "blocked": false, "layer": null, "reason": null },
  "template": "main_prompt.md"
}
```

**`response` va anidado, nunca aplanado.** Dos razones:

1. `SupportResponse` declara `extra="forbid"`. Es *el contrato* documentado en
   `contrato_json.md` y verificado regla por regla en los tests. Meterle
   `latency_ms` adentro lo convierte en otra cosa.
2. La CLI y la API devolverían formas distintas. Hoy `run_query.py > salida.json`
   produce exactamente cuatro campos; si la API produjera nueve, el proyecto
   tendría dos contratos y el informe describiría uno.

Las métricas viajan **al lado** del contrato, no adentro. El contrato es el
producto; las métricas son observabilidad sobre su producción.

En una consulta bloqueada, `metrics` es `null`.

### Status codes

| Situación | CLI | HTTP | Motivo |
|---|---|---|---|
| Respuesta válida | 0 | 200 | |
| Consulta bloqueada | 0 | **200** | Un bloqueo no es un error: devuelve los mismos cuatro campos. Se señala con `safety.blocked: true`. **No 403** — la CLI y la UI estarían en desacuerdo sobre qué es un fallo |
| Body inválido | — | 422 | Lo genera pydantic. Es culpa del cliente |
| Falló la llamada a OpenAI | 1 | 502 | Falló el servicio de arriba |
| Plantilla inexistente | 1 | 422 | Inalcanzable por el `Literal`, se cubre igual |
| El modelo violó el contrato | 2 | 500 | La llamada funcionó; falló el prompt propio |

---

## 7. Concurrencia

**Las rutas se declaran con `def`, no con `async def`.**

`create_chat_completion` es bloqueante: espera ~1700 ms. Dentro de un `async def`
congelaría el event loop y el servidor entero dejaría de responder durante ese
tiempo. Starlette corre las rutas sincrónicas en un threadpool, que es el
comportamiento correcto acá. Escribir `async` sin `await` para el I/O es peor que
no escribirlo.

Como consecuencia, dos requests simultáneos pueden llamar a `append_row` a la
vez y entrelazar líneas. Con un evaluador clickeando es casi imposible, pero un
CSV corrupto es la evidencia del proyecto: se agrega un `threading.Lock` a nivel
de módulo en `metrics.py`, alrededor de la escritura.

---

## 8. Métricas: la columna `source`

`source` se agrega **al final** de `COLUMNS`. Valores: `cli` y `api`.

Los dos tests que dependen del encabezado sobreviven sin tocarse, y conviene
saber por qué antes de escribir el cambio:

- `test_the_six_required_columns_come_first_and_in_order` compara `COLUMNS[:6]`,
  así que agregar al final no lo afecta.
- `test_the_header_is_written_once` compara el encabezado escrito contra
  `COLUMNS`, no contra una lista literal, así que se adapta solo.

⚠️ **`source` debe tener valor por defecto `"cli"` en la firma de `log_metrics`.**
Cuatro tests la invocan con cinco argumentos posicionales
(`log_metrics(1484, 95, 1579, 3606, "main_prompt.md")`). Un parámetro obligatorio
los rompería con `TypeError`, y la afirmación de que los 61 tests se conservan sin
modificación dejaría de ser cierta.

El default también es el correcto por semántica: `cli` es el caso histórico y el
que ya producía todas las filas.

### Backfill de las 27 filas existentes

Un header de diez nombres sobre filas de nueve valores se lee mal. Las filas
viejas se completan con `cli`.

Esto es editar evidencia commiteada, y la justificación tiene que quedar escrita:
**el valor no se inventa, es un hecho verificable.** Las 27 filas se produjeron
por CLI porque la API no existía cuando se escribieron. Ningún token, latencia ni
costo se modifica. Queda constancia en `iteraciones.md`, como la nota de
integridad de la latencia.

### Consecuencia sobre los informes

Cuando el evaluador use la interfaz, el archivo va a tener filas con `source=api`
y los números publicados —n=27, mediana 1709 ms— dejarán de coincidir con un
conteo ingenuo. Los informes pasan a citar **"las 27 filas con `source=cli`"**,
lo que mantiene cada número reproducible con un filtro en vez de exigir un
archivo congelado.

---

## 9. La interfaz

Tres archivos estáticos servidos por FastAPI. Sin framework y sin build: son
cuatro interacciones, y npm rompería *"autocontenido"*.

**Dos pestañas:**

- **Consola** — el ticket entra a la izquierda, el veredicto sale a la derecha.
  El eje horizontal cuenta la tesis del proyecto: entra texto libre, sale
  estructura validada.
- **Comparar** — dispara dos requests en paralelo con distinta plantilla, muestra
  los resultados lado a lado y calcula el delta de tokens y de costo. Reproduce
  en pantalla el experimento del informe. Dos llamadas reales, dos filas en el
  CSV.

**Los cuatro estados que hay que renderizar:**

| Estado | Qué se ve |
|---|---|
| Cargando | Botón deshabilitado y la latencia esperada (~1,7 s), para que la espera no parezca cuelgue |
| Respondido | Los cuatro campos, barra de confianza, acciones como chips, tira de métricas |
| **Bloqueado** | Panel propio, **no rojo de error**: capa que bloqueó, patrón detectado, y "no se hizo ninguna llamada — costo $0". Es un éxito del sistema y tiene que verse como tal |
| Error | Mensaje distinto según sea 502 (falló OpenAI) o 500 (violación de contrato) |

`app.js` solo conoce `/api/query`. **La API key nunca sale del proceso servidor.**

La dirección visual concreta —paleta, tipografías, retícula— se define con el
skill `impeccable` durante la implementación del frontend, que requiere fijar
antes tono y audiencia.

---

## 10. Seguridad

- El servidor bindea a `127.0.0.1`, nunca `0.0.0.0`.
- `safety.py` corre en el endpoint igual que en la CLI: las tres capas cubren
  ambas entradas, y los bloqueos se registran en `safety_log.csv` con el mismo
  formato.
- `template` restringida por `Literal`, para que el cliente no elija rutas.
- `query` con máximo de 2000 caracteres.
- La API key vive solo en el proceso servidor.

---

## 11. Tests

Los 61 actuales se conservan sin modificación. Se agregan tests del pipeline, que
corren **offline** gracias al import diferido y a monkeypatch de
`create_chat_completion`:

| Test | Qué fija |
|---|---|
| Una consulta bloqueada devuelve `usage is None` | Que un bloqueo no gasta la llamada. **Hoy es solo una afirmación del README** |
| El orden: seguridad antes de construir el prompt | La invariante de no gastar la llamada |
| `log_metrics` se llama aunque la validación falle | Que las filas caras no se escondan |
| `source` llega al CSV con el valor recibido | Que las corridas de CLI y API sean separables |
| `COLUMNS` mantiene las seis de la consigna primero | Test existente, debe seguir en verde |

Tests del endpoint con `TestClient` de FastAPI, con el pipeline mockeado: sin red
y sin API key.

| Test | Qué fija |
|---|---|
| 200 y forma del envelope en una respuesta válida | |
| 200 con `metrics: null` en una consulta bloqueada | Que un bloqueo no es un error HTTP |
| 422 con body vacío | |
| 502 cuando el pipeline levanta `RuntimeError` | |
| 500 cuando levanta `ContractViolationError` | |

---

## 12. Riesgos

| Riesgo | Mitigación |
|---|---|
| Se rompen los 61 tests offline | Import diferido en `pipeline.py`, patrón ya usado en `safety.py:181` |
| Regresión en `run_query.py`, que es entregable calificado | Contrato de no regresión de la sección 5, verificado antes de mergear |
| El backfill toca evidencia commiteada | El valor es un hecho verificable; ningún número se modifica; queda constancia escrita |
| La documentación se desincroniza otra vez | README e informes se actualizan en el mismo commit que el código |
| Superficie de red nueva | Bind a loopback; `safety.py` cubre el endpoint; la key no sale del servidor |
| El trabajo rompe algo y no hay vuelta atrás | Tag `entrega-m1` sobre el commit verificado, y todo el trabajo en `feat/web-interface` |

---

## 13. Documentación a actualizar

Dentro de los mismos commits que el código:

- **README** — sección de la interfaz, comando de `uvicorn`, y la invariante
  reformulada: `openai_client.py` es el único que hace llamadas **salientes**
  (FastAPI recibe entrantes, que es otra cosa).
- **Ambos informes** — la cita de `metrics.csv` pasa a `source=cli`.
- **`iteraciones.md`** — constancia del backfill.
- **`CLAUDE.md`** — arquitectura, invariantes y comando nuevo.
- **`requirements.txt`** — regenerado con `uv export --no-hashes --no-emit-project`.

---

## 14. Orden de implementación

Cada paso deja el repo funcionando, y el paso 1 es el que protege a los demás.

1. `pipeline.py` con import diferido, y `run_query.py` adelgazado. **Verificar la
   no regresión de la CLI y los 61 tests antes de seguir.**
2. Tests del pipeline.
3. Columna `source`, backfill y nota en `iteraciones.md`.
4. `app/schemas.py` y `app/main.py`. **Punto de corte válido: acá `/docs` ya es
   una interfaz utilizable.**
5. Tests del endpoint.
6. La interfaz estática, con dirección visual definida con `impeccable`.
7. Documentación.
8. Merge a `main` con los 61 tests más los nuevos en verde.
