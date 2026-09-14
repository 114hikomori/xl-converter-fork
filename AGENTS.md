# Agent Skills (OpenCode)

This machine's skills are installed in the global opencode config
(`C:\Users\Lenovo\.config\opencode\skills\<skill-name>\SKILL.md`).
There is no in-repo `.opencode/` directory in this repo.

## Core Rules

- If a task matches a skill, invoke it with the `skill` tool before acting.
- Follow the skill workflow strictly; do not partially apply it.
- Never skip required steps such as spec, plan, or test when a skill demands them.

## Intent → Skill Mapping

Map the user's intent to the matching skill automatically:

- Feature / new functionality → `spec-driven-development`, then `incremental-implementation` and `test-driven-development`
- Planning / breakdown → `planning-and-task-breakdown`
- Bug / failure / unexpected behavior → `debugging-and-error-recovery`
- Code review → `code-review-and-quality`
- Refactoring / simplification → `code-simplification`
- API or interface design → `api-and-interface-design`
- UI work → `frontend-ui-engineering`

## Execution Model

For every request:

1. Determine if any skill applies (even a small chance).
2. Load the skill with `skill({ name: "<skill-name>" })`.
3. Follow the skill workflow exactly.
4. Only proceed to implementation once required steps are complete.

# Fable family (think / act / prove)
- Before any non-trivial multi-step task, apply the fable-method loop; for tasks that will
  run unattended or fan out subagents, use fable-loop.
- After completing substantive work, or whenever any agent/tool claims work is done,
  run a fable-judge pass before presenting it as finished. "Did that actually work?" = fable-judge.

---

# xl-converter-fork — project layer

Read the root `D:\.Github_Project\.repo\CLAUDE.md` first. It defines the
shared rules for every repo (MCP tools, git safety, session discipline,
evidence rules). This file adds only what is specific to this repository.

## What this repo is

Fork of `JacobDev1/xl-converter` — a Python + PySide6 image converter GUI.
All fork-only fixes live in this fork's `stable` branch; the upstream owner
does not accept agent-generated reports (see Boundaries).

## Tech stack

- Python 3.12.10, PySide6 6.10.3 (Qt6). Deps: `requirements.txt`;
  `requirements_test.txt` adds test deps.
- External converters ship as bundled binaries under `bin/win/`:
  libjxl (`cjxl`, `djxl`, `jxlinfo`, `cjpegli`), libavif (`avifenc`,
  `avifdec`), imagemagick, exiftool, oxipng, pngquant, jpegtran.
  Path constants: `data/constants.py`.
- Two virtualenvs — do not mix them:
  - `env_dev` — running the app and the test suite.
  - `env_build` — PyInstaller builds only (`build.py` must run from here).

## Commands (run from repo root)

- Full test suite: `.\env_dev\Scripts\python.exe -m pytest tests -q`
  (~11 s, mocked, no real conversions).
- Filtered tests: `.\env_dev\Scripts\python.exe test.py -f tests/core/test_worker.py -k <keyword>`
- Release gate (real conversions, needs every `bin/win/` binary):
  `.\env_dev\Scripts\python.exe test_convert.py` (several minutes).
- Portable build: `.\env_build\Scripts\python.exe build.py -b portable`
  → `dist/xl-converter-win-<ver>-x86_64-portable.7z`.
  Rebuild after any user-facing fix so the owner's portable artifact
  actually contains it.

## Code conventions born from this codebase

- Failures raise `FileException("<ID>", msg)` with a family-prefixed ID:
  `C*` convert, `D*` downscale, `SL*` smallestLossless, `P*`
  post-conversion routines, `E*` exiftool, `F*`/`Proxy*` cleanup,
  `S*` timestamps. Reuse the existing family letter for the area you touch.
- Housekeeping failures must never destroy a successful result: fail loudly
  only after the output is promoted to its final name; otherwise use
  `cleanUp()` (best-effort, never raises, logs failures).
- Every fallible step between creating a tmp file and its dedicated cleanup
  must be covered (`try/finally` or a `delete_if_canceled` list) — the
  orphaned-tmp class of bugs lives in exactly these gaps.
- GUI state persists through `WidgetManager` (widget name → JSON in
  `%LOCALAPPDATA%\xl-converter\`). Persistence tests must round-trip
  through the real `WidgetManager`, not the patched app fixture.
- Tests: assert on real call arguments (not mock truthiness), never leave
  duplicate dict keys in fixtures, and match the existing style —
  `tests/core/test_worker.py` fixtures are the reference.

## Boundaries

- `bin/`, `dist/`, `_sample_img/` are gitignored — commit code and docs only.
- Never file issues/PRs/reports on `JacobDev1/xl-converter` from
  agent-driven work — the owner rejects AI-generated reports (issues
  #157–#163 were all closed NOT_PLANNED on 2026-09-07). Hand findings to
  the human owner instead.
- `%LOCALAPPDATA%\xl-converter\*.json` holds the owner's live settings —
  read only, never edit while diagnosing.
- Push/PR only with explicit in-the-moment go-ahead (root CLAUDE.md rule).

## Project map

- `FORK_MASTER_PLAN.md` — owner constraints, architecture map,
  merge-friendliness policy, and the progress log (one checkpoint line
  appended per completed step). Start here.
- `bug_inspection_summary.md` / `bug_inspection_summary_2.md` — audit
  rounds, per-finding detail and fix status.
- `PNG_ENCODER_MIGRATION_PLAN.md` — Track A plan (fork feature work).
