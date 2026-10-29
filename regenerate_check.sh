#!/usr/bin/env bash
# Authoring: every public file, the truth and the verifier's copy of the simulator must reproduce byte for byte.
#     bash authoring/regenerate_check.sh  ->  authoring/evidence/regenerate.txt
set -uo pipefail
TASK="$(cd "$(dirname "$0")/.." && pwd)"
EV="$TASK/authoring/evidence"; mkdir -p "$EV"
W=$(mktemp -d)
mkdir -p "$W/task/authoring/evidence" "$W/task/tests" "$W/task/environment"
cp "$TASK/authoring/generate.py" "$TASK/authoring/simcore.py" "$TASK/authoring/protocol.md" "$W/task/authoring/"
{
  echo "Regeneration from a clean copy (authoring/regenerate_check.sh)"
  python3 -I "$W/task/authoring/generate.py" "$W/task" 2>&1 | sed 's/^/  generator: /'
  bad=0
  for f in $(cd "$TASK/environment/data" && ls); do
    if cmp -s "$TASK/environment/data/$f" "$W/task/environment/data/$f"; then echo "identical  environment/data/$f"; else echo "DIFFERS    environment/data/$f"; bad=1; fi
  done
  for f in truth.json simcore.py; do
    if cmp -s "$TASK/tests/$f" "$W/task/tests/$f"; then echo "identical  tests/$f"; else echo "DIFFERS    tests/$f"; bad=1; fi
  done
  if cmp -s "$TASK/authoring/simcore.py" "$TASK/tests/simcore.py"; then echo "identical  authoring/simcore.py = tests/simcore.py"; else echo "DIFFERS    authoring/simcore.py vs tests/simcore.py"; bad=1; fi
  [ "$bad" -eq 0 ] && echo "every file reproduced byte for byte" || echo "REGENERATION DIFFERS"
} | tee "$EV/regenerate.txt"
rm -rf "$W"
