# Streaming Early-Stop: Zero-API Replay Demo

> Public demo (v0.1) · CC BY 4.0. Data: `data/g4_items.json` (40 real-abort validation items; ids/hashes/statistics only;
> no problem text, prompt, raw output or private paths). The private raw archive is **not distributed**.
> One model, one run, small sample; estimates are marked *est*; no performance/accuracy claim.

## What to run

```bash
python code/streaming_early_stop_demo.py --json
python code/streaming_early_stop_demo.py --report
```

## Replay cases (sanitized)

- `math-hendrycks:mirror-full-12500:1219` — predicted trigger=True, stop_step=0, actual_aborted=True, consistent=True
- `math-hendrycks:mirror-full-12500:4433` — predicted trigger=True, stop_step=3, actual_aborted=True, consistent=True
- `gsm8k:test:1002` — predicted trigger=False, stop_step=None, actual_aborted=False, consistent=True

## How to read

- A **triggered** item is a case where a definite contradiction was found; the validator would stop.
- `consistent=True` means the deterministic replay and the real-abort record agree on trigger/stop position.
- **Do not** infer overall token/latency savings from one case; see `data/g4_summary.json` for the 200-problem aggregates.
- The full-sample saving is an estimate (**est**), not a business benefit.

## Reproduction boundary

`code/streaming_early_stop_demo.py` replays from the sanitized data in this repository (0 API). The full streaming
collector is reference code; it needs a private raw archive and is outside this package. No raw/problem text is shipped.
