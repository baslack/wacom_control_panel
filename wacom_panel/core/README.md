# `core/` — pure logic, models, persistence

Everything the app *knows how to do*, with **no Qt and no UI**. It depends only on
[`../backend`](../backend/README.md). Because it's Qt-free, the GUI view-models and the headless
CLI are interchangeable front-ends over these same functions — which is why `--dry-run` previews
exactly what the GUI applies.

```
core/
├── profile.py          # the data model: *Config dataclasses ⇄ JSON; ButtonAction grammar
├── engine.py           # Profile (+ live devices) → xsetwacom argv → run
├── mapping.py          # force-proportions / anchor / zoom / rotation math (pure)
├── store.py            # named profiles on disk + the active-profile pointer
├── persistence.py      # login autostart + systemd --user unit (pure renderers + side effects)
├── watcher.py          # hotplug watcher (pyudev, polling fallback)
├── pressure_presets.py # named pressure curves (built-ins + user)
└── pad_layout.py       # physical pad layout loaded from layouts/*.json
```

```mermaid
flowchart TD
    PROF["profile.py<br/>MappingConfig · PenConfig<br/>TouchConfig · PadConfig · ButtonAction"]
    ENG["engine.py"]
    MAP["mapping.py"]
    STORE["store.py"]
    PERS["persistence.py"]
    WATCH["watcher.py"]
    PP["pressure_presets.py"]
    PL["pad_layout.py"]

    ENG --> PROF
    ENG --> MAP
    ENG --> BK["(backend: xsetwacom, devices, displays)"]
    STORE --> PROF
    WATCH --> ENG
    WATCH --> STORE
    PERS -. "generates CLI hooks that call" .-> WATCH

    classDef c fill:#2e4030,stroke:#7ec27e,color:#fff
    class PROF,ENG,MAP,STORE,PERS,WATCH,PP,PL c
```

## `profile.py` — the data model

Plain `@dataclass`es that serialise to/from JSON; a `Profile` bundles one of each:

```mermaid
classDiagram
    class Profile {
        +str name
        +save(path)
        +load(path)
        +to_dict()
        +from_dict()
    }
    class MappingConfig {
        +output
        +force_proportions
        +rotate
        +mode
        +anchor
        +zoom
        +area
        +apply_to_touch
    }
    class PenConfig {
        +pressure_curve
        +threshold
        +button1
        +button2
        +button3
    }
    class TouchConfig {
        +enabled
        +gestures
        +scroll_distance
        +zoom_distance
        +tap_time
    }
    class PadConfig {
        +buttons
        +wheels
    }
    class ButtonAction {
        +kind
        +value
        +to_xsetwacom(momentary)
    }
    Profile --> MappingConfig
    Profile --> PenConfig
    Profile --> TouchConfig
    Profile --> PadConfig
    PenConfig --> ButtonAction
    PadConfig --> ButtonAction
```

`kind` is one of `button` / `doubleclick` / `key` / `disabled`; `buttons` and `wheels` are
`dict[str, ButtonAction]`.

**`ButtonAction.to_xsetwacom()` is the one place that knows the action-string grammar**, and it
encodes two hard-won rules:

- Mouse buttons emit the **held** form `button +N` (press-and-hold), because a bare `N` expands
  to `+N -N` (an instant click) and breaks click-and-drag.
- The touch **ring** asks for `momentary=True` → `+N -N`, because each ring detent is one
  discrete event and a never-released `+N` can't scroll.

`PadConfig` keys buttons by xsetwacom **button number** (string, for JSON friendliness) and the
ring by xsetwacom **wheel parameter** (`AbsWheelUp`/`Down`), so layouts stay generic.

## `engine.py` — config → commands → run

The shared heart. `profile_commands(profile, tablet, outputs)` = `mapping_commands` +
`pen_commands` + `touch_commands` + `pad_commands`, each a list of `xsetwacom` argv. `apply_*`
wraps that with execution (or returns the list under `dry_run`).

Mapping highlights:
- **`resolve_area`** recomputes the letterboxed area from [`mapping.py`](#mappingpy--the-math)
  when force-proportions is on, else uses the stored explicit area.
- **`tablet_native_area`** must probe the *true* size via `ResetArea` (then restore the previous
  area) and cache it — reading the current `Area` would shrink the tablet cumulatively on every
  Apply.
- Mapping (`Mode`/`Rotate`/`Area`/`MapToOutput`) is applied to **all pen tools together**, and
  to touch only when `apply_to_touch` is set.
- `detect_pad_buttons` / `parse_pad_buttons` discover the pad's real button numbers from
  `xsetwacom -s --get <pad> all`.

## `mapping.py` — the math

Pure integer/float geometry, no Qt, no subprocess:
- `target_area_aspect(output_aspect, rotate)` — reciprocal under `cw`/`ccw` (axes swap).
- `fit_rect(W, H, aspect)` — largest rect of `aspect` fitting `W×H` (the letterbox).
- `place_rect(...)` — anchor it (center / corners).
- `forced_area(...)` — ties it together with `zoom` ∈ (0,1], clamped to the tablet.

## `store.py` — profiles on disk

`~/.config/wacom-control-panel/` holds `state.json` (`{"active": name}`) and
`profiles/<slug>.json` (one `Profile` each). `ProfileStore` does CRUD + active selection;
`ensure_default()` guarantees at least one profile exists.

## `persistence.py` + `watcher.py` — auto-reapply

`xsetwacom` state is runtime-only. `persistence.py` writes, **with no root**, an XDG autostart
entry (runs `--apply-active` at login) and a `systemd --user` unit (runs `--watch`). Its
`render_*` methods are pure strings (unit-tested); `install`/`uninstall` do the side effects.
`watcher.py` reapplies the active profile when a Wacom device appears — event-driven via
`pyudev` when present, polling `xsetwacom --list devices` otherwise. See the persistence diagram
in the [top-level README](../../README.md#7-persistence-auto-reapply).

## `pressure_presets.py` & `pad_layout.py`

- **`pressure_presets.py`** — named `[x1,y1,x2,y2]` curves; built-ins (`Soft`/`Linear`/`Firm`)
  can't be deleted; user presets live in `pressure_presets.json`.
- **`pad_layout.py`** — loads a physical pad layout (which xsetwacom button is which key, plus
  the ring) from [`../layouts/*.json`](../layouts/README.md), matched to a tablet by name
  substring, with a generic flat fallback for unknown models. **Note:** these numbers are
  hardware-measured, not from libwacom — see the [hardware notes](../../README.md#9-hard-won-hardware-notes).

## Testing

`tests/test_mapping.py`, `test_phase3.py` (command building + config round-trips),
`test_store.py`, `test_persistence.py`, `test_pressure_presets.py`, `test_pad_layout.py` — all
pure, no device required.
