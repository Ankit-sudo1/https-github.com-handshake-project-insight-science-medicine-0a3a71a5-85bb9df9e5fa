"""Verifier for warfarin-dose-plan.

Reads the passive artifact /app/dose_plan.json (no submitted code is executed) and grades it against
tests/truth.json, which holds every patient's half-life and EC50, the model state at the end of the record, the
plan block's vitamin K factor and interaction multiplier of every day, and the start and cause of every
unrecorded episode. The plan is graded by simulating each patient through the plan block with tests/simcore.py,
the clinic's model as protocol.md states it.
"""
import datetime as dt
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import simcore as S  # noqa: E402

with open(os.path.join(HERE, "truth.json"), encoding="utf-8") as _f:
    _TRUTH = json.load(_f)

PRED = "/app/dose_plan.json"
MAX_BYTES = 4 << 20
DFMT = "%Y-%m-%d"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EPISODE_TOL_DAYS = 3
MIN_EPISODE_PRECISION = 0.75
MIN_EPISODE_RECALL = 0.60
MIN_TTR = 0.80                  # per patient, share of plan mornings with INR 2.0-3.0
MAX_OUT_OF_SAFE = 0.03          # per patient, share of plan mornings with INR above 4.0 or below 1.5
CAUSES = ("missed_dose", "unrecorded_interaction")
DOSE_MAX = 20.0

PATIENTS = sorted(_TRUTH["patients"])
PLAN_FIRST = dt.datetime.strptime(_TRUTH["plan_first"], DFMT).date()
PLAN_DATES = [(PLAN_FIRST + dt.timedelta(days=k)).isoformat() for k in range(_TRUTH["plan_days"])]
RECORD_FIRST = dt.datetime.strptime(_TRUTH["record_first"], DFMT).date()
RECORD_LAST = dt.datetime.strptime(_TRUTH["record_last"], DFMT).date()
ROWS = {(pid, d): (pid, k) for pid in PATIENTS for k, d in enumerate(PLAN_DATES)}
TRUE_EPISODES = sorted((h["patient"], dt.datetime.strptime(h["start"], DFMT).date(), h["cause"])
                       for h in _TRUTH["hidden"])
for _pid in PATIENTS:
    _tp = _TRUTH["patients"][_pid]
    assert len(_tp["plan_vk"]) == len(_tp["plan_mult"]) == _TRUTH["plan_days"], f"{_pid}: plan inputs incomplete"
_STATE = {}


def _reject(name):
    raise ValueError(f"{name} is not allowed")


def parsed():
    if "data" in _STATE:
        return _STATE["data"]
    if not os.path.exists(PRED):
        raise FileNotFoundError(f"{PRED} not found")
    if os.path.islink(PRED):
        raise ValueError(f"{PRED} must be a regular file, not a symlink")
    if os.path.getsize(PRED) > MAX_BYTES:
        raise ValueError(f"{PRED} is larger than {MAX_BYTES} bytes")
    with open(PRED, encoding="utf-8") as f:
        data = json.load(f, parse_constant=_reject)
    _STATE["data"] = data
    return data


def _dose_ok(x):
    return (isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and 0.0 <= x <= DOSE_MAX
            and abs(x * 2 - round(x * 2)) < 1e-9)


def schema_problems(data):
    """The first way the artifact breaks the required format, or None."""
    if not isinstance(data, dict) or set(data) != {"episodes", "doses"}:
        return "the object must have exactly the keys episodes and doses"
    rows = data["doses"]
    if not isinstance(rows, list):
        return "doses must be a list"
    seen = set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or set(r) != {"patient", "date", "dose_mg"}:
            return f"doses[{i}] must have exactly the keys patient, date and dose_mg"
        key = (r["patient"], r["date"])
        if not all(isinstance(x, str) for x in key) or key not in ROWS:
            return f"doses[{i}] is not a row of plan_days.csv"
        if key in seen:
            return f"doses[{i}] repeats {key[0]} {key[1]}"
        seen.add(key)
        if not _dose_ok(r["dose_mg"]):
            return f"doses[{i}].dose_mg must be a multiple of 0.5 from 0 to {DOSE_MAX:g}"
    if seen != set(ROWS):
        return f"doses covers {len(seen)} of the {len(ROWS)} rows of plan_days.csv"
    eps = data["episodes"]
    if not isinstance(eps, list):
        return "episodes must be a list"
    seen = set()
    for i, e in enumerate(eps):
        if not isinstance(e, dict) or set(e) != {"patient", "start", "cause"}:
            return f"episodes[{i}] must have exactly the keys patient, start and cause"
        if not isinstance(e["patient"], str) or e["patient"] not in PATIENTS:
            return f"episodes[{i}].patient is not one of the patients"
        if not isinstance(e["start"], str) or not DATE_RE.match(e["start"]):
            return f"episodes[{i}].start is not YYYY-MM-DD"
        try:
            d = dt.datetime.strptime(e["start"], DFMT).date()
        except ValueError:
            return f"episodes[{i}].start is not a valid date"
        if not (RECORD_FIRST <= d <= RECORD_LAST):
            return f"episodes[{i}].start {e['start']} is not within the record"
        if e["cause"] not in CAUSES:
            return f"episodes[{i}].cause is not one of {', '.join(CAUSES)}"
        if (e["patient"], e["start"]) in seen:
            return f"episodes[{i}] repeats a patient and start"
        seen.add((e["patient"], e["start"]))
    return None


def valid():
    data = parsed()
    problem = schema_problems(data)
    if problem:
        raise AssertionError(f"does not follow the required format: {problem}")
    return data


def simulate_plan():
    """For every patient, the INR on each of the 56 mornings that follow a plan dose: the clinic's model
    (tests/simcore.py) from the state at the end of the record, with the patient's half-life and EC50 and the plan
    block's vitamin K factor and interaction multiplier of every day (the planned events included). Returns
    {patient: (share in 2.0-3.0, share above 4.0 or below 1.5)}."""
    if "plan" in _STATE:
        return _STATE["plan"]
    data = valid()
    by_day = {pid: [None] * _TRUTH["plan_days"] for pid in PATIENTS}
    for r in data["doses"]:
        pid, k = ROWS[(r["patient"], r["date"])]
        by_day[pid][k] = float(r["dose_mg"])
    out = {}
    for pid in PATIENTS:
        tp = _TRUTH["patients"][pid]
        st = list(tp["state"])
        inr = []
        for k, dose in enumerate(by_day[pid]):
            st = S.step(st, tp["t_half"], tp["ec50"], dose, tp["plan_mult"][k], tp["plan_vk"][k])
            inr.append(S.inr_of(st))
        n = len(inr)
        out[pid] = (sum(1 for x in inr if 2.0 <= x <= 3.0) / n, sum(1 for x in inr if x > 4.0 or x < 1.5) / n)
    _STATE["plan"] = out
    return out


def match_episodes(rep):
    """A report is correct when an actual episode of the same patient and cause started within EPISODE_TOL_DAYS of
    its date, each actual episode crediting at most one report: the largest such one-to-one pairing (augmenting
    paths), so the score does not depend on the order of the reports."""
    cand = [[i for i, (tp, td, tc) in enumerate(TRUE_EPISODES)
             if tp == pid and tc == cause and abs((d - td).days) <= EPISODE_TOL_DAYS]
            for pid, d, cause in rep]
    owner = {}

    def augment(k, seen):
        for i in cand[k]:
            if i in seen:
                continue
            seen.add(i)
            if i not in owner or augment(owner[i], seen):
                owner[i] = k
                return True
        return False

    hit = sum(1 for k in range(len(rep)) if augment(k, set()))
    n = len(rep)
    return dict(n=n, hit=hit, precision=hit / n if n else 0.0, recall=hit / len(TRUE_EPISODES))


def episode_scores():
    data = valid()
    rep = [(e["patient"], dt.datetime.strptime(e["start"], DFMT).date(), e["cause"]) for e in data["episodes"]]
    return match_episodes(rep)


def test_file_format():
    """The artifact is one JSON object with exactly the keys episodes and doses: one dose per row of plan_days.csv,
    a multiple of 0.5 from 0 to 20 mg; episodes with a patient, a start date within the record and a cause, at most
    one per patient per start. The file is a regular file (not a symlink) of at most 4 MiB holding standard JSON
    (no NaN or Infinity), as the instruction states."""
    valid()


def test_episode_precision():
    """At least 75% of the reported episodes are correct: an actual unrecorded episode of the same patient and cause
    started within 3 days of each, each actual episode crediting at most one report."""
    sc = episode_scores()
    assert sc["precision"] >= MIN_EPISODE_PRECISION, f"episode precision {sc['precision']:.4f} < {MIN_EPISODE_PRECISION}"


def test_episode_recall():
    """At least 60% of the actual unrecorded episodes are found (credited to a correct report)."""
    sc = episode_scores()
    assert sc["recall"] >= MIN_EPISODE_RECALL, f"episode recall {sc['recall']:.4f} < {MIN_EPISODE_RECALL}"


def test_time_in_range():
    """For each patient separately, the INR is within 2.0-3.0 on at least 80% of the mornings after a plan dose."""
    res = simulate_plan()
    bad = {pid: round(ttr, 4) for pid, (ttr, _) in res.items() if ttr < MIN_TTR}
    assert not bad, f"patients with the INR in 2.0-3.0 on less than {MIN_TTR} of the plan mornings: {bad}"


def test_unsafe_inr():
    """For each patient separately, the INR is above 4.0 or below 1.5 on at most 3% of the mornings after a plan
    dose."""
    res = simulate_plan()
    bad = {pid: round(x, 4) for pid, (_, x) in res.items() if x > MAX_OUT_OF_SAFE}
    assert not bad, f"patients with the INR above 4.0 or below 1.5 on more than {MAX_OUT_OF_SAFE} of the plan mornings: {bad}"
