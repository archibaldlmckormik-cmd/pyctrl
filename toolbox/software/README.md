# toolbox.software

The pure-software side of PyCtrl: it holds the **experiment data model**, reads/writes those
results to disk, turns them into lab-journal reports and plots, and resolves config paths.
Nothing here talks to an instrument, so it all runs without hardware (handy for replotting and
analysis on any machine).

## What's inside

| Module | What you get |
|--------|--------------|
| `datamanagement/datastructures.py` | The `*Data` classes (`ScanXY_ZData`, `ScanHWP_ZData`, `RfSpectraData`) and their building blocks. Each carries the experiment's arrays + metadata and knows how to `save()` / `load()` itself as HDF5. |
| `datamanagement/dataparsing.py` | The HDF5 serializer underneath the data classes: writes any object tree to type-tagged groups and restores it without running `__init__`. You rarely call it directly. |
| `common_mathfuns.py` | Fit/model functions and noise: `lorentzian`, `gaussian`, `gaussian2d`, `fano`, `addnoise`. |
| `cuboid_slice_view.py` | `cuboid_slice_view(volume, axis)` → interactive Plotly heatmap that slides through a 3D volume. |
| `save_to_html.py` | Append a measurement block (heading, tag, interactive plots) to the **daily lab-journal HTML**. |
| `save_to_pptx.py` | Append the same figures to the **daily lab-journal PowerPoint** (static PNGs). |
| `loadopxconfig.py` | `load_opx_config()` → the QM/OPX TOML as a nested dict (lists→tuples). |
| `path_config.py` | Resolve lab paths from `configs/path_config(.local).toml`: `get_datapath`, `get_labjournalpath`, `get_logspath`, `get_qmconfigpath`. |
| `logging_config.py` | `setup_logging()` — configure the `pyctrl` logger (daily file under `logspath`, console). Not called on import. |

## Use it

**Data classes — produce, save, reload (no hardware needed):**

```python
from pyctrl.toolbox.software.datamanagement import datastructures as ds

data = ds.ScanXY_ZData()          # picks its own dated HDF5 filename on creation
data.signals["counts"] = counts   # fill arrays + metadata
data.save()                       # writes <datapath>/ScanXY_ZData/<YYYYMMDD>/..._NNN.h5

later = ds.ScanXY_ZData.load()    # no path → file picker; or load("path/to.h5")
```

`save()` never silently clobbers: if the target exists it bumps the `_NNN` suffix (pass
`overwrite=True` to replace). `load()` rebuilds the object **without** running `__init__`, so
it works purely from the stored tree.

**Math:**

```python
from pyctrl.toolbox.software import common_mathfuns as cmf
z = cmf.gaussian2d(x, y, center=(6, 4), fwhm=(2, 1), angle=np.pi/3)  # 2D surface
noisy = cmf.addnoise(z, std_dev=0.1)                                  # additive Gaussian noise
```

**Reporting** (usually called for you by `GenericExp.plot_and_log`):

```python
from pyctrl.toolbox.software.save_to_html import save_to_html
save_to_html(data, figures)   # appends one section to today's lab-journal HTML, returns its path
```

**Logging** (once per notebook kernel, before hardware):

```python
import pyctrl
pyctrl.setup_logging()   # or: from pyctrl.toolbox.software.logging_config import setup_logging
```

## Notes

- Output locations come from `path_config`, i.e. from `configs/path_config(.local).toml` — not
  hardcoded. `get_datapath` (HDF5 root), `get_labjournalpath` (HTML/PPTX root),
  `get_logspath` (daily `pyctrl_YYYY-MM-DD.log` files), `get_qmconfigpath` (OPX config).
- `*Data` files land under `<datapath>/<ClassName>/<YYYYMMDD>/<ClassName>_<date>_<NNN>.h5`.
- `save_to_html` opens the journal in Microsoft Edge **only** on the first write that creates
  the day's file; later appends that day don't relaunch the browser.
- Reporting/plotting need `plotly` (HTML) and `python-pptx` + `kaleido` (PPTX); these are
  imported lazily so the rest of `software` works without them.

## Extend it

- Keep this side **driver-free** — no `hwdrivers` imports. If your helper needs a live
  instrument, it belongs in [`toolbox/hardware/`](../hardware/README.md).
- New experiment data? Add a `*Data` class here (subclass the shared `ExpData` base) so it
  inherits dated-filename + HDF5 `save`/`load`, and pair it with a `GenericExp` subclass in
  `experiments/`.
- Reusable fit/model functions go in `common_mathfuns.py`; document return **meaning + units**,
  not just the type.
