# PyCtrl

Python control stack for the NV/cavity setup: instrument drivers, experiment
classes, data structures, and plotting helpers. Replaces the legacy MATLAB
scripts under `NVAFM/Useful scripts/`.

## What it does

- **Drives the hardware** (DAC, NI-DAQ, OPX, ANC300, WLM, shutter, scope,
  PicoHarp, power meter, spectrometer) through one uniform `Session`.
- **Runs experiments** as classes (`GenericExp` subclasses) with a fixed
  lifecycle: `setup → pre_run → run → plot → save`.
- **Persists results** to HDF5 plus an auto-built HTML lab journal with
  Plotly figures.

## Layout

The repository folder itself **is** the importable package `pyctrl`:

```text
pyctrl/             <- this folder == the `pyctrl` package (git root)
  __init__.py       Package entry point (exposes Session, __version__)
  pyproject.toml    Makes the repo installable as `pyctrl` (editable dev install)
  configs/          TOML configs (committed templates + per-machine *.local.toml)
  hwdrivers/        One subpackage per instrument + Session (instrument pool)
  experiments/      GenericExp + concrete experiments (nonresonant/, calibration/)
  toolbox/          software/ (data, plotting, IO) and hardware/ (relock, etc.)
  PYCTRL_env.yml    Conda env spec (env name: pyctrl)
```

## How to use

### 1. Set up the environment (once per machine)

```powershell
conda env create -f PYCTRL_env.yml
conda activate pyctrl
```

This also installs PyCtrl itself in **editable mode** (see the `pip:` section of
`PYCTRL_env.yml`), so `import pyctrl` works from any directory and from notebooks.
If you build the environment some other way, or `import pyctrl` fails, run the
editable install once from this folder (the one containing `pyproject.toml`):

```powershell
pip install -e .
```

Editable means your edits are picked up immediately — there is **nothing to
re-install while developing**, even though the package is "installed". Adding a
new sub-package (a folder with `__init__.py`) under `hwdrivers/`, `toolbox/`,
etc. just works as `pyctrl.<...>`; no `pyproject.toml` change is needed for
day-to-day development.

### 2. Create machine-local configs

Copy `configs/path_config.toml` → `configs/path_config.local.toml` and
`configs/instr_config.toml` → `configs/instr_config.local.toml`, then edit
the local copies (paths, COM ports, IPs). See `configs/README.md` for
details — the local files are gitignored. Include **`logspath`** (folder for
PyCtrl log files) in `path_config.local.toml`.

### 3. Logging (notebooks and scripts)

`import pyctrl` does **not** turn logging on. Call once per kernel (first cell
is fine; re-running the cell replaces handlers safely):

```python
import pyctrl

pyctrl.setup_logging()  # INFO → daily file; WARNING+ → console
```

Log files: `{logspath}/pyctrl_YYYY-MM-DD.log` (date from each message’s time, so
long sessions roll over at midnight). Override levels or directory:

```python
pyctrl.setup_logging(
    log_level="DEBUG",
    log_level_file="DEBUG",
    log_level_console="ERROR",
    log_dir=r"D:/tmp/pyctrl_logs",
)
```

Disable setup with `PYCTRL_LOG=0` or `setup_logging(enabled=False)`.

Tear down handlers and close the log file (e.g. end of notebook session):

```python
pyctrl.shutdown_logging()
```

### 4. Run an experiment

Always open hardware through a `Session` and use a `with` block so drivers
are closed cleanly:

```python
import pyctrl
from pyctrl.experiments.nonresonant.scanhwp_z import ScanHWP_Z

with pyctrl.Session() as session:
    exp = ScanHWP_Z(session)
    exp.run()
    exp.plot_and_log()   # writes the lab journal HTML
    exp.save()           # writes HDF5
```

All internal modules are imported with the `pyctrl.` prefix
(`from pyctrl.toolbox.software import common_mathfuns`,
`from pyctrl.hwdrivers.instrumentsession import Session`, …). `pyctrl.Session`
is a convenience re-export of `pyctrl.hwdrivers.Session`.

Inside an experiment, grab instruments via `self.session.get("<name>")`
(name matches the TOML table, e.g. `"wlm"`, `"dac"`, `"opx"`). The same
session returns the **same** driver instance on every call — never
instantiate drivers directly.

### 5. Reload saved data

Every `*Data` class in `toolbox/software/datamanagement/datastructures.py`
has a matching `.load()` classmethod for replotting or analysis without
hardware.

## Three cardinal rules for expanding PyCtrl

1. **Hardware always goes through `Session`.** Add a new driver as a
   subpackage of `hwdrivers/<vendor>/`, register it in
   `CLASS_REGISTRY` inside `hwdrivers/instrumentsession.py`, and add a
   `[<name>]` table in `configs/instr_config.toml`. Drivers must expose a
   `close()` method and accept all settings as keyword arguments
   (TOML-driven, no hardcoded ports/IPs).

2. **New experiment = new `GenericExp` subclass + matching `*Data`
   dataclass.** Override `setup`, `pre_run`, `run`, and the classmethod
   `plot(data)`. Store everything you want saved on `self.data`; never
   pickle ad-hoc state. The dataclass lives in
   `toolbox/software/datamanagement/datastructures.py`.

3. **No machine-specific values in tracked code.** Paths, addresses,
   serial numbers, channel assignments, PID gains, etc. belong in
   `*.local.toml`. The tracked `.toml` files are templates only. If you
   need a new setting, add it to the template *and* document it briefly in
   `configs/README.md`.
