# CLAUDE.md

Contexto del proyecto para retomar el trabajo en una sesión nueva. Última
actualización: 2026-07-30.

---

## Qué es este proyecto

Proyecto Integrador del Módulo 1 de AI Engineering (Soy Henry). Es un **asistente para
agentes de soporte al cliente**: entra una consulta, sale un JSON de cuatro campos que
la consola del agente usa para mostrar respuesta, confianza y acciones recomendadas.

El enunciado lo titula *"Multitasking Text Utility"*, pero no pide multi-tarea: lo
"multitasking" es que **una sola llamada resuelve tres trabajos** (clasificar, redactar,
recomendar). Está documentado así en el contrato.

### Entregables, con nombres exactos

Los nombres vienen del enunciado y **no se negocian** — la rúbrica los busca literales:

| Entregable | Ruta exacta |
|---|---|
| Script ejecutable | `src/run_query.py` |
| Plantilla de prompt | `prompts/main_prompt.md` |
| Métricas por ejecución | `metrics/metrics.csv` |
| Informe (1-2 páginas) | `reports/PI_report_en.md` **y** `reports/PI_report_es.md` |
| README | `README.md` |
| Test | `tests/test_core.py` |
| Seguridad (bonus) | `src/safety.py` |

**Columnas del CSV.** Las seis primeras son las del enunciado, en ese orden y con
esos nombres exactos; las tres últimas se agregaron:

```
timestamp, tokens_prompt, tokens_completion, total_tokens, latency_ms,
estimated_cost_usd, input_cost_usd, output_cost_usd, template
```

⚠️ La API de OpenAI devuelve `prompt_tokens` / `completion_tokens` — **orden invertido**.
El mapeo ya está hecho en `openai_client.py`, en el dataclass `CompletionResult`.

Se agregaron tres columnas al final: `input_cost_usd`, `output_cost_usd` y
`template`. El enunciado lista las 6 como *"contenido mínimo"*, así que agregar está
permitido, y un test fija que las seis originales sigan primero y en orden.

⚠️ **`template` no es cosmética.** Sin ella, las corridas de few-shot y zero-shot
quedan indistinguibles en el CSV y el experimento no se puede auditar desde el archivo
que el informe cita.

---

## Estado actual

| Módulo | Estado |
|---|---|
| `src/config.py` | ✅ Variables de entorno y precios |
| `src/prompt_builder.py` | ✅ Carga plantilla y arma `messages` |
| `src/openai_client.py` | ✅ Llamada + `usage` + latencia + JSON mode |
| `src/run_query.py` | ✅ Integrado, con flag `--template` |
| `src/json_validator.py` | ✅ Contrato con pydantic |
| `src/metrics.py` | ✅ Costo, CSV y `append_row` compartido |
| `src/safety.py` | ✅ Capas 1 y 2, log aparte |
| `src/token_estimator.py` | ✅ tiktoken, 7/7 exacto contra `usage` |
| `tests/test_core.py` | ✅ 61 tests, todos offline |
| `README.md` | ✅ |
| `reports/PI_report_en.md` | ✅ Y `PI_report_es.md` |
| `metrics/metrics.csv` | ✅ 27 filas reales, con columna `template` |
| `metrics/safety_log.csv` | ✅ Una fila por decisión, incluidas las permitidas |
| `reports/uso_de_ia.md` | ✅ |
| `docs/superpowers/specs/` | Diseño de los entregables de documentación |

**Fase: el código y la documentación están completos.** Diez iteraciones registradas,
61 tests offline en verde, y el experimento few-shot vs zero-shot corrido.

### Números de referencia

| | Valor |
|---|---|
| Modelo | `gpt-4o-mini` |
| Precios | $0,15 / 1M input, $0,60 / 1M output |
| System prompt few-shot | 1446 tokens (medido con tiktoken) |
| System prompt zero-shot | 860 tokens (medido) |
| Los 5 ejemplos cuestan | **586 tokens**, y **+51,3% de costo total** por consulta |
| Costo por consulta | ~$0,00027 few-shot · $0,00018 zero-shot · media del CSV $0,000227 |
| Latencia, **desde `metrics.csv`** | mediana **1709 ms** (n=27), p25 1595, p75 2226 |
| Latencia, fase exploratoria | mediana 2486 ms (n=24), con outliers de 10518 y 23703 ms |
| ⚠️ | **Son dos poblaciones distintas.** Los valores exploratorios se transcribieron a mano antes de que existiera `metrics.py`; solo los del CSV se pueden recalcular desde la evidencia commiteada |
| `TEMPERATURE` | 0.2 (bajada en la iter. 8; **sin efecto medido**, ver abajo) |
| `MAX_TOKENS` | 300 |

---

## Cómo ejecutar

**Siempre desde la raíz del proyecto**, y **siempre con `-m`**:

```bash
uv run python -m src.run_query "la consulta entre comillas"
```

⚠️ **Dos trampas ya sufridas:**

- `uv run src/run_query.py` → `ModuleNotFoundError: No module named 'src'`. Ejecutar un
  archivo directo pone `src/` en el `sys.path` en vez de la raíz. **Siempre `-m`.**
- Ejecutar parado dentro de `src/` → el mismo error, porque `-m` resuelve contra el
  directorio actual. **Verificar `pwd` antes.**

Tests: `uv run pytest` desde la raíz (`pythonpath = ["."]` ya está en `pyproject.toml`).

El JSON sale por **stdout** y las métricas por **stderr**, para que
`> salida.json` produzca JSON puro.

---

## Arquitectura

```
run_query.py          orquesta, cero lógica propia
   ├─ safety.py ──────────┐
   ├─ prompt_builder.py   ├──► openai_client.py ──► config.py
   ├─ json_validator.py   │      (único que toca la red)
   └─ metrics.py ─────────────► config.py (precios)

token_estimator.py ─────────► config.py
   ▲ fuera del camino de producción: experimentos y tests
```

### Invariantes que hay que preservar

- **Solo `openai_client.py` toca la red.** `safety.py` le pide a él la llamada de
  moderación en vez de crear su propio cliente.
- **Solo `metrics.py` escribe CSVs.** Expone `append_row(path, columns, row)`, y
  `safety.py` lo usa para su propio log en vez de reimplementar las trampas de
  `newline=""` y del encabezado condicional. Resolverlas dos veces es como la segunda
  copia termina sutilmente mal.
- **`config.py` no crea clientes ni ejecuta lógica**, solo lee valores. Por eso se
  puede importar desde los tests sin API key.
- **`log_metrics` recibe valores sueltos**, no el dataclass. Si importara
  `openai_client`, testear una multiplicación exigiría credenciales.
- **`json_validator.py`, `metrics.py`, `prompt_builder.py` y `token_estimator.py` se
  testean sin API key.** Esa propiedad es lo que hace barata la fase de tests.

### Decisiones tomadas

- **`json_validator.py` va con pydantic** (decisión del usuario). Declararlo
  explícitamente en `pyproject.toml`, no usarlo como dependencia transitiva de `openai`.
- **tiktoken NO alimenta el CSV.** Los tokens del CSV salen de `response.usage`, que es
  lo que se factura. tiktoken sirve para estimar prompts sin gastar llamadas y para
  tests offline. **Medido: exacto en 7 de 7** contra `usage`, usando la fórmula que
  incluye los nombres de rol. (El 0,18% que decía esta nota antes era de una medición
  que contaba solo el texto del prompt; con la petición completa el error es cero.)
- **Técnica de prompting: few-shot.** ⚠️ **La justificación cambió con la iteración
  10.** Se eligió argumentando conformidad de esquema; el experimento mostró que eso lo
  garantiza `response_format={"type": "json_object"}` a nivel de API (30 de 30 válidas
  en las dos ramas). **Lo que los ejemplos compran es la calibración de `confidence`**:
  el zero-shot devuelve 0.5 en C2, el punto medio, contra 0,20 del few-shot. Cuesta
  +51,3% por consulta. CoT y self-consistency siguen descartadas por costo y latencia.

---

## Convenciones

- **Identificadores y código en inglés; cada documento en el idioma de su lector.**
  Enums, nombres de funciones, comentarios, docstrings y mensajes de commit: inglés.
  `answer`, contrato, bitácora, prompts y README: español. **El informe va en los dos
  idiomas** (decisión del usuario): `PI_report_en.md` y `PI_report_es.md`, que deben
  mantenerse sincronizados. Todos sus números salen de `metrics.csv` y de
  `iteraciones.md`, nunca transcriptos de un informe al otro.
- **El prompt está en español** deliberadamente: el `answer` sale en español y un prompt
  en español reduce el riesgo de que se filtre inglés en la salida. Cuesta ~15% más
  tokens; es despreciable.
- Commits pequeños, en inglés, y **cada commit debe dejar el repo funcionando**.

---

## Documentos que son fuente de verdad

**No duplicar su contenido acá. Leerlos antes de tocar el prompt o el validator.**

| Archivo | Qué contiene |
|---|---|
| `reports/contrato_json.md` | El contrato JSON completo: campos, tipos, vocabularios, reglas de desambiguación, casos de prueba. **Es la fuente del prompt, del validator y de los tests.** |
| `reports/consultas_de_prueba.md` | Las 5 consultas fijas (C1-C5) con su resultado esperado escrito **antes** de correr. |
| `reports/iteraciones.md` | La bitácora. **10 iteraciones** con mediciones, hipótesis que se cayeron y decisiones. Es la fuente de la sección de prompting del informe. |
| `reports/uso_de_ia.md` | Cómo se usaron herramientas de IA y cómo influyeron en las decisiones técnicas. Incluye las 7 afirmaciones del asistente que las mediciones desmintieron. |

⚠️ **Limitación conocida y asumida:** los vocabularios están duplicados entre el prompt
(`.md`) y el contrato. Si se edita uno hay que editar el otro. Mejora futura: generar
esa sección del prompt desde constantes de Python.

⚠️ **`zero_shot_prompt.md` debe ser idéntico a `main_prompt.md` menos el bloque
`EJEMPLOS`.** Cualquier instrucción nueva va en los dos. Si solo va en uno, la
comparación few-shot vs zero-shot mide dos cosas a la vez y el número del informe es
falso. Verificar siempre después de tocar el prompt.

---

## Método de trabajo

Esto es lo que hizo que las mediciones sirvieran. Respetarlo.

1. **Un cambio por iteración.** Cambiar el prompt y la temperatura a la vez impide
   atribuir la diferencia a algo.
2. **Escribir la expectativa antes de correr.** Convierte "¿anduvo?" en un conteo en vez
   de una opinión, y evita acomodar el criterio al resultado.
3. **Verificar la variable de control.** `tokens_prompt` tiene que cambiar el número
   esperado cuando se toca el prompt. Si no cambió, el prompt nuevo no se cargó y el
   resto de la corrida no es interpretable.
4. **⚠️ Hay parámetros que ningún control derivado de la salida puede verificar.**
   `TEMPERATURE` no toca el prompt, así que `tokens_prompt` queda igual se haya aplicado
   el cambio o no. Y el negativo genuino ("los valores son idénticos a los de antes") es
   **la misma evidencia** que produce el error de operación. Para `TEMPERATURE`, `MODEL`
   y `MAX_TOKENS` el control debe ser una **lectura explícita de la configuración
   efectiva**: `uv run python -c "from src.config import TEMPERATURE; print(TEMPERATURE)"`.
   Un control que no distingue el hallazgo del error de operación no es un control.
5. **Nunca concluir con n=1.** Una medición de latencia dio 23703 ms; tres repeticiones
   dieron ~2100. De haberse reportado sin repetir, el informe habría afirmado algo falso.
   En la iteración 8, un `confidence: 0.50` en la primera corrida de C2 casi instala una
   conclusión sobre calibración que n=4 desmintió (media real 0,325).
6. **Documentar los fallos y las hipótesis que se cayeron.** El enunciado lo pide dos
   veces, y es lo que distingue una bitácora de una lista de logros.
7. **Iteración ≠ corrida.** Una iteración es un cambio y su medición; las corridas son
   muestras dentro de ella. Cuatro ejecuciones de la misma consulta son **una**
   iteración con n=4.

---

## Errores cometidos — no repetirlos

### De medición

- **Estimar en vez de medir.** Se estimó el prompt en 850-1000 tokens (real: 1104) y el
  completion en 200-250 (real: 79). **Si la API devuelve el número, usar el número.**
- **Reportar un promedio sobre poblaciones distintas.** Promediar latencias frías y
  tibias da un valor que no describe ninguna de las dos.
- **Afirmar sin datos que acortar el `answer` bajaría la latencia.** Los datos lo
  desmintieron: la corrida con más tokens de salida fue la más rápida. A esta escala el
  tiempo lo domina el costo fijo del round-trip, no los tokens en ninguna dirección.
- **Afirmar que los finales de línea CRLF contaminarían el conteo de tokens.** Falso:
  Python normaliza `\r\n` a `\n` al leer en modo texto.

### De diseño del contrato

- **Escribir un contrato que se contradice.** La banda baja de `confidence` incluía
  "está fuera de alcance", pero la sección 6 usaba confianza alta para un caso fuera de
  alcance. Confundía *"la consulta es rara"* con *"la respuesta no es confiable"*.
- **Definir una regla con justificación débil.** La precedencia
  `billing > account > technical > other` se justificaba con "billing va primero porque
  involucra dinero". No llegó al modelo en dos intentos y el argumento no se sostenía.
- **⚠️ El riesgo que esto abre:** ya se corrigieron **dos expectativas de test** después
  de ver el resultado. Es legítimo cuando la especificación estaba mal, pero **si cada
  test que falla se reinterpreta como error de especificación, los tests dejan de
  servir**. Regla: decidir con una pregunta de dominio respondida **sin mirar la salida
  del modelo**, y dejar constancia escrita de por qué se cambió.

### De código

- **`try/except` no detecta un valor.** `None` no es un error: acceder a un atributo que
  vale `None` no lanza nada. Se detecta con `if ... is None`, no con `try`.
- **Escribir `objeto.atributo` como sentencia suelta no verifica nada.** La evalúa y la
  descarta.
- **Pasar un parámetro de la API al constructor equivocado.** `response_format` terminó
  en `CompletionResult(...)` en vez de en `client.chat.completions.create(...)`. El
  módulo importaba sin error; fallaba recién al ejecutar.
- **`from pydantic import json`.** Importa un módulo de compatibilidad de pydantic que no
  tiene `load()`. El import funciona y el fallo aparece después, lejos. Además usaba una
  dependencia transitiva.
- **Nombrar una clase igual que un tipo del SDK.** `ChatCompletion` ya existe en
  `openai.types.chat`. Se renombró a `CompletionResult`.
- **Olvidar `encoding="utf-8"`.** En Windows el default es cp1252 y el bug aparece en la
  máquina de quien clone el repo, no en la propia.
- **Olvidar que `print()` redirigido usa el locale.** El JSON salía en cp1252 al hacer
  `> archivo`. Corregido con `sys.stdout.reconfigure(encoding="utf-8")` en `main()`.

### De proceso

- **`git add .` parado dentro de `src/`** solo agrega esa carpeta. Pasó dos veces, y
  dejó un commit cuyo mensaje no describe su contenido (`ff0b083`).
- **Pegar el mismo output dos veces** al transcribir resultados. Convirtió un n=4 en n=3
  sin que se notara hasta revisar que la latencia coincidía al milisegundo.
- **Correr un test con el texto de la consulta modificado.** Invalida la comparación
  contra la expectativa. Usar siempre el texto exacto de `consultas_de_prueba.md`.

---

## Historial de decisiones cerradas

### Cerradas en las iteraciones 8 y 9

- [x] **C2, fallo parcial asumido.** Iter. 9 agregó una regla de desambiguación entre
      `escalate_to_supervisor` y `request_more_information` (eje **comprensión contra
      autoridad**): pasó de **0 de 4 a 3 de 4**. No se cuenta como resuelto — dar por
      arreglado un 3/4 sería acomodar el criterio al resultado. Mejora futura candidata:
      sexto ejemplo few-shot con el par `other` + consulta vaga.
- [x] **El ciclo de prompting está cerrado.** El prompt es definitivo, así que la
      comparación few-shot vs zero-shot ya se puede correr.
- [x] Bajar `TEMPERATURE` a 0.2. Hecho en la iter. 8, **con resultado negativo**: la
      dispersión de `confidence` en C1 no se movió (los mismos 4 valores que a 0.7). Los
      ejemplos few-shot ya habían colapsado la distribución. Se conserva 0.2 porque no
      cuesta nada, pero se documenta como decisión de bajo impacto medido — y eso da un
      argumento **más fuerte** para el informe: en este sistema el prompting redujo la
      varianza más que el parámetro de sampling.

### Fases que faltan

**Ninguna. Todos los entregables están escritos.** Lo que queda son mejoras
opcionales, listadas abajo.

### Limitaciones abiertas, medidas y asumidas

Ninguna bloquea la entrega. Todas están documentadas en el README y en el informe.

- **C2, fallo parcial: 5 de 7.** El `answer` reconoce que falta información y a veces
      emite `escalate_to_supervisor` en vez de `request_more_information`. La regla de
      la iteración 9 lo llevó de 0 de 4 a 3 de 4. Candidato de mejora: un sexto ejemplo
      few-shot con el par `other` + consulta vaga.
- **Registro y destinatario en `RESTRICCIONES`.** El modelo alterna voseo y tuteo, y
      algunas respuestas están redactadas hacia el cliente final en lugar del agente,
      que es lo que el prompt establece en su primera línea.
- **Alucinación blanda — 7 apariciones.** Referencia información que no tiene
      ("departamento de recursos humanos", "las políticas de reembolso"). No inventa
      datos duros, pero presupone documentos y áreas.
- **Vocabulario duplicado** entre el prompt y `json_validator.py`. Mejora futura:
      generar esa sección del prompt desde las constantes de Python. Los `description=`
      de los campos del modelo son la materia prima para eso.

---

## Cosas que el enunciado pide y son fáciles de olvidar

- **Evidencia del proceso de iteración**, pedida dos veces: qué se probó, qué falló y por
  qué se eligió la versión final. Está en `iteraciones.md`.
- **Justificar los parámetros** (`model`, `temperature`, límites de tokens) con registro
  de por qué se eligieron esos valores. *"Los defaults rara vez son la mejor decisión."*
- **Que los cálculos sean reproducibles y auditables.** Por eso el CSV guarda `usage`
  real y no estimaciones.
- **Documentar el uso de herramientas de IA** y cómo influyó en las decisiones técnicas.
- **La defensa de seguridad tiene que resistir variaciones triviales del ataque** — el
  enunciado descarta explícitamente una sola línea de defensa.
- **README y reporte consistentes entre sí.**
