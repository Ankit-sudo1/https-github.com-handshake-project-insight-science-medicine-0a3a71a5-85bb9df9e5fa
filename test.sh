#!/usr/bin/env bash
# Verifier entrypoint. Reward 0 is written first so every exit path leaves a binary reward. The verifier only
# reads the passive artifact /app/dose_plan.json; no agent code is executed. The dose plan is graded by
# simulating each patient with tests/simcore.py and the hidden truth in tests/truth.json.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
cd /tests
python3 -m pytest /tests/test_outputs.py --ctrf /logs/verifier/ctrf.json -rA -p no:cacheprovider
rc=$?
if [ "$rc" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit 0
