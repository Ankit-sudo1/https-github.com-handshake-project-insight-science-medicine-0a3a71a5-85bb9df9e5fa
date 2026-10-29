"""Probe submissions for the harness: each varies a correct answer in one respect, so that a failing probe fails on
its own test alone. Limits are read from the verifier's constants, not restated here.

Usage: python3 probes.py <truth.json> <out_dir> <reference_output.json>
Writes pass_*.json (expected reward 1) and fail_*.json (expected 0) into out_dir.
"""
import copy
import datetime as dt
import importlib.util
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def verifier():
    spec = importlib.util.spec_from_file_location("v", os.path.join(os.path.dirname(HERE), "tests", "test_outputs.py"))
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    return v


def shift(e, days):
    d = dt.date.fromisoformat(e["start"]) + dt.timedelta(days=days)
    return dict(e, start=d.isoformat())


def main(truth_path, out, ref_path):
    v = verifier()
    truth = json.load(open(truth_path))
    ref = json.load(open(ref_path))
    os.makedirs(out, exist_ok=True)
    true_eps = [dict(patient=h["patient"], start=h["start"], cause=h["cause"]) for h in truth["hidden"]]
    good = dict(episodes=true_eps, doses=copy.deepcopy(ref["doses"]))
    tol = v.EPISODE_TOL_DAYS
    probes = {}

    def put(name, obj):
        probes[name] = obj

    def in_record(e):
        return truth["record_first"] <= e["start"] <= truth["record_last"]

    put("pass_reference", ref)
    put("pass_true_episodes", good)
    r = copy.deepcopy(good)
    r["episodes"] = list(reversed(r["episodes"]))
    put("pass_reordered", r)
    r = copy.deepcopy(good)
    r["episodes"] = [e for e in (shift(e, tol * (1 if k % 2 else -1)) for k, e in enumerate(true_eps)) if in_record(e)]
    put("pass_episodes_inside_tolerance", r)
    r = copy.deepcopy(good)
    r["episodes"] = [e for e in (shift(e, (tol + 1) * (1 if k % 2 else -1)) for k, e in enumerate(true_eps)) if in_record(e)]
    put("fail_episodes_outside_tolerance", r)
    r = copy.deepcopy(good)
    r["episodes"] = [dict(e, cause=v.CAUSES[1 - v.CAUSES.index(e["cause"])]) for e in true_eps]
    put("fail_causes_swapped", r)
    # precision boundary: all actual episodes plus the largest number of wrong reports precision still allows
    n = len(true_eps)
    k_ok = int(math.floor(n / v.MIN_EPISODE_PRECISION - n + 1e-9))
    first = dt.date.fromisoformat(truth["record_first"])
    wrong = []
    for i in range(400):
        pid = v.PATIENTS[i % len(v.PATIENTS)]
        d = first + dt.timedelta(days=7 + (13 * i) % 170)
        e = dict(patient=pid, start=d.isoformat(), cause=v.CAUSES[i % 2])
        if all(not (t["patient"] == pid and t["cause"] == e["cause"] and
                    abs((dt.date.fromisoformat(t["start"]) - d).days) <= tol) for t in true_eps) \
                and all((w["patient"], w["start"]) != (pid, e["start"]) for w in wrong):
            wrong.append(e)
        if len(wrong) > k_ok:
            break
    assert len(wrong) == k_ok + 1
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + wrong[:k_ok]
    put("pass_precision_at_limit", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + wrong[:k_ok + 1]
    put("fail_precision_below_limit", r)
    need = int(math.ceil(v.MIN_EPISODE_RECALL * n - 1e-9))
    r = copy.deepcopy(good)
    r["episodes"] = true_eps[:need]
    put("pass_recall_at_limit", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps[:need - 1]
    put("fail_recall_below_limit", r)
    r = copy.deepcopy(good)
    r["episodes"] = []
    put("fail_no_episodes", r)
    # the plan: every dose of one patient 25% too high (fails the range) or far too high (unsafe INR)
    for name, pid, f in (("fail_plan_p09_doses_high", "P09", 1.25), ("fail_plan_p05_doses_double", "P05", 2.0),
                         ("fail_plan_p01_doses_low", "P01", 0.55)):
        r = copy.deepcopy(good)
        for row in r["doses"]:
            if row["patient"] == pid:
                row["dose_mg"] = min(v.DOSE_MAX, round(row["dose_mg"] * f * 2) / 2)
        put(name, r)
    r = copy.deepcopy(good)
    for row in r["doses"]:
        row["dose_mg"] = 0.0
    put("fail_plan_no_warfarin", r)
    # format
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + [dict(true_eps[0])]
    put("fail_episode_repeated", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + [dict(patient="P01", start="2026-07-20", cause="missed_dose")]
    put("fail_episode_after_record", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + [dict(patient="P99", start="2026-03-02", cause="missed_dose")]
    put("fail_unknown_patient", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + [dict(patient="P01", start="2026-03-02", cause="vitamin_k")]
    put("fail_unknown_cause", r)
    r = copy.deepcopy(good)
    r["episodes"] = true_eps + [dict(patient="P01", start="02/03/2026", cause="missed_dose")]
    put("fail_episode_date_format", r)
    r = copy.deepcopy(good)
    r["doses"] = r["doses"][:-1]
    put("fail_dose_row_missing", r)
    r = copy.deepcopy(good)
    r["doses"][0]["dose_mg"] = 2.25
    put("fail_dose_not_half_mg", r)
    r = copy.deepcopy(good)
    r["doses"][0]["dose_mg"] = 25.0
    put("fail_dose_out_of_range", r)
    r = copy.deepcopy(good)
    r["doses"][0]["dose_mg"] = True
    put("fail_dose_boolean", r)
    r = copy.deepcopy(good)
    r["doses"].append(dict(r["doses"][0]))
    put("fail_dose_row_repeated", r)
    r = copy.deepcopy(good)
    r["extra"] = 1
    put("fail_extra_key", r)
    for name, obj in probes.items():
        with open(os.path.join(out, name + ".json"), "w") as f:
            json.dump(obj, f)
    with open(os.path.join(out, "fail_nan_value.json"), "w") as f:
        txt = json.dumps(good)
        f.write(txt.replace('"dose_mg": ' + json.dumps(good["doses"][0]["dose_mg"]), '"dose_mg": NaN', 1))
    with open(os.path.join(out, "fail_truncated_json.json"), "w") as f:
        f.write(json.dumps(good)[:-20])
    with open(os.path.join(out, "fail_top_level_list.json"), "w") as f:
        f.write("[]")
    print(len(probes) + 3, "probes written")


if __name__ == "__main__":
    main(*sys.argv[1:4])
