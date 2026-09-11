# Bug Inspection Summary — Round 2: xl-converter-fork

Follow-up to `bug_inspection_summary.md` (Round 1, full sweep completed 2026-09-05).
Round 2 targets what Round 1 structurally could not cover: (a) code written
after its review stamps — chiefly the 2026-09-06 Same Format preset system
(commit `a02d329`), (b) leads Round 1 explicitly left open, (c) areas Round 1
declared out of scope (`build.py` / `misc/build_scripts/`), and (d) bug
*classes* beyond the per-file pass (persistence round-trips through the real
`WidgetManager`, test-mock wiring errors of the shape found once in Round 1).

Workflow per finding: log here → commit → fix → update → commit.
Reviewed-and-clean areas get a stamp so future passes skip them.

## 1. Inspection Areas & Findings

### Files/Areas Fully Reviewed — Same Format preset system (Round 2) — 2026-09-06
- Scope: the whole of commit `a02d329` re-read adversarially with fresh eyes —
  `core/same_format.py` (`PRESETS`, `PRESET_NAMES`, `apply_format_settings`),
  the `Worker.runChecks` apply hook, `ui/tabs/output_tab.py` (new widgets,
  `_onSfPresetChanged`/`_seedAdvancedFromPreset`/`_getSameFormatSettings`,
  visibility, `resetToDefault`, `_saveFormatVars`/`_loadFormatVars`,
  `disableAutoSaving`), `data/tooltips.py` (5 new keys).
- Checks performed:
  - **Shared-params race:** `apply_format_settings` mutates `self.params` —
    confirmed safe: `Worker.__init__` does `self.params = copy.deepcopy(params)`
    (`core/worker.py:62`), so each worker owns its copy; the pre-existing
    `params["format"] = resolved` mutation relies on the same guarantee.
  - **Startup persistence round-trip** (the one path unit tests cannot reach —
    the `app` fixture patches out `loadState`/`saveState`): real
    `WidgetManager` against a temp `CONFIG_LOCATION`, 3-generation probe —
    set Custom + tweak per-format values + route → save → restore → assert
    widgets, visibility, and emitted `same_format_settings`; then
    Quality-preset round-trip. 14/14 checks passed, including the
    seed-on-enter-Custom guard correctly *not* firing on restore
    (`sf_prev_preset is None` path) so saved Custom values survive.
    Probe script deleted after use.
  - **Tooltip keys:** all 5 new keys (`same_format`, `sf_preset_quality`,
    `sf_preset_balanced`, `sf_preset_small`, `sf_preset_custom`) exist in
    `TOOLTIPS`; the 8 reused per-format keys wired in the Custom branch all
    exist (Round 1's key-existence convention re-applied).
  - **Ranges vs preset values:** every `PRESETS` quality value lies inside its
    widget's `setRange` (PNG 1-100, JXL 0-99, WebP 1-99, AVIF 0-99, JPEG 1-100).
  - **RAM-optimizer ordering:** `runDynamicRamOptimizer()` runs after
    `runChecks()`, so it sees the applied per-format `lossless`/`effort` —
    correct by observation of `Worker.run()` order.
  - **Old-config compatibility:** pre-preset `sf_quality`/`sf_lossless` saved
    vars are simply never read again; new vars fall back to Quality-preset
    defaults via `applyVar` — no crash path, no stale-value path.
- **Finding: no bugs.** One design gap noted, not a defect: advanced mode
  covers per-format quality/lossless only; Effort stays shared across formats
  in Same Format mode (pre-existing behavior, unchanged by `a02d329`).

### Smallest Lossless: Locked Loser File Discards the Already-Determined Winner (`core/worker.py`)
- **Location:** `core/worker.py` (`Worker.smallestLossless`, "Remove bigger files" loop, lines 669-675). Carried over as the one open lead from Round 1 ("whether this is a bug depends on the codebase's own convention... worth a closer look before treating it as confirmed").
- **Inspection:** Re-derived the whole function with fresh eyes plus the two conventions Round 1 had not lined up side by side:
  1. `cleanUp()` (`core/convert.py`) is the codebase's designated tmp-file cleanup - its docstring says "Does not raise an exception", it logs each failure, and `smallestLossless()` itself already uses it on both of its own failure paths (SL2 getsize-failure, SL5 generate-failure).
  2. The "fail loudly on housekeeping" precedents Round 1 cited (`P0` timestamps, `P1` delete-original) both run in `postConversionRoutines()`, which `Worker.run()` calls only **after** `finishConversion()` has already renamed the tmp output to the final file - i.e. the codebase's actual rule is "fail loudly on housekeeping *only when the successful output is already safe*".
- **Finding: Confirmed Bug.** The loser-deletion loop raises `FileException("SL4")` on the first `os.remove` failure and aborts the function - which runs *before* the winner is promoted (`self.output`/`self.final_output` are only assigned afterwards, lines 677-680). A transient lock on a *losing* candidate (AV scanner, indexer - the same realistic trigger class as Round 1's `SetFileTime`/argfile/normalized-JPEG findings) therefore: (a) reports a fully successful conversion as failed, (b) orphans the valid winner as a tmp file that never gets renamed, and (c) skips deleting the remaining losers too (`call_count == 1` in the old test proves the abort). This violates the codebase's own rule reconstructed above: it is the only cleanup-failure site that destroys a good result instead of logging and continuing. The existing `test_smallestLossless_remove_bigger_failed` asserted the current behavior, but per the method's authority order a test codifying behavior cannot outrank the spec/convention the behavior contradicts.
- **Fix applied:** the loop is now `cleanUp([path for key, path in path_pool.items() if key != sm_f_key])` - best-effort, self-logging, never raises; winner promotion always happens. `SL4` removed (project-wide search: zero remaining references). `test_smallestLossless_smallest_file`'s loser check now asserts via the `cleanUp` call args (its old `os.remove`-call-args check would have gone vacuous under the mocked `cleanUp`); `test_smallestLossless_remove_bigger_failed` rewritten as `test_smallestLossless_remove_bigger_failed_keeps_winner`, which runs the **real** `cleanUp` over an always-failing patched `os.remove` and asserts the conversion still completes with the winner promoted. `tests/core/test_worker.py` - 119/119 passing. Full suite `python -m pytest tests/ -q` - 1034/1034 passing.
- `TWINS:` searched for the exact wrong shape - "a loser/tmp-file `os.remove` positioned before, and able to abort, the promotion (rename/assignment) of an already-successful result" - found 1 other site: the JXL intelligent-effort e7/e9 picker in `Worker.convert()` (`core/worker.py`, `except OSError: raise FileException("C2", ...)`) - same shape plus an extra gap (its failure path performs no `cleanUp` at all, orphaning both candidates). Logged and fixed as its own entry below. The other `os.remove` sites Round 1 cleared (finishConversion rename, keep_if_larger, proxy cleanup) remain structurally different (the remove *is* the job step, or runs after promotion).

### JXL Intelligent-Effort Picker: Same SL4 Shape at `C2`, Plus Orphaned Tmps on Failure (`core/worker.py`)
- **Location:** `core/worker.py` (`Worker.convert`, JPEG XL intelligent-effort e7/e9 picker, `try: ... os.remove(loser); os.rename(winner, self.output) ... except OSError: raise FileException("C2", ...)`).
- **Inspection:** Found by the SL4 fix's `TWINS` search (shape: "a loser/tmp-file `os.remove` positioned before, and able to abort, the promotion of an already-successful result"). Read the block fresh and checked its test coverage: `tests/core/test_worker.py` covers only the two happy paths (`..._e9_smaller` / `..._e7_smaller` - which candidate wins); zero coverage of the `C2` failure path.
- **Finding: Confirmed Bug (2 defects, one block).**
  1. Same as SL4: if `os.remove(loser)` fails (AV lock etc.) the `except` fires before `os.rename(winner, self.output)` - a successful double-encode is reported as failed and the winner is orphaned as a tmp file.
  2. Additional gap the SL4 block did not have: when `C2` fires for *any* reason (getsize failure, rename failure, or the remove failure above), nothing cleans up the other tmp candidate(s) - both `.jxl` files (each a full encoded image) are silently left in the user's output directory. The function's own sibling failure paths (`SL2`, `SL5`, and now SL4's replacement) all `cleanUp` before raising.
- **Fix applied:** winner/loser are determined first, `os.rename(winner, self.output)` runs inside the `try`, every `C2` exit now does `cleanUp([path_e7, path_e9])` before raising, and the loser is removed best-effort via `cleanUp([loser])` only after a successful rename. A locked loser can no longer abort promotion and no `C2` exit leaves tmps behind. Added `test_convert_jpeg_xl_intelligent_effort_loser_remove_failed_keeps_winner` (real `cleanUp` over always-failing `os.remove`; asserts rename still happens) and `test_convert_jpeg_xl_intelligent_effort_getsize_failed_cleans_up` (asserts `C2`, both tmps removed, no rename). The two pre-existing happy-path tests pass unchanged (their `os.remove` assertions still hold because `cleanUp` calls the patched `os.remove`). `tests/core/test_worker.py` - 121/121 passing. Full suite - see next entry's verification.
- `TWINS:` searched for the shape "failure exit that orphans tmp files / cleanup positioned before and able to abort promotion" - found 1 more site: `finishConversion`'s `F1`/`F3`/`M*` exits (logged as its own entry below, fixed next). The `Smallest Lossless` + Skip `os.remove(self.output)` site is structurally different (the remove *is* the job step there - skip semantics - and the user's existing file is untouched on failure). Proxy/`F0` is its own already-failed delete.

### `finishConversion` Failure Exits Orphan the Converted Tmp Output (`core/worker.py`)
- **Location:** `core/worker.py` (`Worker.finishConversion`) - the `F3` (empty output), `F1` (`OSError` during metadata/rename/remove/copy steps) and `M*` (`FileException` from `runExifTool()`) exits.
- **Inspection:** Surfaced by the C2 fix's twin search for "failure exits that leave tmp files behind". `getUniqueTmpFilePath` names tmps `tmp_<hex>.<ext>` directly in the user's output folder and nothing in the codebase ever sweeps stale `tmp_*` files (verified: no startup sweep, no other cleanup owner), so every leak is permanent and user-visible. `finishConversion`'s own `try` block wraps checks, ExifTool, rename, destination-delete and the copy-if-larger re-copy - but its only handler is `except OSError -> F1`, and no exit path removes `self.output`.
- **Finding: Confirmed Bug (leak class, same convention as the SL4/C2 fixes above).** Reachable exits that leave a full-size `tmp_*.ext` behind in the user's output directory:
  1. `F3` - encoder produced a 0-byte file (encoder contract is "output exists", not "exit code 0", so a crashed-but-created file reaches here) -> empty tmp orphaned.
  2. `M*` - `runExifTool()` raises `FileException` inside the `try`; `except OSError` does not catch it, so it propagates with no cleanup -> the *successfully converted* image is orphaned and invisible to the user.
  3. `F1` - any `OSError` in the rename/destination-delete/copyfile group (locked destination, disk full during the copy-if-larger re-copy) -> tmp orphaned.
  (`F2` is a no-op leak - by definition the file does not exist; `F0` proxy failure is its own already-failed delete.)
- **Fix applied:** the `except OSError` (`F1`) arm now runs `cleanUp([self.output])` before raising, and a new `except FileException: cleanUp([self.output]); bare raise` arm covers `F3`/`M*` exits with the original error id preserved (`F2`/no-output stays a safe no-op through `cleanUp`'s own existence check). Extended `test_finishConversion_empty_output` (asserts the tmp is removed) and `test_finishConversion_no_output` (asserts nothing is removed when there is nothing to remove), and added `test_finishConversion_exiftool_failure_cleans_up_output` (`M1` propagates, tmp removed) and `test_finishConversion_rename_failure_cleans_up_output` (`F1`, tmp removed). `tests/core/test_worker.py` - 123/123 passing (was 121). Full suite `python -m pytest tests/ -q` - 1038/1038 passing (was 1036).
- `TWINS:` enumerated every `getUniqueTmpFilePath` creation site project-wide and checked each function's failure exits for tmp-orphaning: `setupConversion`'s `self.output` (now covered by this fix + convert's C3 "file missing" precondition), `convert`'s e7/e9 pair (fixed above), PNG two-stage `tmp_raw` (already `finally`-cleaned), `smallestLossless` pool (fixed above), `losslesslyTranscodeJPEG` normalize/verify tmps (Round 1 fixes), `core/downscale.py` proxy/post/e9 tmps (Round 1 full-file review, no leak found), `Proxy.generate` tmp (Round 1 proxy fixes). Found 0 further orphaning sites.

### Surprise: Round 1's "Full Sweep Complete" Claim Had a Hole - `ui/tabs/settings_tab.py` Was Never Reviewed
- Round 1's coverage list ends with "None. Full sweep complete as of 2026-09-05", and its own commit message says "ui/tabs (except settings_tab)" - but `settings_tab.py` (656 lines) appears in Round 1 only as a *witness* in other files' findings (logging toggle, bit-depth consumer, migration caller), never as a reviewed target, and it is absent from the fully-reviewed list. The completeness claim was wrong. Round 2 closes the hole (below).

### Files/Areas Fully Reviewed - `ui/tabs/settings_tab.py` (first full review ever) - 2026-09-06
- Full read (656 lines) + cross-checks:
  - **AVIF bit-depth per-encoder memory** (`onAVIFBitDepthChanged` / `onAVIFEncoderChanged`): the encoder-switch rebuild runs inside `blockSignals(avif_bit_depth_cmb)`, so the per-encoder saved vars (`aom_av1_bit_depth` / `svt_av1_psy_bit_depth`) are never cross-contaminated by the rebuild itself; `loaded_var or "Auto"` handles the never-set case; SVT's shorter option list can never produce a value AOM-only ("12") and vice versa. Correct.
  - **Logging toggle** (`toggleLogging`/`enableLogging`/`disableLogging` vs the checkable button's auto-toggle): clicked-after-toggled ordering leaves the checked state consistent on both transitions; `wipeLogsDir` correctly stops the handler before deleting the dir. Matches Round 1's `logging_manager` fix. Correct.
  - **`changeCategory` visibility lists**: every widget created in `setupWidgets` appears in exactly one category list (enumerated 1:1); the `getattr` + `except AttributeError` log guard also catches the commented-out `avif_aom_tune_*` leftovers safely since they are absent from the lists. Correct.
  - **Startup signal storm**: `loadState` (inside `blockSignals` for only 4 widgets) fires `currentTextChanged` on the encoder combos → `jpeg/png/avif_encoder_changed` emit with zero receivers (main.py wires signals after construction) - harmless; `onRamOptimizerChanged`/`onAVIFEncoderChanged`/`onThemeChanged` etc. are all idempotent refreshes called explicitly right after. Correct.
  - **`resetToDefault` via the button** (unlike the startup call, unblocked): each `setCurrentIndex(0)` that changes text correctly propagates through its own handler (`onAVIFEncoderChanged` rebuild, `onAVIFBitDepthChanged` storing "Auto", encoder-changed signals reaching the OutputTab fix from Round 1). One borderline design ambiguity logged as *not a bug*: per-encoder bit-depth vars for the *inactive* encoder survive a "Reset to Defaults" (only the active encoder's combo resets) - consistent with the per-format memory pattern used everywhere else in this app, so left as intended behavior.
  - **`runMigrations`** ordering (after `loadState`, before `cached_states` init - no saveState can interleave), `compareVersions` guard semantics (Round 1-verified), and the stock/legacy preset string comparisons - correct.
  - **`saveState`/`cached_states`** - identical shape to the OutputTab one Round 1 verified in main.py. Correct.
- **Finding: no bugs.** Stamped reviewed 2026-09-06.

### `check_commands` in the Windows Build Scripts Crashes Instead of Reporting Missing Tools (`misc/build_scripts/windows/_shared.sh`)
- **Location:** `misc/build_scripts/windows/_shared.sh` (`check_commands`, lines 47 and 52), reached by `windows/pngquant.sh` and `windows/exiftool.sh` (both run `set -euo pipefail` before calling it).
- **Inspection:** Round 2 sweep of the packaging scripts Round 1 explicitly excluded. Compared the Windows shared helper against its macOS sibling function-by-function.
- **Finding: Confirmed Bug (2 lines, one copy-paste).** `check_commands` collects missing tools with `missing_commands+=("${pkg}")` - `pkg` is the *loop variable of the other function* (`check_packages`) and is never set inside `check_commands`. When every checked tool is present the buggy line never executes (works by accident); when a tool IS missing, the reference to the unset `pkg` under `set -u` kills the script with a bare `pkg: unbound variable` error instead of the intended actionable message. Line 52 compounds it: the message interpolates `${required_commands[*]}` (every tool that was checked) where `check_packages`'s sibling correctly prints the *missing* list. The macOS `_shared.sh` has the same function written correctly (`${cmd}` / `${missing_commands[*]}`), proving intent - this is a bad copy-paste, not a design choice. Impact is maintainer-facing only (no shipped-app runtime exposure), hence low severity, but it defeats the function's entire purpose at exactly the moment it is supposed to help.
- **Fix applied:** both lines aligned with the macOS sibling (`missing_commands+=("${cmd}")`; message prints `${missing_commands[*]}`). Verified empirically with real MSYS2 bash (`C:\msys64\usr\bin\bash.exe`): pre-fix, `set -u; source _shared.sh; check_commands definitely_missing_tool_xyz` died with `pkg: unbound variable` (exit 127, no message); post-fix it prints `Missing command-line tools: definitely_missing_tool_xyz another_missing` + exit 1, and the all-present path (`check_commands cd true`) passes silently to the end. (Note: `command -v bash` fails under this harness because the inherited Windows PATH lacks `/usr/bin` - a probe artifact; the scripts' real entry point is an MSYS2 MINGW64 shell, enforced by `check_msys2`, where PATH includes it; builtins test the same code path faithfully.)
- `TWINS:` searched all of `misc/build_scripts/` for `missing_commands`/`required_commands` misuse - `macos/_shared.sh` is the correct original (0 bugs); `check_packages` in the same Windows file uses its own loop variable correctly; no other shell function references a variable owned by another function. Linux side uses Dockerfiles (no `_shared.sh`).
- **Rest of the Windows build-script sweep (all read in full, 2026-09-06):** `pngquant.sh`, `exiftool.sh`, `oxipng.sh`, `libjxl.sh`, `imagemagick.sh`, `libavif.sh`, `libjpeg-turbo.sh`, `build.py` (the orchestrator). Leads investigated and cleared, not bugs:
  - `libjpeg-turbo.sh`'s `-outputresource:"${exe}";#1` - the shell really does swallow `;#1` as terminator+comment, but Microsoft's mt.exe docs (learn.microsoft.com/windows/win32/sbscs/mt-exe) state that `-outputresource` without a resource id defaults to `CREATEPROCESS_MANIFEST_RESOURCE` (= 1, exactly the intended id). Harmless; stamped so a future pass does not re-flag it.
  - `imagemagick.sh`'s `cp ./utilities/magick` (no `.exe`) - MSYS2's file layer resolves `magick` to `magick.exe`; confirmed the produced `bin/win/imagemagick/magick.exe` is a real PE (`MZ` header) and `bundle_dlls`' `-name "*.exe"` matched it.
  - `PNGQUANT_VERSION="3.0.3"` declared-but-unused in both windows and macos `pngquant.sh` - identical in both siblings; pngquant.org publishes only a floating `pngquant-windows.zip`, so the variable is a "verified-at" note, not a broken pin. Hygiene observation only.
  - Orchestrator `misc/build_scripts/windows/build.py`: `install.iss` compiled with `cwd=dist` resolves its `Source: "xl-converter\*"` correctly (ISCC anchors to the script's own dir, which build.py copies into `dist/`); the portable-7z-before-innosetup `rmTree(dist)` ordering is deliberate and safe (7z already moved out); `check_python_version`'s `split(".", 2)` handles rc-suffixed versions. One hygiene note, not a bug: its `PYINSTALLER_DIR` (`misc/pyinstaller`) is not in `.gitignore`, so a bootloader build leaves an untracked clone (the root build.py's `/_pyinstaller` entry is ignored).
- **Stamped:** all of `misc/build_scripts/windows/` reviewed in full 2026-09-06. `misc/build_scripts/{linux,macos}/` (Dockerfiles / shell siblings) remain un-swept - maintainer tooling for platforms this fork does not ship; macOS `_shared.sh` was read as the reference for the fix above and is clean.

### Silent Duplicate Dict Keys in `tests/core/test_worker.py` Fixtures (one with conflicting values)
- **Location:** `tests/core/test_worker.py` - the `worker` fixture's params dict (line ~27/43) and the `finishConversion_patches` / `smallestLossless_patches_v2` mock dicts.
- **Inspection:** AST scan of all of `tests/` for duplicate string keys inside dict literals (the shape that silently drops an entry, found by eye twice while working in these fixtures during the SL4/C2 fixes this round). 3 hits, all in this one file.
- **Finding: Confirmed Bug (test hygiene, 1 real + 2 benign).**
  1. `worker` fixture: `"downscaling": {"enabled": False}` appears at line 27 and again at line 43 with the full dict (`mode`, `percent`, `width`, ...). Python keeps the *last* entry - the first is silently dead. No test breaks today only because the surviving value is the correct one; had the order ever been reversed (or someone "fixed" the wrong duplicate), every downscaling-aware test would silently receive an incomplete dict. A live footgun and a misreader.
  2. `finishConversion_patches`: `"removeFile"` key twice (identical patch) - dead duplicate, misleading.
  3. `smallestLossless_patches_v2`: `"os.path.isfile"` key twice (identical patch) - dead duplicate, misleading.
- **Fix applied:** deleted the first (dead) `downscaling` entry and both identical duplicate keys. Re-ran the AST scan: 0 duplicate-key dict literals remain in `tests/`. Full suite `python -m pytest tests/ -q` - 1038/1038 passing.
- `TWINS:` the AST scan itself is the twin check - all of `tests/` (and it flagged nothing outside this file); production `core/`/`data/`/`ui/` dict literals were included in the same scan - 0 duplicate-key sites.

### Cross-Cutting Test-Suite & Settings-Flow Sweeps (classes beyond Round 1's per-file pass) - 2026-09-06
- **AST duplicate-dict-key scan** (`tests/` + `core/`/`data/`/`ui/`): 3 hits, all in `tests/core/test_worker.py` (fixed - see entry above); 0 in production.
- **Mock-assertion-name validity scan** (AST: every `.assert_*()` call in `tests/` checked against unittest.mock's real assertion-method set - a typo'd name on a `MagicMock` silently passes forever because unknown attributes auto-mock): 0 invalid sites.
- **Bare-mock-truthiness assertion scan** (`assert mocks[...]` with no comparison/call - always true for a MagicMock): 0 sites.
- **Params/settings producer-consumer cross-check** (regex over `core/` for every `self.params[...]`/`self.params.get(...)`/`self.settings[...]` key, matched against the keys actually emitted by `OutputTab.getSettings()` + `ModifyTab.getSettings()` and `SettingsTab.getSettings()`): 0 read-but-never-produced keys, 0 typos - this also covers the new `same_format_settings` key end to end. Scope note: reads through intermediate variables (e.g. `scl_params["dst"]` inside downscale.py, whose dict is built in-worker) are outside this check; that dict's shape was already verified in Round 1's full reads of `worker.py`/`downscale.py`.
- **Finding: no further bugs** in these classes.

### `test_convert.py` Release Gate: Dead Nested-Dict Check + Fork Binaries Missing From Dependency List
- **Location:** `test_convert.py` (`test_dict` helper, consumed by `test_get_settings`; `TestMainWindow.test_dependencies`).
- **Inspection:** Full read of the 528-line integration harness (the last un-swept executable file; the Windows orchestrator runs it as a release gate via `python test_convert.py`).
- **Finding: Confirmed Bug (2 sites, harness).**
  1. `test_dict()`'s recursion guard reads `if test_dict(value) is None: return False` - but `test_dict` only ever returns `True` or `False`, never `None`, so the condition is dead: any nested dict (e.g. `smallest_format_pool`, `same_format_routes`, and the new `same_format_settings`) can contain `None` leaves and `test_get_settings` still passes. The helper's own docstring ("Recursively verify dictionary's integrity") states the intent the code fails to implement.
  2. `test_dependencies`' `FILES` tuple lists every bundled binary *except* the two the fork added: `CJPEGLI_PATH` and `PNGQUANT_PATH`. A build missing `cjpegli.exe` fails only indirectly (later JPEG tests), and a missing `pngquant.exe` is caught by nothing at all - no harness test exercises lossy PNG - so the dependency gate silently passes an incomplete bundle.
- **Fix applied:** `test_dict` recursion now `if not test_dict(value): return False` (verified both directions: nested `None` -> `False`, clean nested -> `True`); `FILES` now includes `CJPEGLI_PATH`, `PNGQUANT_PATH` and `JPEGTRAN_PATH`. `test_dependencies`/`test_get_settings`/`test_jpg` run from the harness.
- **Surprise (the strengthened gate immediately caught a real defect):** with `JPEGTRAN_PATH` added, `test_dependencies` FAILS on this machine - `bin\win\jpegtran\jpegtran.exe` does not exist anywhere under `bin/` or the built `dist/` bundle. Consequence: the 2026-09-06 portable 7z ships without jpegtran, so the "Normalize" option of Lossless JPEG Transcoding (`core/lossless_jpeg.py:61` -> `runJPEGtran` -> `Popen`) fails with a raw `OSError` for any user who enables it (default is off, so the common path is unaffected). This is a missing build input on this machine (`bin/` is gitignored; `misc/build_scripts/windows/libjpeg-turbo.sh` is the script that produces it), not a code defect - restoring the binary is proposed to the owner rather than silently downloading an exe into the repo. The gate is deliberately left red: it is now reporting reality.
- `TWINS:` enumerated every `*_PATH` constant in `data/constants.py` against the `FILES` tuple - after the fix, all 10 bundled-binary constants are gated (`LICENSE*`/`FINISHED_SOUND_PATH` are assets, already covered/irrelevant); production consumers of each path were cross-checked via grep (`JPEGTRAN_PATH` -> `convert.py:126` -> `lossless_jpeg.normalizeJPEG` only). No other ungated binary constant remains.
- **Notes, not bugs:** the harness mutates gitignored `_sample_img/` files in place (`os.utime`, EXIF write) and `tear_down` writes real `CONFIG_LOCATION` state - both pre-existing upstream tooling behavior, out of fork scope. `wait_for_done` terminates on every non-cancel path (exceptions still emit `completed`), verified against `Worker.run()`.

### Remaining Tooling Files - Final Completeness Sweep - 2026-09-06
- `test.py` (53 lines) - full read. Thin pytest launcher; no bugs. (Cosmetic only, not logged as a bug: its help epilog references `tests/ui/test_output_tab.py`, actual path is `tests/ui/tabs/test_output_tab.py` - upstream, help text only.)
- `Makefile` (234 lines) - full read. Two findings, both upstream (predating the fork; logged, deliberately not fixed to preserve merge-friendliness with upstream tracking):
  - `build-macos` invokes `misc/build_scripts/macos/build.sh`, which has never existed in this repository's history (`git log --all` empty) - the target has been dangling since upstream commit `eff1d15` (2025-06-28). The fork ships Windows only.
  - `venv-dev` prints "venv-build has been created" (copy-paste echo string, cosmetic).
  - Per-tool `bins_*`/`dest_*` cleanup layout cross-checked against each script's actual output dir (incl. the fork's `e0e09e0` pngquant wiring) - consistent, including `bins_win_libjpeg-turbo := jpegtran` matching `libjpeg-turbo.sh`'s output folder.
- Root `build.py` (483 lines) - full read (also exercised for real on 2026-09-06). Dead `"./fonts/"` entry in the assets tuple (upstream `f8e3840`): no top-level `fonts/` exists; real fonts ship via `"./assets/"` -> `assets/fonts` (verified `ASSETS_FONTS_DIR` resolves there and the built bundle contains them). Silently skipped by `os.path.isdir` - harmless, logged not fixed. `_appendInstaller`'s `replaceLine` targets verified against `misc/install.iss`'s actual `#define MyAppVersion` / `OutputBaseFilename` lines.
- `misc/install.iss`, `misc/main.spec` - full read. All relative paths resolve correctly from both the spec dir and the `dist/` working directory the orchestrator uses; version placeholders are replaced pre-compile. No bugs.
- **Scoped out with reason:** `misc/build_scripts/{linux,macos}/` beyond `macos/_shared.sh` (read as the reference for the Windows fix - clean): upstream container/platform tooling for builds this fork does not ship. `*.metainfo.xml`, `.github/*` templates, docs/plans: non-executable metadata.

## 2. Round 2 Summary

| # | Area | Result |
|---|---|---|
| 1 | Same Format preset system (a02d329) re-review + persistence probe | clean |
| 2 | `smallestLossless` SL4 (Round 1 open lead) | bug fixed (`c249ef4`) |
| 3 | JXL intelligent-effort C2 (twin of #2) | bug fixed (`43f0eed`) |
| 4 | `finishConversion` tmp-orphan exits (twin of #3) | bug fixed (`1fd48d6`) |
| 5 | `settings_tab.py` (Round 1's missed file) | clean, first full review (`06bb71a`) |
| 6 | Windows build scripts (Round 1 out of scope) | 1 bug fixed (`e33a547`), 4 leads cleared |
| 7 | Test-suite class sweeps (dup keys, mock-assert names, mock truthiness, key producer/consumer) | 3 hygiene bugs fixed (`6ce6d58`), rest clean |
| 8 | `test_convert.py` release gate | 2 bugs fixed (`eda410c`) + exposed missing `jpegtran.exe` build input |
| 9 | Remaining tooling (test.py, Makefile, build.py, iss, spec) | clean; 2 upstream findings logged |

Full pytest suite at end of round: 1038/1038. The `test_convert.py::test_dependencies` failure on this machine is real and intentional (missing `bin/win/jpegtran/jpegtran.exe` - restore it via `misc/build_scripts/windows/libjpeg-turbo.sh` or an official libjpeg-turbo 3.1.0 win64 build, then rebuild the portable bundle).

### Resolution (2026-09-06): jpegtran.exe restored, harness green, portable rebuilt
- Restored `bin/win/jpegtran/` from the **official libjpeg-turbo 3.1.0 win64 (vc64) release** - the exact version the fork's `libjpeg-turbo.sh` pins; chosen over a source build because the script's hardcoded `mt.exe` SDK path (10.0.20348.0) is absent on this machine (only 10.0.26100.0 present) and MSVC official artifacts are the documented-good UTF-8 path (`imagemagick.sh` header comment). Copied `jpegtran.exe` + `jpeg62.dll`, then embedded the script's identical UTF-8 `activeCodePage` manifest via `mt.exe` (exit 0).
- Verified by observation: `jpegtran.exe -version` -> "libjpeg-turbo version 3.1.0 (build 20241212)"; app's real `lossless_jpeg.normalizeJPEG()` succeeded on both a plain path and a Thai+Japanese filename through the actual `runJPEGtran -> Popen` path (proves the manifest); full `test_convert.py` -> **31/31 OK** (~5.4 min, real conversions); `build.py -b portable` rebuilt -> `dist/xl-converter-win-1.2.3-x86_64-portable.7z` (56 MiB) with `jpegtran.exe` + `jpeg62.dll` confirmed inside the archive listing; rebuilt exe launched, window title "XL Converter" confirmed, killed.
- `bin/` and `dist/` are gitignored - no repo change from the restore itself; the dependency gate (`test_dependencies`) now passes truthfully. Scratch files (download/extract temp, smoke script) deleted.

## 3. Post-Round-2 field report (2026-09-07): AVIF renders yellow/purple in Windows Photos (`core/worker.py`)

- **Report:** owner converted `_sample_img/Sample_4th_month-HEIC/` (32 HEIC, 3000x4000) to AVIF with all-default settings (AOM AV1, q70, speed 7, chroma "Default", metadata "Encoder - Wipe"). Windows Photos shows every output with a strong yellow/purple cast.
- **Inspection:**
  - The files are not corrupt: all 32 decode under `avifdec` (dav1d, strict) and pixel-match the HEIC originals (RMSE ~0.003 at 400px, all 32 pairs).
  - Root cause is a signalling/interpretation mismatch. avifenc's default for the app's PNG proxy is YUV444 with 601-encoded planes (`nclx 2/2/6`, full range) + the source ICC. dav1d/libavif honour the ICC and decode correctly; **Windows WIC - the engine behind Photos - ignores the ICC and assumes 444 planes are identity RGB**, so it applies a 601→RGB transform to already-RGB values → the yellow/purple cast. Reproduced deterministically by decoding the owner's files through `BitmapDecoder` (WIC): RMSE 0.25 vs reference (Photos-broken), and by re-encoding one sample through the app's exact pipeline (magick proxy → avifenc): identical broken metadata and identical WIC result.
  - Variant matrix (encode → WIC-decode → RMSE vs source PNG): default 444/601 = 0.25 (broken); 444 + `--cicp 2/2/0` (identity) = 0.010 (correct); 444 + `--cicp 1/13/0` = 0.010 (correct); 420 default = 0.012 (correct - with real chroma subsampling WIC reads the matrix properly); 420 + explicit 709 = 0.011 (correct). dav1d cross-check on the chosen variant: 0.009 (correct). Identity 444 costs ~11.6% size at q70 on this sample (1.56→1.74 MB) because three full-energy planes compress worse than Y+2 low-energy chroma planes.
- **Finding: Confirmed practical bug** (upstream's output is spec-valid; the encoder's default 444 signalling is simply one that Windows' built-in viewer misrenders - a converter whose default output looks broken in the OS's default viewer is broken in practice).
- **Fix applied:** `core/worker.py` AOM AV1 branch - when the effective output is 444 (chroma "Default" or explicit "4:4:4"), append `--cicp 2/2/0` so planes are stored as identity and both interpretations (ICC-honouring and WIC's assumption) agree. 4:2:0/4:2:2 paths unchanged (already render correctly). Test expectations updated in `tests/core/test_worker.py::test_convert_args_avif` (Default and 4:4:4 cases). Full suite: 1154/1154. E2E through the real pipeline (magick proxy → avifenc with the new args + Encoder-Wipe metadata args → WIC decode): RMSE 0.0108 vs reference - correct.
