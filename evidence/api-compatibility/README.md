# Sanitized API compatibility evidence (2026-11-20)

This directory contains **sanitized per-call metadata** from the 40-question × 3-protocol observations in:

- Issue: https://github.com/deepseek-ai/DeepSeek-V3/issues/1781
- Report: https://doi.org/10.5281/zenodo.24269158

## Files

| File | Content |
|---|---|
| `api_protocol_records.sanitized.jsonl` | 120 per-call records: protocol, dataset, problem id, prompt/answer SHA256, status, usage, finish reason, latency, stream-event count, terminator flag |
| `failures.csv` | The 8 failed calls (5 Responses + 3 Anthropic), same fields, human-readable |
| `summary.json` | Aggregate per-protocol results copied from the report |

## What is intentionally omitted

- prompt text / problem statements / reference answers;
- raw model outputs;
- API keys;
- local paths and internal IDs.

`problem_id` is the public dataset row identifier; `*_sha256` values are hashes, not content.

## What can be checked

- 5/40 Responses calls without `response.completed` (4 `EMPTY_TEXT`, 1 `STREAM_INCOMPLETE`);
- 3/40 Anthropic calls with `finish_reason=max_tokens`, `output_tokens=2000`, visible text empty;
- all 8 failures are MATH questions;
- failed Responses calls have `stream_events ≈ 2008` and `usage=0`;
- per-call timings and first-token values.

The experiment was single-model, single-run, 40 questions per protocol; it is not a benchmark.
