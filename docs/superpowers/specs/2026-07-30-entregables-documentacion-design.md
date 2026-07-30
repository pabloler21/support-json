# Diseño: entregables de documentación y experimento final

**Fecha:** 2026-07-30
**Alcance:** los últimos entregables del Proyecto Integrador. El código de
producción está completo; falta el experimento que cierra la justificación de la
técnica de prompting, y la documentación.

---

## Contexto

Seis módulos escritos y commiteados, 59 tests offline en verde, nueve
iteraciones de prompting documentadas en `reports/iteraciones.md`. Lo que queda
son cinco artefactos nuevos, un cambio chico en la CLI, y dos arreglos de
higiene en archivos que ya son entregables.

## Decisiones tomadas

| Decisión | Elección | Consecuencia |
|---|---|---|
| Idioma del informe | **Ambos**: `PI_report_en.md` e `PI_report_es.md` | Confirma que el sufijo `_en` es una convención de idioma. Introduce riesgo de desincronización, ver más abajo |
| Selección de plantilla | **Flag `--template` en `run_query.py`** | El evaluador reproduce el experimento con un comando |
| Uso de IA | **Archivo aparte**, `reports/uso_de_ia.md` | No compite por el límite de 1-2 páginas del informe |

---

## Paso 0 — Higiene, antes que nada

Dos archivos del repo que ya son entregables están rotos o de más. Se arreglan
primero, porque escribir documentación que describa un repo que no funciona es
trabajo que hay que rehacer.

### `requirements.txt` está desactualizado

Muestra `pydantic` como dependencia transitiva de `openai`, y **no incluye
`tiktoken`**. Quien clone el repo e instale desde ahí no puede importar
`src/token_estimator.py`.

```bash
uv export --no-hashes --no-emit-project -o requirements.txt
```

**Verificación:** el archivo resultante tiene que listar `tiktoken` y mostrar
`pydantic` sin el comentario `# via openai`.

### `main.py` es residuo del andamiaje

Imprime `"Hello from support-json!"`. No está en la arquitectura del plan de
desarrollo y nadie lo importa. Se borra.

---

## Paso 1 — La columna `template` en `metrics.csv`

**Problema que resuelve:** el experimento va a escribir 30 filas en
`metrics.csv`. Sin una columna que registre qué plantilla produjo cada fila, las
filas quedan indistinguibles y el experimento **no se puede auditar desde el
CSV**, que es justamente lo que el enunciado pide.

Este paso va **antes** del experimento. Descubrirlo después de gastar las
llamadas obliga a repetirlas.

### Cambios

- `metrics.py`: agregar `"template"` al final de `COLUMNS`, y un parámetro
  `template: str` a `log_metrics`.
- `run_query.py`: pasar el nombre de la plantilla efectiva.

Las seis columnas del enunciado conservan su nombre y su orden. El enunciado las
define como *contenido mínimo*, así que agregar está permitido; ya se agregaron
`input_cost_usd` y `output_cost_usd` con el mismo criterio.

### Compatibilidad

Las tres filas reales que ya existen en `metrics.csv` no tienen la columna
nueva. Se agrega el valor `main_prompt.md` a mano en esas filas: es el dato
correcto, porque son corridas previas al flag y todas usaron el default.

### Tests

- Que `COLUMNS` siga empezando con las seis del enunciado en orden.
- Que la fila registre la plantilla que se le pasó.

---

## Paso 2 — Flag `--template` en `run_query.py`

`build_messages` ya acepta `template_name`; la CLI no lo expone.

```
--template main_prompt.md      (default, comportamiento actual)
--template zero_shot_prompt.md
```

**Diseño:** argumento opcional con `default=DEFAULT_TEMPLATE` importado de
`prompt_builder`, para no repetir el literal en dos archivos.

**Manejo de error:** `load_template` ya levanta `FileNotFoundError` con la ruta
completa. `run_query` lo captura y sale con código **1**, que es el código de
fallo de configuración e infraestructura.

**Alcance:** es la única funcionalidad nueva de esta etapa. Se justifica porque
el enunciado exige evidencia de la elección de técnica de prompting y que los
cálculos sean reproducibles; un experimento que solo corre con un script
descartable no cumple lo segundo.

---

## Paso 3 — El experimento few-shot vs zero-shot

### Expectativa, escrita antes de correr

Va a `reports/iteraciones.md` como Iteración 10, **antes** de ejecutar.

| | Few-shot | Zero-shot |
|---|---|---|
| Aciertos sobre 5 | 4 (C2 falla en `actions`) | menos, sobre todo en la calibración de C2 |
| JSON válido | 100% | riesgo de prosa en lugar de JSON |
| `tokens_prompt` | baseline | **exactamente 586 menos** |

La hipótesis concreta: **los ejemplos son lo que enseñó la escala de
`confidence`**, así que el zero-shot debería degradarse primero ahí, no en
`category`.

### Protocolo

- 5 consultas × 2 plantillas × **n=3** = 30 llamadas, ~$0,007.
- Texto exacto de `reports/consultas_de_prueba.md`. Sin modificar una palabra.
- Criterio de éxito: las cinco condiciones ya definidas en ese archivo.
- **Control:** la diferencia de `tokens_prompt` entre ramas para la misma
  consulta tiene que ser exactamente 586. Si no lo es, se cargó la plantilla
  equivocada y la corrida no es interpretable.

### Qué se reporta

- Tasa de acierto por consulta y por plantilla.
- **Cuántas respuestas fueron JSON válido del contrato**, que es el modo de
  fallo esperado del zero-shot y el que más importa.
- El costo de la técnica, medido sobre C1 y con 90 tokens de salida:

  | | |
  |---|---|
  | `tokens_prompt` few-shot | 1484 |
  | `tokens_prompt` zero-shot | 898 |
  | Los ejemplos son | **39,5%** del prompt few-shot |
  | Few-shot cuesta | **+65,3%** de input |
  | Few-shot cuesta | **+46,6%** de costo total, $0,00027660 contra $0,00018870 |

  Los tres porcentajes responden preguntas distintas y es fácil confundirlos.
  El que va al informe como "lo que cuesta la técnica" es **+46,6%**, porque es
  el costo total por consulta, que es lo que se factura.

---

## Paso 4 — `README.md`

**Lector:** alguien que clona el repo. **Idioma:** español.

**Criterio rector:** el README dice *cómo se usa*; el informe dice *qué se
aprendió*. La consigna pide que sean consistentes, no que se repitan.

| Sección | Contenido |
|---|---|
| Qué es | Una llamada resuelve tres trabajos: clasificar, redactar, recomendar |
| El contrato | Los cuatro campos con un ejemplo real y los dos vocabularios |
| Instalación | `uv sync`, copiar `.env.example`, nunca commitear la clave |
| Uso | El comando con `-m`, las dos trampas ya sufridas, stdout/stderr, el flag `--template`, los tres códigos de salida |
| Qué produce | Columnas de `metrics.csv` y de `safety_log.csv` |
| Tests | `uv run pytest`, y que corren sin API key |
| Arquitectura | El grafo de dependencias y la tabla de invariantes |
| Seguridad | Las tres capas con la evidencia medida |
| Limitaciones | C2 3/4, alucinación blanda, registro y destinatario, falsos positivos heurísticos, vocabulario duplicado |
| Registro | Punteros a `iteraciones.md`, `contrato_json.md` y `uso_de_ia.md` |

---

## Paso 5 — El informe, en dos idiomas

`reports/PI_report_en.md` y `reports/PI_report_es.md`.

**Restricción que manda: 1-2 páginas**, unas 1000-1200 palabras. Sin tutorial,
sin código, solo hallazgos y decisiones con números.

| § | Palabras | Contenido |
|---|---|---|
| 1. Qué hace y arquitectura | 120 | El pipeline y la tesis del estrechamiento de tipos |
| 2. Prompting e iteración | 250 | Por qué few-shot. Progresión de C1: 0,614 → 0,750 → 0,838, `open_ticket` 0/7 → 4/4. **Y el fracaso de la iteración 7**, negativo 0/4 |
| 3. Parámetros justificados | 150 | El resultado negativo de la temperatura: los mismos cuatro valores a 0,7 y a 0,2 |
| 4. Métricas | 150 | ~$0,00026/consulta; mediana 2486 ms (n=24, p25 2281, p75 3335); por qué `usage` y no tiktoken |
| 5. Few-shot vs zero-shot | 150 | El resultado del paso 3 |
| 6. Seguridad | 150 | Tres capas, la disjunción medida, 16/16 variantes |
| 7. Limitaciones | 120 | C2, alucinación blanda, el trade-off heurístico |

Cierra con una línea que apunta a `reports/uso_de_ia.md`. Es un puntero, no una
sección: el ítem lo pide el enunciado y un evaluador que lo busque en el informe
tiene que encontrar al menos la referencia.

### ⚠️ Riesgo asumido: dos informes se desincronizan

Es el mismo problema que ya tiene el proyecto entre el prompt y el contrato, y
está documentado como limitación conocida.

**Mitigación:** los dos se escriben en la misma sesión, a partir de la misma
estructura de secciones, y **todos los números salen de `metrics.csv` y de
`iteraciones.md`**, nunca transcriptos de un informe al otro. Cada uno lleva una
nota que nombra al otro como su par.

---

## Paso 6 — `reports/uso_de_ia.md`

El enunciado pide documentar el uso de herramientas de IA **y cómo influyó en
las decisiones técnicas**. Lo segundo es lo que le da valor; *"usé un asistente
para el código"* no dice nada.

| Sección | Contenido |
|---|---|
| División del trabajo | Quién escribió qué: el código lo escribió el autor, el asistente revisó, propuso diseños, corrió mediciones y redactó documentación |
| **Dónde el asistente se equivocó** | Estimó el prompt en 850-1000 tokens contra 1104 reales; afirmó que CRLF contaminaría el conteo; afirmó que acortar el `answer` bajaría la latencia; afirmó dos regímenes de latencia que se cayeron con n=24; diseñó un contrato que se contradecía; diseñó una regla de precedencia que falló dos veces |
| Dónde el asistente atrapó errores | `from pydantic import json`; la colisión de nombre con `ChatCompletion` del SDK; el `try/except` que no detecta `None`; `response_format` en el constructor equivocado |
| El método | Un cambio por iteración, expectativa escrita antes de correr, nunca concluir con n=1, variable de control. **Las afirmaciones del asistente se trataron como hipótesis a medir, no como hechos** |
| Verificar en vez de recordar | Se comprobó empíricamente que `float` acepta `True` en pydantic, que `datetime.utcnow()` está deprecada en 3.12, que `csv.writer` produce `\r\r\n` sin `newline=""`, y que el endpoint de moderación no detecta inyección |

La sección de errores es el corazón del documento. El enunciado pide dos veces
evidencia de qué se probó y qué falló, y este archivo es donde esa evidencia se
vuelve explícita sobre el rol de la herramienta.

---

## Orden de ejecución

Cada paso deja el repo funcionando.

1. Higiene: `requirements.txt` y borrar `main.py`
2. Columna `template` en `metrics.csv` y sus tests
3. Flag `--template` en `run_query.py`
4. Escribir la expectativa de la Iteración 10
5. Correr el experimento, 30 llamadas
6. Documentar la Iteración 10 con los resultados
7. `README.md`
8. `PI_report_en.md`
9. `PI_report_es.md`
10. `reports/uso_de_ia.md`

Los pasos 2 y 3 van antes del 5 y no son opcionales: sin la columna, las 30
filas quedan sin atribución y hay que repetir las llamadas.

---

## Criterios de terminado

- [ ] `pip install -r requirements.txt` deja el proyecto ejecutable
- [ ] `uv run pytest` en verde, sin API key
- [ ] El experimento corrido, con su control de 586 tokens verificado
- [ ] `metrics.csv` commiteado con corridas reales y atribuidas
- [ ] Informe dentro de 1-2 páginas
- [ ] README e informe consistentes entre sí, sin duplicarse
- [ ] Los cinco ítems que el enunciado pide y son fáciles de olvidar, cubiertos:
      evidencia de iteración, justificación de parámetros, cálculos auditables,
      uso de IA, y defensa que resiste variaciones triviales
