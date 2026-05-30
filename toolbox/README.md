# toolbox

Everything in PyCtrl that is **not** a hardware driver and **not** an experiment: data
structures, persistence, plotting/reporting, math, config access, and a few hardware-using
helper routines. Experiments and drivers lean on the toolbox; the toolbox never owns the
experiment lifecycle itself.

## How it fits in PyCtrl

```text
experiments ──uses──> toolbox.software   (data classes, save/load, plots, math, paths)
drivers     ──uses──> toolbox.software   (path_config, OPX config loader)
toolbox.hardware ──uses──> drivers       (multi-instrument lab routines)
```

The toolbox splits in two by **whether the code touches instruments**:

| Subpackage | Touches hardware? | What lives there | README |
|------------|-------------------|------------------|--------|
| [`software/`](software/README.md) | No | Data classes + HDF5 save/load, lab-journal HTML/PPTX, plotting, math, config/path resolution | [software/README.md](software/README.md) |
| [`hardware/`](hardware/README.md) | Yes | Routines that orchestrate several drivers (e.g. cavity relock) | [hardware/README.md](hardware/README.md) |

Rule of thumb: **pure Python / files / numpy → `software/`; needs a live instrument → `hardware/`.**

## Use it

Import the piece you need; nothing here requires a `Session` unless it lives in `hardware/`:

```python
from toolbox.software import common_mathfuns as cmf      # math: gaussian, lorentzian, addnoise...
from toolbox.software.datamanagement import datastructures as ds  # *Data classes (save/load)
from toolbox.software.path_config import get_datapath     # resolved lab paths
```

For what each side offers and how to extend it, follow the subpackage READMEs above.

## Extend it (keep the split clean)

- New **pure** helper (math, IO, plotting, a data class) → `software/`, no driver imports.
- New **lab routine** that drives instruments → `hardware/`, taking drivers as arguments
  (never constructing them; the caller passes them in from a `Session`).
- Keep machine-specific values out of code — paths and settings come from
  `configs/*.toml` via `toolbox.software.path_config`.
