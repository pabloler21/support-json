# Contrato de salida JSON

Este documento define la salida de la aplicación: una consulta de soporte entra y,
en una sola llamada al modelo, sale un objeto JSON de cuatro campos que clasifica la
consulta, propone una respuesta, estima su confiabilidad y recomienda acciones.

El JSON lo consumen sistemas downstream que lo muestran en la consola del agente de
soporte. El destinatario del campo `answer` es **el agente, no el cliente final**: es
un borrador que el agente revisa y adapta antes de responder, escrito en registro
neutro y profesional, sin saludos ni despedidas.

El contrato se define acá **antes** de pedírselo al modelo y se mantiene estable
durante todo el proyecto. Es la única fuente de verdad: el prompt lo pide,
`json_validator.py` lo verifica y `tests/test_core.py` lo prueba.

---

## 1. Ejemplo canónico

Consulta: *"Un cliente dice que le cobraron dos veces el plan de este mes. ¿Cómo procedo?"*

```json
{
  "category": "billing",
  "answer": "Un cargo duplicado en el mismo ciclo suele originarse en un reintento de cobro que impactó dos veces. Verificá la identidad del cliente, confirmá que ambos cargos tengan el mismo importe y concepto, y si coinciden iniciá la devolución del segundo. No prometas plazos de acreditación sin confirmarlos.",
  "confidence": 0.75,
  "actions": ["verify_identity", "issue_refund_request"]
}
```

Los cuatro campos son obligatorios y van siempre en este orden.

---

## 2. Reglas de validación

| Campo | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `category` | `str` | sí | Pertenece al vocabulario de la sección 3 |
| `answer` | `str` | sí | No vacío tras `.strip()`; máximo **500 caracteres**; texto plano sin Markdown; en el mismo idioma que la consulta |
| `confidence` | `int` o `float`, **nunca `bool`** | sí | `0.0 <= confidence <= 1.0` |
| `actions` | `list[str]` | sí | Entre **0 y 3** elementos; sin repetidos; cada elemento pertenece al vocabulario de la sección 4 |

**El contrato es cerrado.** El objeto tiene exactamente estas cuatro claves: ni una
menos ni una más. Una clave que no fue pedida indica que el modelo se desvió del
prompt, y eso tiene que detectarse, no ignorarse.

**Ante cualquier incumplimiento**, `json_validator.py` levanta una excepción y la
respuesta se descarta. No hay corrección automática ni reparación parcial: una salida
que no cumple el contrato no es consumible por los sistemas downstream, que es la
razón por la que el contrato existe.

---

## 3. Vocabulario de `category`

| Valor | Alcance |
|---|---|
| `billing` | Cobros, facturas, reembolsos, medios de pago, planes y precios |
| `technical` | Fallas del producto: errores, caídas, comportamiento defectuoso, performance |
| `account` | Acceso y datos de una cuenta puntual: login, contraseña, datos personales, permisos, alta y baja |
| `other` | No encaja en las anteriores, o la consulta fue bloqueada por `safety.py` |

### Regla de desambiguación

El solapamiento clásico es entre `technical` y `account` (por ejemplo, *"no puedo
iniciar sesión"*):

> Si el problema afecta el acceso o los datos de **una cuenta puntual**, es `account`.
> Si es una falla del producto que le pasaría a **cualquier usuario**, es `technical`.

### Regla de intención principal

Cuando una consulta toca más de una categoría, se clasifica por **lo que el cliente
quiere resolver**, no por todo lo que la consulta menciona.

> Ejemplo: *"quiero dar de baja mi cuenta y que me reintegren lo que no usé"* es
> `account`. La baja es lo que el cliente pide; el reintegro es una tarea derivada.

Las dimensiones secundarias no se pierden: siguen apareciendo en el `answer` y en
`actions`. Lo que la categoría responde es a qué equipo corresponde el caso, y eso lo
determina el pedido, no los temas que roza.

**Esta regla reemplaza a una anterior, y el cambio se documenta porque importa.** El
contrato definía originalmente un orden fijo de precedencia
(`billing` > `account` > `technical` > `other`), con el argumento de que `billing` iba
primero por involucrar dinero. Se descartó por dos motivos:

1. **No llegaba al modelo.** Se intentó dos veces —enunciada en prosa, y después
   demostrada con un ejemplo few-shot— y en las dos el modelo siguió clasificando por
   intención principal, de forma consistente. El detalle revelador es que ni siquiera
   percibía esas consultas como multi-categoría: veía un pedido con un tema secundario
   adentro, así que la regla nunca llegaba a dispararse.
2. **El argumento era débil.** Que un caso involucre dinero no lo convierte en su eje.
   Una solicitud de baja es un evento de cancelación y corresponde al equipo de cuentas;
   el reembolso es una consecuencia.

El motivo por el que se había elegido un orden fijo era evitar que un criterio subjetivo
produjera clasificaciones distintas en cada ejecución. **Ese riesgo no se materializó:**
el modelo aplicó el criterio de intención principal de forma idéntica en las cuatro
corridas de prueba.

---

## 4. Vocabulario de `actions`

Las acciones las ejecuta **el agente de soporte**. Cada una describe algo que una
persona puede efectivamente hacer.

| Valor | Cuándo corresponde |
|---|---|
| `request_more_information` | Falta información para resolver y hay que pedírsela al cliente |
| `verify_identity` | Antes de acceder a datos sensibles o modificar la cuenta |
| `open_ticket` | Requiere seguimiento asíncrono; no se resuelve en la interacción |
| `escalate_to_supervisor` | Excede la autoridad o el alcance del agente |
| `send_help_article` | Existe documentación pública que resuelve la consulta |
| `issue_refund_request` | Corresponde iniciar el trámite de devolución |

**La lista vacía es una respuesta válida.** Si el agente puede resolver la consulta
solo con el `answer`, `actions` va en `[]`. No existe una acción `none`: habría dos
formas de expresar lo mismo y eso vuelve ambigua la validación.

El tope de 3 elementos es deliberado. Sin tope, el modelo tiende a devolver todas las
acciones aplicables "por las dudas", y una recomendación que siempre incluye todo no
recomienda nada.

### La lista está ordenada

Cuando aplica más de una acción, el orden es el de ejecución sugerida para el agente.
En el ejemplo canónico de la sección 1, `verify_identity` va antes que
`issue_refund_request` porque la identidad se confirma antes de mover dinero.

### Regla de desambiguación

A diferencia de `category`, las acciones no son mutuamente excluyentes: varias pueden
aplicar a la vez y se incluyen todas. Pero hay un solapamiento que sí produce
resultados inconsistentes si no se resuelve.

`request_more_information` y `open_ticket` se cumplen los dos al mismo tiempo en
cualquier reporte de falla al que le falten datos del entorno: falta información **y**
el caso no se resuelve en la interacción. Sin una regla, el modelo elige uno u otro
según la ejecución, y la misma consulta produce acciones distintas cada vez.

> Si la consulta describe una falla del producto que se puede reproducir, corresponde
> `open_ticket` aunque además falte información. En ese caso van las dos.

El criterio es que un reporte reproducible merece quedar registrado de inmediato: pedir
los datos del entorno es un paso adicional, no un motivo para postergar el ticket.

---

## 5. Semántica de `confidence`

`confidence` expresa cuán confiable es el contenido de `answer` para el caso
concreto. No mide la calidad de la redacción ni la certeza de la clasificación.

| Rango | Significado |
|---|---|
| `0.80` – `1.00` | La consulta es clara y la respuesta se apoya en información explícita del enunciado o en procedimiento estándar |
| `0.50` – `0.79` | La respuesta es razonable pero descansa en supuestos no confirmados |
| `0.00` – `0.49` | Falta información, o la consulta es ambigua |

Definir los rangos es lo que hace que el campo signifique algo. Sin esta tabla,
`confidence` es un número sin unidad y no puede responder ninguna pregunta útil. Los
ejemplos few-shot del prompt tienen que cubrir al menos dos de estos rangos para que
el modelo aprenda a moverse dentro de la escala.

### Una consulta fuera de alcance no baja la confianza

La banda baja incluía originalmente el caso "está fuera de alcance". **Era un error de
diseño** y se corrigió: confundía *"la consulta es rara"* con *"la respuesta no es
confiable"*, que son cosas distintas.

Si alguien pregunta por vacantes laborales, el `answer` correcto —"esto no corresponde
a soporte"— es exacto y confiable, así que la confianza es **alta**. Lo que baja la
confianza es que el contenido del `answer` sea incierto, no que la consulta sea
inesperada.

Es el mismo criterio que ya aplicaba la sección 6 a las consultas bloqueadas, donde
`confidence` vale `1.0` porque el `answer` describe con certeza lo que ocurrió. La
tabla de bandas contradecía ese precedente.

---

## 6. Respuesta ante entradas bloqueadas

Cuando `safety.py` bloquea una consulta, la aplicación **devuelve el mismo contrato**.
No hay una forma de salida alternativa para errores: los sistemas downstream esperan
siempre estos cuatro campos, y una respuesta con otra forma los rompería.

```json
{
  "category": "other",
  "answer": "La consulta fue bloqueada por la capa de seguridad y no se envió al modelo. Derivá el caso a un supervisor para su revisión manual.",
  "confidence": 1.0,
  "actions": ["escalate_to_supervisor"]
}
```

`confidence` vale `1.0` porque el campo califica la exactitud del `answer`, y en este
caso el `answer` describe con certeza lo que ocurrió.

---

## 7. Decisiones de diseño

**`confidence` es un número y no un enum `low`/`medium`/`high`.** Un float admite dos
validaciones independientes (tipo y rango), lo que produce una batería de tests más
rica, y es promediable en `metrics.csv`. La contra es conocida y está asumida: los LLM
están mal calibrados y tienden a concentrarse en valores altos. La tabla de la sección
5 y los ejemplos few-shot son la mitigación.

**Los vocabularios de `category` y `actions` son cerrados.** Una acción en texto libre
es decorativa: el programa no puede rutear, contar ni condicionar sobre una cadena que
el modelo redacta distinto en cada ejecución. Un vocabulario cerrado permite validar
pertenencia y habilita que la aplicación haga algo real con el valor.

**El contrato rechaza claves extra.** Ignorarlas en silencio deja crecer el desvío del
prompt sin que quede registro. Rechazarlas convierte ese desvío en una señal visible.

**Los identificadores están en inglés y `answer` va en el idioma de la consulta.** Los
valores de los enums son identificadores de máquina y siguen la convención del código;
`answer` es prosa dirigida a una persona y tiene que estar en su idioma.

**Se agregó `category` a los tres campos que pedía el enunciado.** Con la
clasificación, una sola llamada al modelo resuelve tres tareas —clasificar, redactar y
recomendar—, que es lo que sostiene el nombre "Multitasking Text Utility". El costo
marginal son unos pocos tokens y aporta una dimensión de análisis a las métricas.

**Limitación conocida: el vocabulario está duplicado.** Vive en el prompt (`.md`) y en
las constantes de `json_validator.py`, porque el prompt es texto y no código. Si uno se
edita y el otro no, el modelo devolvería valores que el validador rechaza. Mejora
futura: generar esa sección del prompt a partir de las constantes de Python.

---

## 8. Casos de prueba

Estos casos son los fixtures de `tests/test_core.py`. El caso válido es el ejemplo
canónico de la sección 1; los inválidos se describen como mutaciones sobre él.

### Válidos

El objeto de la sección 1, más estas variantes que **deben pasar**:

| Mutación | Por qué es válido |
|---|---|
| `"actions": []` | La lista vacía está permitida |
| `"confidence": 1` | Un entero es aceptable, no solo un float |
| `"confidence": 0.0` y `"confidence": 1.0` | Los extremos del rango son inclusivos |

### Inválidos

| # | Mutación | Regla que rompe |
|---|---|---|
| 1 | Una coma de más antes de `}` | No es JSON parseable |
| 2 | Se elimina la clave `confidence` | Falta una clave obligatoria |
| 3 | Se agrega `"reasoning": "..."` | El contrato es cerrado |
| 4 | `"confidence": 1.5` | Fuera del rango `[0.0, 1.0]` |
| 5 | `"confidence": true` | `bool` no es un tipo admitido, aunque en Python `isinstance(True, int)` sea `True` |
| 6 | `"answer": ""` | Vacío tras `.strip()`, aunque sea un `str` válido |
| 7 | `"category": "billin"` | Fuera del vocabulario de la sección 3 |
| 8 | `"actions": ["send_discount"]` | Fuera del vocabulario de la sección 4 |
| 9 | `"actions": ["open_ticket", "open_ticket"]` | Elementos repetidos |

Los casos 5 y 6 son los que más se pasan por alto: los dos superan un chequeo de tipo
ingenuo y solo se detectan con una validación explícita.
