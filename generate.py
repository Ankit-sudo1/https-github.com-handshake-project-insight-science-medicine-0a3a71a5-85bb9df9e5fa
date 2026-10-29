"""Generator for warfarin-dose-plan: six months of home INR self-testing and dosing diaries of twelve adults on
warfarin, the eight-week plan block, and the hidden truth the verifier grades against.

Usage: python3 generate.py <task_dir>
Writes <task_dir>/environment/data/* (agent-visible) and <task_dir>/tests/truth.json (verifier only).
Seeded: two runs write byte-identical files.
"""
import csv
import datetime as dt
import json
import math
import os
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import simcore as S  # noqa: E402

SEED = 20260105
START = dt.date(2026, 1, 5)
RECORD_DAYS = 182
PLAN_DAYS = 56
N_PAT = 12
METER_SD = 0.05                 # INR meter error, log-normal
VK_PHI = 0.85                   # day-to-day vitamin K factor: log AR(1)
ANTIBIOTIC = 1.60               # interaction multiplier of the antibiotics the clinic warns about (every patient)
AMIODARONE = 1.65               # full interaction multiplier of amiodarone (every patient)
AMIO_HIST = ("P04", 75)         # patient, first day on amiodarone in the record (continues)
AMIO_PLAN = ("P09", 7)          # patient, first plan day (0-based) on amiodarone (continues)
ABX_PLAN = ("P02", 21, 7)       # planned antibiotic course in the plan block: patient, first plan day, days
TARGET_INR = 2.5


def ds(day):
    return (START + dt.timedelta(days=day)).isoformat()


def rng(k):
    return np.random.default_rng([SEED, k])


def ec50_for(dss):
    """EC50 such that the steady state on dss mg/day (v = 1) has INR 2.5."""
    s = TARGET_INR ** (-1.0 / S.GAMMA)
    return dss / (1.0 / s - 1.0)


def week_pattern(weekly):
    """Daily doses (Mon..Sun) for a weekly dose: whole 0.5 mg steps, the extra half-milligrams on the first days."""
    halves = int(round(weekly / 0.5))
    base, extra = divmod(halves, 7)
    return [0.5 * (base + (1 if k < extra else 0)) for k in range(7)]


def adjust(weekly, inr):
    """The clinic's dosing algorithm at each INR (returns new weekly dose and whether to omit the next dose)."""
    if inr < 1.8:
        return weekly * 1.10, False
    if inr < 2.0:
        return weekly * 1.05, False
    if inr <= 3.0:
        return weekly, False
    if inr <= 3.5:
        return weekly * 0.95, False
    if inr <= 4.5:
        return weekly * 0.90, False
    return weekly * 0.85, True


def main(task):
    data = os.path.join(task, "environment", "data")
    os.makedirs(data, exist_ok=True)
    os.makedirs(os.path.join(task, "tests"), exist_ok=True)
    r1 = rng(1)
    pids = [f"P{k:02d}" for k in range(1, N_PAT + 1)]
    pats = {}
    for pid in pids:
        t_half = float(np.clip(40.0 * math.exp(0.25 * r1.normal()), 22.0, 70.0))
        dss = float(np.clip(5.0 * math.exp(0.35 * r1.normal()), 1.5, 11.0))
        pats[pid] = dict(t_half=round(t_half, 2), ec50=round(ec50_for(dss), 4), dss=dss,
                         vk_sd=round(0.12 + 0.10 * r1.uniform(), 3),
                         age=int(45 + 40 * r1.uniform()), sex="F" if r1.uniform() < 0.5 else "M",
                         indication=["atrial fibrillation", "venous thromboembolism", "mechanical valve"][
                             int(r1.integers(3)) if pid not in ("P03", "P11") else 1],
                         test_days=sorted({(a := int(r1.integers(7))), (a + 3) % 7}))

    # recorded antibiotic courses (patient, first day, days)
    r2 = rng(2)
    abx = []
    for pid in pids:
        for _ in range(int(r2.integers(0, 3))):
            d0, n = int(r2.integers(10, RECORD_DAYS - 15)), int(r2.integers(5, 11))
            if all(q != pid or d0 > e0 + m + 20 or d0 + n + 20 < e0 for q, e0, m in abx):
                abx.append((pid, d0, n))
    abx.sort(key=lambda e: (e[0], e[1]))

    # hidden episodes: missed doses (1 or 2 days) and unrecorded antibiotic courses (5 to 10 days)
    r3 = rng(3)
    hidden = []
    busy = {pid: [] for pid in pids}
    for pid, d0, n in abx:
        busy[pid].append((d0 - 10, d0 + n + 10))
    busy[AMIO_HIST[0]].append((AMIO_HIST[1] - 10, AMIO_HIST[1] + 40))
    plan_kinds = ["missed_dose"] * 18 + ["unrecorded_interaction"] * 14
    r3.shuffle(plan_kinds)
    for kind in plan_kinds:
        while True:
            pid = pids[int(r3.integers(N_PAT))]
            d0 = int(r3.integers(14, RECORD_DAYS - 12))
            n = int(r3.integers(2, 5)) if kind == "missed_dose" else int(r3.integers(7, 15))
            if all(not (lo - 12 <= d0 <= hi + 12) for lo, hi in busy[pid]):
                break
        busy[pid].append((d0, d0 + n))
        hidden.append(dict(patient=pid, day=d0, days=n, cause=kind))
    hidden.sort(key=lambda e: (e["patient"], e["day"]))

    # simulate the record with the clinic's algorithm
    r4 = rng(4)
    rows_inr, rows_dose, truth_pat = [], [], {}
    for pid in pids:
        p = pats[pid]
        vk = np.zeros(RECORD_DAYS + PLAN_DAYS)
        eta = p["vk_sd"] * r4.normal()
        for d in range(RECORD_DAYS + PLAN_DAYS):
            eta = VK_PHI * eta + p["vk_sd"] * math.sqrt(1 - VK_PHI ** 2) * r4.normal()
            vk[d] = math.exp(eta)
        mult = np.ones(RECORD_DAYS + PLAN_DAYS)
        for q, d0, n in abx:
            if q == pid:
                mult[d0:d0 + n] *= ANTIBIOTIC
        for e in hidden:
            if e["patient"] == pid and e["cause"] == "unrecorded_interaction":
                mult[e["day"]:e["day"] + e["days"]] *= ANTIBIOTIC
        if pid == AMIO_HIST[0]:
            for d in range(AMIO_HIST[1], RECORD_DAYS + PLAN_DAYS):
                mult[d] *= S.amiodarone_factor(d - AMIO_HIST[1], AMIODARONE)
        if pid == AMIO_PLAN[0]:
            for d in range(RECORD_DAYS + AMIO_PLAN[1], RECORD_DAYS + PLAN_DAYS):
                mult[d] *= S.amiodarone_factor(d - RECORD_DAYS - AMIO_PLAN[1], AMIODARONE)
        if pid == ABX_PLAN[0]:
            mult[RECORD_DAYS + ABX_PLAN[1]:RECORD_DAYS + ABX_PLAN[1] + ABX_PLAN[2]] *= ANTIBIOTIC
        missed = set()
        for e in hidden:
            if e["patient"] == pid and e["cause"] == "missed_dose":
                missed.update(range(e["day"], e["day"] + e["days"]))
        weekly = round(7 * p["dss"] * (0.85 + 0.3 * r4.uniform()) / 0.5) * 0.5
        state = S.steady_state(p["t_half"], p["ec50"], weekly / 7, v=1.0)
        omit = False
        retest = -1
        for d in range(RECORD_DAYS):
            inr = S.inr_of(state)
            wd = (START + dt.timedelta(days=d)).weekday()
            if (wd in p["test_days"] or d == retest) and r4.uniform() > 0.08:
                meas = round(inr * math.exp(METER_SD * r4.normal()), 1)
                rows_inr.append([pid, ds(d), f"{meas:.1f}"])
                retest = d + 4 if not 2.0 <= meas <= 3.0 else -1
                weekly, omit = adjust(weekly, meas)
                weekly = round(weekly / 0.5) * 0.5
            dose = 0.0 if omit else week_pattern(weekly)[wd]
            omit = False
            rows_dose.append([pid, ds(d), f"{dose:.1f}"])
            taken = 0.0 if d in missed else dose
            state = S.step(state, p["t_half"], p["ec50"], taken, mult[d], vk[d])
        truth_pat[pid] = dict(t_half=p["t_half"], ec50=p["ec50"], vk_sd=p["vk_sd"],
                              state=[round(x, 10) for x in state],
                              plan_vk=[round(float(x), 6) for x in vk[RECORD_DAYS:]],
                              plan_mult=[round(float(x), 6) for x in mult[RECORD_DAYS:]],
                              last_weekly=weekly)

    # ----- write the public files
    def write(name, header, rows):
        with open(os.path.join(data, name), "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(header)
            w.writerows(rows)

    write("patients.csv", ["patient", "sex", "age", "indication"],
          [[pid, pats[pid]["sex"], pats[pid]["age"], pats[pid]["indication"]] for pid in pids])
    write("inr.csv", ["patient", "date", "inr"], rows_inr)
    write("doses.csv", ["patient", "date", "dose_mg"], rows_dose)
    write("plan_days.csv", ["patient", "date"], [[pid, ds(RECORD_DAYS + k)] for pid in pids for k in range(PLAN_DAYS)])
    log = [[pid, ds(d0), ds(d0 + n - 1), "antibiotic course"] for pid, d0, n in abx]
    log.append([AMIO_HIST[0], ds(AMIO_HIST[1]), "", "amiodarone started (continuing)"])
    log.append([AMIO_PLAN[0], ds(RECORD_DAYS + AMIO_PLAN[1]), "", "amiodarone planned to start (continuing)"])
    log.append([ABX_PLAN[0], ds(RECORD_DAYS + ABX_PLAN[1]), ds(RECORD_DAYS + ABX_PLAN[1] + ABX_PLAN[2] - 1),
                "antibiotic course planned"])
    log.sort(key=lambda r: (r[0], r[1]))
    write("clinic_log.csv", ["patient", "start_date", "end_date", "event"], log)
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "protocol.md"), os.path.join(data, "protocol.md"))

    truth = dict(record_first=ds(0), record_last=ds(RECORD_DAYS - 1), plan_first=ds(RECORD_DAYS),
                 plan_days=PLAN_DAYS, antibiotic=ANTIBIOTIC, amiodarone=AMIODARONE,
                 hidden=[dict(patient=e["patient"], start=ds(e["day"]), days=e["days"], cause=e["cause"]) for e in hidden],
                 patients=truth_pat)
    with open(os.path.join(task, "tests", "truth.json"), "w", encoding="utf-8") as fh:
        json.dump(truth, fh, indent=0)
        fh.write("\n")
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "simcore.py"), os.path.join(task, "tests", "simcore.py"))
    print(f"{N_PAT} patients, {len(rows_inr)} INR results, {len(abx)} recorded antibiotic courses, "
          f"{len(hidden)} hidden episodes")


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
