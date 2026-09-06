# PNG Encoder Migration Plan (xl-converter-fork)

## Goal
Replace ImageMagick as the *default* encoder for the "PNG" output format with:
- **oxipng** for lossless PNG (already bundled in this repo, but currently only
  used by the "Smallest Lossless" feature, not by plain PNG conversion)
- **pngquant** for lossy PNG (not present anywhere in the codebase yet)

ImageMagick is kept as an explicit fallback/legacy option — never removed.

## Scope
In scope: the "PNG" target-format code path only (`core/worker.py`
`Worker.convert`'s `case "PNG":` branch, its downscaling counterpart in
`core/downscale.py`, the settings/UI that expose it, packaging so the new
binary ships, and tests for all of the above.

Out of scope: JPEG/WebP/AVIF/JPEG XL encoder choices, the existing
"Smallest Lossless" feature's own oxipng usage (already correct — must not
regress it), and any UI redesign beyond what's needed to expose PNG-specific
quality/lossless controls.

## Status
Planning only. No source file in this repo has been modified. This document
itself is the only file written so far, at the user's explicit request.
Nothing below should be started without the user's go-ahead on this plan.

## Key findings from the actual codebase
(read via `serena` / `desktop-commander` before writing this plan — not
assumed from memory or from the upstream project's README/FAQ alone)

1. `data/constants.py` **already defines `OXIPNG_PATH`** per platform, and the
   binary is **already bundled** (`misc/build_scripts/{windows,linux,macos}/
   oxipng.*`). But it is wired only into `Worker.smallestLossless()` (the
   "Smallest Lossless" pool feature) — never into the plain "convert to PNG"
   path.
2. The plain "convert to PNG" path (`Worker.convert`, `case "PNG":`) currently
   has **zero quality/lossless options**. It always calls
   `getDecoder(self.item_ext)`, which resolves to `IMAGE_MAGICK_PATH` for a
   PNG (or any ImageMagick-readable) source, `DJXL_PATH` for a JXL source, or
   `AVIFDEC_PATH` for an AVIF source. This confirms the user's reading of the
   FAQ / Transcoding Options page.
3. `pngquant` has **zero references anywhere** in the repository (verified
   with a project-wide search). It needs a constant, a metadata-arg branch, a
   build/bundling script, and packaging entries, all from scratch.
4. The downscaling path for PNG (`core/downscale.py:decodeAndDownscale`)
   always finishes through `IMAGE_MAGICK_PATH`. Adding oxipng/pngquant here
   means a post-processing pass after the resize, not a replacement of the
   resize step itself — oxipng/pngquant cannot resize images.
5. `core/metadata.py:getArgs()` already has a per-encoder branch pattern
   (`IMAGE_MAGICK_PATH`, `CJXL_PATH`, `AVIFENC_PATH`, `OXIPNG_PATH`) that a
   new `PNGQUANT_PATH` branch can slot into directly.
6. `ui/tabs/settings_tab.py` already has the exact pattern to copy for a "PNG
   Encoder" choice: `jpg_encoder_cmb` (JPEGLI vs. legacy ImageMagick) and
   `avif_encoder_cmb`, plus a custom-args section (`avifenc_args_te`,
   `cjxl_args_te`, `cjpegli_args_te`, `im_args_te`) that new
   `oxipng_args_te` / `pngquant_args_te` fields can join.
7. `ui/tabs/output_tab.py` already has generic `lossless_cb` +
   `quality_sb`/`quality_sl` widgets reused across WebP/AVIF/JPEG XL — plan is
   to reuse these for PNG too, rather than inventing new PNG-specific
   widgets, matching the user's "easy to extend, not a separate example"
   instruction.
8. **Possible licensing conflict — flagged for Phase 1, not resolved here.**
   oxipng/libavif/libjxl/ImageMagick are all permissively licensed.
   `pngquant` (and the `libimagequant` it depends on) has historically
   shipped under terms that are not simple MIT/BSD (dual-licensed, GPL for
   open-source use, per the author's own project pages as commonly known —
   this must be re-checked against pngquant's actual current LICENSE file,
   not assumed from memory, before bundling a binary or touching
   `LICENSE_3RD_PARTY.txt`). Treat this as a go/no-go gate at the very start
   of Phase 1, not an afterthought.
9. Two test files both appear to cover `core/convert.py`:
   `tests/core/test_convert.py` and a root-level `test_convert.py`. Clarify
   in Phase 1/5 whether the root one is legacy cruft before extending both.
10. No `CLAUDE.md` stub or `.serena/` gitignore entry exists yet in this repo
    (confirmed — the fork is completely untouched), unlike the other repos
    under this root.

## Recommended approach (and alternatives dismissed)
**Recommendation:** extend the existing per-format dispatch pattern already
used for JPEG/AVIF/WebP (a `settings["<format>_encoder"]` choice, reusing the
generic lossless/quality widgets) rather than building a parallel
PNG-specific subsystem. Two-stage pipeline for the "PNG" case: (1) obtain a
raw PNG exactly as today (`getDecoder`, unchanged) when the source isn't
already PNG, otherwise use the source file directly; (2) run oxipng
(lossless, default) or pngquant (lossy) as a second pass, with a
`settings["png_encoder"] == "Legacy (ImageMagick)"` switch that reproduces
today's exact single-pass behavior untouched.

- *Alternative — remove ImageMagick entirely from the PNG path:* rejected,
  contradicts the user's explicit "keep it as fallback/backup" instruction.
- *Alternative — a fully separate, standalone PNG-conversion module:*
  rejected, contradicts the user's explicit "easy to extend/maintain, not a
  completely separate example" instruction; the existing per-format `match`
  block in `Worker.convert` is the established extension point.
- *Alternative — do the oxipng/pngquant pass inside `getDecoder`/
  `getDecoderArgs` themselves:* rejected — those two functions are also used
  by `decodeAndDownscale` and, in spirit, by the Smallest-Lossless feature's
  own decode step. Conflating "get a decoder for this source extension" with
  "apply the final PNG compression policy" would blur two concerns and risks
  regressing the already-working Smallest-Lossless path.

## Session discipline for this plan
Per this root's `CLAUDE.md`: trust a phase marked done below without
re-verifying it from scratch in a new session; only re-check on an actual
contradiction encountered while working. After finishing each numbered step,
append one line to the **Progress Log** at the bottom of this file
(append-only — don't rewrite the log) before starting the next step, so an
unexpected quota cutoff mid-phase never loses progress.

## Phase dependency graph
```
Phase 0 (housekeeping)
   -> Phase 1 (research/decisions)
        -> Phase 2 (core backend, ordered 2.1..2.5)
             -> Phase 3 (settings/UI, ordered 3.1..3.2)
                  -> Phase 5 (tests, unordered among themselves)
                       -> Phase 6 (docs + final verification)
        -> Phase 4 (packaging/build) -- independent, any time after
           Phase 1, in parallel with 2 / 3 / 5
```

## Phase 0 - Repo housekeeping (tiny, do first, ~S effort)
Unordered among themselves:
- Add a one-line `CLAUDE.md` stub in this repo's root pointing back to
  `D:\[Github Project]\.repo\CLAUDE.md`, matching the other repos' convention.
- Add `.serena/` to `.gitignore`.
- Note this fork's actual git remote name via `git_status` before any future
  `git_push` is ever authorized (the default `"origin"` assumption has
  already bitten one repo under this root).

**Verification:** the new/changed files exist; `git status` (via
`git-mcp-server`) shows only these additions, nothing else touched.

## Phase 1 - Research & decisions (blocks Phase 2; ~M effort, mostly
reading/searching, no code written)
Ordered — each step gates the next:
1. Check `pngquant`'s (and `libimagequant`'s) actual current license terms
   directly from its own repository before deciding anything else. If
   incompatible with this project's redistribution intent, fall back to
   "oxipng-only default, no lossy PNG option yet" and re-scope Phases 2-5
   accordingly — per the priority rule, minimizing this session's effort
   beats forcing the original scope through.
2. Determine whether pngquant ships official prebuilt binaries for Windows/
   Linux/macOS (lower effort) or must be built from source like oxipng
   (mirroring `misc/build_scripts/*/oxipng.*`).
3. Confirm exact CLI syntax for both tools to write to a distinct output
   path (not in-place): oxipng's `--out <path>`, pngquant's `--output <path>`
   (or its default `-fs8.png`-suffixed naming, which the wrapper would then
   need to rename).
4. Confirm pngquant's default metadata-handling behavior (strips vs.
   preserves what), to fill in `core/metadata.py`'s new branch correctly
   instead of guessing.
5. Decide whether a `png_encoder` setting needs the same cross-tab signal
   wiring `avif_encoder`/`jpg_encoder` use to toggle `OutputTab` widget
   visibility, by re-reading `SettingsTab.onAVIFEncoderChanged` and
   `OutputTab.onJPEGEncoderChanged` together.

**Verification:** a short findings note (can live at the top of this file's
Phase 2 section once written) answering all five points with a citation
(file or URL) for each — not from memory.

## Phase 2 - Core backend wiring (ordered internally; ~M-L effort;
depends on Phase 1)

### Phase 1 findings (verified 2026-08-23, with citations)
1. **License — GO.** pngquant + libimagequant are dual-licensed: Kornel
   Lesiński's contributions under **GPL v3-or-later** (inherited Poskanzer/
   Roelofs parts are permissive/BSD), or a paid commercial license
   (github.com/kornelski/pngquant `COPYRIGHT` + README, fetched 2026-08-23).
   This project already redistributes GPL-family tools the same way
   (`LICENSE_3RD_PARTY.txt`: PyInstaller GPL-2.0, ExifTool Artistic,
   PySide6 LGPL-3, 7-Zip LGPL-2.1) and invokes encoders as separate
   subprocesses (mere aggregation), so bundling pngquant adds no new
   licensing situation beyond a license-file entry.
2. **Binaries:** pngquant.org ships official prebuilts for Windows
   (`pngquant-windows.zip`), Linux and macOS (`pngquant.tar.bz2`, current
   v3.0.3). Build scripts can download instead of compiling.
3. **CLI output flags (verified, not from memory):** oxipng writes to a
   distinct path via `--out <file>` (oxipng MANUAL.txt); pngquant via
   `--output <path>`, single input only (pngquant README). Neither takes a
   trailing positional output, so `core.convert.runBinary`'s dst mechanism
   can't be used — a small dedicated wrapper is needed.
4. **pngquant metadata:** optional PNG chunks are **preserved by default**;
   `--strip` removes them (pngquant README). So the `getArgs` branch is
   Wipe → `["--strip"]`, Preserve → `[]` — same shape as oxipng's.
5. **Signal wiring — yes, needed for parity:** SettingsTab emits
   `jpeg_encoder_changed`/`avif_encoder_changed`, connected in
   `main.py:setupSignals` to `OutputTab.onJPEGEncoderChanged/
   onAVIFEncoderChanged`. A `png_encoder_changed` signal →
   `OutputTab.onPNGEncoderChanged` follows the same pattern so switching to
   "Legacy (ImageMagick)" live-hides the (ineffective) lossless/quality
   widgets for the PNG format.
6. Extra verified facts used in Phase 2: PNG target never uses a proxy
   (`core/proxy.py:isProxyNeeded` returns False for PNG); quality slider
   maps to pngquant as `--quality=0-<q>` (min 0 so pngquant never refuses
   to write); oxipng lossless pass uses `-o 2` (oxipng's documented
   default level) + `-t <threads>` (same flags `smallestLossless` uses).

1. Add `PNGQUANT_PATH` to `data/constants.py`, one line per platform block,
   mirroring `OXIPNG_PATH` exactly.
2. Add a `PNGQUANT_PATH` branch to `core/metadata.py:getArgs()`, using
   Phase 1 step 4's finding.
3. Rewrite `Worker.convert`'s `case "PNG":` branch in `core/worker.py` for
   the two-stage pipeline described above, gated by
   `settings["png_encoder"]` (`"OXIPNG"` default / `"Legacy (ImageMagick)"`)
   and `params["lossless"]` (mirroring how WebP already reads that same key)
   to pick oxipng vs. pngquant when not in legacy mode.
4. Extend `core/downscale.py:decodeAndDownscale` (or add a thin wrapper
   called right after it) to run the same Stage-B oxipng/pngquant post-pass
   on the resized PNG, reusing the helper written in step 3 rather than
   duplicating its logic.
5. Add new `core/exceptions.py` error codes for the new failure paths only
   if the existing generic codes ("C2"/"C3") turn out to be insufficient for
   clear diagnostics.

**Verification:** a manual throwaway script (or `test.py`) converts one
existing sample PNG through each of the three encoder choices and produces a
valid, openable PNG each time; `Worker.smallestLossless`'s own tests still
pass unmodified (regression guard for finding #1 above).

## Phase 3 - Settings/UI wiring (ordered internally; ~M effort; depends on
Phase 2's settings keys existing)
1. `ui/tabs/settings_tab.py`: add `png_encoder_l`/`png_encoder_cmb`
   (mirroring `jpg_encoder_cmb`) and `oxipng_args_te`/`pngquant_args_te`
   (mirroring the existing custom-args fields) through `setupWidgets` /
   `setupLayouts` / `getSettings` / `resetToDefault` / `setToolTips`; add the
   cross-tab signal from Phase 1 step 5's finding only if needed.
2. `ui/tabs/output_tab.py`: extend `_onFormatChange` so choosing "PNG"
   reveals the existing `lossless_cb`/`quality_sb`/`quality_sl` widgets with
   PNG-appropriate range/labels, and extend `getSettings` / `resetToDefault`
   / `_saveFormatVars` / `_loadFormatVars` accordingly.
3. `data/tooltips.py`: add tooltip strings for every new control from
   steps 1-2.

**Verification:** launching the app and selecting "PNG" as the output format
shows the lossless/quality controls exactly like WebP does today; switching
`png_encoder` in Settings changes what `OutputTab.getSettings()` reports.

## Phase 4 - Packaging/build (independent of Phases 2/3/5 - only needs
Phase 1's decision; any order relative to them; ~M effort)
Unordered among themselves:
- Add `misc/build_scripts/{windows,linux,macos}/pngquant.*`, mirroring the
  `oxipng.*` scripts (or a simpler download script, per Phase 1 step 2).
- Update `misc/main.spec` to bundle the new binary the same way oxipng's is
  bundled today.
- Update `LICENSE_3RD_PARTY.txt` with pngquant's actual license text (from
  Phase 1 step 1).
- Add a `misc/changelog.md` entry, matching the existing style (it already
  has a line about updating oxipng/libavif/ExifTool/ImageMagick).

**Verification:** a local PyInstaller build (`build.py`) includes the new
binary in its output directory listing.

## Phase 5 - Tests (items below are independent of each other; the phase as
a whole depends on Phases 2 & 3; ~M effort)
- `tests/data/test_constants.py`: add a `PNGQUANT_PATH` assertion, mirroring
  the existing `OXIPNG_PATH` one.
- `tests/core/test_metadata.py`: add a `PNGQUANT_PATH` row to the existing
  parametrized table.
- `tests/core/test_worker.py`: add cases for the oxipng-default,
  pngquant-lossy, and ImageMagick-legacy PNG paths.
- `tests/core/test_convert.py` **and** the root `test_convert.py`: extend
  both, after Phase 1/5 clarifies finding #9 (or consolidate them if one
  turns out to be dead weight).
- `tests/ui/tabs/test_output_tab.py`: extend for the new PNG format-change
  behavior (this file already exists and already asserts on `jpg_encoder`,
  confirmed by direct search).
- Check whether an equivalent settings-tab test file exists; extend it or
  create one for the new `png_encoder`/args fields.

**Verification:** `pytest` (per `requirements_test.txt`/`Makefile`) passes in
full, not just the new cases.

## Phase 6 - Documentation & final verification (independent, trails
everything; ~S effort)
- Update the `README.md` FAQ section the user quoted, to mention
  oxipng/pngquant as the PNG defaults and ImageMagick as the fallback.
- Manual smoke test: PNG->PNG lossless (oxipng), PNG->PNG lossy (pngquant),
  a non-PNG source -> PNG (through the untouched decode step), and a
  downscaled PNG conversion - confirm all four produce valid images with no
  crash and no regression in "Smallest Lossless".

**Verification:** all four smoke-test conversions produce a valid, openable
image; full `pytest` run stays green.

## Progress Log
(append one line per completed step here, in every future session - do not
rewrite this section, only add to it)
- 2026-08-23: Plan drafted and written (this file). No code changed yet.
- 2026-08-23: Phase 0 done — CLAUDE.md stub created, `/.serena/` added to
  .gitignore (verified: .serena/ no longer untracked in git status), remote
  confirmed as `origin` → github.com/114hikomori/xl-converter-fork.git.
- 2026-08-23: Phase 1 done — all 5 decision points answered with citations,
  written into the "Phase 1 findings" note atop Phase 2. License gate = GO
  (GPL v3+ dual-license, same pattern as already-bundled PyInstaller/ExifTool);
  official pngquant prebuilts exist; flags `--out`/`--output` confirmed;
  metadata preserve-by-default confirmed; cross-tab signal needed.
- 2026-08-23 23:06 [Session A]: A-P2a done (Phase 2 steps 1–2) —
  `PNGQUANT_PATH` added to `data/constants.py` (fallback + win/linux/mac),
  `PNGQUANT_PATH` Wipe branch (`["--strip"]`) added to
  `core/metadata.py:getArgs()`; py_compile OK; pytest/PySide6 not installed
  on this machine (deferred to A-P5).
- 2026-08-23 23:21 [Session A]: Phase 2 step 3–4 (A-P2b) done — two-stage
  pipeline in `Worker.convert` `case "PNG"` (oxipng lossless `-o 2 -t N`
  default, pngquant `--quality=0-q` when lossless=False, `.get("png_encoder",
  "Legacy (ImageMagick)")` gate), new `runPNGPostProcessor` in
  `core/convert.py`, post-pass hook at end of `decodeAndDownscale`
  (post→tmp→replace, code D23); custom-args branches `oxipng_args`/
  `pngquant_args` wired via `.get`. Existing PNG tests updated (legacy split
  into legacy/oxipng/pngquant/non-png-source + downscale png_post case);
  py_compile OK on all four files. Real-binary smoke test deferred (no
  binaries installed).
- 2026-08-23 23:40 [Session A]: Phase 3 (A-P3) done — settings_tab: PNG
  Encoder combo (Oxipng / Legacy (ImageMagick)) + oxipng/pngquant custom-args
  fields wired through widgets/layout/sizes/signals/tooltips/categories/
  getSettings/reset; `png_encoder_changed` signal added and connected in
  main.py to new OutputTab.onPNGEncoderChanged (live-hides quality/lossless
  for PNG when legacy); output_tab: PNG shows quality+Lossless when non-
  legacy, per-format saved vars png_quality (default 80) / png_lossless
  (default True), PNG tooltips; tooltips.py keys png_encoder / quality_png /
  lossless_png. Tests updated: test_output_tab fixture +png_encoder,
  test_settings_tab category lists + png widgets, test_signals +png row,
  test_main mock +onPNGEncoderChanged. py_compile OK all seven files.
  UI launch smoke deferred (no PySide6 installed).
- 2026-08-24 00:27 [Session A]: Phase 4 (packaging, partial) + Phase 5 (tests)
  done - LICENSE_3RD_PARTY.txt pngquant entry added (GPL v3+ dual per Phase 1
  finding #1). Full unit suite executed in fresh env_dev venv: 944 passed /
  0 failed (core 461, data 115, ui 368), including all new PNG pipeline and
  Same Format cases. PENDING: misc/build_scripts/{windows,linux,macos}
  pngquant fetch scripts + Makefile wiring (needs verified prebuilt URLs +
  docker); root test_convert.py functional suite (needs real binaries).
  **2026-09-07: all PENDING items closed** - pngquant scripts exist for
  windows/linux/macos and are wired into the Makefile TOOLS list;
  test_convert.py runs green (31/31, 2026-09-06/07, incl. the dependency
  gate now covering pngquant/cjpegli/jpegtran binaries).
