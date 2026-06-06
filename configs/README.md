# Author: yannik fontana, created: 05.05.2026
# Config files

This folder holds TOML configuration for PyCtrl.

## Tracked defaults vs machine-local overrides

| File | Purpose |
|------|---------|
| `path_config.toml` | Example paths (data, lab journal, logs, QM config path). Committed. |
| `instr_config.toml` | Example instrument registry and connection settings. Committed. |
| `qm_base_config.toml` | Quantum Machine / OPX configuration. Committed. |
| `path_config.local.toml` | **This machine's** paths. Not committed. |
| `instr_config.local.toml` | **This machine's** instruments. Not committed. |

**Runtime rule:** if `*.local.toml` exists, the code loads **only** that file (no merge with the tracked `.toml`). If it does not exist, the tracked `.toml` is used so a fresh clone has a minimal working template.

QM does not use a separate `.local.toml`. Set `qmconfigpath` in `path_config.local.toml` to point at the QM file for this PC (often the tracked `qm_base_config.toml`, or another path).

Passing an explicit config path to `Session(..., config_path=...)` bypasses this resolution entirely.

## Onboarding a new machine

1. Clone the repo and install the environment as usual.

2. Create local overrides (do not edit the tracked `.toml` files for machine-specific values):

   ```text
   configs/path_config.toml   →  copy to  configs/path_config.local.toml
   configs/instr_config.toml  →  copy to  configs/instr_config.local.toml
   ```

3. Edit **`path_config.local.toml`**:
   - `datapath` — where experiment data is stored on this PC.
   - `labjournalpath` — lab journal / HTML export root.
   - `logspath` — folder for PyCtrl log files (`pyctrl_YYYY-MM-DD.log`; required).
   - `qmconfigpath` — path to the QM config file (e.g. `configs/qm_base_config.toml` or a machine-specific copy elsewhere).

4. Edit **`instr_config.local.toml`**:
   - Enable/disable instruments, addresses, ports, and any per-driver settings for hardware attached to this machine.

5. Confirm the app sees your files (log lines on first load), e.g. `Using path config: .../path_config.local.toml`.

6. Optional: adjust `qm_base_config.toml` only if you commit QM changes for everyone; otherwise point `qmconfigpath` at a local copy outside git.

`configs/*.local.toml` is listed in `.gitignore` — they must not be committed.

## Usage notes

- Keep instrument settings in `instr_config` (local on each machine).
- Keep filesystem paths in `path_config` (local on each machine).
- Avoid duplicating the same setting in both files.
- When adding a new instrument type to the project, update the tracked `instr_config.toml` template so new machines know the expected structure.

## Logging

PyCtrl does not configure logging on import. In a notebook or script, after path
config exists:

```python
import pyctrl
pyctrl.setup_logging()
```

Uses `logspath` from the resolved path config. See the main `README.md` for levels
and `PYCTRL_LOG`.
