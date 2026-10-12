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
| `figures/` | The mission plots, generated from decoded telemetry |
| `code/` | The simulation: physics, packet encoding, CRC, ground-station decode, plots |
| `data/` | Raw telemetry bytes, decoded CSV, mission summary |

## Reproduce the mission

```bash
cd code
python cansat_mission_demo.py     # simulate -> encode -> decode -> analyse -> plots
python gen_replay.py              # rebuild the interactive replay from the results
node test_replay_render.js        # exercise the replay JS across the whole flight
```

Requires Python 3 with `numpy` and `matplotlib`. The scripts write their outputs next to
themselves (`code/figures/`, `code/*.csv`, `code/*.bin`); the copies in `data/` and `figures/`
are the ones this site was built from.

## Honest scope

Everything here is a **simulation**. No CanSat hardware has been built or flown, and the flight
numbers come from a physics model rather than a real drop. What the demo does demonstrate is the
full data chain: parachute sizing from the drag equation, a sensor model with realistic noise and
lag, a 34-byte telemetry frame with CRC-16/CCITT, a decode path that survives 12 % packet loss and
corrupted frames, and the analysis that turns it into defensible figures.

Competition rules, dates and scoring are taken from the published BSA / AUBH guidelines
(CanSat Bahrain Competition 2026). The guideline PDF itself is not redistributed here.
