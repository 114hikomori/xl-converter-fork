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
