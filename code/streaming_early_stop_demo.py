#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-API replay demo for streaming early-stop (public release v0.1).

Reads only sanitized aggregate data bundled in ../data (ids/hashes/statistics; no problem text,
prompt, raw model output, customer data or private paths). No network; no API key.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_items(path: Path | None = None) -> list[dict]:
    p = path or DATA / "g4_items.json"
    if not p.is_file():
        raise FileNotFoundError(f"sanitized data not found: {p.name}")
    obj = json.loads(p.read_text(encoding="utf-8"))
    items = obj.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("g4_items.json has no items")
    return items


def load_summary(path: Path | None = None) -> dict:
    p = path or DATA / "g4_summary.json"
    if not p.is_file():
        raise FileNotFoundError(f"sanitized data not found: {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


def pick_cases(items: list[dict], n: int = 3) -> list[dict]:
    """Pick triggered/consistent cases first, then non-triggered consistent cases."""
    triggered = [x for x in items if x.get("predicted_triggered") and x.get("consistent")]
    rest = [x for x in items if not (x.get("predicted_triggered") and x.get("consistent"))]
    out = (triggered + rest)[:max(0, n)]
    if not out:
        raise ValueError("no replay cases")
    return out


def replay(cases: list[dict]) -> dict:
    rows = []
    for x in cases:
        rows.append({
            "id": x["id"],
            "predicted_triggered": bool(x.get("predicted_triggered")),
            "predicted_stop_step_index": x.get("predicted_stop_step_index"),
            "actual_aborted": bool(x.get("actual_aborted")),
            "consistent": bool(x.get("consistent")),
        })
    return {
        "cases": rows,
        "triggered": sum(1 for x in rows if x["predicted_triggered"]),
        "consistent": sum(1 for x in rows if x["consistent"]),
    }


def summary_text(summary: dict | None = None) -> str:
    s = summary or load_summary()
    arm = s.get("arm_b_simulation") or {}
    return (
        f"triggered={arm.get('triggered_items')}/{arm.get('items')} "
        f"({arm.get('trigger_rate', 0) * 100:.1f}%), "
        f"token saving est={arm.get('token_saved_fraction_all_items_est', 0) * 100:.2f}%, "
        f"latency saving={arm.get('latency_saved_fraction_all_items', 0) * 100:.1f}%, "
        f"mis-stop={arm.get('false_stop_count')}/{arm.get('triggered_items')}"
    )


def render_report(cases: list[dict], summary: dict | None = None) -> str:
    rep = replay(cases)
    lines = ["## Public replay (sanitized data)", "", summary_text(summary), "", "| id | trigger | stop_step | consistent |", "|---|---:|---:|---:|"]
    for x in rep["cases"]:
        lines.append(f"| {x['id']} | {x['predicted_triggered']} | {x['predicted_stop_step_index']} | {x['consistent']} |")
    lines += ["", "The private raw archive is not distributed; these rows are ids/statistics only."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Streaming early-stop zero-API replay (sanitized data)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--report", action="store_true", help="Markdown replay report")
    ap.add_argument("--n", type=int, default=3)
    args = ap.parse_args(argv)
    try:
        items = load_items()
        summary = load_summary()
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {exc}")
        return 1
    cases = pick_cases(items, args.n)
    if args.json:
        print(json.dumps({"summary": summary.get("arm_b_simulation", {}), "replay": replay(cases)}, ensure_ascii=False, indent=2))
    elif args.report:
        print(render_report(cases, summary), end="")
    else:
        print(summary_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
