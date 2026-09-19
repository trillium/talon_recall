# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Syncing with the live config

This repo is a standalone mirror of `~/.talon/user/trillium_talon/plugin/recall/`.
The mirror drifts: run `.scripts/sync_from_active.sh --dry-run` first when the
brief references files that do not exist here. Never edit `~/.talon` directly.
`saved_windows.json` is live personal data and is never synced.

## Tests

`python3 -m pytest .tests/` — self-contained (fake `talon` in sys.modules,
no Talon running). Tests live in dot-prefixed `.tests/` so the Talon runtime
loader skips them; keep it that way. See `pyproject.toml`.

## Perf sharp edge

`ui.apps()` / `a.windows()` cross into the mac accessibility API per call.
Never call them per saved window inside a draw pass — resolve against
`recall_commands.get_windows_by_id()`, which caches the map across draws
and invalidates on win_open/win_close (ids are stable, rect reads stay live).
(Talon Rect has no value `__eq__`; compare `(x, y, w, h)` tuples.)

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
