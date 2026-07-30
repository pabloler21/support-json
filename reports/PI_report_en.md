# Support assistant: design, iteration and measurements

*Integrative Project, Module 1 — AI Engineering (Soy Henry).
Spanish version: [`PI_report_es.md`](PI_report_es.md).*

---

## 1. What it does

A support query goes in as free text; a four-field JSON object comes out for an
agent's console: `category`, `answer`, `confidence`, `actions`. One model call
does three jobs — classify, draft, recommend.

There are **two entry points** — a CLI and an HTTP endpoint with a web console —
and neither holds logic of its own: both translate into
`pipeline.answer_query()` and translate back. A `RuntimeError` is exit code 1 for
the CLI and HTTP 502 for the API. Because the order of the steps exists once,
the two cannot contradict each other: a blocked query returns the same four
fields, with exit code 0 and with HTTP 200.

The architecture follows one idea: **each module is a boundary that receives
something less trustworthy and returns something more trustworthy.** After
`json_validator`, `category` *cannot* hold an arbitrary value, which is what lets
everything downstream stop defending itself. Two invariants carry the weight:
`openai_client.py` is the only module that reaches out to the network, and no
module holding logic imports it at module level — which is why all **88 tests
run offline**.

## 2. Prompting: technique and iteration

Ten iterations are logged in [`iteraciones.md`](iteraciones.md). Three rules made
them worth logging: one change per iteration, the expected result written *before*
running, and never concluding from n=1.

Two interventions on C1, the base case:

| Stage | Mean `confidence` | `open_ticket` present |
|---|---|---|
| Baseline, 3 examples | 0.614 | **0 of 7** |
| + a fourth example | 0.750 | 1 of 3 |
| + a prose disambiguation rule | **0.838** | **4 of 4** |

**Iteration 7 is the one worth reading, because it failed.** A fifth example was
added to teach a category-precedence rule; the result was negative, 0 of 4. The
model never perceived those queries as multi-category, so the rule had no trigger
condition and never fired. Precedence was discarded for a primary-intent rule —
classify by what the customer wants resolved — which passed 3 of 3.

It also raised a risk worth stating: two test expectations had been corrected
after seeing results. That is legitimate when the specification was wrong, but
**if every failing test is reinterpreted as a spec error, tests stop being
evidence.** Such cases are now settled by answering a domain question without
looking at the model's output, with the reason recorded.

## 3. Parameters, justified by measurement

`TEMPERATURE` began at the vendor default of 0.7. Iteration 8 lowered it to 0.2,
predicting reduced dispersion in `confidence`.

**The result was negative.** C1 returned the same four values at both settings —
0.80, 0.85, 0.85, 0.85 — identical mean and range. The few-shot examples had
already collapsed the output distribution, leaving the sampling parameter nothing
to do. 0.2 is kept because it costs nothing, but as a **decision of measured low
impact**, not an improvement.

That iteration also exposed a hole in the method. Earlier iterations used
`tokens_prompt` as a control: if it did not move as predicted, the new prompt had
not loaded. Temperature does not touch the prompt, so **the genuine null result
is the same evidence a failed edit would produce.** Parameters that leave no trace
in the output need an explicit read of the effective configuration instead.

`MAX_TOKENS` is 300, set after measuring that a complete answer runs 80–100
completion tokens.

## 4. Metrics

`metrics.csv` records one row per call. Token counts come from `response.usage` —
what OpenAI bills — never from an estimate, which is what makes costs auditable.
`tiktoken` only sizes prompts without spending a call; its framing formula,
including role names, matched `prompt_tokens` **exactly on 7 of 7** real calls.

| | `metrics.csv`, rows with `source=cli` | Exploratory phase |
|---|---|---|
| n | 29 | 24 |
| Cost per query, mean | $0.00023058 | — |
| Latency, median | **1709 ms** (p25 1595, p75 2225) | 2486 ms (p25 2281, p75 3335) |
| Range | 1078 – 4411 ms | up to 23703 ms |

The `source` column separates CLI runs from the ones the web interface
produces, so these figures stay recomputable with a filter rather than needing
a frozen file.

**The two columns are different populations and only the first is auditable.**
The exploratory figures were transcribed by hand from terminal output during
iterations 1 to 9, before `metrics.py` existed; they are preserved in
[`iteraciones.md`](iteraciones.md) because the conclusions drawn from them are
part of the record. Everything the committed CSV reports can be recomputed from
the file itself, which is the standard the rest of this report holds to.

Latency also produced two corrected claims. A reading of 23703 ms was reported
before being repeated; three reruns gave ~2100 ms. Later, a clean split into cold
and warm regimes was asserted and withdrawn: at n=24, five of seven cold calls
fell inside the warm range. What survives is that the extreme values appear only
in first-of-batch calls.

## 5. Few-shot versus zero-shot

The templates are identical except for the examples block — exactly **586
tokens**, verified as the control on all four queries that reached the model.
Five queries × two templates × three runs.

| | Few-shot | Zero-shot |
|---|---|---|
| Queries passed | **4 of 5** | 3 of 5 |
| Valid contract JSON | 15 of 15 | 15 of 15 |
| Mean cost | $0.00026706 | $0.00017656 |
| **Cost of the technique** | **+51.3%** | baseline |

**The hypothesis held: zero-shot degrades on `confidence`, not `category`.**
Categories were correct across all 24 calls. The only difference was C2, the
deliberately ambiguous query, where zero-shot returned exactly `0.5` three times
out of three — the midpoint an estimator reaches for with no information. Both
templates describe the bands in identical prose; only few-shot anchors them to
numbered cases, and there it returns 0.20.

**One prediction was wrong, and it matters more.** Zero-shot was expected to risk
answering in prose and breaking the contract. It never did: 30 of 30 valid.
Format is held by `response_format={"type": "json_object"}` at the API level, not
by the prompt.

That qualifies the original justification. Few-shot was chosen arguing the problem
was schema conformance rather than reasoning difficulty; schema conformance turns
out to be covered by an API parameter. **What the examples buy is calibration** —
at $0.00009 extra per query, a reasonable price for the only contract field that
expresses uncertainty.

## 6. Security

Three layers over **disjoint** threats: local injection heuristics, the moderation
endpoint, and an instruction in the prompt.

Disjointness is measured. Test case C5, an injection, comes back from moderation
**unflagged with no category set** — its content is not harmful, it only tries to
change what the program does; OpenAI's documentation confirms injection is not
among the 13 categories. Conversely, a harassing message contains no injection
pattern.

Layer 1 **normalises before matching**: lowercase, Unicode NFD with the nonspacing
marks dropped, collapsed whitespace. Unicode can spell "á" two visually identical
but unequal ways, so an attacker need only pick the form a literal filter does not
know. Measured: **16 of 16** trivial variations blocked, **0 of 6** legitimate
queries. A blocked query returns the same four fields, exits 0, and is recorded in
a separate log — it was never sent, so it has no tokens, latency or cost.

## 7. Limitations

**C2 still fails partially**, 5 of 7 correct: the model recognises in the `answer`
that information is missing, then sometimes escalates instead of asking. A prose
rule moved it from 0 of 4 to 3 of 4, and it is kept as a partial fix — counting
3 of 4 as resolved would be fitting the criterion to the result.

**Escalation drags the category with it**, from the same cause. A battery of
eight tickets run against the endpoint scored 7 of 8; the failure asks to speak
to a supervisor about a billing problem and comes back as `other` instead of
`billing`. `other` is the only category the prompt binds to a mandatory action,
so the model applies that pair backwards: it picks escalation and pulls the
category along. **It returns that with `confidence` 0.90**, above cases it gets
right — the calibration does not catch this error.

It was left unfixed for a methodological reason: changing the prompt now would
mean replicating the rule in the zero-shot template, and would still leave
section 5's comparison measured against a prompt that no longer exists. **Going
from 7 to 8 out of eight is not worth invalidating the report's central
finding.**

**Soft hallucination**, seven occurrences: references to a "human resources
department" or "the refund policy". Never hard data such as amounts or balances,
but presupposed documents and teams.

**The heuristics trade false positives for coverage** and cannot minimise both;
layer 3 is the backstop. **The vocabularies are duplicated** between the prompt
and `json_validator.py`, because a prompt is text and not code.

---

*Use of AI tools during development, and how it shaped technical decisions:
[`uso_de_ia.md`](uso_de_ia.md).*
