# hwdrivers

The hardware layer of PyCtrl. It turns physical instruments (DAC, NI-DAQ, OPX+, ANC300,
wavemeter, shutter, scope, PicoHarp, power meter, spectrometer) into plain Python objects,
and hands them out through a single entry point: the `Session`.

## How it fits in PyCtrl

Experiments never talk to instruments directly. They ask a `Session` for what they need:

```text
experiment  ──>  Session.get("opx")  ──>  Opx driver  ──>  hardware
                     ▲
                     └── reads instr_config(.local).toml to know what exists and how to build it
```

- **One pool per run.** A `Session` is the instrument pool. It reads the instrument config
  TOML once, then builds each driver lazily (lazy means it only loads what it needs, along the way, instead of all at the begining) and caches it.
- **Config-driven, not hardcoded.** Which instruments exist, their COM ports / IPs / serials,
  and their options all come from `configs/instr_config.toml` (template) and
  `configs/instr_config.local.toml` (this machine, gitignored).
- **Closed surface.** `hwdrivers/__init__.py` exports only `Session`. Individual driver
  classes are intentionally *not* part of the public API — you reach them via `Session.get`.

## Use it

Always go through a `Session`, if possible inside a `with` block so every opened driver is closed cleanly:

```python
from pyctrl.hwdrivers import Session   # or: import pyctrl; pyctrl.Session()

with Session() as session:
    print(session.available_instruments)   # names you can pass to get(), nothing opened yet

    dac = session.get("dac")               # opens + caches the DAC on first call
    dac.voltage[1] = 0.5                   # same instance returned on later get("dac")

    wlm = session.get("wlm")               # frequencies in THz
# leaving the block closes all opened instruments
```

Key behaviors:

- **`session.available_instruments`** — names declared in the active config; reading it opens
  no hardware.
- **`session.get("<name>")`** — `<name>` is the **TOML table name** (e.g. `"opx"`, `"dac"`,
  `"wlm"`), not the class name. First call constructs the driver from its TOML keys; later
  calls return the **same** instance. Raises `RuntimeError` if the driver fails to build
  (bad port/IP, device offline, wrong config).
- **`with Session() as session:`** — on exit, `close_all()` calls `.close()` on every opened
  driver and logs (but does not raise) on individual close failures.
- **Custom config** — `Session(config_path=...)` bypasses the local/template resolution; handy
  for tests or a one-off rig.

## How it is built (so you extend it the same way)

Each instrument is **one subpackage** under `hwdrivers/<vendor>/`, exposing a driver class.
The `Session` binds the config string to that class via `CLASS_REGISTRY` in
`instrumentsession.py`, and builds it by unpacking the TOML table as keyword arguments:

```python
inst = cls(**cfg)   # every config key for that table becomes a constructor kwarg
```

That single line is the whole contract, and it dictates the philosophy below.

### The driver contract

A driver that plugs into `Session` must:

1. **Accept all settings as keyword arguments** that match its `instr_config` table keys.
   No hardcoded ports, IPs, serials, or gains in code — those live in `*.local.toml`.
2. **Expose `close()`** that releases the hardware (serial port, .NET handle, QM job, etc.).
   `Session.close_all()` relies on it; make it safe to call once.
3. **Open the resource on construction** (or on an explicit connect), and prefer a
   `validate_on_init` kwarg so a missing/offline device fails loudly and early.
4. **Present a functionality-first surface** — methods/properties named for what the user
   wants (`dac.voltage[1] = 0.5`, `shutter.open = True`), with units stated in docstrings
   (V, THz, ns, counts). See `.cursor/skills/pyctrl-docs/SKILL.md`.

### Adding a new instrument (checklist)

1. Create `hwdrivers/<vendor>/<driver>.py` with the driver class (kwargs in, `close()` out).
   Keep its `__init__.py` minimal — drivers stay private to the package.
2. Register it in `CLASS_REGISTRY` (`instrumentsession.py`): `"<name>": <DriverClass>`.
3. Add a `[<name>]` table to `configs/instr_config.toml` (template) with a `cls = "<name>"`
   line and the connection settings, and document any new keys in `configs/README.md`.
4. Put the real machine values in `configs/instr_config.local.toml`.
5. Add a `test_<driver>.py` next to the driver (the package already follows this pattern).

After that, `session.get("<name>")` just works — no experiment code needs to change.

## Notes

- `cls` in each TOML table is the registry key, **not** a Python path; an unknown `cls`
  makes `Session()` raise `KeyError` at load time (before any hardware is touched).
- Nested tables (e.g. `[wlm.ch1]`) are passed through as nested kwargs to the driver; only
  top-level tables with a valid `cls` become entries in `available_instruments`.
- Drivers are cached per `Session`, so two `get("opx")` calls share one connection. Use a new
  `Session` if you truly need a fresh device handle.
- Vendor SDK quirks (pythonnet/.NET, QM `qm-qua`, NI-DAQmx) stay **inside** each driver, so the
  rest of PyCtrl sees only clean Python. Keep it that way when extending.
