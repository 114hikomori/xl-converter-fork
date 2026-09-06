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
