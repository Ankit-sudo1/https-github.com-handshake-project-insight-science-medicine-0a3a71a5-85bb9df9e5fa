#!/usr/bin/env bash
# Authoring: run the oracle, an empty submission and the probes (authoring/probes.py) through the unmodified
# tests/test.sh in a verifier-like layout (/app, /tests, /solution) and log each reward.
#     bash authoring/harness_checks.sh
# writes authoring/evidence/{harness.txt,reference_run.txt,reference_output.json}.
# REUSE_ORACLE=1 re-grades the last oracle output instead of running the reference again.
# pytest is the pinned 9.1.1 of tests/Dockerfile. Where the authoring sandbox cannot reach PyPI, numpy and
# pytest live in different interpreters: PYTHONPATH joins them and authoring/shim/ctrf_standin.py stands in for
# pytest-json-ctrf (it only writes the CTRF file; test selection, collection and exit status are real pytest's).
# The line at the top of harness.txt records which combination produced that log.
set -uo pipefail
TASK="$(cd "$(dirname "$0")/.." && pwd)"
ART=/app/dose_plan.json
EV="$TASK/authoring/evidence"; mkdir -p "$EV" /app /tests /solution /logs/verifier
rm -rf /app/data /tests/* /solution/*
cp -r "$TASK/environment/data" /app/data; cp -r "$TASK/tests/." /tests/; cp -r "$TASK/solution/." /solution/
rm -f "$ART"

PYTEST_NOTE="pytest $(python3 -m pytest --version 2>&1 | head -1)"
if ! python3 -c "import pytest" 2>/dev/null; then
  UVPY=$(ls -d /root/.local/share/uv/tools/pytest/lib/python*/site-packages 2>/dev/null | head -1)
  if [ -n "$UVPY" ]; then
    export PYTHONPATH="$UVPY:$TASK/authoring/shim${PYTHONPATH:+:$PYTHONPATH}"
    export PYTEST_PLUGINS=ctrf_standin
    PYTEST_NOTE="real pytest $(python3 -c 'import pytest; print(pytest.__version__)') from the uv tool store (PyPI unreachable here), with authoring/shim/ctrf_standin.py in place of pytest-json-ctrf"
  fi
fi

grade() {   # $1 label, $2 expected reward
  bash /tests/test.sh > /tmp/harness_pytest.log 2>&1
  local got; got=$(cat /logs/verifier/reward.txt)
  local fails; fails=$(grep -E "^FAILED" /tmp/harness_pytest.log | sed -E 's/^FAILED [^:]*::([a-z_]+).*/\1/' | sort -u | tr '\n' ' ')
  local why; why=$(grep -E "^E  *(AssertionError|assert|FileNotFoundError|ValueError|json)" /tmp/harness_pytest.log \
      | grep -oE "episode precision [0-9.]+ < [0-9.]+|episode recall [0-9.]+ < [0-9.]+|patients with the INR in 2.0-3.0 on less than [0-9.]+ of the plan mornings: \{[^}]{0,60}|patients with the INR above 4.0 or below 1.5 on more than [0-9.]+ of the plan mornings: \{[^}]{0,60}|not found|is not allowed|Expecting [a-z ]+|does not follow the required format: [^;]{0,70}" | head -1)
  printf "%-40s reward %s (expected %s) %s %s %s\n" "$1" "$got" "$2" "$([ "$got" = "$2" ] && echo ok || echo MISMATCH)" "${fails:+failed: $fails}" "${why:+($why)}"
}

{
  echo "machine: $(python3 -c 'import os; print(os.cpu_count())') CPUs; test runner: $PYTEST_NOTE"
  echo "verifier: $(grep -oE '^(EPISODE_TOL_DAYS|MIN_EPISODE_PRECISION|MIN_EPISODE_RECALL|MIN_TTR|MAX_OUT_OF_SAFE) = [^#]+' /tests/test_outputs.py | tr '\n' ';')"
  if [ "${REUSE_ORACLE:-0}" = 1 ]; then
    cp "$EV/reference_output.json" "$ART"
  else
    start=$(date +%s)
    bash /solution/solve.sh > "$EV/reference_run.txt" 2>&1 &
    pid=$!; peak=0
    while kill -0 "$pid" 2>/dev/null; do
      # resident memory of every process under solve.sh (the solver and its worker processes)
      rss=$(ps -eo pid=,ppid=,rss= | awk -v root="$pid" '{par[$1]=$2; mem[$1]=$3} END {for (p in par) {q=p; while (q in par && q != root) q=par[q]; if (q == root && p != root) s+=mem[p]} print s+0}')
      [ "${rss:-0}" -gt "$peak" ] && peak=$rss; sleep 2
    done
    wait "$pid"
    printf "\nwall time %d s; peak resident memory of the solver %d MB\n" $(( $(date +%s) - start )) $(( peak / 1024 )) >> "$EV/reference_run.txt"
    cp "$ART" "$EV/reference_output.json"
  fi
  t0=$(date +%s.%N); grade "oracle" 1; t1=$(date +%s.%N)
  echo "the verifier graded the oracle in $(python3 -c "print(round($t1 - $t0, 1))") s"
  python3 -I "$TASK/authoring/score.py" "$TASK" "$EV/reference_output.json" | sed 's/^/  /'
  if [ "${REUSE_ORACLE:-0}" != 1 ]; then
    bash /solution/solve.sh > /dev/null 2>&1
    if cmp -s "$ART" "$EV/reference_output.json"; then echo "oracle run twice: byte-identical output"; else echo "oracle run twice: OUTPUT DIFFERS"; fi
  fi
  rm -f "$ART"; grade "no submission" 0
  W=$(mktemp -d); python3 -I "$TASK/authoring/probes.py" /tests/truth.json "$W" "$EV/reference_output.json" > /dev/null
  for f in "$W"/pass_*.json "$W"/fail_*.json; do
    cp "$f" "$ART"
    case "$(basename "$f")" in pass_*) e=1;; *) e=0;; esac
    grade "$(basename "$f" .json)" "$e"
  done
  rm -f "$ART"
  echo "final permissions: $(stat -c '%a %U' /logs/verifier) $(stat -c '%a' /logs/verifier/reward.txt) $(stat -c '%a' /logs/verifier/ctrf.json)"
} | tee "$EV/harness.txt"
