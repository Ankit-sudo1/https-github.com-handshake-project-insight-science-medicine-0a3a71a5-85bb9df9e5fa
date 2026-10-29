"""Ablation table: each variant is the full reference pipeline with one step done naively (or one choice changed),
refitted from scratch and graded with the verifier's functions. Resumable: a variant whose output exists is not
rerun.
    python3 authoring/ablations.py [variant ...]      (no argument: every variant, then the table)
writes authoring/ablation_out/<variant>.json and evidence/ablations.txt."""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(HERE)
OUT = os.path.join(HERE, "ablation_out")
EV = os.path.join(HERE, "evidence")

VARIANTS = {
    "reference": "the reference as shipped",
    "white_vitamin_k": "the vitamin K factor treated as independent from day to day (no AR(1) correlation)",
    "meter_noise_only": "the vitamin K variation ignored: only the meter error in the likelihood",
    "fixed_half_life": "every patient's half-life fixed at 40 h",
    "no_episode_model": "no episode is detected, so none is reported or modelled in the fit",
    "ignore_planned_events": "the planned amiodarone start and antibiotic course are ignored in the plan",
    "amiodarone_stops": "the record's amiodarone treated as ending with the record in the plan",
    "no_half_life_prior": "no prior on the half-life (the protocol's 20-70 h range not used)",
    "finer_course_lengths": "every course length from 7 to 14 days tried, not every other one",
    "lookahead_five": "the dose design aims the INR five days ahead instead of three",
    "meter_six_percent": "the meter error taken as 6% instead of 5%",
}

PATCH = r'''
import sys, os, numpy as np
sys.path.insert(0, os.path.join(TASK, "solution"))
import solve as S
v = VARIANT
if v == "white_vitamin_k":
    S.ar_cov = lambda n: np.eye(n)
elif v == "meter_noise_only":
    S.ar_cov = lambda n: np.zeros((n, n))
elif v == "fixed_half_life":
    S.T_HALF_PRIOR = (40.0, 1e-4)
elif v == "no_episode_model":
    S.Z_ADD = 1e9
elif v == "no_half_life_prior":
    S.T_HALF_PRIOR = (40.0, 100.0)
elif v == "finer_course_lengths":
    S.COURSE_LENGTHS = tuple(range(7, 15))
elif v == "lookahead_five":
    S.LOOKAHEAD = 5
elif v == "meter_six_percent":
    S.METER_SD = 0.06
elif v == "amiodarone_stops":
    S.AMIO_CONTINUES = False
an = S.analyse(os.path.join(TASK, "environment", "data"))
if v == "ignore_planned_events":
    an["plan_events"] = {}
S.write(an, OUTFILE)
'''


def run(v):
    path = os.path.join(OUT, v + ".json")
    if os.path.exists(path):
        return
    os.makedirs(OUT, exist_ok=True)
    code = f"TASK = {TASK!r}\nVARIANT = {v!r}\nOUTFILE = {path + '.tmp'!r}\n" + PATCH
    subprocess.run([sys.executable, "-c", code], check=True)
    os.replace(path + ".tmp", path)


def table():
    sys.path.insert(0, HERE)
    from score import load_verifier, score
    ver = load_verifier(TASK)
    lines = [f"{'variant':22s} {'rep':>4s} {'hit':>4s} {'prec':>6s} {'recall':>6s} {'min TTR':>8s} {'max unsafe':>10s}  result"]
    for v, what in VARIANTS.items():
        path = os.path.join(OUT, v + ".json")
        if not os.path.exists(path):
            lines.append(f"{v:22s} (not run)")
            continue
        s = score(TASK, path, ver)
        failed = [k for k, ok in s["passes"].items() if not ok]
        worst = min(s["ttr"], key=lambda p: s["ttr"][p])
        res = "passes" if not failed else "FAILS " + ",".join(failed)
        lines.append(f"{v:22s} {s['reported']:4d} {s['hit']:4d} {s['precision']:6.3f} {s['recall']:6.3f} "
                     f"{s['min_ttr']:8.3f} {s['max_unsafe']:10.3f}  {res} (lowest TTR {worst})")
        lines.append(f"{'':22s} ({what})")
    lines.append(f"limits: precision >= {ver.MIN_EPISODE_PRECISION}, recall >= {ver.MIN_EPISODE_RECALL}, "
                 f"every TTR >= {ver.MIN_TTR}, every unsafe share <= {ver.MAX_OUT_OF_SAFE}")
    with open(os.path.join(EV, "ablations.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    todo = sys.argv[1:] or list(VARIANTS)
    for v in todo:
        if v != "table":
            run(v)
    table()
