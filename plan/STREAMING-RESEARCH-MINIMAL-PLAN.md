# Minimal Research Plan: Streaming Early-Stop

> Public plan v0.1 · CC BY 4.0. Based on a single-model, 200-problem run (one run, small sample).
> Costs are call/token orders, **not prices**; no GPU is required. No accuracy/SOTA/benefit claim.

## Question

Can a step-level verifier safely stop a streaming mathematical derivation on a **definite contradiction**, and
what does that stop cost? The measurable objects are trigger rate, estimated token/latency saving, mis-stop rate
and replay consistency.

## Minimal assets

| Asset | Minimal reproduction | Already reported |
|---|---|---|
| Streaming collector | 200-problem single-model streaming run, resumable, hard API budget | yes |
| Step judge | reuse a coverage-v2-style step judge; four decisions ALLOW/WARNING/REVIEW/BLOCK | yes |
| Early-stop simulation | offline replay from time series (0 API) | yes |
| Real-abort validation | 40 real stream-abort trials + 0-API replay check | yes |
| Sample | 200 problems (GSM8K 100 + MATH 100), frozen seed | yes |
| Writing/evidence | 1 workshop note/technical report (4–8 pages) | template in this package |

## Cost (order of magnitude; no prices)

| Plan | API calls | tokens | time | GPU | output |
|---|---:|---:|---|---|---|
| Reproduce from aggregates | 0 | 0 | hours | no | stats/figures |
| 50-problem sanity run | ~50 (+~10 abort) | ~66k | half day | no | sanity check |
| **Same-scale minimum** | **244** | **265,359** | **1–2 days** | **no** | workshop note/tech report |
| +1 model | +~200 | +~265k | +1 day | no | cross-model comparison |
| +protocols/larger sample | +120 and up | sample-dependent | +2–5 days | no | robustness |
| Human audit | no API | no tokens | human hours | no | gold-standard mis-stop |

## 1–2 day execution

- Day 1: confirm local archive access; run the 200-problem streaming collector (or replay from existing aggregates);
  simulate early stop; run 40 real-abort trials and the 0-API replay check.
- Day 2: recompute statistics/figures; write a 4–8 page note; run the public safety check; archive with DOI.

## Boundaries

Single model/single run/small sample; token positions are estimated from usage × character ratio (*est*); answer
consistency ≠ correctness; stop only on definite BLOCK; REVIEW/UNKNOWN must remain review signals; the observed
REVIEW-stop counterexample (89.4% mis-stop in a sensitivity check) is why. Do not report prices unless an
independently verifiable quote exists.
