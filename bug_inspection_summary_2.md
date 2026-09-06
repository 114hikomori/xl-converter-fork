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
