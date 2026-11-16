# Could Streaming Verification Stop Earlier? A Small Reproducible Study

> **Public draft v0.1 · 2026-11-16 · CC BY 4.0.** Independent observation; AI-assisted editing of the author's
> own experiment records. **Not a peer-reviewed paper; no novelty/first/SOTA/accuracy claim.**
> Single model, single run, small sample. All cost figures are small-sample estimates, not prices.
> No problem text, prompts, raw model output, customer data or private paths are included.

## 1. Summary

This note asks a narrow engineering question: when a model is generating a step-by-step mathematical
derivation, can a verifier stop generation as soon as it sees a **definite contradiction** — and what does
that early stop cost? We report a minimal, reproducible experiment (200 problems; one model; one run) plus
engineering observations from compatible streaming APIs. The contribution is the **question, a small
measurement protocol, honest boundaries, and open assets** — not a full research programme.

## 2. Minimal evidence: streaming early-stop (G4)

- **Sample**: 200 problems (GSM8K 100 + MATH 100; fixed seed), one model, one run, streaming with usage.
- **Rule**: stop only on a definite contradiction (BLOCK); REVIEW/UNKNOWN are *not* stop signals.
- **Trigger rate**: 11/200 = **5.5%**; triggered-item average estimated saving **569.9 tokens** and
  **574.8 ms**, stopping at **60.1%** of characters on average.
- **Full-sample estimated saving**: **2.36% tokens / 2.2% latency** (only 5.5% trigger, so the average is
  diluted). Token positions are estimated from usage × character ratio and marked *est*.
- **Mis-stop**: **0/11** by definition (stopping only on definite BLOCK does not turn BLOCK into non-BLOCK);
  this is **not** a claim that the system never mis-stops. A hypothetical “stop on REVIEW/UNKNOWN” rule
  would trigger 52% and mis-stop 89.4% (93/104) — evidence for keeping REVIEW/UNKNOWN out of the stop rule.
- **Implementation replay**: 40 real stream-abort trials match the offline deterministic replay **40/40**;
  re-generation under the same settings matches 37/40 (92.5%, endpoint generation variation).

**Read this as**: a small, honest measurement of a narrow compromise. It does not establish general benefit,
model quality or deployment readiness.

## 3. Engineering observations A–E (compatible APIs)

A small 40-problem × 3-protocol comparison (120 calls; same prompt/parameters; single model, single run) was
run as an engineering check, not a benchmark. All protocols returned HTTP success; the differences below are
about stream semantics and accounting.

### Observation A — Responses-style termination

5/40 Responses calls did not deliver a completion event (4 empty visible text, 1 incomplete stream; all MATH).
No usage or explicit stop reason was available for those calls. **Suggestion**: always emit a terminal event
with a reason and usage when available, and document when it may be absent.

### Observation B — Anthropic-style thinking vs output budget

3/40 Anthropic-compatible calls had empty visible text with `finish_reason=max_tokens` and output budget
exhausted, preceded by many reasoning/thinking deltas; 1 further call had visible text but no parsable answer.
**Suggestion**: document thinking defaults/counting and support an explicit disable/separate cap.

### Observation C — Usage semantics differ

Average input+output tokens per call were ≈**1150+137.9 / 1029+580.9 / 177+881.9** for the three protocols.
These counts are **not directly comparable** because system-prompt/cache/thinking accounting differs.
Cross-protocol cost comparisons need clarified semantics, not raw totals.

### Observation D — First-visible-token latency

Mean latency was **1.29 / 5.30 / 5.44 s**, and first-visible-text token mean **0.65 / 4.21 / 4.51 s**
(the latter protocols may emit reasoning deltas before visible text). These are **not** cross-protocol speed
rankings; they reflect different event definitions.

### Observation E — Research suggestion: structured step events

For “verifiable AI” pipelines, structured **step-boundary events / JSON partial streams** would let a
validator safely stop on definite contradictions. In the streaming experiment above: trigger 5.5%,
full-sample estimated token saving 2.36%, mis-stop 0/11 when stopping only on BLOCK. This is an optional API
capability; it does not require changing existing semantics.

## 4. Call for Collaboration

The author cannot carry this to a full study alone. Capable teams are invited to take any of these questions:

1. **When is early stop safe?** What signal separates a definite contradiction from “not verifiable yet”?
2. **Does it generalise?** Multi-model, cross-provider, non-math tasks, larger and more diverse samples.
3. **What is the human-audited cost of mis-stop?** Define “a repairable derivation” and measure truncation loss.
4. **What is the end-to-end latency benefit?** Online early stop, structured step events, and UI/stream semantics.

Suggested budget (based on the reported run; no prices):

| Plan | API calls | tokens (order) | time | GPU | output |
|---|---:|---:|---|---|---|
| Reproduce analysis from existing aggregates | 0 | 0 | hours | no | recompute stats/figures |
| Small sanity run (50 problems) | ~50 (+~10 abort) | ~66k | half day | no | sanity check, wide error bars |
| **Minimum publishable (same scale)** | **244** | **265,359** | **1–2 days** | **no** | workshop note/tech report |
| Add one model | +~200 | +~265k | +1 day | no | cross-model differences |
| Add protocols/larger sample | +120 and up | sample-dependent | +2–5 days | no | protocol robustness |
| Human audit | no API | no tokens | human hours | no | gold-standard mis-stop |

Expected outputs: a 4–8 page workshop note/technical report, reproducible code, and an honest
limitations/data card. Contact: open an issue/discussion in the public repository; author metadata is in
`CITATION.cff` (no email published in this package).

## 5. Boundaries and data availability

- **Single model, single run, 200 problems** for the early-stop experiment; 40 problems × 3 protocols for the
  engineering observations. No multi-model/cross-provider/human-audit claims.
- Token positions are **estimated** (*est*) from usage × character ratio; not per-token timestamps.
- Answer consistency is measured against reference answers without full human verification; consistent ≠ correct.
- No problem text, prompts, raw model outputs, customer data or private paths are distributed. `data/` contains
  only sanitized aggregates/IDs/hashes/decisions; `raw` and the private archive are not included.
- Responses/Anthropic observations are engineering notes, not protocol rankings; production path remains
  `chat/completions`; no model-quality or performance claim.
- Code MIT; report/data CC BY 4.0. Cite via `CITATION.cff`; DOI placeholder until a DOI exists.
