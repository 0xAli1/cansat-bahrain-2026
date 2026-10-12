"""
CanSat Bahrain 2026 - Mission Demo
==================================
End-to-end demonstration of one full mission:
  1. Parachute sizing from the drag equation (target descent rate)
  2. Physics simulation of the flight (release -> deploy -> landing)
  3. Synthetic sensor model (BMP180, DHT11, 6-axis IMU, magnetometer) with noise/lag
  4. Packet encoding into the exact byte layout the Arduino firmware puts on the wire
  5. Ground-station decode with CRC-16/CCITT validation + link-loss accounting
  6. Mission analysis + the plots that go into the review decks and final presentation

Run:  python cansat_mission_demo.py
Out:  telemetry.bin, telemetry_decoded.csv, figures/*.png, mission_data.json, mission_summary.txt
"""

import os
import csv
import json
import math
import random
import struct

import numpy as np

random.seed(20261212)
np.random.seed(20261212)

OUT = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(OUT, "figures")
os.makedirs(FIG, exist_ok=True)

# ----------------------------------------------------------------------------
# MISSION DESIGN PARAMETERS  <- these are the engineering decisions
# ----------------------------------------------------------------------------
MASS_KG = 0.350               # CanSat mass: kit + structure + payload
CAN_DIA_M = 0.066             # 350 ml soft-drink can envelope
CAN_CD = 0.80                 # drag coefficient of the bare can body
RELEASE_ALT_M = 250.0         # release altitude (tall building / drone / rocket)
DEPLOY_T_S = 2.0              # parachute deployment timer after release
TARGET_DESCENT_MPS = 5.0      # design requirement: 4-7 m/s for a safe landing

WIND_MPS = 2.5                # horizontal wind (Bahrain, December)
RHO0 = 1.225                  # sea-level air density [kg/m3]
G = 9.80665
CHUTE_CD = 0.85               # hemispherical canopy drag coefficient

DT = 0.02                     # physics timestep [s]
TELEM_HZ = 5.0                # sensor sampling + downlink rate [Hz]
TEMP_GROUND_C = 31.0          # surface temperature
RH_GROUND_PCT = 62.0


def air_density(alt_m):
    """Exponential atmosphere - accurate well past our flight envelope."""
    return RHO0 * math.exp(-alt_m / 8500.0)


def pressure_pa(alt_m):
    """ISA barometric formula referenced to sea level."""
    return 101325.0 * (1.0 - 2.25577e-5 * alt_m) ** 5.25588


def altitude_from_pressure(p_pa):
    """The inverse the ground station runs on every packet."""
    return 44330.7 * (1.0 - (p_pa / 101325.0) ** (1 / 5.25588))


def temp_at(alt_m):
    """Surface temperature with the standard -6.5 K/km lapse rate."""
    return TEMP_GROUND_C - 0.0065 * alt_m


def size_parachute(mass_kg, target_mps, cd=CHUTE_CD, rho=RHO0):
    """Canopy diameter required to hold a given descent rate: v = sqrt(2mg/(rho Cd A))."""
    area = 2.0 * mass_kg * G / (rho * cd * target_mps ** 2)
    dia = math.sqrt(4.0 * area / math.pi)
    return area, dia


CHUTE_AREA_M2, CHUTE_DIA_M = size_parachute(MASS_KG, TARGET_DESCENT_MPS)
CAN_AREA_M2 = math.pi * (CAN_DIA_M / 2) ** 2


# ----------------------------------------------------------------------------
# 1 + 2. FLIGHT SIMULATION with sensor model
# ----------------------------------------------------------------------------
def record(t, alt, v, x, chute, swing_amp, swing_freq, spin_rate, heading):
    """Build one telemetry sample exactly as the flight firmware would."""
    # BMP180 pressure, with realistic noise: oversampled mode gives ~0.06-0.12 hPa
    # (~0.5-1 m of altitude noise), which is exactly why the ground station must
    # filter before differentiating.
    p = pressure_pa(alt) * (1.0 + np.random.normal(0, 6.0e-5))

    # DHT11: 1 C / 1 % quantisation, slow thermal response (it trails the truth)
    true_temp = temp_at(alt)
    lag = 0.30 if not chute else 0.55
    temp_meas = true_temp + lag * (TEMP_GROUND_C - true_temp) + np.random.normal(0, 0.4)
    hum_true = RH_GROUND_PCT + 9.0 * (1.0 - math.exp(-(RELEASE_ALT_M - alt) / 40.0))
    hum_meas = max(0.0, min(100.0, hum_true + np.random.normal(0, 1.0)))
    temp_meas = int(round(temp_meas))
    hum_meas = int(round(hum_meas))

    # IMU: gravity + pendulum swing + body spin, plus sensor noise
    if chute:
        ang = swing_amp * math.sin(2 * math.pi * swing_freq * t)
    else:
        ang = math.radians(6.0) * math.sin(2 * math.pi * 0.4 * t)
    ax = (G * math.sin(ang)) + np.random.normal(0, 0.08)
    ay = (G * math.cos(ang) * math.sin(spin_rate * t) * 0.35) + np.random.normal(0, 0.08)
    az = (G * math.cos(ang) * math.cos(spin_rate * t) * 0.35) + np.random.normal(0, 0.08)
    accel_meas = [int(round(a / G * 1000)) for a in (ax, ay, az)]
    gyro_meas = [
        int(round(math.degrees(swing_amp * 2 * math.pi * swing_freq *
                               math.cos(2 * math.pi * swing_freq * t)) * 10
                  + np.random.normal(0, 4))),
        int(round(math.degrees(spin_rate) * 10 + np.random.normal(0, 4))),
        int(round(math.degrees(spin_rate) * 5 + np.random.normal(0, 4))),
    ]

    # Magnetometer: heading + swing coupling + noise
    hdg = heading + (ang * 0.8 if chute else 0.0) + np.random.normal(0, 1.5)
    mag = [
        round(28.0 * math.cos(hdg) + np.random.normal(0, 0.5), 2),
        round(28.0 * math.sin(hdg) + np.random.normal(0, 0.5), 2),
        round(-41.0 + np.random.normal(0, 0.4), 2),
    ]

    return {
        "t": round(t, 3), "alt_true": round(alt, 3), "v_true": round(v, 3),
        "x_drift": round(x, 3), "chute": int(chute), "pressure_pa": round(p, 2),
        "temp_c": temp_meas, "hum_pct": hum_meas,
        "abs_mg": accel_meas, "gyro_dps": gyro_meas, "mag_ut": mag,
    }


def simulate():
    t, alt, v, x = 0.0, RELEASE_ALT_M, 0.0, 0.0
    chute = False
    samples = []
    swing_amp, swing_freq, spin_rate = math.radians(14.0), 1.15, 0.9
    heading = math.radians(118.0)
    step = 0
    every = max(1, int(round(1.0 / (TELEM_HZ * DT))))

    while True:
        speed = abs(v)
        cd, area = (CHUTE_CD, CHUTE_AREA_M2) if chute else (CAN_CD, CAN_AREA_M2)
        drag_f = 0.5 * air_density(alt) * cd * area * speed * speed
        a_drag = (drag_f / MASS_KG) * (1.0 if v < 0 else -1.0)
        v += (-G + a_drag) * DT
        alt += v * DT
        x += WIND_MPS * (1.0 if chute else 0.35) * DT

        if (not chute) and t >= DEPLOY_T_S:
            chute = True

        if step % every == 0:
            samples.append(record(t, alt, v, x, chute, swing_amp, swing_freq,
                                  spin_rate, heading))

        if alt <= 0.0:
            touch = record(t, 0.0, v, x, chute, swing_amp, swing_freq, spin_rate, heading)
            if samples and abs(samples[-1]["t"] - touch["t"]) < 1e-9:
                samples[-1] = touch          # keep timestamps strictly increasing
            else:
                samples.append(touch)
            return samples, t
        t += DT
        step += 1
        if t > 600:
            break
    return samples, t


# ----------------------------------------------------------------------------
# 3. PACKET ENCODING - the wire format the Arduino firmware emits
#    sync(2) | seq(1) | t_ms(4) | p_pa(4) | t_c*100(2) | rh(1) |
#    ax,ay,az (6) | gx,gy,gz (6) | mx,my,mz (6) | crc16(2)          = 34 bytes
# ----------------------------------------------------------------------------
SYNC = b"\xAA\x55"
PKT_BYTES = 34
LOSS_RATE = 0.12          # packets lost over the 433 MHz link
BITFLIP_RATE = 0.03       # packets that arrive with a corrupted bit


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def encode(samples):
    frames, dropped, corrupted = [], 0, 0
    for i, s in enumerate(samples):
        payload = struct.pack(
            "<I I h B hhh hhh hhh",
            int(round(s["t"] * 1000)), int(s["pressure_pa"]),
            int(round(s["temp_c"] * 100)), int(s["hum_pct"]),
            s["abs_mg"][0], s["abs_mg"][1], s["abs_mg"][2],
            s["gyro_dps"][0], s["gyro_dps"][1], s["gyro_dps"][2],
            int(s["mag_ut"][0] * 100), int(s["mag_ut"][1] * 100), int(s["mag_ut"][2] * 100),
        )
        body = struct.pack("<B", i & 0xFF) + payload
        frame = SYNC + body + struct.pack("<H", crc16_ccitt(body))
        r = random.random()
        if r < LOSS_RATE:
            dropped += 1
            continue
        if r < LOSS_RATE + BITFLIP_RATE:
            f = bytearray(frame)
            f[random.randrange(len(f))] ^= 1 << random.randrange(8)
            frame = bytes(f)
            corrupted += 1
        frames.append(frame)
    return b"".join(frames), dropped, corrupted


# ----------------------------------------------------------------------------
# 4. GROUND STATION DECODE
# ----------------------------------------------------------------------------
def decode(blob):
    rows, bad_crc, seq_gaps = [], 0, 0
    i, n, seq_expected = 0, len(blob), None
    while i < n - 1:
        if blob[i:i + 2] != SYNC:
            i += 1
            continue
        frame = blob[i:i + PKT_BYTES]
        if len(frame) < PKT_BYTES:
            break
        body, crc_rx = frame[2:-2], struct.unpack("<H", frame[-2:])[0]
        if crc16_ccitt(body) != crc_rx:
            bad_crc += 1
            i += 1                                  # resync one byte forward
            continue
        (seq, t_ms, p_pa, t_c100, rh, ax, ay, az, gx, gy, gz, mx, my, mz) = \
            struct.unpack("<B I I h B hhh hhh hhh", body)
        if seq_expected is not None and seq != (seq_expected + 1) % 256:
            seq_gaps += 1
        seq_expected = seq
        rows.append({
            "seq": seq, "t": round(t_ms / 1000.0, 3), "pressure_pa": p_pa,
            "alt_baro": round(altitude_from_pressure(p_pa), 2),
            "temp_c": t_c100 / 100.0, "hum_pct": rh,
            "ax_mg": ax, "ay_mg": ay, "az_mg": az,
            "gx_dps": gx / 10.0, "gy_dps": gy / 10.0, "gz_dps": gz / 10.0,
            "mag_x": mx / 100.0, "mag_y": my / 100.0, "mag_z": mz / 100.0,
        })
        i += PKT_BYTES
    return rows, bad_crc, seq_gaps


# ----------------------------------------------------------------------------
# 5. ANALYSIS + PLOTS
# ----------------------------------------------------------------------------
def moving_average(x, n):
    """Edge-padded moving average - keeps the array length and the end points."""
    if n <= 1 or len(x) < n:
        return x.copy()
    pad = n // 2
    xp = np.concatenate([np.full(pad, x[0]), x, np.full(pad, x[-1])])
    k = np.ones(n) / n
    return np.convolve(xp, k, mode="valid")[:len(x)]


def descent_rate(t, alt, smooth_n=7, span=2):
    """Ground-station processing chain (must be justified in the CDR):
       raw baro altitude -> moving average -> central difference.
       Differentiating unfiltered baro data at 5 Hz is pure noise."""
    alt_s = moving_average(alt, smooth_n)
    d = np.zeros_like(alt_s)
    for i in range(len(alt_s)):
        a, b = max(0, i - span), min(len(alt_s) - 1, i + span)
        if t[b] > t[a]:
            d[i] = (alt_s[b] - alt_s[a]) / (t[b] - t[a])
        else:
            d[i] = d[i - 1] if i else 0.0
    return alt_s, d


def analyse(rows, truth):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = np.array([r["t"] for r in rows])
    alt = np.array([r["alt_baro"] for r in rows])
    temp = np.array([r["temp_c"] for r in rows], dtype=float)
    hum = np.array([r["hum_pct"] for r in rows], dtype=float)
    gy = np.array([r["gy_dps"] for r in rows])
    heading = np.degrees(np.arctan2(np.array([r["mag_y"] for r in rows]),
                                    np.array([r["mag_x"] for r in rows]))) % 360
    raw_descent = np.gradient(alt, t)
    alt_smooth, descent = descent_rate(t, alt)

    # terminal velocity from the settled phase (last fifth of the descent)
    tail = descent[-max(5, len(descent) // 5):]
    terminal = float(np.mean(tail))

    # deploy detection on the filtered signal: free fall -> canopy. A naive
    # max-slope detector fails here (free-fall acceleration ~9.8 m/s2 has almost
    # the same slope as the filtered canopy step), so use the recovery criterion:
    # the fall rate has arrested to within 30% of terminal velocity after having
    # been at least twice terminal velocity.
    freefall_peak = float(descent.min())
    term_mag = max(1e-3, abs(terminal))
    arrested = np.where((descent > -1.3 * term_mag) &
                        (np.minimum.accumulate(descent) < -2.0 * term_mag))[0]
    deploy_idx = int(arrested[0]) if len(arrested) else int(
        np.argmax(np.abs(np.diff(descent))))
    deploy_t = float(t[deploy_idx])
    # measured lapse rate from the payload itself (compare to -0.65 C/100 m ISA)
    k = np.polyfit(alt, temp, 1)[0] if len(alt) > 3 else 0.0
    lapse_per_100m = float(k * 100.0)

    with open(os.path.join(OUT, "telemetry_decoded.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    plt.rcParams.update({
        "figure.facecolor": "#EDEFF2", "axes.facecolor": "#FDFDFC",
        "axes.edgecolor": "#C6CDD4", "axes.labelcolor": "#131A21",
        "text.color": "#131A21", "xtick.color": "#5A6672", "ytick.color": "#5A6672",
        "grid.color": "#D6DBE0", "font.size": 10, "figure.dpi": 135,
        "axes.titleweight": "semibold", "axes.titlesize": 11,
        "legend.framealpha": 0.92, "legend.edgecolor": "#D6DBE0",
    })
    ACC, ACC2, ACC3, WARN = "#0F6E6B", "#C4541F", "#1F5C9E", "#8A96A3"

    # --- Fig 1: mission profile
    fig, ax = plt.subplots(2, 1, figsize=(7.8, 5.8), sharex=True,
                           gridspec_kw={"height_ratios": [2, 1]})
    ax[0].plot(t, alt, color=ACC, lw=2, label="Barometric altitude (decoded downlink)")
    ax[0].plot([s["t"] for s in truth], [s["alt_true"] for s in truth],
               color="#8A96A3", lw=1.1, ls="--", label="Truth (simulated reference)")
    ax[0].axvline(deploy_t, color=WARN, ls=":", lw=1.6)
    ax[0].annotate("parachute deploy", (deploy_t, alt.max() * 0.62), color=WARN,
                   fontsize=9, xytext=(deploy_t + 3, alt.max() * 0.68))
    ax[0].set_ylabel("Altitude [m]")
    ax[0].set_title(f"CanSat Bahrain 2026 - Mission Profile ({RELEASE_ALT_M:.0f} m release)")
    ax[0].legend(loc="upper right", fontsize=8)
    ax[0].grid(True)
    ax[1].plot(t, raw_descent, color="#A8B2BC", lw=0.8, alpha=0.7,
               label="raw differentiated baro (noise dominated - why we filter)")
    ax[1].plot(t, descent, color=ACC2, lw=1.8, label="filtered: 7-sample MA + central diff")
    ax[1].axhline(terminal, color=WARN, ls="--", lw=1.2,
                  label=f"mean terminal descent {abs(terminal):.2f} m/s")
    ax[1].axhline(-TARGET_DESCENT_MPS, color="#8A96A3", ls=":", lw=1.2,
                  label=f"design target {TARGET_DESCENT_MPS:.1f} m/s")
    ax[1].set_ylabel("Descent rate [m/s]")
    ax[1].set_xlabel("Mission elapsed time [s]")
    ax[1].legend(loc="lower right", fontsize=8)
    ax[1].grid(True)
    fig.tight_layout()
    p1 = os.path.join(FIG, "01_mission_profile.png")
    fig.savefig(p1); plt.close(fig)

    # --- Fig 2: the science (secondary mission deliverable).
    # 1 C sensor resolution plotted raw against altitude is a cloud of horizontal
    # bands; a real report bins the data by altitude and quotes mean +/- sigma.
    bins = np.arange(0.0, alt.max() + 10.0, 10.0)
    idx = np.clip(np.digitize(alt, bins) - 1, 0, len(bins) - 2)
    centres, t_mean, t_std, h_mean, h_std = [], [], [], [], []
    for b in range(len(bins) - 1):
        m = idx == b
        if m.sum() >= 3:
            centres.append(0.5 * (bins[b] + bins[b + 1]))
            t_mean.append(temp[m].mean()); t_std.append(temp[m].std())
            h_mean.append(hum[m].mean()); h_std.append(hum[m].std())
    centres = np.array(centres); t_mean = np.array(t_mean); t_std = np.array(t_std)
    h_mean = np.array(h_mean); h_std = np.array(h_std)

    fig, ax = plt.subplots(1, 3, figsize=(11.5, 4.4))
    ax[0].scatter(temp, alt, s=4, color=WARN, alpha=0.20, label="raw samples (1 C steps)")
    ax[0].plot(t_mean, centres, color=WARN, lw=2, label="10 m binned mean")
    ax[0].fill_betweenx(centres, t_mean - t_std, t_mean + t_std, color=WARN, alpha=0.22,
                        label="+/- 1 sigma")
    ax[0].set_xlabel("Temperature [$^\\circ$C]"); ax[0].set_ylabel("Altitude [m]")
    ax[0].set_title("Temperature profile"); ax[0].grid(True); ax[0].legend(fontsize=7)

    ax[1].scatter(hum, alt, s=4, color=ACC3, alpha=0.20)
    ax[1].plot(h_mean, centres, color=ACC3, lw=2)
    ax[1].fill_betweenx(centres, h_mean - h_std, h_mean + h_std, color=ACC3, alpha=0.22)
    ax[1].set_xlabel("Relative humidity [%]")
    ax[1].set_title("Humidity profile"); ax[1].grid(True)
    ax[1].set_yticklabels([])

    ax[2].plot(t, temp, color=WARN, lw=1.6, label="Temperature [$^\\circ$C]")
    ax[2].plot(t, hum / 2.0, color=ACC3, lw=1.6, label="RH [%] / 2")
    ax[2].set_xlabel("Mission time [s]"); ax[2].set_ylabel("Value [mixed units - see legend]")
    ax[2].set_title("Sensor time series"); ax[2].grid(True); ax[2].legend(fontsize=8)
    fig.suptitle("Science Payload - Vertical Atmospheric Profile (binned 10 m, mean +/- 1 sigma)",
                 fontweight="bold")
    fig.tight_layout()
    p2 = os.path.join(FIG, "02_science_profile.png")
    fig.savefig(p2); plt.close(fig)

    # --- Fig 3: vehicle dynamics
    fig, ax = plt.subplots(2, 1, figsize=(7.8, 5.4), sharex=True)
    ax[0].plot(t, gy, color=ACC2, lw=1.2)
    ax[0].axvline(deploy_t, color=WARN, ls=":", lw=1.6)
    ax[0].set_ylabel("Y-gyro [deg/s]")
    ax[0].set_title("Vehicle Dynamics - pendulum oscillation under canopy (6-axis IMU)")
    ax[0].grid(True)
    ax[1].plot(t, heading, color=ACC, lw=1.6)
    ax[1].set_ylabel("Heading [deg]"); ax[1].set_xlabel("Mission elapsed time [s]")
    ax[1].grid(True)
    fig.tight_layout()
    p3 = os.path.join(FIG, "03_dynamics.png")
    fig.savefig(p3); plt.close(fig)

    summary = {
        "packets_decoded": len(rows),
        "flight_time_s": round(float(t[-1]), 2),
        "release_altitude_m": RELEASE_ALT_M,
        "apogee_measured_m": round(float(alt.max()), 2),
        "deploy_time_s": round(deploy_t, 2),
        "deploy_timer_s": DEPLOY_T_S,
        "peak_freefall_rate_mps": round(freefall_peak, 2),
        "mean_terminal_descent_mps": round(abs(terminal), 2),
        "design_descent_target_mps": TARGET_DESCENT_MPS,
        "chute_diameter_m": round(CHUTE_DIA_M, 3),
        "chute_area_m2": round(CHUTE_AREA_M2, 4),
        "measured_lapse_rate_C_per_100m": round(lapse_per_100m, 3),
        "isa_lapse_rate_C_per_100m": -0.65,
        "temp_min_c": float(temp.min()), "temp_max_c": float(temp.max()),
        "hum_max_pct": float(hum.max()),
        "heading_deg": round(float(np.median(heading)), 1),
        "wind_drift_m": round(float(truth[-1]["x_drift"]), 1),
    }
    return (p1, p2, p3), summary, (t, alt, temp, hum, descent)


# ----------------------------------------------------------------------------
# RUN
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    samples, flight_time = simulate()
    blob, DROPPED, CORRUPT = encode(samples)
    with open(os.path.join(OUT, "telemetry.bin"), "wb") as fh:
        fh.write(blob)

    rows, CRC_BAD, SEQ_GAPS = decode(blob)
    figs, summary, series = analyse(rows, samples)
    t, alt, temp, hum, descent = series
    summary["crc_errors_rejected"] = CRC_BAD
    summary["packets_lost_over_air"] = DROPPED
    summary["bits_flipped_in_transit"] = CORRUPT
    summary["sequence_gaps"] = SEQ_GAPS
    summary["link_success_rate_pct"] = round(
        100.0 * len(rows) / (len(rows) + DROPPED + CRC_BAD), 1)

    with open(os.path.join(OUT, "mission_data.json"), "w") as fh:
        json.dump({"summary": summary, "series": {
            "t": [round(float(v), 3) for v in t],
            "alt": [round(float(v), 2) for v in alt],
            "temp": [round(float(v), 1) for v in temp],
            "hum": [round(float(v), 1) for v in hum],
            "descent": [round(float(v), 3) for v in descent],
        }}, fh)

    with open(os.path.join(OUT, "mission_summary.txt"), "w") as fh:
        fh.write("CanSat Bahrain 2026 - simulated mission results\n" + "=" * 56 + "\n")
        for k, v in summary.items():
            fh.write(f"{k:34s} {v}\n")
        fh.write(f"\n{os.path.getsize(os.path.join(OUT,'telemetry.bin'))} bytes on the wire, "
                 f"{len(rows)} packets decoded\n")

    print(json.dumps(summary, indent=2))
    print("\nfigures:")
    for p in figs:
        print(" ", p)
