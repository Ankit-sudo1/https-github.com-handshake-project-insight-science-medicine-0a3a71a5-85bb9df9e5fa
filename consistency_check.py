"""Internal consistency of the public data with protocol.md and the instruction, and of the truth with the public
files. Usage: python3 consistency_check.py > evidence/consistency.txt"""
import csv
import datetime as dt
import json
import os

TASK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(TASK, "environment", "data")
FIRST, LAST = dt.date(2026, 1, 5), dt.date(2026, 7, 5)
PLAN_FIRST, PLAN_LAST = dt.date(2026, 7, 6), dt.date(2026, 8, 30)


def rows(name):
    with open(os.path.join(D, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    bad = 0

    def chk(ok, what):
        nonlocal bad
        print(f"{'PASS' if ok else 'FAIL'}  {what}")
        bad += not ok

    T = json.load(open(os.path.join(TASK, "tests", "truth.json")))
    pats = [r["patient"] for r in rows("patients.csv")]
    inr, doses, log, plan = rows("inr.csv"), rows("doses.csv"), rows("clinic_log.csv"), rows("plan_days.csv")
    chk(len(pats) == 12 and sorted(T["patients"]) == sorted(pats), "twelve patients, the same in patients.csv and the truth")
    chk(all(r["patient"] in pats for r in inr + doses + log + plan), "every row names a patient of patients.csv")
    days = [(FIRST + dt.timedelta(days=k)).isoformat() for k in range((LAST - FIRST).days + 1)]
    chk(all(sorted(r["date"] for r in doses if r["patient"] == p) == days for p in pats),
        "doses.csv has every day of the record, 2026-01-05 to 2026-07-05, for every patient")
    chk(all(float(r["dose_mg"]) * 2 == round(float(r["dose_mg"]) * 2) for r in doses), "every diary dose is a multiple of 0.5 mg")
    chk(all(FIRST.isoformat() <= r["date"] <= LAST.isoformat() for r in inr), "every INR result lies within the record")
    chk(all(len(r["inr"].split(".")[-1]) == 1 for r in inr), "every INR result is rounded to 0.1")
    keys = [(r["patient"], r["date"]) for r in inr]
    chk(len(set(keys)) == len(keys), "at most one INR result per patient per day")
    pdays = [(PLAN_FIRST + dt.timedelta(days=k)).isoformat() for k in range(56)]
    chk(all(sorted(r["date"] for r in plan if r["patient"] == p) == pdays for p in pats) and len(plan) == 12 * 56,
        "plan_days.csv has each patient's 56 days, 2026-07-06 to 2026-08-30")
    chk(T["record_first"] == FIRST.isoformat() and T["record_last"] == LAST.isoformat() and T["plan_first"] == PLAN_FIRST.isoformat(),
        "the truth's record and plan dates are the instruction's")
    chk(all(h["patient"] in pats and h["cause"] in ("missed_dose", "unrecorded_interaction") for h in T["hidden"]),
        "every hidden episode names a patient and one of the instruction's two causes")
    chk(all(FIRST.isoformat() <= h["start"] <= LAST.isoformat() for h in T["hidden"]), "every hidden episode starts within the record")
    chk(all((2 <= h["days"] <= 4) if h["cause"] == "missed_dose" else (7 <= h["days"] <= 14) for h in T["hidden"]),
        "missed-dose spells last 2 to 4 days and unrecorded courses 7 to 14 days, as the instruction states")
    recorded = [(r["patient"], r["start_date"], r["end_date"]) for r in log if r["event"] == "antibiotic course"]
    ok = True
    for h in T["hidden"]:
        if h["cause"] != "unrecorded_interaction":
            continue
        s = dt.date.fromisoformat(h["start"])
        e = s + dt.timedelta(days=h["days"] - 1)
        ok &= all(not (p == h["patient"] and dt.date.fromisoformat(a) <= e and s <= dt.date.fromisoformat(b))
                  for p, a, b in recorded)
    chk(ok, "no unrecorded course overlaps a recorded one")
    planned = [r for r in log if "planned" in r["event"]]
    chk(all(PLAN_FIRST.isoformat() <= r["start_date"] <= PLAN_LAST.isoformat() for r in planned) and len(planned) == 2,
        "the two planned events in clinic_log.csv fall in the plan block")
    for pid in pats:
        tp = T["patients"][pid]
        ok &= len(tp["plan_vk"]) == 56 and len(tp["plan_mult"]) == 56
    chk(ok, "the truth carries 56 days of vitamin K factor and interaction multiplier for every patient")
    words = len(open(os.path.join(D, "protocol.md"), encoding="utf-8").read().split())
    iw = len(open(os.path.join(TASK, "instruction.md"), encoding="utf-8").read().split())
    chk(words < iw, f"protocol.md ({words} words) is shorter than the instruction ({iw})")
    print(f"\n{bad} FAIL lines")


if __name__ == "__main__":
    main()
