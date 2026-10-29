"""Run the reference's analysis once and keep what the calibration scripts need (every patient's fit and
forward-selection sequence), cached in /tmp so the studies can share it."""
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TASK = os.path.dirname(HERE)
DATA = os.path.join(TASK, "environment", "data")
sys.path.insert(0, os.path.join(TASK, "solution"))
import solve as S  # noqa: E402

CACHE = "/tmp/warfarin_analysis.pkl"


def analysis():
    if os.path.exists(CACHE):
        with open(CACHE, "rb") as fh:
            return pickle.load(fh)
    an = S.analyse(DATA)
    with open(CACHE, "wb") as fh:
        pickle.dump(an, fh)
    return an
