# Streaming Early-Stop Demo

**Public research release v0.1 · 2026-11-16**

> English below · 中文见后半部分
>
> **Status**: independent, small-sample engineering study; **not** a peer-reviewed paper and **not** a
> performance/accuracy/first/SOTA claim. Single model, single run. All token/latency savings are estimates
> (*est*), not prices or business benefits. No problem text, prompts, raw model output, customer data or
> private paths are included.

## What this is

This repository asks one narrow question: **when a model is streaming a step-by-step mathematical derivation,
can a verifier stop early on a definite contradiction — and what does that stop cost?** It contains a
reproducible minimum report, a zero-API replay demo, a minimal research plan, sanitized aggregate data, and an
open invitation for a capable team to take the question further.

## Layout

| Path | Content |
|---|---|
| `report/report.md` · `report/report.pdf` | Public report: minimal evidence, observations A–E, call for collaboration, boundaries |
| `demo/STREAMING-EARLY-STOP-DEMO.md` · `demo/…pdf` | Zero-API replay demo using sanitized data |
| `plan/STREAMING-RESEARCH-MINIMAL-PLAN.md` | Minimal reproduction plan and call/token budget (no prices) |
| `data/` | Sanitized aggregates/IDs/hashes/decisions only — **no raw, prompts, answers or problem text** |
| `code/` | Self-contained replay demo and protocol adapter (MIT) |
| `tests/` | Offline tests (0 API, no network) |
| `tools/check_public_release.py` | Out-of-domain safety scan (text + PDF); FAILs on internal/path/customer/secret/prompt leaks |
| `REPORT-LICENSE.md` | Report/data license: CC BY 4.0 |
| `LICENSE` | Code license: MIT |
| `CITATION.cff` | Citation metadata (author Yin Kang; affiliation/ORCID intentionally blank) |
| `MANIFEST.json` · `CHECKSUMS` | SHA256 integrity records |

## Quick reproduce (0 API)

```bash
# Replay a few sanitized real-abort cases
python code/streaming_early_stop_demo.py --json
python code/streaming_early_stop_demo.py --report

# Offline tests (pytest; no network/API)
python -m pytest tests/ -q

# Out-of-domain safety scan (needs pypdf for PDF text; otherwise fail-closed)
python tools/check_public_release.py
```

The full streaming collector that produced these aggregates is **not** included as a runnable pipeline because
it needs a private raw archive. The public code is the replay/verification reference; no raw/problem text is
distributed.

## What is in the evidence (small-sample estimates)

- 200 problems (GSM8K 100 + MATH 100), one model, one run.
- Definite-contradiction (BLOCK) trigger: **11/200 = 5.5%**.
- Full-sample token/latency saving: **≈2.36% / 2.2%** (*est*; token positions approximated from usage ×
  character ratio).
- Mis-stop: **0/11** under the “only definite BLOCK” rule (definition-level, not a claim that the system
  never mis-stops); a REVIEW/UNKNOWN-stop sensitivity would trigger 52% and mis-stop 89.4% (93/104).
- Real stream-abort replay consistency: **40/40**.

## Call for collaboration

Four open questions: (1) when is early stop safe; (2) does it generalise across models/providers/tasks;
(3) what is the human-audited cost of mis-stop; (4) what is the end-to-end latency benefit of structured
step events? A minimum publishable run is estimated at **244 API calls / 265,359 tokens / 1–2 days / no GPU**
(orders, not prices). See `report/report.md` §4 for the suggested experiments and expected outputs.

## Boundaries

- Single model, single run, 200-problem small sample; no multi-model/cross-provider/human-audit claim.
- Token/latency savings are **estimated**; answer consistency ≠ correctness; no accuracy/SOTA/benefit claim.
- Stop only on a **definite contradiction**; REVIEW/UNKNOWN must remain review signals.
- Engineering observations about compatible APIs are **not protocol rankings**; the production path remains
  the standard chat-completions route.
- No problem text, prompts, raw model outputs, customer data or private paths. `raw` is not distributed.

## License

- Code: **MIT** — see `LICENSE`.
- Report, demo, plan, data and documentation: **CC BY 4.0** — see `REPORT-LICENSE.md`.

## Citation (DOI placeholder)

```bibtex
@misc{streaming_early_stop_demo_2026,
  title        = {Streaming Early-Stop for Step-Level LLM Verification: A Minimal Reproducible Study},
  author       = {Yin, Kang},
  year         = {2026},
  version      = {v0.1},
  howpublished = {Public research repository},
  note         = {DOI: TBD; single-model/single-run small sample; not a performance claim}
}
```

---

# 中文简介（同一内容）

**公开研究发布 v0.1（2026-11-16）**：本仓是一个**独立的、小样本的工程观察**，不是同行评审论文，也不宣称首发、SOTA、正确率或性能优势；单模型、单次运行，所有 token/延迟节省均为估算（est），不是价格或业务收益。仓内不含题干、提示词、原始模型输出、业务资料或私有路径。

**它是什么**：只问一个窄问题——当模型流式输出数学推导时，验证器能否在**确定矛盾**出现时安全早停，代价是什么？本仓提供最小可复现报告、零 API 回放演示、最小研究计划、脱敏聚合数据，以及给有能力团队的接力邀请。

**最小证据（小样本估算口径）**：200 题（GSM8K 100 + MATH 100）、单模型单次；确定矛盾触发 **11/200=5.5%**；全样本 token/延迟节省 **≈2.36%/2.2%**（est）；只对确定 BLOCK 早停时误停 **0/11**（定义口径，不等于系统永不误停；把 REVIEW/UNKNOWN 也当停止信号的敏感性会带来 52% 触发/89.4% 误停）；40 题真中断回放 **40/40**。

**接力邀请（4 个问题）**：①何时早停才安全；②跨模型/跨厂商/其他任务是否泛化；③人审金标准下误停的真实代价；④结构化步骤事件/在线早停的端到端延迟收益。最小可发表规模约 **244 次 API / 265,359 tokens / 1–2 天 / 无 GPU**（量级，不写价格）。

**边界**：单模型/单次/小样本；token 位置按 usage×字符比例估算（est）；答案一致≠正确；只对确定矛盾早停，REVIEW/UNKNOWN 不早停；兼容协议观察不是性能排序，生产仍用 chat-completions 路径；不发布 raw/题干/密钥/业务资料/私有路径。

**复现**：`python code/streaming_early_stop_demo.py --json`（0 API）；`python -m pytest tests/ -q`；`python tools/check_public_release.py`（出域自检，需要 pypdf 扫描 PDF 文本）。

**许可与引用**：代码 MIT；报告/数据/文档 CC BY 4.0；作者 Yin Kang（单位/ORCID 留空）；引用模板见上（DOI 待填）。
