# Fork Master Plan (xl-converter-fork)

Written 2026-08-23. Planning document only — no source file modified by it.

Supersedes nothing; **extends** [`PNG_ENCODER_MIGRATION_PLAN.md`](PNG_ENCODER_MIGRATION_PLAN.md)
(referred to below as "Plan A"). That file stays the single source of truth for
the pngquant/oxipng migration; its Phase 0–1 are already done with citations.
This master plan adds Track B (a new "Same Format" mode) and organizes both
tracks into quota/session-friendly phases per the owner's instructions.

## Owner constraints (binding, quoted intent)

1. Read CLAUDE.md / AGENTS.md / mcp-local-capabilities.md first — done.
2. Base the modification plan on Plan A — done (Track A = Plan A as-is).
3. Order steps for minimum effort/tokens with maximum effect.
4. Every phase must fit inside one small session (quota + context limits).
5. Split tasks into strictly-ordered groups vs order-independent groups.
6. On conflicting/impossible requirements, constraints 3–4 win.
7. Fork currently identical to upstream (verified below).
8. This plan is written as English markdown into the repo.
9. Research net/local before acting — done; citations inline.

## Verified starting state (this session)

- Local `stable` HEAD = `6fcad3a` and upstream
  `JacobDev1/xl-converter@stable` = `6fcad3a2c39603516e7e49a29230a7f9330f64f5`
  (`git ls-remote`, checked 2026-08-23) — constraint 7 confirmed: zero drift.
- Working tree: tracked files clean vs HEAD; untracked local-only files kept
  by owner decision (AGENTS.md, CLAUDE.md stubs, Plan A, capabilities notes,
  `.serena/`).
- Plan A Phase 0 (housekeeping) and Phase 1 (research/decisions, 5/5 answered
  with citations) are done per its Progress Log. Trust these; re-verify only
  on contradiction (root AGENTS.md session discipline).

## Architecture map (verified touchpoints, file:line)

Everything a new format/mode touches in this codebase:

| Concern | Location | Mechanism |
|---|---|---|
| Format list shown in UI | `ui/tabs/output_tab.py:98-107` | `ComboBox((...))` literal tuple |
| Per-widget show/hide per format | same file, e.g. `:333` | `wm.setVisibleByTag(tag, cond)`; widgets registered with tags via `wm.addWidget(...)` |
| Persisted per-format values | `_saveFormatVars`/`_loadFormatVars` (`output_tab.py:488+`) | `wm.setVar/getVar` per `prev_format` |
| Output extension | `core/pathing.py:72-88` `getExtension()` | returns `None` for modes handled in Worker |
| Compatibility gate | `core/conflicts.py:checkForConflicts` (gif/apng `valid_routines`, multipage TIFF/WebP) | raised from `Worker.runChecks` (`core/worker.py:140-151`) |
| Proxy decision | `core/proxy.py:isProxyNeeded(format, src_ext, jpgli, downscaling)` | called in `setupConversion` |
| Encoder dispatch | `Worker.convert` `match self.params["format"]` (`core/worker.py:245-393`) | one case per display-name format |
| Downscale availability | `ui/tabs/modify_tab.py:277` | format-not-in-tuple check |
| Pool-empty guard | `core/controller.py:107` | only for "Smallest Lossless" |
| Tooltips | `data/tooltips.py` | single `TOOLTIPS` dict keyed by widget tag |
| Test tables | `tests/core/test_pathing.py:131`, `test_proxy.py:23`, `tests/ui/tabs/test_output_tab.py:160`, `test_modify_tab.py:168` | parametrized rows |

Key insight driving Track B's design: if a new mode **resolves itself into an
existing real format string early** (in `runChecks`, before anything downstream
reads `params["format"]`), then extension assignment, conflicts, proxy, encoder
dispatch, metadata args, custom args, and downscaling all behave correctly with
zero further changes. The mode becomes a thin router, not a parallel subsystem.

## Track A — PNG encoder migration

Execute [`PNG_ENCODER_MIGRATION_PLAN.md`](PNG_ENCODER_MIGRATION_PLAN.md)
Phases 2–6 exactly as written there. No content is duplicated in this file.
Its Phase 1 findings (license GO, prebuilt binaries, `--out`/`--output`
flags, metadata default, signal wiring) are the verified inputs for those
phases. Before starting its Phase 2, re-check upstream `stable` hasn't
already shipped an equivalent change (one `git ls-remote` + changelog glance).

## Track B — new mode: "Same Format"

### B.1 What it is (design decided from evidence, not guesswork)

One new entry in "Format / Mode" that accepts **every** supported source and
re-encodes each file **by a per-source-extension routing table**, where each
route is an *existing* pipeline. Output keeps the source extension except
where a route intentionally changes it — this honors both owner statements:
"result ที่เป็นไฟล์สกุลเดิม" as the default, and the explicit example
"jpg → lossless jxl" as a configurable route (Lossless JPEG Transcoding
produces `.jxl`; that extension change is intended and documented).

- Name: `"Same Format"` (terse, matches upstream naming style:
  "Smallest Lossless", "JPEG Reconstruction").
- Alternatives dismissed: "Recompress" (says nothing about format),
  "Keep Original Format" (long; and it *can* change format via routes).
- It is a **router over existing pipelines** — no new encoder code, maximal
  reuse of Plan A's two-stage PNG pipeline once Track A lands.

### B.2 Routing table (v1 defaults)

| Source ext | Default route | Allowed alternates | Output ext |
|---|---|---|---|
| png | `PNG` | (behavior governed by existing `png_encoder` + lossless/quality settings after Track A) | png |
| jpg / jpeg | `JPEG` | `Lossless JPEG Transcoding` (owner's example) | jpg / jxl |
| webp | `WebP` | — | webp |
| avif | `AVIF` | — | avif |
| jxl | `JPEG XL` | — | jxl |
| gif / apng | not routable | — | skipped + logged (conflicts matrix CF0 would reject most targets anyway) |
| anything else | not routable v1 | — | skipped + logged |

Not-routable files are **skipped per-item with a log line** (same mechanism
as "Skip if file exists"), never aborting the batch.

### B.3 Resolution point — the one load-bearing decision

Resolve once, early, then let everything downstream run unchanged:

1. New pure module `core/same_format.py`: `DEFAULT_ROUTES` dict,
   `resolve(src_ext, routes) -> str | None`, input validation. New file =
   zero merge-conflict surface with upstream.
2. Hook at top of `Worker.runChecks` (`core/worker.py:140`): if
   `params["format"] == "Same Format"`: resolved = resolve(...);
   `None` → set `self.skip = True` and return; otherwise overwrite
   `self.params["format"] = resolved`.
3. Everything downstream needs **no edit**: `setupConversion`'s
   `getExtension(resolved)` yields exactly the source ext for same-ext routes;
   conflicts check sees the real target; proxy and encoder dispatch follow.
4. Guard: resolver never returns `"Same Format"` or `"Smallest Lossless"`.

### B.4 Settings/UI (minimal but configurable)

- Add `"Same Format"` to the combo tuple (`output_tab.py:107`).
- When selected, show the **existing generic widgets** (quality slider,
  effort, lossless checkbox) bound to new saved vars `sf_quality`,
  `sf_effort`, `sf_lossless` — the mode carries its own quality state applied
  to whichever lossy route runs (v1 simplification; per-format hydration from
  each format's own saved vars is the documented future extension).
- One route control in v1: `sf_jpeg_route_cmb` = {JPEG, Lossless JPEG
  Transcoding} (the only route with a real choice today). Other routes are
  constants in `core/same_format.py` — adding UI for them later is additive.
- Extend `_saveFormatVars` / `_loadFormatVars` / `getSettings` /
  `resetToDefault` with a `"Same Format"` case; add tag group
  (`"same_format"`) visibility toggles next to `output_tab.py:333`.
- Tooltips: new keys in `data/tooltips.py` for every new control, including
  one explaining that JPEG→LJT changes the extension to `.jxl` on purpose.

- Downscaling: **disabled for this mode in v1** — add `"Same Format"` to the
  tuple at `ui/tabs/modify_tab.py:277` (one line, same treatment as the other
  special modes). Revisit later; per-route resize rules are a separate design.
- Proxy: no code change — `isProxyNeeded` receives the resolved format.

### B.5 Files touched by Track B (complete list)

New: `core/same_format.py`, `tests/core/test_same_format.py`.
Edited: `ui/tabs/output_tab.py` (combo entry, tag group, getSettings/save/
load/reset), `data/tooltips.py` (~4 keys), `core/worker.py` (~8-line hook at
`runChecks` top), `ui/tabs/modify_tab.py` (1 line), parametrized test tables
(`test_modify_tab.py`, `tests/ui/tabs/test_output_tab.py`),
`misc/changelog.md`, `README.md` FAQ note. `core/pathing.py` and
`core/conflicts.py`: **no changes needed** (resolution precedes both).

## Execution order — session-phased (constraints 3–4)

Each phase = one session-sized unit, ≤ ~1 focused sitting. Start each session
by reading only this file + the phase's file set; end it by appending one
Progress Log line. If a phase overruns quota mid-way, stop at its internal
step boundary — steps are sized so partial completion is still a clean state.

**Ordered spine** (each blocks the next; shared files edited in fixed order
to minimize re-reads and conflicts):

| # | Phase | Contents | Files |
|---|---|---|---|
| 1 | A-P2a | `PNGQUANT_PATH` constant + metadata branch (Plan A 2.1–2.2) | constants.py, metadata.py |
| 2 | A-P2b | two-stage PNG pipeline + downscale wrapper (Plan A 2.3–2.5) | worker.py, downscale.py |
| 3 | A-P3 | PNG settings/UI + signal wiring (Plan A Phase 3) | settings_tab.py, output_tab.py, tooltips.py |
| 4 | A-P5 | Track A tests, full pytest green (Plan A Phase 5) | tests/* |
| 5 | B-S1 | `core/same_format.py` + runChecks hook + modify_tab line; manual convert smoke | same_format.py, worker.py, modify_tab.py |
| 6 | B-S2 | Same-Format UI + saved vars + tooltips | output_tab.py, tooltips.py |
| 7 | B-S3 | Track B tests + README/changelog; full pytest green | tests/*, docs |

**Order-independent group** (no deps on each other; drop into any spare
session or parallelize): Plan A Phase 4 packaging items (build scripts,
main.spec, LICENSE_3RD_PARTY pngquant entry — license already cleared in
Plan A Phase 1), changelog entries for Track A.

Verification per phase: the phase's own check (Plan A defines them; B phases:
unit tests for resolver incl. skip/guard paths, one real PNG→PNG and
JPG→route conversion through `Worker`, UI shows/hides correctly) plus full
`pytest` before closing any phase that touched core.

## Merge-friendliness policy (upstream tracking)

Constraint from owner: "ดัดแปลงในแบบที่ง่ายต่อการต่อเติม/บำรุงรักษา" —

- Prefer new files (`core/same_format.py`) over edits to shared ones.
- Shared-file edits stay small and sit at stable anchors (tail of a combo
  tuple, tail of a match, top of a function) so upstream edits elsewhere in
  the file merge cleanly.
- Never reorder/reformat existing upstream lines; never rename upstream
  symbols; match existing style exactly.
- Every Progress Log entry lists touched files → that list is the
  conflict-checklist for the next upstream merge.
- After each future upstream bump: `git ls-remote` diff first, then rebase,
  then full pytest, before resuming any open phase.

## Risks & caveats (flagged, not resolved)

- **Params hydration (B-S2):** with v1's shared `sf_*` quality vars, the
  JPEG route ignores per-format saved quality by design. If that feels wrong
  in practice, the future extension is hydrating from each format's own
  saved vars at resolution time — contained inside `core/same_format.py` +
  one call site.
- **JPEG "lossless" wording:** default jpg route is a *re-encode* (jpegli or
  ImageMagick; visually lossless only at q≈100). The tooltip must not claim
  true losslessness; only the LJT route is bit-exact.
- **Silent skips:** unroutable sources are skipped with a log line; make sure
  the log surfaces in the UI error list so batches don't look silently
  truncated.
- **Upstream drift:** Plan A Phase 1 findings are dated 2026-08-23 against
  `6fcad3a`; re-check before A-P2a if upstream moves.
- **pngquant license** was cleared as GO in Plan A Phase 1 (GPL v3+ dual,
  subprocess aggregation) — keep the LICENSE_3RD_PARTY entry in the same
  phase that first ships the binary.

## Progress Log

(append-only; one line per completed step, every session)
- 2026-08-23: FORK_MASTER_PLAN.md drafted (this file). Evidence gathered via
  serena + git ls-remote this session; no source files modified. Track B
  design decided: thin router resolving into existing pipeline ids at
  runChecks; v1 route table fixed; phases 1–7 defined (spine) + orderless
  packaging group.
- 2026-08-23 23:05 [Session A]: Execution authorized by owner (phase-per-commit,
  judge each phase, no push). Both plan docs committed as baseline.
  Env note: python 3.12 present, NO pytest/PySide6 installed - decision
  deferred to Phase 4 (A-P5).
- 2026-08-23 23:07 [Session A]: Phase 1 (A-P2a) code done + committed —
  `data/constants.py`, `core/metadata.py` (+ checkpoint lines in both plan
  docs).
- 2026-08-23 23:21 [Session A]: Phase 2 (A-P2b) done + committed — two-stage
  PNG pipeline live behind `png_encoder` setting; `core/convert.py`,
  `core/worker.py`, `core/downscale.py`, `tests/core/test_worker.py`.
  Deviation note: pulled the affected test updates into this phase (instead
  of A-P5) to keep the tree green at every commit.
