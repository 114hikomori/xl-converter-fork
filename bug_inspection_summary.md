# Investigation and Debugging Summary: xl-converter-fork

## 1. Inspection Areas & Findings

### PNG Lossy Quality Setting (`pngquant`)
- **Location:** `core/worker.py` (`Worker.convert`), `output_tab.py`, `settings_tab.py`, and CLI binary `bin\win\pngquant\pngquant.exe` (v2.17.0).
- **Inspection:** Evaluated whether `--quality=0-N` parameters were parsed properly by `pngquant` or ignored by UI state logic.
- **Finding:** CLI behavior verified on real-world complex images (626k+ colors). Output sizes scale properly between quality settings (e.g., q10 = 1.45 MB vs q90 = 2.71 MB). Initial flat results were due to testing on a low-color sample image (`sample.png`) which converged to identical palettes. End-to-end integration within `Worker.convert` operates as intended.
- **Follow-up (2026-08-31), not a bug:** A `compare-image`-tool `preflight.json` run against `_sample_img\real_sample` flagged 32 content groups where the app's own PNG lossy80/90/95 outputs were byte-identical, raising doubt about the "operates as intended" finding above. Re-verified by running `pngquant.exe` directly at quality 60/80/90/95 on 4 of the flagged `real_sample` files. The quality parameter does keep varying correctly (q60 differs from q80/90/95 on every file; on a lower-complexity control file 02_CP01.png, q80/90/95 also stay distinct: 18/28/40 colors, Q83/93/95). But on the 3 high-complexity photographic files tested (500k+ unique colors, e.g. `01_CP00.png`, `31_CP30.png`, `44_44.png`), q80/90/95 converge to byte-identical output because pngquant saturates PNG's hard 256-entry `PLTE` palette cap (confirmed against the PNG spec itself) — no encoder can add palette entries the 8-bit indexed format doesn't have room for. Cross-checked `31_CP30.png`'s hash from this direct pngquant run (`2B86D58858BA`) against preflight.json's own recorded hash for the same file across the same 3 variants — exact match, confirming this is real, reproducible pngquant behavior, not a `compare-image` artifact. Other palette-based lossy-PNG tools (pngnq/pngnq-s9, TinyPNG, exoquant) hit the identical ceiling for the same reason (verified via each tool's own docs) — this is a PNG-format limit, not a pngquant- or xl-converter-specific defect, so no code change was made. Worth surfacing to users (e.g. a note that PNG lossy quality above ~80 has little/no effect on busy photos already at the palette cap) rather than treated as a bug to fix.

### Duplicate Metadata Arguments during PNG Downscaling
- **Location:** `core/downscale.py` (`decodeAndDownscale()`) and `core/worker.py`.
- **Inspection:** Traced argument pipeline when combining downscaling with `oxipng` or `pngquant` post-processing.
- **Finding:** **Confirmed Bug.** `png_post["args"]` received from `Worker.convert` already contained metadata arguments (inherited via reference from `png_stage_b`). `decodeAndDownscale()` called `.extend(metadata.getArgs(...))` again, resulting in duplicate arguments (e.g., `--strip safe --strip safe`).

### Same Format JPEG Route Not Applied to All JPEG Aliases
- **Location:** `ui/tabs/output_tab.py` (`OutputTab.getSettings()`), `data/constants.py` (`JPEG_ALIASES`).
- **Inspection:** Traced how the "Same Format" mode's JPEG Route control (`sf_jpeg_route_cmb`) populates `same_format_routes` for JPEG-family extensions.
- **Finding:** **Confirmed Bug.** `getSettings()` only set `same_format_routes` for `"jpg"` and `"jpeg"`, while `JPEG_ALIASES` in `data/constants.py` lists 5 extensions (`jpg, jpeg, jfif, jif, jpe`). Setting the JPEG Route to e.g. "Lossless JPEG Transcoding" silently didn't apply to `.jfif`/`.jif`/`.jpe` files, which fell back to plain "JPEG" with no warning. Design intent (`FORK_MASTER_PLAN.md` B.4, and `core/same_format.py`'s own default mapping of every `JPEG_ALIASES` entry to "JPEG") confirms one control should govern the whole family.

### JXL/AVIF Proxy Metadata Argument Staleness (Bug 3)
- **Location:** `core/downscale.py` (`decodeAndDownscale()` proxy branch).
- **Inspection:** Traced historical usage of ImageMagick and the proxy decoding path for JXL/AVIF inputs targeting PNG output.
- **Finding:** **Confirmed Bug, now fixed.** When input format is JXL or AVIF, `decodeAndDownscale()` decodes to a proxy PNG via `DJXL_PATH` or `AVIFDEC_PATH` (where `metadata.getArgs()` returns `[]`). It then set `params["enc"] = IMAGE_MAGICK_PATH` to perform downscaling but failed to recompute `params["args"]` for ImageMagick, so metadata-wipe flags (e.g. `-strip` under "Encoder - Wipe") were skipped during the downscale pass. Git log confirmed this logic predates the fork (`6fcad3a`); previously retained as a documented-only finding per instructions, now fixed on request.

### UI State & Persistence Logic
- **Location:** `output_tab.py` (`_saveFormatVars`/`_loadFormatVars`), `WidgetManager`.
- **Inspection:** Verified per-format quality variable saving, slider/spinbox synchronization, and default encoder values.
- **Finding:** Format variable swapping and value bindings operate as expected without state leakage.

### Non-ANSI Path Handling for JPEG XL / JPEGLI on Windows (`core/pathing.py`)
- **Location:** `core/pathing.py` (`isANSICompatible`), `core/worker.py` (`Worker.runChecks`/`Worker.convert`), `core/conflicts.py`.
- **Inspection:** `isANSICompatible()` and the setting `disable_jxl_utf8_check` used to guard JXL/JPEGLI conversion on Windows against paths with non-ANSI characters (added in `bb688b5`, "Refactor UTF check", 2024-03-28; shipped as "Added detection for incompatible characters" per `misc/changelog.md` 0.9.6). A project-wide search found **zero** current references to `isANSICompatible`, `disable_jxl_utf8_check`, or "non-ANSI" outside the orphaned function itself and its own unit test (`tests/core/test_pathing.py`) — `Worker.runChecks()` no longer calls it, and `core/conflicts.py` (which replaced the old check's call site) only handles animation/multipage conflicts, nothing path-encoding related. This looked like a silent regression: `Worker.convert()` passes `self.item_abs_path` straight to `cjxl.exe`/`cjpegli.exe` with no ANSI check and no safe-copy fallback.
- **Finding: Investigated, not a bug.** Empirically tested the actual bundled binaries (`bin\win\libjxl\cjxl.exe` v0.11.1, `cjpegli.exe`) via the exact invocation path the app uses (`subprocess.Popen` with a list of args, i.e. `CreateProcessW`, not a shell command line) against a real Thai-character source filename. Both encoders succeeded (retcode 0, valid output produced, no errors) — confirmed via a real conversion, not inferred from code. A first attempt invoking `cjxl.exe` directly through `cmd.exe`'s own command-line parsing *did* fail ("The filename, directory name, or volume label syntax is incorrect.") — but that failure is `cmd.exe`'s own OEM-codepage argument mangling, not a `cjxl`/`cjpegli` defect; re-run through PowerShell with a literal Unicode argument, and again through Python's `subprocess.Popen(list)` (matching `core/process.py`'s `runProcess2`, the app's real invocation path), both succeeded cleanly. Conclusion: the currently-bundled libjxl build genuinely supports non-ANSI Windows paths, so the check's removal correctly reflects reality rather than reintroducing a bug — no code change needed. The orphaned `isANSICompatible()` helper and its test are now pure dead code (nothing production calls them) and could be deleted as tidiness, but leaving them is harmless; not treated as a bug.

---

## 2. Actions Taken

1. **Fixed Duplicate Metadata Extension Bug:**
   - Removed redundant `.extend(metadata.getArgs(...))` call on `png_post["args"]` in `core/downscale.py`.
   - Added explanatory documentation in `decodeAndDownscale()` indicating `png_post["args"]` already includes metadata arguments.

2. **Added Unit Test Coverage:**
   - Created `test_decodeAndDownscale_png_post_does_not_duplicate_metadata_args` in `tests/core/test_downscale.py`.
   - Verified test execution via `python -m pytest tests/core/test_downscale.py -q` (32 tests passing).

3. **Fixed Same Format JPEG Route Not Covering All JPEG Aliases:**
   - Changed `same_format_routes` in `output_tab.py`'s `getSettings()` from two hardcoded keys (`"jpg"`, `"jpeg"`) to a dict comprehension over `JPEG_ALIASES` (imported from `data/constants.py`), so the single JPEG Route control governs all 5 aliases.
   - Added `jfif`/`jif`/`jpe` assertions to `test_getSettings_same_format_routes` in `tests/ui/tabs/test_output_tab.py`.
   - Searched the project for the same hardcoded `"jpg"`/`"jpeg"` pair (outside tests) - no other occurrences found.

4. **Fixed JXL/AVIF Proxy Metadata Argument Staleness (Bug 3):**
   - In `decodeAndDownscale()`'s proxy branch, added `params["args"] = metadata.getArgs(params["enc"], metadata_mode)` immediately after `params["enc"]` is switched to `IMAGE_MAGICK_PATH`, so the downscale pass gets ImageMagick's own metadata args instead of the stale (always-`[]`) args computed against the original JXL/AVIF decoder.
   - Added `test_decodeAndDownscale_proxy_recomputes_metadata_args_for_imagemagick` in `tests/core/test_downscale.py`.
   - While verifying, found and fixed an unrelated pre-existing defect in `test_decodeAndDownscale_other`: its `@patch` parameter names didn't match the actual (bottom-up) mock injection order, so `params_fixture` was silently never the real fixture and every `mock_*` name pointed at the wrong mock. Reordered the parameter list to match actual injection order (confirmed against the correctly-ordered `test_decodeAndDownscale_png_post_does_not_duplicate_metadata_args` in the same file) - no assertions changed.
   - `TWINS:` searched `params["enc"]` reassignment sites and all `metadata.getArgs()` call sites project-wide - found 0 other sites with the same staleness pattern (one other reassignment, in `core/worker.py:393`, sets `args` from the same `encoder` in the same statement group and is immediately superseded when routed through `decodeAndDownscale()`, so it isn't exposed to this bug).
   - Verified via `python -m pytest tests/ -q` (976 tests passing).
