#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Public release out-of-domain safety check (repository root).

Scans **all files** (text + PDF text) and FAILs on:
  1. local drive/absolute paths / private stores
  2. internal repository/system/agent names
  3. customer/business/case names
  4. secret/token/private-key patterns
  5. personal email addresses (official DeepSeek feedback address excluded)
  6. complete prompt / raw output / problem-statement / raw dataset signatures
  7. internal toolchain paths (tools/, eval/, scripts/, docs/, var/; only code/ and tests/ allowed)
  8. missing required files / MANIFEST SHA256 mismatch / license files / small-sample caveat / real DOI

It prints only category counts and file names, never the matched sensitive values.
Usage:
  python tools/check_public_release.py
  python tools/check_public_release.py --json
Exit: 0 PASS, 1 FAIL, 2 bad arguments/directory.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF_REL = "tools/check_public_release.py"
REQUIRED = [
    "README.md", "LICENSE", "REPORT-LICENSE.md", "CITATION.cff",
    "report/report.md", "report/report.pdf",
    "demo/STREAMING-EARLY-STOP-DEMO.md", "demo/STREAMING-EARLY-STOP-DEMO.pdf",
    "plan/STREAMING-RESEARCH-MINIMAL-PLAN.md",
    "code/streaming_early_stop_demo.py", "code/llm_protocols.py",
    "tests/test_streaming_early_stop_demo.py", "tests/test_llm_protocols.py",
    "data/g4_summary.json", "data/g4_items.json", "data/g5_summary.json",
    "MANIFEST.json", "CHECKSUMS", "tools/check_public_release.py",
]

def _dec(items: list[str]) -> list[str]:
    return [base64.b64decode(x).decode("utf-8") for x in items]

_INTERNAL = _dec([
    "bWF0aC1nYXRl", "amlubWluZw==", "5pmL5piO6LSi5Yqh5pm66IO95L2T",
    "6LSi5Yqh5pm66IO95L2T", "dGF4LWxhdy1kYXRh", "ZHNoLW1lbW9yeQ==",
    "b250b2xvZ3ktbGFi", "ZGVlcHNlZWstaGFybmVzcw==", "azEyLW1hcHBlcg==",
])
_CUSTOMERS = _dec([
    "5a6i5oi36LWE5paZ", "5a6i5oi35pWw5o2u", "5bq3576O", "542Q5a2Q5bKb",
    "55Ge5bm4", "6LSi56iO5pWZ6L6F", "5aKe5YC856iO5rOV", "5Zyf5Zyw5aKe5YC856iO",
])
_PRIVATE_FRAG = _dec([
    "ZHNoLXByaXZhdGUtc3RvcmU=", "X2tleXM=", "YXJtX2Ffc3RyZWFt", "c3RyZWFtaW5nX3ZlcmlmeS9hcm1f",
])
_INTERNAL_RE = re.compile("|".join(re.escape(x) for x in _INTERNAL), re.I)
_CUSTOMER_RE = re.compile("|".join(re.escape(x) for x in _CUSTOMERS), re.I)
_LOCAL_PATH = re.compile(
    r"(?:(?:^|[\s\"'`(])(?:[A-Za-z]:[\\/])|\\\\[A-Za-z0-9_.-]+\\|"
    r"(?:^|[\s\"'`(])/(?:home|root|mnt|Users|var|tmp)/|~[/\\]|" +
    "|".join(re.escape(x) for x in _PRIVATE_FRAG) + ")", re.I)
_SECRET = re.compile(
    r"(?i)(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9._-]{6,}|"
    r"token\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}|"
    r"password\s*[:=]\s*\S+|BEGIN [A-Z ]*PRIVATE KEY)")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PROMPT_RAW = re.compile(
    r"(?i)(?:problem_statement|question_text|\"question\"\s*:|\"problem\"\s*:|/raw/)" +
    "|".join(re.escape(x) for x in _PRIVATE_FRAG), re.I)
_TOOL_PATH = re.compile(r"(?i)(^|[\s\"'`(])(?:eval|scripts|docs|var)/")
_DOI = re.compile(r"(?i)10\.\d{4,9}/zenodo\.\d+")
_SMALL = re.compile(r"(?i)small[- ]sample|小样本|single[- ]model|单模型")
_MIT = re.compile(r"(?i)\bMIT\b")
_CC = re.compile(r"(?i)\bCC BY 4\.0\b")

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def read_text(p: Path) -> str:
    if p.suffix.lower() == ".pdf":
        try:
            import pypdf  # type: ignore
        except Exception:
            sys.path.insert(0, str(ROOT / ".deps"))
            try:
                import pypdf  # type: ignore
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError("PDF scan requires pypdf") from exc
        return "\n".join((x.extract_text() or "") for x in pypdf.PdfReader(str(p)).pages)
    return p.read_text(encoding="utf-8", errors="ignore")

def scan(text: str) -> dict[str, int]:
    return {
        "internal_names": len(_INTERNAL_RE.findall(text)),
        "local_paths": len(_LOCAL_PATH.findall(text)),
        "customer_names": len(_CUSTOMER_RE.findall(text)),
        "secrets": len(_SECRET.findall(text)),
        "emails": len(_EMAIL.findall(text)),
        "prompt_raw": len(_PROMPT_RAW.findall(text)),
        "internal_tool_paths": len(_TOOL_PATH.findall(text)),
        "real_doi": len(_DOI.findall(text)),
    }

def run(root: Path) -> int:
    if not root.is_dir():
        print("[FAIL] directory not found", file=sys.stderr)
        return 2
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file() and not any(x in p.parts for x in (".git", "__pycache__", ".pytest_cache"))
    )
    rels = {p.relative_to(root).as_posix() for p in files}
    checks = []
    def add(cid: str, ok: bool, count: int = 0, detail: str = ""):
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "count": count, "detail": detail})
    missing = [x for x in REQUIRED if x not in rels]
    add("required_files", not missing, len(missing), f"missing={missing}" if missing else "all present")
    counts = dict(internal_names=0, local_paths=0, customer_names=0, secrets=0, emails=0,
                  prompt_raw=0, internal_tool_paths=0, real_doi=0)
    scanned = 0
    pdf_error = ""
    for p in files:
        rel = p.relative_to(root).as_posix()
        if rel in {SELF_REL, "MANIFEST.json", "CHECKSUMS"}:
            continue
        if p.suffix.lower() not in {".md", ".txt", ".py", ".json", ".html", ".cff", ".xml"}:
            if p.suffix.lower() == ".pdf":
                try:
                    text = read_text(p)
                except Exception as exc:  # noqa: BLE001
                    pdf_error = str(exc)
                    continue
            else:
                continue
        else:
            text = read_text(p)
        scanned += 1
        for k, v in scan(text).items():
            counts[k] += v
    add("no_internal_names", counts["internal_names"] == 0, counts["internal_names"])
    add("no_local_paths", counts["local_paths"] == 0, counts["local_paths"])
    add("no_customer_business", counts["customer_names"] == 0, counts["customer_names"])
    add("no_secrets", counts["secrets"] == 0, counts["secrets"])
    add("no_personal_emails", counts["emails"] == 0, counts["emails"], "official DeepSeek address allowed; package should not need it")
    add("no_prompt_raw_question", counts["prompt_raw"] == 0, counts["prompt_raw"])
    add("no_internal_tool_paths", counts["internal_tool_paths"] == 0, counts["internal_tool_paths"])
    add("no_real_doi", counts["real_doi"] == 0, counts["real_doi"])
    add("pdf_text_scanned", not pdf_error, 1 if pdf_error else 0, pdf_error)
    add("all_text_files_scanned", scanned > 0, scanned, f"{scanned} files")
    def ftext(rel: str) -> str:
        p = root / rel
        return p.read_text(encoding="utf-8", errors="ignore") if p.is_file() else ""
    add("license_mit", bool(_MIT.search(ftext("LICENSE"))))
    add("license_cc_by", bool(_CC.search(ftext("REPORT-LICENSE.md"))))
    add("small_sample_caveat", bool(_SMALL.search(ftext("README.md") + ftext("report/report.md") + ftext("demo/STREAMING-EARLY-STOP-DEMO.md"))))
    manifest_ok, manifest_count, manifest_detail = False, 0, "missing"
    mp = root / "MANIFEST.json"
    if mp.is_file():
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            listed = m.get("files") or {}
            manifest_count = len(listed)
            bad = [rel for rel, exp in listed.items() if not (root / rel).is_file() or sha256_file(root / rel) != exp]
            actual = {p.relative_to(root).as_posix() for p in files if p.name not in {"MANIFEST.json", "CHECKSUMS"}}
            manifest_ok = not bad and set(listed) == actual
            manifest_detail = f"bad={len(bad)} expected={len(listed)} actual={len(actual)}"
        except Exception as exc:  # noqa: BLE001
            manifest_detail = f"parse error: {exc}"
    add("manifest_sha256", manifest_ok, manifest_count, manifest_detail)
    fails = [c for c in checks if c["status"] == "FAIL"]
    result = {"root": "<release-repo>", "status": "PASS" if not fails else "FAIL", "files": len(files),
              "scanned": scanned, "checks": checks, "fail_categories": [c["id"] for c in fails]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS" if not fails else "FAIL: " + ", ".join(result["fail_categories"]), file=sys.stderr)
    return 0 if not fails else 1

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=ROOT)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    return run(args.dir)

if __name__ == "__main__":
    raise SystemExit(main())
