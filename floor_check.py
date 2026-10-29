"""Floor of the plan criteria: the reference's own dose design given each patient's true half-life, EC50, state at
the end of the record and interactions (only the vitamin K factor unknown, taken at its median), graded by the
verifier. Usage: python3 floor_check.py"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from score import load_verifier, score  # noqa: E402
sys.path.insert(0, os.path.join(TASK, "solution"))
import solve as V  # noqa: E402


def main():
    v = load_verifier(TASK)
    T = json.load(open(os.path.join(TASK, "tests", "truth.json")))
    rows = []
    for pid, tp in sorted(T["patients"].items()):
        doses = V.design(tp["t_half"], tp["ec50"], tuple(tp["state"]), tp["plan_mult"])
        rows += [dict(patient=pid, date=d, dose_mg=x) for d, x in zip(v.PLAN_DATES, doses)]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "plan.json")
        json.dump(dict(episodes=[], doses=rows), open(path, "w"))
        s = score(TASK, path, v)
    print("Plan with the true physiology (vitamin K at its median), graded by the verifier:")
    for pid in sorted(s["ttr"]):
        print(f"  {pid}  TTR {s['ttr'][pid]:.3f}  unsafe {s['unsafe'][pid]:.3f}")
    low = min(s["ttr"].values())
    print(f"lowest TTR {low:.3f} against the limit {v.MIN_TTR}; highest unsafe share {max(s['unsafe'].values()):.3f} "
          f"against {v.MAX_OUT_OF_SAFE}: " + ("both limits reachable" if low >= v.MIN_TTR and
                                              max(s['unsafe'].values()) <= v.MAX_OUT_OF_SAFE else "A PLAN LIMIT IS NOT REACHABLE"))


if __name__ == "__main__":
    main()
