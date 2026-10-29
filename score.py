"""Score a submission with the verifier's own functions (no pytest). Usage: python3 score.py <task_dir> <plan.json>"""
import importlib.util
import json
import os
import sys


def load_verifier(task):
    spec = importlib.util.spec_from_file_location("verifier", os.path.join(task, "tests", "test_outputs.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score(task, path, verifier=None):
    v = verifier or load_verifier(task)
    v.PRED = path
    v._STATE.clear()
    problem = v.schema_problems(v.parsed())
    if problem:
        return dict(format=problem)
    ep = v.episode_scores()
    plan = v.simulate_plan()
    ttr = {p: round(a, 4) for p, (a, b) in plan.items()}
    unsafe = {p: round(b, 4) for p, (a, b) in plan.items()}
    ok = dict(precision=ep["precision"] >= v.MIN_EPISODE_PRECISION, recall=ep["recall"] >= v.MIN_EPISODE_RECALL,
              ttr=all(a >= v.MIN_TTR for a in ttr.values()),
              unsafe=all(b <= v.MAX_OUT_OF_SAFE for b in unsafe.values()))
    return dict(reported=ep["n"], hit=ep["hit"], precision=round(ep["precision"], 4), recall=round(ep["recall"], 4),
                ttr=ttr, unsafe=unsafe, min_ttr=min(ttr.values()), max_unsafe=max(unsafe.values()), passes=ok,
                reward=int(all(ok.values())))


if __name__ == "__main__":
    print(json.dumps(score(sys.argv[1], sys.argv[2]), indent=1))
