# The Lua runtime, one file per domain

Everything the harness reads or does inside the game is an `H.*` function in one of these files. They are
injected into the InGame Lua state together, in the order `MANIFEST` in `harness/runtime_source.py` lists them,
each as its own named chunk: a Lua error reads `events.lua:57:`, and the Lua 5.1 compiler limits (200 locals,
60 upvalues per function) apply per file. `runtime_source.py` is the only place that knows the order and the
files; `Game.ensure_runtime` and the tests both load through it. There is no generated monolith to keep in sync.

## Which file

The `MANIFEST` comments name each fragment's domain. In short: `bootstrap.lua` (version, the `H` table and the
state that survives a reload), `json.lua`, `helpers.lua` (localisation, enum and network-command helpers),
`events.lua` (event log, rosters, hooks), then the game domains -- empire, units, city views and actions, map,
diplomacy, policies, notifications, city strikes, unit orders, popup choosers, religion, deals, war,
city-states, trade routes, league, overviews, espionage, research, production, unit actions, combat and its
previews, step cost, tactical view, movement, turn state, victory, the reference rule book, briefing, assignments,
comparisons -- and `install.lua`, which runs last and installs the hooks.

A new `H.*` function goes into the file of its domain. Keep a domain's reads, legality checks and writes
together, and let aggregate reads (briefing, turn state) call the domain's functions rather than repeat them.

## Sharing between files

Each file is compiled alone, so a top-level `local` is visible only inside its file. A helper another file needs
goes through `H._ns`, which `bootstrap.lua` creates fresh on every injection:

```lua
-- at the END of the owner (helpers.lua):
H._ns.short = short
-- at the TOP of the consumer:
local L, short = H._ns.L, H._ns.short
```

The consumer must come after the owner in `MANIFEST`. Bodies never spell `H._ns.x`; they use the imported
local, so a body reads the same as it did in the single file. `H.*` functions need none of this: they are
looked up on `H` when called, in any order.

`tests/test_runtime_source.py` enforces the rest: a fragment compiled alone may read only the game's API,
Lua's builtins and `H` (a local another file declares, read as a global, fails the lint), every import has an
earlier export and every export an importer, and every chunk stays under the 5.1 limits. It needs `luac`
(Debian/Ubuntu: `apt install lua5.4`); `scripts/check.sh` refuses to run without it.

## Adding a fragment

1. Create the file here and add it to `MANIFEST` at the position its imports allow (after every owner it
   imports from) and before `install.lua`.
2. Import what it needs at its top, export what later files need at its end.
3. Bump `RUNTIME_VERSION` in `bootstrap.lua`.

Nothing else: the manifest is the package data list, the digest and the installer.

## Reloads

`RUNTIME_VERSION` goes up with **every** change to any file here (CHANGELOG.md, #26); commit subjects carry it
as `runtime vNNN`. Independently, `Game.ensure_runtime` compares the SHA-256 of the assembled source with
`H.source_hash` inside the game and re-injects on any difference, so a forgotten bump still reloads. The hash is
set by the installer after the last chunk: a load that fails midway leaves no hash, is never taken as current,
and the next call re-injects. `bootstrap.lua` carries the accumulated state (events, cursors, hook closures,
fog caches, standing moves, per-seat snapshots) from the previous `H` and rebuilds everything derived
(`_enum_names`, `_ns`); `install.lua` removes the previous handlers before adding the new ones, so an event
fires one handler after any number of reloads.

`generic_popup_shim.lua` (the GenericPopup state) and `audit.lua` (a raw event tap) are separate and are not
part of the runtime.
