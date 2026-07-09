---
name: pyctrl-docs
description: >-
  Writes and reviews PyCtrl documentation (docstrings, module headers, READMEs) with a
  functional, usage-first focus: what a function/method/class does, when to use it, what
  the user gets back (return meaning, units, shapes), side effects, and hardware/data
  contracts — not code restatement. Use when documenting drivers, experiments, toolbox
  APIs, adding a new instrument/experiment, refreshing a README, or doing a docs pass.
---

# pyctrl-docs

Documentation in PyCtrl exists to give a **lab user real usage insight**, not to mirror the
code. The reader wants: *what does this give me, when do I call it, what happens to the
hardware/data?* Favor functionality over implementation.

Apply `.cursor/rules/pyctrl-docs.mdc` (style guardrails) on every doc edit; this skill is the
full workflow for larger documentation tasks.

## Workflow

```
- [ ] 1. Identify the audience-facing surface (public class/method/function/README)
- [ ] 2. Read the code to extract the real contract (returns, units, side effects, failures)
- [ ] 3. Write outcome-first docs using the templates below
- [ ] 4. Strip anything that only restates type hints or narrates implementation
- [ ] 5. Verify against the checklist
```

### 1. Scope

Document the **public** surface a user touches:

- Drivers: the class + the methods called through `Session` (connect/measure/move/close).
- Experiments: `setup / pre_run / run / plot / save` and the matching `*Data` class.
- Toolbox: functions meant to be imported and reused.

Skip private `_helpers`, trivial getters, and `__init__` plumbing unless behavior surprises.

### 2. Extract the real contract

Before writing, find from the code:

- **Return meaning**: not "a numpy array" but "counts per point, shape `(nx, ny)`, in Hz".
- **Units**: ns, V, THz, counts, clock cycles (1 cycle = 4 ns on OPX+).
- **Side effects**: opens a QUA job, blocks until halt, writes HDF5, moves a stage, mutates
  `self.data`, holds hardware state until `close()`.
- **Preconditions**: needs an open `Session`, a TOML key, a connected device, a prior `setup()`.
- **Typical failures**: the one or two `RuntimeError`/config mistakes a user actually hits.

## Templates

### Function / method docstring

```python
def turn_outputs_on(self, elements, t_s):
    """
    Drive the given OPX elements continuously until explicitly stopped.

    Starts an infinite QUA loop that plays the constant pulse on each element; use this
    for steady-state output (e.g. holding an AOM on). The job runs in the background and
    is stored on ``self._running_job``; call ``turn_outputs_off`` to halt it.

    t_s is the per-pulse duration in seconds (converted to OPX clock cycles internally).

    Returns nothing. Leaves the OPX actively outputting until halted.
    """
```

What makes it good: outcome first, side effect (background job) named, unit on `t_s`, the
"what you get" is the *hardware state*, and the stop path is cross-referenced.

### Class docstring

```python
class ScanXY_Z(GenericExp):
    """
    Raster an XY grid and, at each point, run a cavity z-scan and record fluorescence.

    Lifecycle (from GenericExp): setup -> pre_run -> run -> plot -> save. After ``run``,
    results live on ``self.data`` (a ``ScanXY_ZData``): ``counts`` shaped (ny, nx, nz),
    plus the x/y/z axes. ``plot`` builds the Plotly figures; ``save`` writes HDF5.

    Get hardware via the shared ``Session`` (``self.session.get(...)``); never construct
    drivers directly.
    """
```

### README (module/driver/experiment)

Mirror the repo root README shape: **what it does → how to use → gotchas**. Not an API list.

```markdown
# <Thing>

One or two sentences: what it controls / computes and why a user reaches for it.

## Use it

```python
# smallest real example, via Session where hardware is involved
```

## Notes
- Config keys it reads (in `instr_config` / `*.local.toml`).
- Units, ranges, and any state left behind (open job, held output, files written).
```

## Checklist

- [ ] First line says what it does / produces, in lab terms.
- [ ] Return documented by **meaning + units + shape**, not just type.
- [ ] Side effects and hardware/data state changes stated.
- [ ] Only non-obvious parameters get a line (units/constraints), no type-hint echo.
- [ ] Preconditions named (Session, TOML key, connected device, prior setup).
- [ ] No "see code", no step-by-step implementation narration.
- [ ] Private/trivial members left undocumented unless surprising.

## Anti-patterns

- `"""Parameters: x, y. Returns: array."""` — restates signature, adds nothing.
- README that is just a directory tree.
- Documenting `__init__` argument-by-argument when the class docstring already covers usage.
- Explaining *how* the loop works instead of *what the caller gets*.
