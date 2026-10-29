#!/usr/bin/env bash
# Authoring: clean the task folder and write the submission archive.
#     bash authoring/package.sh [out-dir]
# Removes caches and scratch, runs the static checks, and writes <out-dir>/<slug>.zip.
set -uo pipefail
TASK="$(cd "$(dirname "$0")/.." && pwd)"
SLUG=$(basename "$TASK")
OUT=${1:-$(dirname "$TASK")}

find "$TASK" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
find "$TASK" -name '*.pyc' -delete 2>/dev/null
find "$TASK" -name '.DS_Store' -delete 2>/dev/null
rm -rf "$TASK/authoring/ablation_out"

# every text file must be UTF-8 with LF endings
bad=$(find "$TASK" -type f \( -name '*.py' -o -name '*.sh' -o -name '*.md' -o -name '*.csv' -o -name '*.json' \
      -o -name '*.toml' -o -name '*.c' -o -name 'Dockerfile' \) -exec file {} \; | grep -i 'CRLF' | head)
[ -n "$bad" ] && { echo "CRLF line endings found:"; echo "$bad"; exit 1; }

bash "$TASK/authoring/static_checks.sh" > /dev/null 2>&1
# the static checks run pytest-adjacent code, which can recreate caches: clean again before zipping
find "$TASK" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
find "$TASK" -name '*.pyc' -delete 2>/dev/null
fails=$(grep -c '^FAIL' "$TASK/authoring/evidence/static_checks.txt")
echo "static checks: $fails FAIL lines"
grep '^FAIL' "$TASK/authoring/evidence/static_checks.txt"
if [ "$fails" -ne 0 ]; then
  echo "refusing to package while a static check fails; fix the lines above and run this again" >&2
  exit 1
fi

mkdir -p "$OUT"
rm -f "$OUT/$SLUG.zip"
( cd "$(dirname "$TASK")" && zip -qr "$OUT/$SLUG.zip" "$SLUG" -x '*/__pycache__/*' '*.pyc' )
echo "wrote $OUT/$SLUG.zip ($(du -h "$OUT/$SLUG.zip" | cut -f1))"
unzip -l "$OUT/$SLUG.zip" | tail -3
