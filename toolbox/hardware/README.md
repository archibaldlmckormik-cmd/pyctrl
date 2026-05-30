# toolbox.hardware

Lab routines that **orchestrate several instruments at once** — the logic that sits above a
single driver but below a full experiment. If a helper needs a live OPX, DAC, shutter, etc.
working together, it lives here.

## How it fits in PyCtrl

```text
experiment ──> toolbox.hardware.<routine>(opx, dac, shutter, ...) ──> coordinated hardware action
                         ▲
                         └── drivers are passed IN (from a Session); this layer never opens them
```

These routines are the reusable "moves" an experiment performs (e.g. relocking the cavity)
without each experiment re-implementing the multi-instrument choreography.

## What's inside

| Module | What you get |
|--------|--------------|
| `oneway_relock.py` | Cavity relock helpers. `oneway_relock(...)` sweeps the cavity z-voltage and accumulates APD counts at each step (no analysis). `oneway_relock_fit(...)` adds a Lorentzian fit and returns `(counts, center_v)`. `oneway_relock_mass(...)` instead returns `(counts, center_v)` with `center_v` from a counts-weighted center of mass. Both estimators fall back to the max-signal voltage if the fit/sum is degenerate. |

## Use it

Pass in already-opened drivers from a `Session`; the routine drives them and returns results:

```python
from pyctrl.hwdrivers import Session
from pyctrl.toolbox.hardware.oneway_relock import oneway_relock

with Session() as session:
    opx = session.get("opx")        # OPX must have an open QM
    dac = session.get("dac")
    shutter = session.get("shutter")

    counts = oneway_relock(
        opx, dac, shutter,
        z_targets=z_volts,          # cavity voltages to step through
        duration_s=0.1,             # optical drive time per step
        AOMg1=1.0,                  # which laser line(s) to fire
    )
    # counts: fluorescence per z step (acquired via opx.quasicw_counts)
```

Side effects to expect: the cavity DAC is ramped at each step, the shutter is opened for the
sweep and closed afterward, and the DAC returns to the first sweep voltage when done.

## Notes

- **Drivers in, never constructed here.** Routines take `opx`, `dac`, `shutter`, … as
  arguments so the caller controls the `Session` lifecycle and closing.
- Counts come from `opx.quasicw_counts` (quasi-CW: count while the optical drive is on,
  chunked on the OPX); the OPX must already have an open quantum machine.
- Fitting/model math is reused from `toolbox.software.common_mathfuns` (e.g. `lorentzian`),
  keeping the numerical core on the software side.

## Extend it

- Put a new routine here only if it **coordinates instruments**; pure numerics/IO belong in
  [`toolbox/software/`](../software/README.md).
- Accept drivers as parameters (don't import `Session` or build drivers); state the required
  hardware state (e.g. "OPX with open QM") and any state left behind (shutter, DAC position).
