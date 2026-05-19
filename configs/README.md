# Author: yannik fontana, created: 05.05.2026
# Config Files

This folder contains project-level TOML configuration files.

- `instr_config.toml`:
  Instrument defaults and connection parameters used by `hwdrivers.instrumentsession.Session`.
  Update this file when adding/removing instruments or changing hardware settings.

- `path_config.toml`:
  Frequently used filesystem paths for routines and scripts (data import/export, logs, temp files, etc.).
  Keep this separate from instrument settings to avoid mixing hardware config with path/layout config.

## Usage Notes

- Keep instrument-specific values in `instr_config.toml` only.
- Keep reusable path values in `path_config.toml`.
- Use clear section names and comments; avoid duplicating the same setting in both files.
