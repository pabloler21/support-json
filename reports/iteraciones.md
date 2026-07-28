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

- [ ] Correr C1 con la regla nueva de `actions` y medir si `open_ticket` aparece de
      forma consistente. Es el test de la decisión tomada acá.
- [ ] Bajar `TEMPERATURE`. Ninguna regla del prompt va a producir determinismo total a
      0.7; el objetivo declarado del sistema es conformidad de formato, no variedad.
- [ ] Correr las 5 consultas de `consultas_de_prueba.md` con few-shot y con zero-shot.
      La diferencia entre ambos prompts es exactamente 457 tokens.
