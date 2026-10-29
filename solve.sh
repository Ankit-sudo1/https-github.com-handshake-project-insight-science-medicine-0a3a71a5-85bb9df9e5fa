#!/usr/bin/env bash
# Oracle: a maximum-likelihood fit of the clinic's dose model to each patient's home INR record (vitamin K
# variation through its exact linear response), unrecorded missed doses and antibiotic courses found by forward
# selection on likelihood-ratio tests, and doses designed with the fitted model. All logic is in solve.py.
set -euo pipefail
python3 /solution/solve.py --data /app/data --out /app/dose_plan.json
