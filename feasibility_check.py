"""Reachability of the episode limits. Each actual episode's expected score with everything else known (the true
half-life, EC50 and vitamin K spread, the true interactions and the other episodes): the square root of
s' C^-1 s, where s is the episode's effect on the log INR at the patient's test days and C the covariance of the
vitamin K variation (sampled paths of the stated AR(1)) plus the meter error. Usage: python3 feasibility_check.py"""
import datetime as dt
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import generate as G  # noqa: E402
import simcore as S  # noqa: E402
from score import load_verifier  # noqa: E402
sys.path.insert(0, os.path.join(TASK, "solution"))
import solve as V  # noqa: E402


def main():
    v = load_verifier(TASK)
    T = json.load(open(os.path.join(TASK, "tests", "truth.json")))
    pats, first, n, _, _ = V.load(os.path.join(TASK, "environment", "data"))
    rng = np.random.default_rng(7)
    out = []
    for h in T["hidden"]:
        pid = h["patient"]
        p, tp = pats[pid], T["patients"][pid]
        others = [(e["cause"], (dt.date.fromisoformat(e["start"]) - first).days, e["days"])
                  for e in T["hidden"] if e["patient"] == pid and e is not h]
        me = (h["cause"], (dt.date.fromisoformat(h["start"]) - first).days, h["days"])

        def logs(extra, vk):
            doses, mult = p.taken(extra), p.mult(T["antibiotic"], T["amiodarone"], extra)
            st = S.steady_state(tp["t_half"], tp["ec50"], float(np.mean(doses[:7])), m=mult[0])
            inr, _ = S.run(st, tp["t_half"], tp["ec50"], doses, mult, vk)
            return np.log(np.array(inr))[p.tdays]

        ones = np.ones(n)
        base = logs(others, ones)
        s = logs(others + [me], ones) - base
        paths = []
        for _ in range(200):
            eta, vk = tp["vk_sd"] * rng.normal(), []
            for _d in range(n):
                eta = G.VK_PHI * eta + tp["vk_sd"] * math.sqrt(1 - G.VK_PHI ** 2) * rng.normal()
                vk.append(math.exp(eta))
            paths.append(logs(others, vk) - base)
        C = np.cov(np.array(paths).T) + np.diag(G.METER_SD ** 2 + p.rvar)
        out.append((math.sqrt(float(s @ np.linalg.solve(C, s))), pid, h["start"], h["cause"], h["days"]))
    out.sort(reverse=True)
    print("Unrecorded episodes, expected score with everything else known:")
    for z, pid, start, cause, days in out:
        print(f"  {pid} {start} {cause:24s} {days:2d} days  z {z:5.2f}")
    need = math.ceil(v.MIN_EPISODE_RECALL * len(out) - 1e-9)
    for thr in (5.0, 4.0, 3.0, 2.0):
        print(f"  episodes with expected z >= {thr:.1f}: {sum(1 for o in out if o[0] >= thr)} of {len(out)}")
    c3 = sum(1 for o in out if o[0] >= 3.0)
    print(f"recall limit {v.MIN_EPISODE_RECALL} needs {need} of {len(out)}; {c3} have an expected score of 3 or more: "
          + ("the limit is inside the ceiling" if need <= c3 else "THE RECALL LIMIT IS ABOVE THE CEILING"))


if __name__ == "__main__":
    main()
