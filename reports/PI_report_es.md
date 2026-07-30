# Asistente de soporte: diseño, iteración y mediciones

*Proyecto Integrador, Módulo 1 — AI Engineering (Soy Henry).
Versión en inglés: [`PI_report_en.md`](PI_report_en.md).*

---

## 1. Qué hace

Entra una consulta de soporte en texto libre; sale un objeto JSON de cuatro
campos para la consola de un agente: `category`, `answer`, `confidence`,
`actions`. Una sola llamada al modelo resuelve tres trabajos: clasificar,
redactar y recomendar.

La arquitectura sigue una idea: **cada módulo es una frontera que recibe algo
menos confiable y devuelve algo más confiable.** Después de `json_validator`,
`category` **no puede** valer un string arbitrario, y esa garantía es lo que
permite que todo lo que sigue deje de defenderse solo. Dos invariantes sostienen
el peso: `openai_client.py` es el único módulo que toca la red, y ningún módulo
con lógica lo importa — por eso los **61 tests corren sin credenciales**.

## 2. Prompting: técnica e iteración

Hay diez iteraciones registradas en [`iteraciones.md`](iteraciones.md). Tres
reglas hicieron que valiera la pena registrarlas: un cambio por iteración, la
expectativa escrita **antes** de correr, y nunca concluir con n=1.

Dos intervenciones sobre C1, el caso base:

| Etapa | `confidence` media | `open_ticket` presente |
|---|---|---|
| Baseline, 3 ejemplos | 0,614 | **0 de 7** |
| + un cuarto ejemplo | 0,750 | 1 de 3 |
| + una regla de desambiguación en prosa | **0,838** | **4 de 4** |

**La iteración 7 es la que conviene leer, porque fracasó.** Se agregó un quinto
ejemplo para enseñar una regla de precedencia entre categorías; el resultado fue
negativo, 0 de 4. El modelo nunca percibió esas consultas como multi-categoría,
así que la regla no tenía condición de disparo y jamás se activó. La precedencia
se descartó por una regla de intención principal —clasificar por lo que el
cliente quiere resolver— que pasó 3 de 3.

Esa iteración levantó además un riesgo que hay que declarar: ya se habían
corregido dos expectativas de test después de ver resultados. Es legítimo cuando
la especificación estaba mal, pero **si cada test que falla se reinterpreta como
error de especificación, los tests dejan de ser evidencia.** Desde entonces esos
casos se deciden respondiendo una pregunta de dominio **sin mirar la salida del
modelo**, y dejando constancia escrita del motivo.

## 3. Parámetros, justificados por medición

`TEMPERATURE` arrancó en 0.7, el default de fábrica. La iteración 8 lo bajó a
0.2, prediciendo menor dispersión en `confidence`.

**El resultado fue negativo.** C1 devolvió los mismos cuatro valores con las dos
configuraciones —0,80, 0,85, 0,85, 0,85—, media y rango idénticos. Los ejemplos
few-shot ya habían colapsado la distribución de salida, así que el parámetro de
muestreo no tenía margen para actuar. Se conserva 0.2 porque no cuesta nada,
pero como **decisión de bajo impacto medido**, no como una mejora.

Esa iteración expuso también un agujero del método. Las anteriores usaban
`tokens_prompt` como control: si no se movía lo previsto, el prompt nuevo no se
había cargado. La temperatura no toca el prompt, así que **el negativo genuino es
la misma evidencia que produciría un cambio mal aplicado.** Los parámetros que no
dejan huella en la salida necesitan una lectura explícita de la configuración
efectiva.

`MAX_TOKENS` es 300, fijado tras medir que una respuesta completa ocupa entre 80
y 100 tokens de salida.

## 4. Métricas

`metrics.csv` registra una fila por llamada. Los conteos salen de
`response.usage` —lo que OpenAI factura—, nunca de una estimación, y eso es lo
que hace auditables los costos. `tiktoken` solo se usa para medir prompts sin
gastar llamadas; su fórmula de envoltura, incluidos los nombres de rol, coincidió
con `prompt_tokens` **exacto en 7 de 7** llamadas reales.

| | `metrics.csv`, filas con `source=cli` | Fase exploratoria |
|---|---|---|
| n | 29 | 24 |
| Costo por consulta, media | $0,00023058 | — |
| Latencia, mediana | **1709 ms** (p25 1595, p75 2225) | 2486 ms (p25 2281, p75 3335) |
| Rango | 1078 – 4411 ms | hasta 23703 ms |

La columna `source` distingue las corridas de la CLI de las que produce la
interfaz web, para que estos números se sigan recalculando con un filtro en vez
de exigir un archivo congelado.

**Son dos poblaciones distintas y solo la primera es auditable.** Los valores de
la fase exploratoria se transcribieron a mano desde la terminal durante las
iteraciones 1 a 9, antes de que `metrics.py` existiera; se conservan en
[`iteraciones.md`](iteraciones.md) porque las conclusiones que se sacaron de
ellos forman parte del registro. Todo lo que reporta el CSV commiteado se puede
recalcular desde el propio archivo, que es el estándar que sostiene el resto de
este informe.

La latencia produjo además dos afirmaciones que hubo que corregir. Una medición
de 23703 ms se reportó antes de repetirla; tres repeticiones dieron ~2100 ms.
Después se afirmó una separación limpia entre régimen frío y tibio, y se retiró:
con n=24, cinco de siete llamadas frías caían dentro del rango de las tibias. Lo
que sobrevive es que los valores extremos aparecen solo en primeras llamadas.

## 5. Few-shot contra zero-shot

Las dos plantillas son idénticas salvo el bloque de ejemplos: exactamente **586
tokens**, verificados como control en las cuatro consultas que llegaron al
modelo. Cinco consultas × dos plantillas × tres corridas.

| | Few-shot | Zero-shot |
|---|---|---|
| Consultas que pasan | **4 de 5** | 3 de 5 |
| JSON válido del contrato | 15 de 15 | 15 de 15 |
| Costo medio | $0,00026706 | $0,00017656 |
| **Lo que cuesta la técnica** | **+51,3%** | baseline |

**La hipótesis se confirmó: el zero-shot se degrada en `confidence`, no en
`category`.** Las categorías fueron correctas en las 24 llamadas. La única
diferencia apareció en C2, la consulta deliberadamente ambigua, donde el
zero-shot devolvió exactamente `0.5` tres veces sobre tres — el punto medio al
que se va un estimador sin información. Las dos plantillas describen las bandas
con idéntica prosa; solo el few-shot las ancla a casos con números, y ahí
devuelve 0,20.

**Una predicción falló, y pesa más que la que se cumplió.** Se esperaba que el
zero-shot corriera riesgo de contestar en prosa y romper el contrato. No ocurrió
nunca: 30 de 30 válidas. El formato lo sostiene
`response_format={"type": "json_object"}` a nivel de la API, no el prompt.

Eso matiza la justificación original. Se eligió few-shot argumentando que el
problema era conformidad de esquema y no dificultad de razonamiento; la
conformidad de esquema resulta estar cubierta por un parámetro de la API. **Lo
que los ejemplos compran es calibración** — a $0,00009 extra por consulta, un
precio razonable por el único campo del contrato que expresa incertidumbre.

## 6. Seguridad

Tres capas sobre amenazas **disjuntas**: heurísticas locales de inyección, el
endpoint de moderación, y una instrucción en el propio prompt.

La disjunción está medida. El caso de prueba C5, una inyección, vuelve de
moderación **sin marcar y sin ninguna categoría** — su contenido no es dañino,
solo intenta cambiar lo que el programa hace; la documentación de OpenAI confirma
que la inyección no está entre las 13 categorías. A la inversa, un mensaje de
acoso no contiene ningún patrón de inyección.

La capa 1 **normaliza antes de comparar**: minúsculas, descomposición Unicode NFD
descartando las marcas combinantes, y colapso de espacios. Unicode puede escribir
"á" de dos formas visualmente idénticas y distintas entre sí, así que a un
atacante le basta elegir la que un filtro literal no conoce. Medido: **16 de 16**
variaciones triviales bloqueadas, **0 de 6** consultas legítimas. Una consulta
bloqueada devuelve los mismos cuatro campos, sale con código 0, y se registra en
un log aparte — nunca se envió, así que no tiene tokens, latencia ni costo.

## 7. Limitaciones

**C2 sigue fallando parcialmente**, 5 de 7 correctas: el modelo reconoce en el
`answer` que falta información y a veces escala en vez de preguntar. Una regla en
prosa lo llevó de 0 de 4 a 3 de 4, y se conserva como arreglo parcial — dar por
resuelto un 3 de 4 sería acomodar el criterio al resultado.

**Alucinación blanda**, siete apariciones: referencias a un "departamento de
recursos humanos" o a "las políticas de reembolso". Nunca datos duros como montos
o saldos, pero sí documentos y áreas presupuestos.

**Las heurísticas cambian falsos positivos por cobertura** y no pueden minimizar
las dos cosas; la capa 3 es la contención. **Los vocabularios están duplicados**
entre el prompt y `json_validator.py`, porque un prompt es texto y no código.

---

*Uso de herramientas de IA durante el desarrollo, y cómo influyó en las
decisiones técnicas: [`uso_de_ia.md`](uso_de_ia.md).*
