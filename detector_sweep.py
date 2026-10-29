"""Operating grid of the episode detector: every joining threshold, scored with the verifier's own matching on
the reference's forward-selection sequences (a higher threshold selects a prefix of each patient's sequence).
Usage: python3 detector_sweep.py > evidence/detector_sweep.txt"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import TASK, S, analysis  # noqa: E402
from score import load_verifier  # noqa: E402

GRID = [2.5, 2.6, 2.7, 2.75, 2.8, 2.85, 2.9, 3.0, 3.1, 3.25, 3.5, 3.75, 4.0, 4.5, 5.0]


def main():
    an = analysis()
    v = load_verifier(TASK)
    first = an["first"]
    rows = []
    for za in GRID:
        rep = [(pid, first + dt.timedelta(days=d0), k) for pid, r in sorted(an["res"].items())
               for k, d0, n, z in r["seq"] if z >= za]
        sc = v.match_episodes(rep)
        ok = sc["precision"] >= v.MIN_EPISODE_PRECISION and sc["recall"] >= v.MIN_EPISODE_RECALL
        rows.append(ok)
        print(f"z_add {za:4.2f}  reported {sc['n']:3d} correct {sc['hit']:3d}  precision {sc['precision']:.3f} "
              f"recall {sc['recall']:.3f}  {'PASS' if ok else 'fail'}")
    ref = json.load(open(os.path.join(TASK, "authoring", "evidence", "reference_output.json")))
    shipped = sorted((pid, (first + dt.timedelta(days=d0)).isoformat(), k) for pid, r in an["res"].items()
                     for k, d0, n, z in r["seq"] if z >= S.Z_ADD)
    submitted = sorted((e["patient"], e["start"], e["cause"]) for e in ref["episodes"])
    print(f"the grid at the shipped point reproduces the reference's submitted episodes: {'yes' if shipped == submitted else 'NO'}")
    print(f"{sum(rows)} of {len(rows)} joining thresholds clear both limits (precision >= {v.MIN_EPISODE_PRECISION}, "
          f"recall >= {v.MIN_EPISODE_RECALL}); shipped point {S.Z_ADD}")
    print("forward selection over all patients, strongest first (patient, start, cause, days, z, correct?):")
    allseq = sorted(((z, pid, (first + dt.timedelta(days=d0)), k, n) for pid, r in an["res"].items()
                     for k, d0, n, z in r["seq"]), reverse=True)
    for z, pid, d, k, n in allseq:
        hit = any(tp == pid and tc == k and abs((d - td).days) <= v.EPISODE_TOL_DAYS for tp, td, tc in v.TRUE_EPISODES)
        print(f"  {pid} {d.isoformat()} {k:24s} {n:2d}  z {z:5.2f}  {'correct' if hit else 'false'}")


if __name__ == "__main__":
    main()
