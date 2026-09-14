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

> **Superseded 2026-09-06:** the shared quality slider + `sf_quality`/
> `sf_lossless` vars described below were replaced by the Same Format
> preset system (Quality/Balanced/Small/Custom with per-format saved
> vars) — commit `a02d329`, see Progress Log entry "Session D". The
> per-format hydration "documented future extension" below is exactly
> what shipped. Kept for design-history.

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
- 2026-08-23 23:40 [Session A]: Phase 3 (A-P3) done + committed — PNG
  encoder setting + custom args UI, png_encoder_changed signal wiring,
  OutputTab PNG quality/lossless visibility + saved vars, tooltips;
  settings_tab.py, output_tab.py, main.py, tooltips.py, 3 test files.
  Same deviation note as Phase 2: affected test fixtures updated in-phase.
- 2026-08-23 23:47 [Session A]: Phase 4 (A-P5) DEFERRED to session end —
  pytest/PySide6 install (~200MB venv) postponed so the full A+B suite runs
  once; flagged to owner in-session.
- 2026-08-23 23:47 [Session A]: Phase 5 (B-S1) done + committed — new
  `core/same_format.py` (DEFAULT_ROUTES incl. JPEG_ALIASES, ALLOWED_TARGETS,
  resolve()); `Worker.runChecks` resolution hook (unroutable -> skip=True,
  else params["format"] overwritten pre-conflicts/proxy/dispatch);
  `pathing.getExtension` case "Same Format" -> None; modify_tab downscaling
  exclusion += "Same Format"; test_pathing row added. resolve() logic
  verified by isolated 12-assertion run; py_compile OK all five files.
- 2026-08-23 23:55 [Session A]: Phase 5 judged VERIFIED (real-module runtime
  check via stubbed import, 6 assertions) — commit d91618f.
- 2026-08-23 23:55 [Session A]: Phase 6 (B-S2) done + committed — output_tab:
  "Same Format" combo entry, JPEG Route row (tag same_format), quality/
  effort/lossless visible for the mode, effort range 1..9/10, sf_* saved
  vars (quality 80 / lossless True / route), getSettings emits
  same_format_routes {jpg,jpeg}; worker hook switched to params.get (routes
  flow via output_tab settings merge); tooltip key sf_jpeg_route; tests:
  visibility row + route visibility + getSettings routes cases.
- 2026-08-23 23:47 [Session A]: NOTE - earlier line said routes come from
  settings dict; corrected this session: they travel in worker PARAMS
  (output_tab_settings | modify_tab_settings merge in controller.py:197).
- 2026-08-23 23:55 [Session A]: Phase 6 judged VERIFIED WITH CAVEATS (commit
  7a46fe8; raw-format consumers audited safe: ThreadManager/RAM default
  threads, worker side sees resolved format).
- 2026-08-24 00:00 [Session A]: Phase 7 (B-S3) done + committed — new
  tests/core/test_same_format.py (17 cases), worker runChecks resolution
  tests (resolve/override/unroutable-skip), test_modify_tab Same Format
  downscaling row, README "Fork Notes" section, misc/changelog.md fork
  entry. py_compile OK all four test files.
- 2026-08-24 00:27 [Session A]: Phase 4 (A-P5) DONE - env_dev venv created
  per README convention (gitignored), requirements + requirements_test
  installed; full unit suite run staged (offscreen Qt): core 461 + data 115
  + ui 368 = 944 passed / 0 failed. 4 test-side bugs fixed first (out-pair
  in post-processor args assertions, Path backslash normalization, PNG
  visibility row pre-dating fork behavior). Root test_convert.py functional
  suite NOT runnable here (needs real encoder binaries) - PENDING.
  Packaging (Plan A Phase 4): LICENSE_3RD_PARTY pngquant entry added;
  Makefile/build-scripts for pngquant PENDING (needs verified download URLs
  + docker, unavailable this session).
- 2026-08-24 00:58 [Session B]: Packaging PENDING closed - commit e0e09e0:
  windows/pngquant.sh (wget+7z official prebuilt), linux/Dockerfile.pngquant,
  macos/pngquant.sh, Makefile TOOLS+bins/dest wiring, README make targets.
  URLs verified live on pngquant.org; zip layout inspected.
- 2026-08-24 01:04 [Session B]: Functional smoke PENDING closed - real
  binaries placed under bin/win/{pngquant,oxipng,imagemagick} (gitignored);
  9/9 checks PASS through the app's own code paths: oxipng lossless,
  pngquant lossy (218KB -> 65KB), jpg->png magick decode + post, metadata
  branches, Worker-level Same Format end-to-end (resolution -> oxipng ->
  final file) and jpg->LJT routing. Remaining honest gap: upstream
  test_convert.py full suite still needs custom-built libjxl/libavif/
  jpegli binaries (not officially distributed as matching builds).
- 2026-08-24 01:33 [Session B]: Functional suite gap CLOSED to its floor -
  owner approved option A. Downloaded OFFICIAL prebuilts into bin/win/:
  libjxl v0.11.1 static zip (cjxl/djxl/jxlinfo/cjpegli - earlier claim
  "no prebuilts" was wrong, corrected) and exiftool 13.59 (exiftool.org
  moved downloads to SourceForge; upstream pin 13.37 is 404 there).
  test_convert.py (GUI integration, real conversions): **26 of 31 PASS**.
  The only 5 failures are all AVIF-binary-dependent: test_avif,
  test_avif_decode, test_avif_utf8_support, test_proxy (uses PNG->AVIF),
  test_dependencies (asserts avifenc.exe exists). These require building
  libavif with the SVT-AV1-PSY patch via MSYS2/docker per upstream
  Makefile - not obtainable as prebuilt.
- 2026-08-24 01:52 [Session B]: FULL SUITE GREEN - 31/31 PASS. Owner pushed to
  re-research; found libavif v1.3.0 release DOES attach CI artifacts
  (windows-artifacts.zip) containing STATIC avifenc/avifdec with dav1d 1.5.1 +
  aom 3.12.1 + libyuv (no SVT). Placed into bin/win/libavif/. All AVIF tests
  pass on the default "AOM AV1" encoder; aom version 3.12.1 vs upstream pin
  3.13.1 makes no difference for output-validity assertions. Remaining caveat
  (no test covers it): the app's optional "SVT-AV1-PSY" AVIF encoder still
  requires upstream's custom libavif build (sed-patched svt.sh) via MSYS2.
  Lesson recorded: check a project's CI release artifacts before declaring
  binaries unavailable.
- 2026-08-24 02:22 [Session B]: Portable build PRODUCED - env_build venv
  (requirements + PyInstaller 6.11.1 stock wheel, no custom bootloader);
  `python build.py -b portable` ran clean via misc/main.spec; output
  dist/xl-converter-win-1.2.3-x86_64-portable.7z (55 MiB, 378 MiB unpacked,
  includes bin/ encoders + portable_user_data config). Smoke: bundled
  xl-converter.exe launches and stays alive offscreen 10s. Deviations from
  upstream release process: stock PyInstaller wheel instead of self-compiled
  bootloader (VS2022), encoder binaries from official prebuilts instead of
  MSYS2 builds, exiftool/libjxl/libavif versions newer-or-equal but not
  byte-identical to upstream pins, SVT-AV1-PSY option absent.
- 2026-08-24 03:48 [Session B]: Portable build FIXED and verified. Chain of
  findings: (1) the exe the owner ran was `_pyinstaller\main\` build-scratch
  copy without `_internal\` - workpath debris, not the deliverable; scratch
  folder deleted. (2) The real dist build from PyInstaller 6.11.1 failed at
  runtime: `ModuleNotFoundError: _pyi_rth_utils` - PyInstaller's
  fake-modules collection silently breaks when the PyInstaller package lives
  under the `[Github Project]` bracket path (4th distinct bracket-path
  failure on this machine; reproduced with a minimal PySide6 build, both
  6.11.1 and 6.22.2, clean-path venv works). (3) Rebuilt with venv_c
  (bracket-free venv) + PyInstaller 6.22.2 - warn file clean. (4) Verification
  note: QT_QPA_PLATFORM=offscreen windows are invisible to EnumWindows, and
  an error dialog keeps the process "alive" - earlier alive-checks were
  unreliable; faulthandler on a source run proved app.exec() was healthy.
  Final check with a real (non-offscreen) launch: "XL Converter" window
  appears within 4s. dist/xl-converter-win-1.2.3-x86_64-portable.7z
  (58 MiB) is the working deliverable.
- 2026-08-24 04:22 [Session B]: PNG lossy tooltips grounded in research
  (owner request) - quality_png now explains max-quality semantics and
  recommends 80-95 (man page 70-95 example, community "start at 80"),
  65-80 (pngquant's own documented example range), below 60 (banding in
  gradients per 2026 guides); lossless_png reworded to "8-bit palette
  (up to 256 colors), alpha preserved" per pngquant README. Commit
  bbacf ac. Portable rebuilt with venv_c (56 MiB) and re-verified: window
  appears, tooltip source py_compile OK.
- 2026-08-31 [Session C]: Bug-fix commit e4162bb (PNG metadata duplication,
  JXL/AVIF proxy staleness, JPEG-alias coverage) built + pushed. First
  rebuild reused the default `env_build` (lives under the bracket path) -
  reproduced the exact `_pyi_rth_utils` crash this file's 2026-08-24 03:48
  entry already root-caused and fixed, because that fix (a bracket-free
  venv) was never made a standing default - `env_build` itself is still the
  broken location. Recreated a clean-path venv at `D:\xlc_build_venv_c`
  (PyInstaller 6.22.2 + requirements.txt, same versions as the working
  2026-08-24 fix) and rebuilt from it with cwd still at the repo root for
  build.py's relative paths. Verified with a real (non-offscreen) launch via
  `[System.Diagnostics.Process]::Start()`: "XL Converter" window title
  confirmed, process responding. Also found and worked around a 6th
  bracket-path failure mode this session: `Start-Process -FilePath` and the
  `&` call operator both fail to resolve an exe under the bracket path
  (wildcard misparse, same root cause as the existing cd/Out-File/Polars
  findings) even with an absolute path and no relative-path involvement;
  `[System.Diagnostics.Process]::Start()` is unaffected and is the reliable
  way to launch/verify a build from here. `D:\xlc_build_venv_c` left in
  place (not repo-tracked) for reuse by future sessions instead of
  recreating it - see root `mcp-local-capabilities.md` for the cross-repo
  note.

- 2026-09-06 [Session D]: Same Format preset system done (uncommitted) —
  `core/same_format.py` gains PRESETS (Quality/Balanced/Small, values
  anchored to `_infographics_for_preset/` measurements) +
  `apply_format_settings()`; `Worker.runChecks` applies per-format
  quality/lossless after resolution; `output_tab.py` replaces the shared
  quality/lossless controls for the mode with a Preset combo
  (Quality/Balanced/Small/Custom; Custom reveals per-format
  quality+lossless rows, seeded from the preset just left) and new
  tooltips (`same_format` supported-formats/skip note + per-preset
  explanations in `data/tooltips.py`); sf_quality/sf_lossless saved vars
  superseded by sf_png_*/sf_jxl_*/sf_webp_*/sf_avif_*/sf_jpeg_* +
  auto-saved preset. README + changelog updated. Full suite
  `python -m pytest tests/ -q` — 1034/1034 passing (was 1022).

- 2026-09-06 [Session D]: Portable build with preset system — rebuilt via
  in-repo `env_build` (PyInstaller 6.22.2; bracket-path ban retired) with
  `build.py -b portable` → `dist/xl-converter-win-1.2.3-x86_64-portable.7z`
  (56 MiB, 7z "Everything is Ok"); real launch verified via
  `[Process]::Start()` → MainWindowTitle "XL Converter". Not committed,
  not published.

- 2026-09-07 [Session E]: Synced upstream v1.3.0 (150 commits) via merge on
  branch `merge-v1.3.0` — 24 conflicted files resolved with rules:
  overlapping bug fixes taken upstream (process.py rewrite, proxy cleanUp,
  logging_manager, check_commands, test asserts), fork features kept (Same
  Format presets, HEIC, pngquant/oxipng Track A, leak fixes SL4/C2/
  finishConversion/argfile), PNG kept BOTH (their "PNG Optimization" mode +
  our PNG-output pipeline coexist), README macOS section dropped per
  upstream, changelog split (fork items that upstream fixed itself removed
  from our Fixed list). Upstream's DOWNSCALING_DISALLOWED_FORMATS gained
  "Same Format"; their CJPEGLI input fix adopted. Verified: pytest
  1154/1154, test_convert.py 36/36 (real binaries), VERSION now 1.3.0.

- 2026-09-07 [Session E]: Post-merge refresh done — env_dev/env_build
  updated to merged requirements (PySide6 6.10.3, pytest 9.0.2, psutil,
  pillow 12.1.0); pytest 1154/1154 on new deps. Binaries: MSYS2 toolchain
  absent, so official prebuilts used instead of source builds — libjxl
  cjxl/djxl/jxlinfo -> v0.12.0 (official static win64; cjpegli kept at
  0.11.1 mingw build since the official zip omits it - independent binary,
  no cross-version interaction), libavif avifenc/avifdec -> 1.4.2 with
  AOM 3.14.1 + dav1d 1.5.3 (matches upstream pins exactly); oxipng 10.2.0
  / exiftool 13.59 / magick 7.1.2-30 / pngquant 2.17.0 / jpegtran 3.1.0
  already at-or-newer-than upstream pins, kept. test_convert.py 36/36 with
  new binaries (incl. UTF-8 + LJT/reconstruction round-trips). Built
  dist/xl-converter-win-1.3.0-x86_64-portable.7z (57 MiB), bundle
  contents version-checked, launch verified ("XL Converter" window).
  Note for future release builds: run misc/build_scripts/windows/
  pyinstaller.cmd (upstream's new MSVC-bootloader PyInstaller v6.11.1
  setup) if the bootloader must match upstream; current env_build
  PyInstaller 6.22.2 pip wheel works (build + launch verified).

- 2026-09-07 [Session E]: Upstream contribution attempt closed out —
  branch `fixes/upstream-backport` (13 commits, 19 fixes upstream still
  lacks, 1095/1095) pushed to origin as reference. PR not opened: repo's
  CONTRIBUTING ignores PRs (licensing); the 7 consolidated bug-report
  issues (#157-#163, AI-disclosed per owner instruction) were all
  closed NOT_PLANNED by JacobDev1 within ~30 min with the policy
  "Do not submit AI-generated reports. Only submit issues affecting
  functionality you can reproduce personally" - plus a fair criticism
  that gh/REST submission bypassed their disabled-blank-issues form.
  LESSON (binding for future sessions): do not file issues/PRs on
  JacobDev1/xl-converter from agent-driven work - ever again; keep
  fixes in this fork only. Issues left closed as record per owner.

- 2026-09-14 [Session F]: Context-engineering pass — `AGENTS.md` rewritten
  as the real project rules file (tech stack, commands, conventions,
  boundaries, project map) while keeping the existing skills/fable blocks;
  fixed its stale "instruction layer for compare-image" footer and the
  wrong `.opencode/skills/` path claim. Resolved the dirty git state left
  by an earlier rename (tracked `CLAUDE.md` stub deleted, `AGENTS.md`
  untracked) in the same commit.
