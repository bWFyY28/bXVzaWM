# Repository Guidelines

## Project Structure & Module Organization

Keep the original project and display name **`bXVzaVM`** exactly, including capitalization. `bxvzm` is the Python package and CLI alias, not a replacement project name.

The first implementation milestone now provides packaging, configuration, a SQLite migration foundation, and a starter TUI. Read `README.md` and `PLAN.md` before extending bXVzaVM. Use `src/bxvzm/` for UI, catalog adapters, import verification, SQLite persistence, and playback modules. Put Textual CSS under `src/bxvzm/themes/` and automated checks under `tests/`. Store user audio and databases outside the repository.

## Keeping Decisions Current

Whenever an idea or decision changes the project scope, behavior, architecture, dependencies, storage, or workflow, update **both `PLAN.md` and `AGENTS.md` in the same change**. Keep their decisions consistent with the implementation; record unfinished work and validation limits in `PLAN.md`. Update `README.md` whenever user-facing setup or behavior changes. Preserve these local documents even though Git ignores them and related agent/planning artifacts.

## Personal-Use Scope

This is a personal, single-user application. Favor straightforward modules and a small SQLite schema. Add abstractions only when an implemented feature needs them; avoid speculative infrastructure, service layers, plugin systems, account management, and enterprise features. Keep standard security practical: validate paths and provider URLs, safely extract archives with size limits, use parameterized SQL, keep credentials out of source control, and preserve original audio. Test meaningful data-integrity and security cases without elaborate test infrastructure.

## Build, Test, and Development Commands

Use Python 3.13 and a project-local `.venv`; recreate it when switching between Windows and WSL. Install the pinned requirements with `python -m pip install -r requirements/dev.txt`, then install the package with `python -m pip install --no-deps --no-build-isolation -e ".[dev]"`. `bxvzm` starts the starter TUI; `bxvzm --library PATH --check` initializes and remembers an external library without starting the UI. Run `python -m pytest`, `python -m ruff check .`, and `python -m ruff format --check .` for validation. `docker compose run --rm checks` repeats these in Docker. Dependency installation and Docker validation remain unverified in the restricted bootstrap session; standard-library tests can run with `PYTHONPATH=src` and `python -m unittest discover -s tests -v`.

## Coding Style & Naming Conventions

Use four-space indentation, type hints at module boundaries, `snake_case` functions/modules, and `PascalCase` classes. Keep network, extraction, hashing, and playback I/O off the UI thread. Separate provider metadata from local file metadata. Use Textual 8.1.1, pin dependencies, and isolate development tools from runtime requirements.

## Testing Guidelines

Use pytest and Textual's testing facilities; name files `test_*.py`. Mock remote catalogs and playback for deterministic tests. Prioritize album edition conflicts, missing tracks, duplicate files, multi-disc releases, archive traversal, interrupted imports, export, and relocation. No numeric coverage target is established. Manually verify native Windows playback; Docker checks do not replace that validation.

## Commit & Pull Request Guidelines

No Git history is available to establish existing conventions. Use short imperative messages, preferably `docs:`, `feat:`, or `fix:` prefixes. PRs should explain behavior changes, relevant issues, validation, and limitations. Include terminal screenshots for visual changes; update documentation when commands or storage behavior changes.

## Data & Integration Rules

Keep audio files on disk and relative paths in SQLite. Preserve source audio and edition evidence. Hold uncertain imports for review. Never infer clean/explicit status from absent metadata. Use manual DoubleDouble browser handoff. Keep `.venv`, credentials, audio, databases, and staging artifacts out of version control. Preserve any existing `AGENTS.md` during guide-generation tasks.
