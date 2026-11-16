# -*- coding: utf-8 -*-
"""Offline tests for the self-contained replay demo (0 API)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
import streaming_early_stop_demo as demo  # noqa: E402


def test_load_items_has_ids_and_flags():
    items = demo.load_items()
    assert len(items) == 40
    assert all("id" in x and "id_sha256" in x for x in items)
    assert not any(any(k in x for k in ("problem", "question", "answer", "prompt", "raw")) for x in items)


def test_load_summary_has_expected_metrics():
    s = demo.load_summary()
    assert s["arm_b_simulation"]["triggered_items"] == 11
    assert s["arm_b_simulation"]["items"] == 200
    assert abs(s["arm_b_simulation"]["token_saved_fraction_all_items_est"] - 0.0236) < 1e-9


def test_pick_cases_prefers_triggered():
    items = demo.load_items()
    cases = demo.pick_cases(items, 3)
    assert len(cases) == 3
    assert any(x["predicted_triggered"] for x in cases)


def test_replay_and_report_no_raw_text():
    rep = demo.replay(demo.pick_cases(demo.load_items(), 3))
    assert rep["cases"] and rep["consistent"] >= 0
    text = demo.render_report(demo.pick_cases(demo.load_items(), 3))
    assert "| id | trigger |" in text
    assert "raw" not in text.lower() or "raw archive is not distributed" in text.lower()


def test_missing_data_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        demo.load_items(tmp_path / "missing.json")


def test_cli_json(capsys):
    rc = demo.main(["--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "arm_b_simulation" in data["summary"] or "triggered_items" in data["summary"]
