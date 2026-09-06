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
- **Fix (in progress):** add `cleanUp([self.output])` on the `F1` (`OSError`) exit and a new `except FileException: cleanUp; bare-raise` arm so `M*`/`F3` propagate unchanged but leave nothing behind; `cleanUp`'s own `isfile` guard makes the `F2` case a safe no-op. Extend `test_finishConversion_empty_output`/`_no_output` with cleanup assertions and add an exiftool-failure regression test.
