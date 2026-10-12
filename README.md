# CanSat Bahrain 2026 — mission brief, plan, and a working mission demo

A single-page brief on the CanSat Bahrain 2026 competition, a week-by-week plan for a team
entering it, and a complete simulated mission showing the engineering end to end.

**Live site:** https://0xali1.github.io/cansat-bahrain-2026/

## What is here

| Path | What it is |
|---|---|
| `index.html` | The brief: what the competition is, how it is scored, the plan, the demo results |
| `plan.html` | The full plan — role split, architecture, schedule, questions for the organisers |
| `replay.html` | Interactive flight replay (play / pause / scrub through the descent) |
| `model.html` | Interactive true-scale 3D model: click a part to select it, drag it out, isolate it |
| `models/` | Printable STLs of the can envelope and lid (fit check before you cut anything) |
| `figures/` | The mission plots, generated from decoded telemetry |
| `code/` | The simulation: physics, packet encoding, CRC, ground-station decode, plots |
| `data/` | Raw telemetry bytes, decoded CSV, mission summary |

## Reproduce the mission

```bash
cd code
python cansat_mission_demo.py     # simulate -> encode -> decode -> analyse -> plots
python gen_replay.py              # rebuild the interactive replay from the results
python cansat_3d_model.py         # regenerate the printable STLs (checks they are watertight)
node test_replay_render.js        # exercise the replay JS across the whole flight
```

Requires Python 3 with `numpy` and `matplotlib`. The scripts write their outputs next to
themselves (`code/figures/`, `code/*.csv`, `code/*.bin`); the copies in `data/` and `figures/`
are the ones this site was built from.

## Checking the layout

`code/mobile_check.py` drives headless Chrome over the DevTools protocol and reports every
element wider than the viewport, plus a screenshot at each width. (Headless Chrome clamps its own
window to about 500 px, so `--window-size` alone cannot produce a real phone viewport — the check
uses `Emulation.setDeviceMetricsOverride` instead.)

```bash
pip install websocket-client
python code/mobile_check.py . 360 390 430        # overflow report + screenshots
python code/shot_element.py . index.html ".replay" 390   # clip one element
```

Current status: **0 overflowing pages** at 360, 390 and 430 px for `index.html` and `replay.html`;
`plan.html` keeps its wide timeline tables inside their own scroll boxes so the page itself never
exceeds the viewport.

## Honest scope

Everything here is a **simulation**. No CanSat hardware has been built or flown, and the flight
numbers come from a physics model rather than a real drop. What the demo does demonstrate is the
full data chain: parachute sizing from the drag equation, a sensor model with realistic noise and
lag, a 34-byte telemetry frame with CRC-16/CCITT, a decode path that survives 12 % packet loss and
corrupted frames, and the analysis that turns it into defensible figures.

Competition rules, dates and scoring are taken from the published BSA / AUBH guidelines
(CanSat Bahrain Competition 2026). The guideline PDF itself is not redistributed here.
