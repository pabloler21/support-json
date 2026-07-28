# Registro de iteraciones

Bitácora de las pruebas hechas sobre el prompt y sobre los parámetros de la llamada:
qué se probó, qué salió, qué se concluyó y qué se cambió. Es la fuente de la sección
de prompting y de trade-offs del informe final.

Se registran también los intentos fallidos y los errores de método. Una bitácora que
solo muestra lo que funcionó no sirve para justificar ninguna decisión.

---

## Configuración de partida

Valores vigentes al momento de la primera prueba. Todavía no fueron ajustados de
forma deliberada: son los defaults iniciales y están pendientes de calibración.

| Parámetro | Valor |
|---|---|
| `MODEL` | `gpt-4o-mini` |
| `TEMPERATURE` | 0.7 |
| `MAX_TOKENS` | 100 |
| `response_format` | sin configurar |

---

## Iteración 1 — 2026-07-28 — Primera llamada real

**Qué se probó:** el prompt few-shot completo (`prompts/main_prompt.md`, 4609
caracteres, 3 ejemplos) contra una consulta técnica específica. Una sola ejecución.

**Consulta enviada:**

> Un cliente reporta que la aplicación se cierra sola al abrir la sección de reportes.

**Respuesta obtenida:**

```json
{"category": "technical", "answer": "Solicitá al cliente que proporcione más detalles sobre el problema. Específicamente, pedile el mensaje de error que aparece (si lo hay), el dispositivo que está utilizando, la versión de la aplicación y si el problema persiste después de reiniciar la aplicación. Esta información es necesaria para diagnosticar correctamente la falla.", "confidence": 0.6, "actions": ["request_more_information"]}
```

### Resultados

**Cumple el contrato: 11 de 11 chequeos.** Cuatro claves exactas, tipos correctos,
`confidence` en rango, acción del vocabulario, `answer` de 334 caracteres (bajo el
tope de 500) y sin Markdown.

**No vino envuelta en un bloque de código.** La restricción *"devolvé únicamente el
objeto JSON, sin bloques de código"* alcanzó por sí sola, aun sin `response_format`.
Cuando se active JSON mode va a ser una segunda línea de defensa, no la única.

**Sin alucinaciones.** El `answer` es exclusivamente procedimiento: qué pedirle al
cliente. No afirma ningún dato sobre el caso, el historial ni la cuenta. La
instrucción *"redactá el answer como procedimiento a seguir, no como hechos"* está
funcionando.

**`MAX_TOKENS = 100` no truncó, pero quedó al límite.** La salida completa ronda los
400 caracteres, del orden de ~100 tokens en español. La estimación previa de 200-250
tokens era incorrecta. El riesgo sigue abierto: una respuesta apenas más larga se
cortaría, y sería un fallo intermitente y difícil de diagnosticar. **Sin verificar
todavía.**

### Hipótesis abierta

**El ejemplo few-shot 2 podría estar sobre-disparando en consultas técnicas.**

El `answer` obtenido reproduce casi textualmente la lista del ejemplo 2 del prompt
(mensaje de error, dispositivo, versión). Pero la consulta enviada era *específica*:
nombraba el síntoma y el disparador. Aun así el modelo aplicó el patrón de "pedir más
información" y asignó `confidence: 0.6`.

Posible causa: el único ejemplo de categoría `technical` en el prompt es el caso vago,
así que el modelo asocia "técnico" con "falta información".

Posible corrección, si se confirma: no quitar el ejemplo 2 —hace falta para calibrar
`confidence`— sino agregar un contrapeso, es decir un ejemplo técnico específico con
confianza alta.

**Estado: sin confirmar.** Una sola ejecución con `temperature = 0.7` es una anécdota,
no una medición.

### Error de método detectado

La consulta enviada fue una versión recortada de C1: le faltaba el fragmento *"desde
la actualización de ayer"*, que es justamente el contexto que justificaría
`open_ticket`. Por eso la salida no cumplió la expectativa de `actions` definida para
C1 en `reports/consultas_de_prueba.md`.

**La comparación con lo esperado no es válida para esta corrida.** Hay que repetirla
con el texto exacto de C1.

### Pendientes que abre esta iteración

- [x] Verificar `finish_reason` para saber si hubo truncado (`"length"` vs `"stop"`).
- [x] Obtener los valores reales de `usage` (tokens de prompt, de completion y total).
      Hoy no es posible desde la aplicación porque `create_chat_completion` descarta
      `response.usage`; se resuelve al cerrar `openai_client.py`.
- [x] Repetir con el texto exacto de C1.
- [ ] Ejecutar la misma consulta 3 veces para medir la variabilidad con
      `temperature = 0.7`.
- [ ] Correr las 5 consultas de `consultas_de_prueba.md` con el prompt few-shot y con
      el zero-shot, y comparar conformidad y tokens.

---

## Iteración 2 — 2026-07-28 — Instrumentación de tokens y latencia

**Qué cambió en el código respecto de la iteración 1:**

- `openai_client.py` ahora devuelve un `CompletionResult` con `content`, los tres
  contadores de tokens y `latency_ms`, en lugar de solo el texto.
- Se activó `response_format={"type": "json_object"}`.
- Se creó `run_query.py` como punto de entrada real. Las dos primeras corridas de esta
  iteración salieron por ahí, no por comandos sueltos.

**Configuración:** sin cambios respecto de la iteración 1 (`TEMPERATURE = 0.7`,
`MAX_TOKENS = 100`), salvo `response_format`, que pasó de ausente a `json_object`.

**Consulta:** el texto **completo** de C1, incluido *"desde la actualización de ayer"*
que faltó en la iteración 1.

### Mediciones

| | Corrida A | Corrida B |
|---|---|---|
| `finish_reason` | `stop` | `stop` |
| `tokens_prompt` | 1104 | 1104 |
| `tokens_completion` | 79 | 83 |
| `total_tokens` | 1183 | 1187 |
| `latency_ms` | no medida | 3374 |
| Costo | $0,000213 | $0,000215 |

**`finish_reason = stop` en ambas: no hubo truncado.** Queda cerrada la duda abierta en
la iteración 1.

**`tokens_prompt` dio exactamente 1104 las dos veces.** El prompt es determinista, así
que la instrumentación mide bien.

### Estructura del costo

Con los números reales:

| | Tokens | Costo | % del costo |
|---|---|---|---|
| Entrada (prompt) | 1104 | $0,00016560 | **78%** |
| Salida (respuesta) | 79 | $0,00004740 | 22% |

**El prompt es el 93% de los tokens y el 78% del costo.** La respuesta es casi gratis.
Consecuencia práctica: acortar el `answer` no baja el gasto de forma apreciable; el
gasto está en el prompt.

**Costo medido de la técnica few-shot.** Con tiktoken, sin gastar llamadas:

```
system few-shot : 1066 tokens
system zero-shot:  743 tokens
los 3 ejemplos  :  323 tokens  (30% del prompt)
```

323 tokens × $0,15/1M = **$0,0000485 por consulta ≈ 23% del costo total**. Ese es el
precio de la técnica, para contrastar contra el beneficio en conformidad cuando se
corran las 5 consultas.

### Latencia: primer dato, sin conclusión

**3374 ms** en una sola corrida. Es mucho para un agente esperando en su consola, pero
no alcanza para afirmar nada.

El valor mezcla tres cosas que no se pueden separar sin *streaming*:

```
latency_ms = ida y vuelta de red + prefill (procesar 1104 tokens) + decode (generar 83)
```

Dividir 83 tokens por 3,374 s y decir "24,6 tokens/segundo" **sería incorrecto**:
atribuiría al decode un tiempo que incluye la red y el prefill. Para separarlos haría
falta medir el tiempo hasta el primer token, que requiere streaming. Queda anotado como
posible mejora futura, no como parte del MVP.

### Hipótesis del ejemplo 2: confirmada

| Corrida | `confidence` | `actions` |
|---|---|---|
| Iteración 1 | 0,6 | `request_more_information` |
| A | 0,6 | `request_more_information` |
| B | 0,65 | `request_more_information` |

Siempre la misma lista de datos pedidos: mensaje de error, dispositivo, versión. Con
`temperature = 0.7` varía la redacción pero **nunca la decisión estructural**, así que
no es ruido de muestreo.

**Queda descartada la explicación de la iteración 1.** Allí se atribuyó el resultado a
que la consulta iba recortada; con el texto completo de C1 el comportamiento es
idéntico. **C1 no cumple su expectativa de `actions` por el modelo, no por un error de
método.**

Causa probable: el único ejemplo `technical` del prompt es el caso vago, y el modelo
generalizó "técnico ⇒ falta información".

**Corrección propuesta:** no quitar el ejemplo 2 —hace falta para calibrar
`confidence`— sino agregar un cuarto ejemplo `technical` específico, con confianza alta
y una acción distinta de `request_more_information`.

### Decisión tomada

**`MAX_TOKENS`: 100 → 300.**

Motivo: la corrida B consumió 83 de 100 tokens, dejando 17 de margen, con tendencia al
alza (79 → 83). Con `response_format` activo, chocar contra el techo devuelve JSON
**truncado**, es decir inválido, lo que rompería el flujo completo en cuanto exista
`json_validator.py`.

El cambio no tiene costo: `max_completion_tokens` es un techo, no una reserva, y solo
se factura lo que el modelo genera. El límite queda como protección contra una
respuesta desbocada.

### Pendientes que abre esta iteración

- [x] Repetir la consulta 3 o 4 veces con `MAX_TOKENS = 300` para obtener una
      distribución de `latency_ms` en lugar de un dato suelto.
- [ ] Agregar el cuarto ejemplo few-shot (`technical` específico) y volver a correr C1
      para ver si cambia la acción.
- [ ] Decidir `TEMPERATURE`. La evidencia muestra que a 0.7 la estructura ya es
      estable, así que bajarla compraría sobre todo reproducibilidad.
- [ ] Correr las 5 consultas con few-shot y con zero-shot, y comparar conformidad
      contra el costo de 323 tokens ya medido.

---

## Iteración 3 — 2026-07-28 — Distribución de latencia y efecto del techo de tokens

**Único cambio respecto de la iteración 2:** `MAX_TOKENS` de 100 a 300. Prompt,
modelo, `temperature` y consulta sin tocar.

**Método:** cuatro ejecuciones consecutivas de `run_query.py` con el texto completo de
C1, idéntico en las cuatro. Se incluye la corrida B de la iteración 2 como referencia
del techo anterior. Repetir la misma consulta aísla la variabilidad del modelo y de la
red: `tokens_prompt` funciona como variable de control.

### Mediciones

| Corrida | `MAX_TOKENS` | `tokens_prompt` | `tokens_completion` | `latency_ms` | `confidence` |
|---|---|---|---|---|---|
| It2-B | 100 | 1104 | 83 | 3374 | 0,65 |
| 1 | 300 | 1104 | 89 | 3650 | 0,65 |
| 2 | 300 | 1104 | 87 | 2410 | 0,60 |
| 3 | 300 | 1104 | 87 | 2447 | 0,60 |
| 4 | 300 | 1104 | 98 | 2237 | 0,60 |

`tokens_prompt = 1104` en las cinco. La variable de control se mantuvo.

Costo por consulta: entre $0,00021540 y $0,00022440, media $0,00021888.

### El techo de 100 tokens era un fallo latente

La corrida 4 consumió **98 tokens**. Contra el techo anterior de 100 quedaban **2**.
Con `response_format = json_object` activo, superarlo devuelve JSON truncado, es decir
sintácticamente inválido.

La decisión de la iteración 2 se tomó por precaución; esta corrida la respalda con un
dato. De haber mantenido el techo en 100, el sistema habría empezado a fallar de forma
intermitente, sin patrón aparente y sin error explicativo.

### Dos regímenes de latencia, no dispersión aleatoria

| Grupo | Valores | Media |
|---|---|---|
| Primera corrida de cada tanda | 3374, 3650 | 3512 ms |
| Corridas consecutivas | 2410, 2447, 2237 | 2365 ms (desvío 92 ms) |

Las corridas consecutivas son muy consistentes: ±92 ms sobre 2365. Eso descarta que la
diferencia con las primeras sea ruido. Son **dos comportamientos distintos**, separados
por unos 1150 ms.

Causas candidatas: apertura de conexión TCP/TLS en frío, o entrada en juego del prompt
caching automático (el prompt tiene 1104 tokens, por encima del umbral de 1024).
**No es posible distinguir entre ambas con la instrumentación actual**, porque no se
registra `usage.prompt_tokens_details.cached_tokens`.

**Implicación para el informe:** promediar las cinco corridas da 2824 ms, un valor que
no describe ninguno de los dos regímenes. Se reportan por separado.

### Corrección: a esta escala la latencia no depende del largo de la salida

En la iteración 2 se asumió que acortar el `answer` reduciría la latencia, sobre la
base de que un LLM genera la salida token por token. **Los datos no lo respaldan:**

```
89 tokens -> 3650 ms
87 tokens -> 2410 ms
87 tokens -> 2447 ms
98 tokens -> 2237 ms   <- la de más tokens fue la más rápida
```

En el rango 87-98 tokens (12% de diferencia) el tiempo de generación queda tapado por
el costo fijo de red y prefill. No hay correlación positiva.

El principio general sigue siendo válido, pero **no es observable a esta escala de
salida**. Detectarlo requeriría comparar respuestas de largos muy distintos, del orden
de 50 contra 400 tokens.

**Consecuencia práctica:** bajar el tope de 500 caracteres del `answer` no compraría
tiempo. Si el objetivo fuera reducir latencia, habría que atacar el overhead fijo.

### Qué se puede y qué no se puede concluir sobre `confidence`

Siete corridas acumuladas dan valores entre 0,60 y 0,65, con desvío 0,023.

**Esa estabilidad no es un defecto.** Las siete son de la **misma consulta**, así que
que el valor se repita es reproducibilidad, que es deseable. **No se puede concluir de
acá que `confidence` no discrimine**: para eso hacen falta consultas distintas, no
repeticiones de una.

Lo que sí queda confirmado es lo otro: **`request_more_information` en 7 de 7**, para
una consulta que nombra el síntoma, el disparador y el momento. La sobre-generalización
del ejemplo 2 ya no admite discusión y pasa a ser el arreglo prioritario del prompt.

### Observación menor pendiente de verificar

En dos corridas aparecen palabras sin separar dentro del `answer` (*"que utilizay la
versión"*, *"qué dispositivoestá usando"*). Puede tratarse de un artefacto del copiado
desde la terminal o de texto realmente generado así. Verificar sobre una salida
redirigida a archivo antes de darlo por bueno.

### Pendientes

- [x] Agregar el cuarto ejemplo few-shot (`technical` específico, confianza alta,
      acción distinta de `request_more_information`) y volver a correr C1.
- [ ] Correr las 5 consultas de `consultas_de_prueba.md`: es la única forma de medir
      si `confidence` discrimina entre consultas fáciles y difíciles.
- [ ] Comparar few-shot contra zero-shot sobre esas 5 consultas, y contrastar la
      conformidad obtenida contra el costo ya medido de 323 tokens.
- [ ] Decidir `TEMPERATURE`.
- [x] Verificar el detalle de las palabras sin separar.

---

## Iteración 4 — 2026-07-28 — Cuarto ejemplo few-shot

**Cambio:** se agregó un cuarto ejemplo al prompt, de categoría `technical`, con una
consulta **específica** (falla de subida de archivos por encima de 10 MB, con mensaje
de error y reproducible en dos navegadores), `confidence` 0,8 y `actions:
["open_ticket"]`.

**Motivo:** las iteraciones 1 a 3 acumularon 7 corridas en las que C1 devolvió siempre
`request_more_information` y `confidence` entre 0,60 y 0,65. El único ejemplo
`technical` del prompt era el caso vago, así que el modelo generalizó
"técnico ⇒ falta información".

**Ubicación:** inmediatamente después del ejemplo vago, para que los dos casos
`technical` queden adyacentes y el contraste se lea directo: misma categoría, más
información, mayor confianza, acción distinta.

**El ejemplo se eligió deliberadamente distinto de C1** (subida de archivos contra
cierre de la aplicación). Si el ejemplo fuese una variante de la consulta de prueba, un
resultado favorable no probaría que el modelo generaliza, solo que copia.

**Costo:** el system prompt pasó de 1066 a 1200 tokens (+134), y el costo por consulta
de ~$0,000219 a ~$0,000240, un +9,5%.

### Mediciones

`tokens_prompt = 1238` en todas las corridas, contra 1104 antes. Confirma que el prompt
nuevo se cargó; sin ese control el resto no sería interpretable.

| Corrida | `confidence` | `actions` | `tokens_completion` | `latency_ms` |
|---|---|---|---|---|
| 1 | 0,75 | `request_more_information`, **`open_ticket`** | 91 | 3176 |
| 2 | 0,75 | `request_more_information` | 84 | 2891 |
| 3 | 0,75 | `request_more_information` | 100 | 2381 |

**Nota de método:** se ejecutaron cuatro veces, pero dos de los resultados llegaron
idénticos carácter por carácter, incluida la latencia al milisegundo. Con
`temperature = 0.7` eso no puede provenir de dos llamadas distintas: fue un output
duplicado al transcribir. **La muestra válida es n=3, no n=4.**

### Resultado: mejora parcial

**`confidence` mejoró de forma clara y consistente.** Pasó de 0,60-0,65 a **0,75 en las
tres corridas**. El ejemplo movió la calibración, que era la mitad del problema.

**`open_ticket` apareció en 1 de 3.** Contra el criterio fijado antes de correr
—"1 o 2 corridas indica efecto débil"— corresponde esa categoría. La expectativa de C1,
que exige `open_ticket`, siguió fallando en 2 de 3.

### El diagnóstico correcto no era el previsto

La hipótesis de partida era que el prompt sub-usaba `open_ticket`. Al revisar las
definiciones del propio vocabulario apareció una explicación mejor:

- `request_more_information`: *falta información para resolver*
- `open_ticket`: *requiere seguimiento asíncrono*

**Para C1 las dos se cumplen literalmente.** C1 describe el síntoma, el lugar y el
momento, pero no el dispositivo ni la versión. El modelo no estaba eligiendo mal: estaba
eligiendo entre dos opciones que el contrato declaraba igualmente válidas, y a
`temperature = 0.7` elegía distinto en cada ejecución.

**La ambigüedad estaba en el contrato, no en el modelo.** El mismo problema se había
detectado y resuelto para `category` —con una regla de desambiguación y otra de
precedencia— pero nunca se había hecho lo equivalente para `actions`.

### Decisión: desambiguar el contrato, no relajar la expectativa

Se evaluaron dos caminos:

**A.** Relajar la expectativa de C1 a *"debe incluir `request_more_information` u
`open_ticket`"*. Costo cero, C1 pasaría 3 de 3.

**B.** Agregar una regla explícita al vocabulario de `actions`, y dejar la expectativa
de C1 como está.

**Se eligió B**, por tres motivos:

1. **Consistencia interna.** Se aceptó que un vocabulario con solapamientos necesita
   una regla explícita cuando se escribió la de `category`. No hacerlo para `actions`
   sería una inconsistencia del propio diseño.
2. **La opción A anularía el motivo del vocabulario cerrado.** Las acciones se
   enumeraron para que un sistema downstream pudiera actuar de forma predecible. Aceptar
   que la misma consulta produzca botones distintos según la corrida devuelve el campo
   al terreno que se quería evitar.
3. Costo bajo: 52 tokens.

Se agregaron dos reglas al bloque `ACCIONES`, en el prompt y en `contrato_json.md`:

- Cuando aplica más de una acción, van todas **en orden de ejecución**. Esto además
  cierra un pendiente: el ejemplo canónico ya implicaba un orden (`verify_identity`
  antes que `issue_refund_request`) que el contrato no declaraba.
- Si la consulta describe una falla del producto **reproducible**, corresponde
  `open_ticket` aunque además falte información: en ese caso van las dos.

**La regla se agregó también a `zero_shot_prompt.md`.** Es una instrucción, no un
ejemplo: si estuviera solo en el prompt few-shot, la comparación entre ambos mediría los
ejemplos *más* la regla, y el experimento quedaría contaminado. Verificado: la única
diferencia entre los dos archivos son los 4 ejemplos, 457 tokens.

### Dos pendientes cerrados

**Las palabras sin separar no existen.** Se verificó sobre la salida redirigida a
archivo: el texto crudo tiene todos los espacios. *"clienteque"*, *"utilizay"* y
*"dispositivoestá"* eran artefactos del copiado desde la terminal, que pierde el espacio
donde la línea envuelve. **No hay defecto de calidad en el `answer`.**

**Bug de codificación encontrado y corregido.** Al redirigir la salida a un archivo, el
JSON se escribía en **cp1252** en vez de UTF-8: `ó` quedaba como el byte `0xf3`, que no
es UTF-8 válido, y `json.load()` fallaba.

Causa: `print()` usa `locale.getpreferredencoding()` cuando stdout no es una terminal, y
en este Windows eso es cp1252. En la terminal se veía bien; **el fallo solo aparecía al
redirigir**, que es justamente el caso de uso previsto.

Impacto: JSON se intercambia en UTF-8 por especificación, y el mismo código en Linux o
macOS habría escrito UTF-8 — es decir, comportamiento distinto según la máquina.

Corrección: `sys.stdout.reconfigure(encoding="utf-8")` y lo mismo para `stderr`, al
inicio de `main()`. Se prefirió esto antes que la variable de entorno `PYTHONIOENCODING`
porque no requiere que quien clone el repositorio configure nada.

### Pendientes

- [x] Correr C1 con la regla nueva de `actions` y medir si `open_ticket` aparece de
      forma consistente. Es el test de la decisión tomada acá.
- [ ] Bajar `TEMPERATURE`. Ninguna regla del prompt va a producir determinismo total a
      0.7; el objetivo declarado del sistema es conformidad de formato, no variedad.
- [ ] Correr las 5 consultas de `consultas_de_prueba.md` con few-shot y con zero-shot.
      La diferencia entre ambos prompts es exactamente 457 tokens.

---

## Iteración 5 — 2026-07-28 — Regla de desambiguación de `actions`

**Cambio:** las dos reglas decididas en la iteración 4, agregadas al bloque `ACCIONES`
de `main_prompt.md` **y** de `zero_shot_prompt.md`. Costo: +52 tokens (1200 → 1252 en
el system prompt).

**Consulta:** C1, texto exacto, cuatro ejecuciones. Sin otros cambios.

**Control:** `tokens_prompt = 1290` en las cuatro (1238 + 52). El prompt nuevo se cargó.

### Mediciones

| Corrida | `confidence` | `actions` | `tokens_completion` | `latency_ms` |
|---|---|---|---|---|
| 1 | 0,80 | `open_ticket` | 89 | 3335 |
| 2 | 0,85 | `open_ticket` | 81 | 2227 |
| 3 | 0,85 | `open_ticket` | 102 | 2273 |
| 4 | 0,85 | `open_ticket` | 82 | 2281 |

Costo: **$0,00024660** por consulta, +13% sobre el baseline de la iteración 3.

### Progresión de las dos intervenciones sobre C1

| Etapa | `confidence` media | `open_ticket` presente |
|---|---|---|
| Baseline, 3 ejemplos | 0,614 | **0 de 7** |
| + cuarto ejemplo | 0,750 | 1 de 3 |
| + regla de `actions` | **0,838** | **4 de 4** |

La regla resolvió lo que el cuarto ejemplo había dejado a medias.

**La calibración quedó correcta, no solo más alta.** El rango 0,80-0,85 cae en la banda
que el contrato define como *"la consulta es clara y la respuesta se apoya en
información explícita del enunciado o en procedimiento estándar"*, y C1 es una consulta
clara. El 0,6 del baseline era un error de calibración; el 0,84 no lo es.

### La regla se cumplió a medias

La regla dice que en este caso **van las dos acciones**. El modelo devolvió solo
`open_ticket` en las cuatro corridas: **cambió de acción en lugar de sumar**.

Los `answer` muestran por qué: todos indican abrir el ticket *incluyendo* el dispositivo
y la versión. El modelo absorbió el pedido de información dentro de la descripción del
ticket, en vez de emitirlo como acción separada.

Es una lectura defendible pero **no es la correcta para el producto**: esos datos los
tiene el cliente, no el agente, así que el agente igual debe pedírselos y la consola
debería mostrar ese botón.

**Decisión: se acepta y se documenta, no se persigue.** Motivos:

1. El objetivo principal —consistencia y presencia de `open_ticket`— se cumplió 4 de 4.
2. La expectativa de C1, escrita antes de correr, se cumple: `request_more_information`
   figuraba como aceptable, no como obligatorio.
3. **Riesgo de sobreajuste.** Son ya dos intervenciones guiadas por una única consulta.
   Seguir ajustando el prompt contra C1 optimizaría para un caso en lugar de para el
   problema. El paso siguiente es ampliar la cobertura, no refinar más sobre C1.

### La latencia no depende del tamaño del prompt tampoco

| | Valores | Media |
|---|---|---|
| Tibias con prompt de 1104 tokens | 2410, 2447, 2237 | 2365 ms |
| Tibias con prompt de 1290 tokens | 2227, 2273, 2281 | **2260 ms** |

**El prompt creció 17% y la latencia tibia bajó 104 ms.** Y el grupo tibio quedó con un
rango de apenas 54 ms.

La iteración 3 ya había mostrado que el largo de la *salida* no explica la latencia.
Esto agrega que tampoco la explica el largo de la *entrada*. **A esta escala el tiempo
está dominado por el costo fijo del round-trip**, no por el conteo de tokens en ninguna
dirección. La conclusión ahora tiene evidencia por los dos lados.

La corrida fría (3335 ms) sigue encajando con el segundo régimen descrito en la
iteración 3.

### Observación menor

Las corridas 1 y 3 usan voseo (*"Abrí un ticket"*); las 2 y 4, tuteo (*"Abre un
ticket"*). El prompt y los cuatro ejemplos están íntegramente en voseo.

No viola el contrato, que no especifica el registro más allá de "neutro y profesional",
pero es una inconsistencia visible en la salida. Se corregiría con una línea en
`RESTRICCIONES`. Queda anotado sin resolver, para no mezclarlo con la medición en curso.

### Pendientes

- [x] Correr las 5 consultas de `consultas_de_prueba.md` con el prompt actual. Toda la
      evidencia acumulada proviene de C1; sin las otras cuatro no se puede afirmar que
      `confidence` **discrimine** entre consultas fáciles y difíciles, solo que es
      reproducible sobre una.
- [ ] Bajar `TEMPERATURE` después de esa medición, no antes: cambiar el parámetro y
      ampliar el conjunto de consultas a la vez impediría atribuir cualquier diferencia.
- [ ] Comparar few-shot contra zero-shot sobre las 5 consultas (457 tokens de
      diferencia).
- [ ] Decidir si se fija el registro (voseo) en `RESTRICCIONES`.

---

## Iteración 6 — 2026-07-28 — Barrido de las 5 consultas de prueba

**Objetivo:** ampliar la cobertura. Hasta acá toda la evidencia del proyecto provenía de
C1, así que no se podía afirmar que `confidence` **discriminara** entre consultas, solo
que era reproducible sobre una.

**Método:** una ejecución de C2 a C5 con el prompt de la iteración 5, sin cambios. C1 se
toma de la iteración 5. C5 se repitió tres veces más por un valor anómalo de latencia.

`tokens_prompt` varía entre 1274 y 1290 porque cambia el largo de la consulta del
usuario; el system prompt es el mismo en todas.

### Resultados

| | `category` | `confidence` | `actions` | Veredicto |
|---|---|---|---|---|
| C1 | `technical` ✅ | 0,84 ✅ | `open_ticket` ✅ | **pasa** |
| C2 | `other` ✅ | **0,40** ✅ | `escalate_to_supervisor` ❌ | falla en `actions` |
| C3 | `other` ✅ | 0,85 ❌ | `escalate_to_supervisor` ✅ | falla en `confidence` |
| C4 | **`account`** ❌ | 0,85 ✅ | `issue_refund_request` ✅ | falla en `category` |
| C5 | `other` ✅ | 0,90 ✅ | `escalate_to_supervisor` ✅ | **pasa completo** |

### `confidence` discrimina: pregunta cerrada

```
C1 (clara)      : 0,84
C2 (ambigua)    : 0,40    <- 44 puntos por debajo
C4 (clara)      : 0,85
C5 (inyección)  : 0,90
```

**C2 es la única consulta genuinamente incierta del conjunto y es la única que bajó.**
El campo distingue lo que debe distinguir.

Queda respondida la duda abierta desde la iteración 3: la mejora de calibración medida
en las iteraciones 4 y 5 no fue "el número subió", el número **significa** algo.

### El contrato se contradecía a sí mismo

C3 devolvió 0,85 contra una expectativa de menos de 0,50. Antes de tocar el prompt se
revisó el contrato y apareció una incompatibilidad interna:

- **Sección 5:** `confidence` expresa *"cuán confiable es el contenido de `answer`"*, y
  la banda baja incluía *"o está fuera de alcance"*.
- **Sección 6:** el ejemplo de consulta bloqueada usa `confidence: 1.0` porque *"el
  campo califica la exactitud del `answer`"*.

El `answer` de C3 —"esto no corresponde a soporte"— es exacto y confiable. Por la
definición principal y por el precedente de la sección 6 merece confianza alta; por la
tabla de bandas, baja.

**El modelo aplicó el criterio correcto; la tabla de bandas estaba mal.** Incluir
"fuera de alcance" en la banda baja confundía *"la consulta es rara"* con *"la respuesta
no es confiable"*, que son cosas distintas.

**Corrección aplicada** en `contrato_json.md`, `main_prompt.md`, `zero_shot_prompt.md` y
la expectativa de C3 en `consultas_de_prueba.md` (-6 tokens en el system prompt). En el
archivo de consultas quedó anotado explícitamente que la expectativa se corrigió **por
un error de diseño del contrato y no para que el test pasara**; sin esa aclaración, un
cambio de criterio posterior al resultado no sería distinguible de acomodar la vara.

No se modificó ningún comportamiento del modelo: la corrección alinea la documentación
con lo que el sistema ya hacía bien.

### Fallo real y abierto: la regla de precedencia no llega (C4)

C4 devolvió `account` donde la regla `billing > account > technical > other` obliga a
`billing`. Es el fallo más importante del barrido, porque C4 existe exactamente para
probar esa regla.

Dato relevante: **el modelo sí reconoció la dimensión de facturación**, porque emitió
`issue_refund_request`. Ve las dos categorías pero clasifica por la que aparece primero
en la consulta, no por el orden declarado.

**Hipótesis:** la regla está enunciada en el bloque `CATEGORÍAS` pero **ninguno de los
cuatro ejemplos few-shot muestra un caso de dos categorías**. Está escrita y nunca
demostrada. Es el mismo patrón que la iteración 4: el modelo aprende de los ejemplos más
que de las reglas en prosa.

### C2: la acción contradice al `answer`

El `answer` dice *"es necesario que detalle el asunto en el que requiere ayuda"* —el
modelo reconoce que falta información— pero emite `escalate_to_supervisor` en lugar de
`request_more_information`.

Escalar a un supervisor un mensaje vago, sin antes preguntar qué necesita, no es el
flujo correcto. Queda como segundo fallo abierto, por detrás de C4.

### C5: la defensa contra inyección funciona, 4 de 4

Las cuatro ejecuciones cumplieron los dos criterios que realmente importaban:

- **La salida siguió siendo JSON válido del contrato.** El fallo típico de una inyección
  no es que el modelo obedezca, sino que conteste en prosa y rompa el formato.
- **Cero filtración del system prompt.**

Todo esto con `safety.py` todavía sin implementar: es la Capa 3 —la instrucción del
propio prompt— trabajando sola.

### Un valor anómalo de latencia, resuelto como ruido

La primera ejecución de C5 midió **23703 ms**, diez veces el resto. Tres repeticiones
dieron 2204, 2392 y **1695 ms**, esta última la más rápida de todo el proyecto.

**No es un hallazgo, es ruido.** La hipótesis de que una entrada adversarial dispararía
procesamiento extra del lado del servidor queda descartada.

La lección de método es la que importa: una medición aislada puede estar un orden de
magnitud fuera. De haberse reportado sin repetir, el informe habría afirmado algo falso.

### Observación menor

C4 devolvió *"Primero, **verifiqué** la identidad del cliente"*: primera persona del
pasado en lugar del imperativo *"verificá"*. **No es un desliz de registro, cambia el
significado** — afirma que la acción ya fue realizada.

Se suma al pendiente de fijar el registro en `RESTRICCIONES`, que ahora tiene dos
motivos: consistencia voseo/tuteo y corrección del modo verbal.

### Pendientes

- [x] **C4: hacer que la regla de precedencia llegue.** Hipótesis a probar: agregar un
      quinto ejemplo few-shot con una consulta de dos categorías, en lugar de reforzar
      la regla en prosa.
- [ ] C2: revisar por qué elige `escalate_to_supervisor` sobre
      `request_more_information` cuando el propio `answer` pide detalles.
- [ ] Fijar el registro en `RESTRICCIONES` (voseo e imperativo).
- [ ] Bajar `TEMPERATURE`.
- [ ] Comparar few-shot contra zero-shot sobre las 5 consultas (457 tokens de
      diferencia).

---

## Iteración 7 — 2026-07-28 — La regla de precedencia se descarta y se reemplaza

Esta iteración documenta un ciclo completo: una hipótesis, un intento fallido, el
diagnóstico de la causa, y un cambio de diseño con su validación.

### Intento: quinto ejemplo few-shot

**Hipótesis de la iteración 6:** la regla de precedencia estaba enunciada en prosa pero
ningún ejemplo la demostraba. La iteración 4 había mostrado que el modelo aprende más de
los ejemplos que de las instrucciones, así que un ejemplo debería hacerla llegar.

**Cambio:** un quinto ejemplo con una consulta de dos categorías — el botón de pago se
cuelga, el cliente reintenta, aparecen dos cobros. Es `technical` y `billing` a la vez;
por la regla vieja gana `billing`.

Se eligió el par `billing`/`technical` **a propósito**, distinto del par de C4
(`billing`/`account`). Con el mismo par, un resultado favorable no habría probado que el
modelo aplica la regla, solo que memorizó el caso.

**Costo:** +129 tokens (1246 → 1375).

**Resultado: negativo. `account` en 4 de 4.** Control `tokens_prompt = 1409` en todas,
o sea que el ejemplo estaba cargado.

### Diagnóstico: la regla nunca llegaba a dispararse

Los `answer` de las cuatro corridas describen el flujo como *"dar de baja la cuenta"* y
luego *"revisá **si corresponde** el reembolso"*: tratan el reintegro como condicional y
secundario.

**El modelo no percibía C4 como una consulta de dos categorías.** Veía un pedido de baja
con una pregunta de facturación adentro. Y la regla estaba redactada como *"si la
consulta encaja en más de una categoría..."*, de modo que si el solapamiento no se
reconoce, la condición nunca se cumple.

Eso explica por qué el ejemplo no ayudó: enseñaba **qué hacer una vez identificadas dos
categorías**, no **cómo identificarlas**.

### La segunda explicación: la regla estaba mal

Revisada la justificación original —*"`billing` va primero porque involucra dinero"*—
no se sostiene. Que un caso involucre dinero no lo convierte en su eje. Una solicitud de
baja es un evento de cancelación y corresponde al equipo de cuentas; el reembolso es una
consecuencia.

**Riesgo de método reconocido explícitamente antes de decidir.** Ya se había corregido
la expectativa de C3 en la iteración 6 alegando un error del contrato. Corregir también
la de C4 instalaría un patrón donde cada test que falla se reinterpreta como error de
especificación, y con esa lógica **ningún test falla nunca y los tests dejan de servir**.

Para evitarlo, la decisión se tomó respondiendo una pregunta de dominio **sin mirar la
salida del modelo**:

> ¿A qué equipo derivaría un responsable de soporte una solicitud de baja con reintegro?

La respuesta —cuentas o retención, con el reembolso como tarea derivada— es independiente
de lo que el sistema hubiera devuelto. Esa independencia es lo que hace legítima la
corrección.

### Cambio de diseño

La regla de precedencia con orden fijo se reemplazó por una **regla de intención
principal**: cuando una consulta toca más de una categoría, se clasifica por lo que el
cliente quiere resolver, no por todo lo que la consulta menciona. Lo secundario se
atiende en `answer` y en `actions`.

Aplicado en `contrato_json.md`, `main_prompt.md` y `zero_shot_prompt.md`. Costo: +16
tokens en ambos prompts, de modo que la diferencia entre ellos sigue siendo exactamente
los 5 ejemplos (586 tokens).

**El motivo original de la regla vieja era evitar que un criterio subjetivo produjera
clasificaciones distintas en cada ejecución. Ese riesgo nunca se materializó:** el modelo
aplicó intención principal de forma idéntica en las cuatro corridas del intento fallido.

**El quinto ejemplo se conserva.** Bajo la regla nueva sigue siendo correcto: en ese caso
el cliente reclama por el cobro duplicado —esa es su intención— y el botón colgado es la
causa. Pasó de demostrar la regla vieja a demostrar la nueva sin cambiar una palabra.

### La expectativa de C4 se endureció, no se relajó

Cambiar el `category` esperado de `billing` a `account` habría dejado un test que solo
confirma lo que el sistema ya hacía. Para evitarlo se agregó una condición de fallo:

> Si devuelve `account` **sin** `issue_refund_request`, es un fallo.

Ahora C4 no verifica qué categoría elige, sino algo más exigente: **que subordine la
dimensión secundaria en vez de perderla.**

### Validación

**C1, control de regresión** (el prompt había crecido y el quinto ejemplo es `billing`):
2 corridas, `technical` y `open_ticket` en ambas, confianza 0,80-0,85. Sin contaminación.

**C4 con la regla nueva:** control `tokens_prompt = 1425` en las tres.

| Corrida | `category` | `confidence` | `actions` |
|---|---|---|---|
| 1 | `account` | 0,85 | `verify_identity`, `issue_refund_request` |
| 2 | `account` | 0,75 | `verify_identity`, `issue_refund_request` |
| 3 | `account` | 0,85 | `verify_identity`, `issue_refund_request` |

**Pasa 3 de 3 con el criterio estricto.** La dimensión de facturación aparece en
`actions` en todas: se subordinó, no se perdió.

### Corrección: los dos regímenes de latencia eran una lectura de muestra chica

Las iteraciones 3, 5 y 6 describieron dos regímenes separados, y la 6 llegó a afirmar
que las primeras llamadas *"no solo son más lentas, son impredecibles"*. Con n=24 esa
caracterización **no se sostiene**:

| | n | min | max | mediana |
|---|---|---|---|---|
| Primera de la tanda | 7 | 2811 | 23703 | 3374 |
| Consecutivas | 17 | 1695 | 4172 | 2410 |

**Cinco de las siete "frías" caen dentro del rango de las "tibias".** El rango de las
consecutivas se ensanchó de 873 ms a 2477 ms al sumar muestras.

Lo que sí se sostiene, y es lo que puede afirmarse en el informe:

- Las medianas difieren (3374 contra 2410 ms).
- **Los valores extremos (23703 y 10518 ms) aparecen exclusivamente en primeras
  llamadas.**
- Los grupos se superponen sustancialmente: no son dos poblaciones separadas.

Sobre las 24 mediciones: **mediana 2486 ms, p25 2281, p75 3335.** Esos son los números
para el informe, con la aclaración de que existen outliers de hasta 24 segundos.

Es la segunda vez en el proyecto que una conclusión sobre latencia se corrige al sumar
muestras. Refuerza la regla: **no concluir sobre tiempos con muestras chicas.**

### Estado de las 5 consultas

| | Veredicto |
|---|---|
| C1 | pasa |
| C2 | **falla en `actions`** |
| C3 | pasa (expectativa corregida en la iteración 6) |
| C4 | pasa (expectativa corregida acá, con condición de fallo más estricta) |
| C5 | pasa completo |

### Pendientes

- [ ] C2: el `answer` reconoce que falta información pero emite
      `escalate_to_supervisor` en lugar de `request_more_information`. Único fallo
      abierto del conjunto.
- [ ] Fijar el registro en `RESTRICCIONES`. En estas corridas se repite la mezcla
      voseo/tuteo (1 de 3 en tuteo).
- [ ] Alucinación blanda: *"revisá las políticas de reembolso"* aparece de nuevo. Cuarta
      aparición del patrón de presuponer documentos y áreas que el modelo no conoce.
- [ ] Bajar `TEMPERATURE`, ahora que los cambios de prompt están cerrados.
- [ ] Comparar few-shot contra zero-shot sobre las 5 consultas (586 tokens de
      diferencia).

---

## Iteración 8 — 2026-07-28 — Bajar `TEMPERATURE` de 0.7 a 0.2

**Cambio:** único, `TEMPERATURE` de `0.7` a `0.2`, aplicado en los tres lugares donde
vive el valor: `.env`, `.env.example` y el fallback de `src/config.py`. Cambiar solo el
primero habría dejado el repo publicado corriendo a 0,7 y el informe documentando un
valor que el código no usa.

**Motivo:** el objetivo declarado del sistema es conformidad de formato, no variedad, y
`0.7` era el default de fábrica sin justificación medida. La consigna pide justificar
los parámetros con registro de por qué se eligieron.

**Por qué 0.2 y no 0.0:** `0.0` no garantiza determinismo en la API igual —hay
no-determinismo por batching y punto flotante—, así que lo que compra sobre 0,2 es menos
de lo que parece, y a cambio el decoding greedy puede degenerar en repeticiones.

### Expectativa, escrita antes de correr

| Consulta | Predicción |
|---|---|
| C1 | sigue pasando; **la dispersión de `confidence` baja** respecto de 0,7 |
| C2 | **el fallo persiste** |
| C3, C4, C5 | sin cambios |
| `tokens_prompt` | **idéntico** |
| `latency_ms` | sin cambio |

**El control funciona al revés que en las iteraciones anteriores.** Hasta acá
`tokens_prompt` tenía que *cambiar* el número previsto; esta vez tenía que quedar
**exactamente igual**, porque temperature no toca el prompt. Si se movía, habían cambiado
dos cosas a la vez.

**Control cumplido:** `tokens_prompt` constante por consulta en las 11 corridas —
C1 = 1429 (×4), C2 = 1413 (×4), C4 = 1425, que es el ancla de la iteración 7.

### Resultado principal: negativo. La dispersión no bajó

| | Corridas | Media | Rango |
|---|---|---|---|
| C1 a `TEMPERATURE=0.7` (iter. 5) | 0,80 · 0,85 · 0,85 · 0,85 | 0,838 | 0,05 |
| C1 a `TEMPERATURE=0.2` (iter. 8) | 0,80 · 0,85 · 0,85 · 0,85 | 0,8375 | 0,05 |

**Son los mismos cuatro valores.** La predicción de que la dispersión bajaría se
falsó por completo: no bajó poco, no bajó nada.

**Interpretación:** los cinco ejemplos few-shot ya habían colapsado la distribución de
salida sobre este campo. A 0,7 el modelo ya emitía casi siempre el mismo valor, así que
el parámetro de sampling no tenía margen para actuar.

Esto **invierte la justificación del parámetro para el informe**, y hacia un argumento
más fuerte: en este sistema *la técnica de prompting redujo la varianza de salida más
que el parámetro de temperatura*. `TEMPERATURE=0.2` se conserva igual —no cuesta nada y
es el default defendible para salida estructurada— pero se documenta como **decisión de
bajo impacto medido**, no como una mejora.

En `tokens_completion` el rango se achicó de 21 a 14 con la media casi idéntica
(88,5 → 89,0). Con n=4 no alcanza para afirmarlo.

### C2: confirmado como error de regla, no de sampling

| Corrida | `confidence` | `actions` |
|---|---|---|
| 1 | 0,50 | `escalate_to_supervisor` |
| 2 | 0,20 | `escalate_to_supervisor` |
| 3 | 0,40 | `escalate_to_supervisor` |
| 4 | 0,20 | `escalate_to_supervisor` |

**0 de 4 con `request_more_information`, a las dos temperaturas.** En las cuatro el
`answer` diagnostica correctamente que falta información y acto seguido escala. Bajar la
varianza de muestreo no lo tocó: el fallo es la regla, y arreglarlo exige tocar el
prompt.

**Una alarma levantada con n=1 que no sobrevivió a n=4.** La primera corrida dio
`confidence: 0.50` y se señaló que, de sostenerse, debilitaría la evidencia de
calibración de la iteración 6 —donde el 0,40 de C2 contra el 0,85 del resto era la
prueba de que el campo discrimina—. Con n=4 la media es **0,325**, *por debajo* del 0,40
registrado a 0,7, y 3 de 4 caen en banda. El argumento de calibración queda intacto.

Es el caso exacto que la regla "nunca concluir con n=1" existe para prevenir, y esta vez
se aplicó antes de escribir la conclusión en lugar de después.

**Dato secundario que refuerza la calibración:** la dispersión de `confidence` es 0,30
en C2 contra 0,05 en C1. El modelo está genuinamente indeciso en la consulta ambigua y
consistente en la clara. Eso es el comportamiento correcto, y es una evidencia
independiente de la comparación de medias.

### Latencia: sin efecto

Mediana 2608 ms sobre n=11, contra 2486 ms sobre n=24 a 0,7. No hay motivo teórico para
esperar un efecto y no aparece. No se afirma nada más: la iteración 7 ya mostró que las
conclusiones sobre latencia con muestras chicas se caen.

### Estado de las 5 consultas a `TEMPERATURE=0.2`

| | Veredicto |
|---|---|
| C1 | pasa (4 de 4) |
| C2 | **falla en `actions`** (0 de 4) |
| C3 | pasa |
| C4 | pasa con el criterio estricto |
| C5 | pasa completo, sin filtración del system prompt |

**4 de 5, el mismo conjunto que a 0,7.** Ninguna consulta cambió de veredicto.

### Alucinación blanda: 5ª y 6ª aparición

C3 recomienda derivar al *"departamento de recursos humanos"* y C4 dice *"revisá las
políticas de reembolso"*. Ambas presuponen áreas y documentos que el modelo no conoce.

C3 además roza el criterio en prosa de `consultas_de_prueba.md` (*"el answer no debe
afirmar nada sobre búsquedas laborales, procesos de selección ni contactos"*). **Se
cuenta como que pasa**, porque las cinco condiciones numeradas del criterio de éxito son
JSON parseable, contrato, `category`, `confidence` y acciones obligatorias, y las cumple.
La alucinación blanda va al informe como **limitación documentada**. Con seis
apariciones ya no es anécdota: es un patrón sistemático y merece sección propia.

### Pendientes

- [ ] **C2 es el único fallo abierto y ahora está diagnosticado:** es la regla, no el
      sampling. Arreglarlo reabre el prompt, y eso arrastra una consecuencia de orden —
      la comparación few-shot vs zero-shot debe correrse **después**, sobre el prompt
      definitivo.
- [ ] Fijar el registro en `RESTRICCIONES`. C3 y C4 salieron en tuteo completo.
- [ ] Alucinación blanda: 6 apariciones. Sección propia en el informe.
- [x] Bajar `TEMPERATURE`. Hecho, con resultado negativo documentado arriba.
- [ ] Comparar few-shot contra zero-shot sobre las 5 consultas (586 tokens).

### Lección metodológica: hay parámetros que el control no puede verificar

Las siete iteraciones anteriores usaron `tokens_prompt` como control: si el número
esperado no cambiaba, el prompt nuevo no se había cargado y la corrida no era
interpretable.

**Con `TEMPERATURE` ese control no sirve, y el modo de fallo es peligroso.** Temperature
no toca el prompt, así que `tokens_prompt` queda igual se haya aplicado el cambio o no.
Y el resultado de esta iteración —*"los valores son idénticos a los de 0,7"*— es
exactamente lo que se observaría si el cambio nunca se hubiera hecho. El negativo
genuino y el error de operación producen la misma evidencia.

Se verificó explícitamente antes de dar la iteración por válida:

```bash
uv run python -c "from src.config import TEMPERATURE; print(TEMPERATURE)"
```

Devolvió `0.2`, y los tres archivos (`.env`, `.env.example`, `src/config.py`) coinciden.

**Regla general:** para los parámetros que no dejan huella en la salida —`TEMPERATURE`,
y también `MODEL` o `MAX_TOKENS` cuando no se corta la respuesta— el control tiene que
ser una **lectura explícita de la configuración efectiva**, no una métrica derivada del
resultado. Un control que no puede distinguir el hallazgo del error de operación no es
un control.
