---
name: qm-opx
description: >-
  Resolves the installed qm-qua / qualang-tools / QOP versions for PyCtrl, fetches the
  matching Quantum Machines documentation, and produces a small version-locked context
  (API summary + repo-specific checklist) for QM/OPX work. Use whenever working on
  hwdrivers/qm_opx/**, configs/qm_*.toml, QUA programs, baking, the OPX driver, or when
  the user mentions QM, OPX, qm-qua, qualang-tools, QUA, or baked pulses.
---

# qm-opx workflow

PyCtrl drives a Quantum Machines OPX+. The QM Python stack changes often and breaks
quietly. The agent must not reason from memory or from "latest docs" — always pin to
the installed versions first.

## Invocation contract

- This skill is the preferred entry point for any QM/OPX task in this repo.
- When dispatched as a **subagent**, callers MUST pass `readonly: true`. This skill
  only investigates and reports; the parent agent applies any edits.
- The subagent's deliverable is the **Report** template at the bottom of this file —
  short, structured, with explicit version pins and doc URLs.

## Workflow

Copy this checklist and tick items as you go:

```
- [ ] 1. Resolve installed versions
- [ ] 2. Pick the matching doc set
- [ ] 3. Read the user's actual task
- [ ] 4. Cross-check against repo state
- [ ] 5. Produce the Report
```

### 1. Resolve installed versions

Read, do not guess:

- `PYCTRL_env.yml` → look for `qm-qua` and `qualang-tools` pins.
- If the user has a live shell available, also surface:
  - `pip show qm-qua qualang-tools` (installed versions).
  - At runtime: `QuantumMachinesManager(...).version_dict()` for QOP/server versions.
- Note: OPX+ uses controller `type = "opx1"`. OPX1000 / FEM cluster uses a different
  schema and is **not** what this repo currently targets.

If versions cannot be resolved, stop and ask the user before proceeding.

### 2. Pick the matching doc set

Pin documentation lookups to the resolved versions, not "latest":

- qm-qua / QUA reference: `https://docs.quantum-machines.co/<version>/` — choose the
  page set that matches the installed `qm-qua` minor (e.g. `1.2/` for `qm-qua==1.2.6`).
- qualang-tools / bakery: `https://qua-platform.github.io/qua-libs/` and the
  `qualang_tools.bakery` API reference for the installed version.
- Changelog cross-check before claiming an API exists or behaves a given way.

Prefer fetching the specific page over dumping a whole section. Quote URLs in the
Report; do not paste large doc excerpts.

### 3. Read the user's actual task

State in one sentence what is being asked. Common categories in this repo:

- TOML config change (`configs/qm_base_config.toml`).
- Driver behaviour (`hwdrivers/qm_opx/qm_opx.py`).
- New QUA program / experiment (`experiments/**`).
- Baked pulse change.

### 4. Cross-check against repo state

For the task type, read the relevant repo files and compare against the version-matched
docs. Things to verify (non-exhaustive):

- TOML config:
  - Top-level `version` key: required pre-1.2.0, removed for `qm-qua >= 1.2.0`.
  - Pulse `waveforms` keys: `single` for single-input, `I`/`Q` for mixedInput.
  - Waveform `type`: `constant` → `sample` (scalar); `arbitrary` → `samples` (list).
  - Controller `type` matches hardware (`opx1` for OPX+).
  - Element `operations` reference existing pulse names.
- Driver:
  - `bake_all` uses `padding_method` and `sampling_rate` kwargs.
  - `seconds_to_cycles` semantics (1 cycle = 4 ns on OPX+).
  - `turn_outputs_on/off` lifecycle and `self._running_job`.
  - `Opx.close` halts the running job then closes `self._qm` (no `self.qmm.close()`).
- QUA program:
  - Stream processing API (`stream_processing`) matches installed `qm-qua`.
  - `play`/`measure`/`wait`/`align` argument order and types match the doc set.

### 5. Produce the Report

Return only the Report — no extra prose.

## Report template

```
## qm-opx report

Task: <one-line restatement>

Pinned versions
- qm-qua:       <X.Y.Z from PYCTRL_env.yml / pip>
- qualang-tools: <X.Y.Z>
- QOP/server:   <if known, else "unknown — runtime check needed">

Docs consulted
- <topic>: <URL pinned to matching version>
- <topic>: <URL pinned to matching version>

Findings
- <fact 1 about the relevant code/config, with file path>
- <fact 2 ...>

Mismatches / risks
- <gap between repo and version-matched docs, if any>

Suggested next steps (for the parent agent, not executed here)
- <concrete edit 1: file + what to change + why>
- <concrete edit 2: ...>

Open questions for the user
- <if any version, hardware, or intent is ambiguous>
```

## What this skill does NOT do

- Apply edits. The subagent runs `readonly: true`; edits are the parent agent's job.
- Replace hardware testing. Anything timing- or pulse-shape-dependent must be
  validated against the OPX (or the QM simulator) on the lab LAN.
- Substitute for talking to the user when intent is unclear.
