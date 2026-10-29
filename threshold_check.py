"""Every graded limit must read the same in the verifier's constants, in its test docstrings and in instruction.md.

    python3 authoring/threshold_check.py [task-dir]
"""
import os
import re
import sys

TASK = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ver = open(os.path.join(TASK, "tests", "test_outputs.py"), encoding="utf-8").read()
ins = open(os.path.join(TASK, "instruction.md"), encoding="utf-8").read()


def const(name):
    return re.search(rf"^{name} = ([0-9.]+)", ver, re.M).group(1)


def pct(name):
    return int(round(float(const(name)) * 100))


checks = [
    ("episode precision", const("MIN_EPISODE_PRECISION"), [f"at least {pct('MIN_EPISODE_PRECISION')}% of the reported"],
     [f"At least {pct('MIN_EPISODE_PRECISION')}% of the reported"]),
    ("episode recall", const("MIN_EPISODE_RECALL"), [f"at least {pct('MIN_EPISODE_RECALL')}% of the actual"],
     [f"At least {pct('MIN_EPISODE_RECALL')}% of the actual"]),
    ("episode tolerance", const("EPISODE_TOL_DAYS"), [f"within {const('EPISODE_TOL_DAYS')} days of its date"],
     [f"within {const('EPISODE_TOL_DAYS')} days of each"]),
    ("time in range", const("MIN_TTR"), [f"on at least {pct('MIN_TTR')}% of those mornings"],
     [f"on at least {pct('MIN_TTR')}% of the mornings"]),
    ("unsafe INR", const("MAX_OUT_OF_SAFE"), [f"on at most {pct('MAX_OUT_OF_SAFE')}% of those mornings"],
     [f"on at most {pct('MAX_OUT_OF_SAFE')}% of the mornings"]),
]
bad = 0
for name, value, in_instruction, in_docstrings in checks:
    ok_i = all(s in ins for s in in_instruction)
    ok_d = all(s in ver for s in in_docstrings)
    print(f"{'PASS' if ok_i and ok_d else 'FAIL'}  {name} = {value}: instruction {'ok' if ok_i else 'MISSING ' + str(in_instruction)}, "
          f"docstrings {'ok' if ok_d else 'MISSING ' + str(in_docstrings)}")
    bad += 0 if ok_i and ok_d else 1
sys.exit(1 if bad else 0)
