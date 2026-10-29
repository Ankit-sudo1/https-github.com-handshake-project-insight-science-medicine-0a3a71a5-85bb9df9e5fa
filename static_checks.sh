#!/usr/bin/env bash
# Authoring: the repository-independent static checks, run over the task folder before pushing.
#     bash authoring/static_checks.sh   ->  authoring/evidence/static_checks.txt
# Each line is PASS or FAIL; a FAIL means the task would be rejected by the corresponding gate.
set -uo pipefail
TASK="$(cd "$(dirname "$0")/.." && pwd)"
EV="$TASK/authoring/evidence"; mkdir -p "$EV"
SLUG=$(basename "$TASK")
fails=0
chk() {  # $1 description, $2 = 0 for pass
  if [ "$2" -eq 0 ]; then printf "PASS  %s\n" "$1"; else printf "FAIL  %s\n" "$1"; fails=$((fails+1)); fi
}
{
echo "Static checks for $SLUG"
echo

# --- layout -------------------------------------------------------------------------------------------------
for f in task.toml instruction.md README.md solution/solve.sh environment/Dockerfile tests/Dockerfile \
         tests/test.sh tests/test_outputs.py; do
  [ -f "$TASK/$f" ]; chk "required file $f exists" $?
done
[ -d "$TASK/environment/data" ]; chk "environment/data/ exists" $?
[ -z "$(find "$TASK" -name __pycache__ -o -name '*.pyc' -o -name '.DS_Store' | head -1)" ]
chk "no __pycache__, .pyc or editor metadata anywhere in the task" $?
[ -z "$(find "$TASK" -name 'trajector*' -o -name 'pass2*' -o -name '*.png' -o -name 'blind*_output.json' | head -1)" ]
chk "no trajectories, pass2 output, screenshots or blind-trial output files (the blind-trial summary in evidence/ is intended)" $?
n=$(awk -F- '{print NF}' <<< "$SLUG"); [ "$n" -le 3 ]; chk "slug '$SLUG' is at most three hyphen-separated tokens" $?

# --- task.toml ----------------------------------------------------------------------------------------------
T="$TASK/task.toml"
head -1 "$T" | grep -q '^artifacts = \['; chk "artifacts is the first line, above any [section]" $?
awk '/^\[/{found=1} /^artifacts =/{if(found) exit 1} END{exit 0}' "$T"; chk "artifacts appears above the first TOML section header" $?
grep -q '^schema_version = "2.0"$' "$T"; chk "schema_version is 2.0" $?
grep -q "^name = \"insight/$SLUG\"$" "$T"; chk "task name is insight/$SLUG" $?
grep -q '^environment_mode = "separate"$' "$T"; chk "verifier environment_mode is separate" $?
! grep -q 'allow_internet' "$T"; chk "allow_internet is absent" $?
AT=$(grep -oP '(?<=^timeout_sec = )[0-9.]+' "$T" | tail -1)
grep -q "You have ${AT%.0} seconds to complete this task" "$TASK/instruction.md"
chk "instruction timeout matches [agent] timeout_sec (${AT})" $?
VT=$(awk '/^\[verifier\]/{f=1} f&&/^timeout_sec/{print $3; exit}' "$T")
awk -v v="$VT" 'BEGIN{exit !(v<=18000)}'; chk "verifier timeout ${VT} is within the 18000 s cap" $?
awk -v v="$AT" 'BEGIN{exit !(v<=18000+10800)}'; chk "agent timeout ${AT} is a stated 8 h budget" $?
python3 -c "import tomllib,sys; tomllib.load(open('$T','rb'))"; chk "task.toml parses as TOML" $?
python3 - "$T" <<'PY'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], 'rb'))
m = d.get('metadata', {})
need = {"domain", "field", "subfield", "tags", "expert_time_estimate_hours", "relevant_experience"}
other = {"difficulty_explanation", "solution_explanation", "verification_explanation", "category", "subcategory"}
missing = need - set(m)
mixed = other & set(m)
assert not missing, f"missing {sorted(missing)}"
assert not mixed, f"mixes the other layout's fields {sorted(mixed)}"
assert m["expert_time_estimate_hours"] > 0
PY
chk "[metadata] uses exactly one layout (domain/field/subfield, explanations in README.md)" $?
grep -qiE '"(Pass@|gpt|claude|solved in|trial)' "$T"; [ $? -ne 0 ]
chk "no pass rates, model names or trial talk in task.toml" $?

# --- instruction.md -----------------------------------------------------------------------------------------
I="$TASK/instruction.md"
# the CI limit is 1500 tokens of the consumer's tokenizer (Qwen3); this text measured 1522 tokens at 954 words,
# 1.595 tokens per word, so 910 words keeps it near 1450 tokens
W=$(wc -w < "$I"); [ "$W" -le 910 ]; chk "instruction is $W words, within the 1500-token limit (about 1.6 Qwen3 tokens per word here)" $?
tail -1 "$I" | grep -q "^You have ${AT%.0} seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.$"
chk "instruction ends with the exact timeout sentence" $?
! grep -qE '(^|[^/a-zA-Z])data/[a-z_]+\.csv' "$I"; chk "every input path in the instruction is absolute (/app/data/...)" $?
grep -q '/app/dose_plan.json' "$I"; chk "the artifact path is named in the instruction" $?
for f in $(ls "$TASK/environment/data"); do
  grep -q "$f" "$I" || { echo "FAIL  $f is in environment/data but never named in the instruction"; fails=$((fails+1)); }
done
chk "every file in environment/data is named in the instruction" 0
! grep -qiE "pass@|gpt-|claude|best effort|if you run out of time" "$I"
chk "no pass rates, model names or best-effort language in the instruction" $?
DOCW=$(wc -w < "$TASK/environment/data/protocol.md"); [ "$DOCW" -lt "$W" ]
chk "the referenced document ($DOCW words) is shorter than the instruction ($W words)" $?

# --- Dockerfiles --------------------------------------------------------------------------------------------
E="$TASK/environment/Dockerfile"; V="$TASK/tests/Dockerfile"
! grep -q 'FROM --platform' "$E" && ! grep -q 'FROM --platform' "$V"; chk "neither Dockerfile pins --platform" $?
grep -q 'FROM .*@sha256:' "$E" && grep -q 'FROM .*@sha256:' "$V"; chk "both images are pinned by digest" $?
[ "$(grep -oP 'FROM \K\S+' "$E")" = "$(grep -oP 'FROM \K\S+' "$V")" ]; chk "both Dockerfiles use the same base image" $?
grep -q 'pytest==9.1.1' "$V" && grep -q 'pytest-json-ctrf==0.5.2' "$V"; chk "verifier image pins pytest==9.1.1 and pytest-json-ctrf==0.5.2" $?
grep -q 'COPY . /tests/' "$V"; chk "verifier image copies tests/ into /tests" $?
grep -qE 'mkdir -p /app' "$V"; chk "verifier image pre-creates the artifact parent /app" $?
! grep -qE '^\s*(COPY|ADD).*(solution|tests|truth|simcore)' "$E"; chk "agent image copies nothing from solution/, tests/, the truth or the verifier's simulator" $?
! grep -qE 'pip install[^=]*[a-z] *$|pip install .*[a-z]+ [a-z]' "$E" || grep -q '==' "$E"
chk "agent image pins its pip dependencies with ==" $?
! grep -qE 'apt-get install.*[a-z0-9]=[0-9]' "$E"; chk "agent image does not pin apt package versions" $?
grep -q 'apt-get update' "$E" && grep -q 'rm -rf /var/lib/apt/lists' "$E"; chk "agent image updates apt and cleans its lists in one layer" $?

# --- test.sh ------------------------------------------------------------------------------------------------
S="$TASK/tests/test.sh"
awk '/echo 0 > \/logs\/verifier\/reward.txt/{if(!z)z=NR} /pytest/{if(!p)p=NR} END{exit !(z && p && z<p)}' "$S"
chk "test.sh writes reward 0 before running pytest" $?
grep -q 'exit 0' "$S"; chk "test.sh always exits 0" $?
! grep -qE 'pip install|apt-get' "$S"; chk "test.sh installs nothing" $?
grep -q -- '--ctrf /logs/verifier/ctrf.json' "$S"; chk "test.sh writes the CTRF report" $?

# --- leakage ------------------------------------------------------------------------------------------------
! grep -rqiE 'truth|withheld (level|measurement)|true_ng|random_state|np\.random|seed' "$TASK/environment/data/" 2>/dev/null
chk "no truth, seed or simulation language in environment/data" $?
[ ! -f "$TASK/environment/data/truth.json" ]; chk "the truth is not in the agent image" $?
grep -q 'truth.json' "$TASK/.dockerignore" 2>/dev/null || ! grep -rq 'truth' "$TASK/environment/" 2>/dev/null
chk "environment/ contains no reference to the truth" $?

# --- README -------------------------------------------------------------------------------------------------
R="$TASK/README.md"
! grep -qi 'PLACEHOLDER' "$R"; chk "README has no leftover placeholders" $?
# the rubric reads the three metadata explanations; those must describe the task, not the review pipeline.
# A factual change history elsewhere in the README is expected and is not checked here.
! sed -n '/^## Task metadata explanations/,$p' "$R" | grep -qiE 'pass@|gpt-|claude|too_many_solves|solved in|blind trial|trial'
chk "the metadata explanations carry no pass rates, model names or trial talk" $?
grep -q '### Difficulty' "$R" && grep -q '### Solution' "$R" && grep -q '### Verification' "$R"
chk "README carries the three metadata explanations" $?
N=$(grep -cE '^(pass|fail)_' "$EV/harness.txt" 2>/dev/null || echo 0)
[ "$N" -gt 0 ] && [ "$(grep -oE '[0-9]+ probes' "$R" | awk '{print $1}' | sort -u | tr -d '\n')" = "$N" ]
chk "every probe count stated in README matches the $N probes in harness.txt" $?
cmp -s "$TASK/authoring/simcore.py" "$TASK/tests/simcore.py"; chk "the verifier's simulator is the generator's (tests/simcore.py = authoring/simcore.py)" $?
! grep -q "THE RECALL LIMIT IS ABOVE" "$EV/feasibility.txt" 2>/dev/null && [ -f "$EV/feasibility.txt" ]
chk "feasibility.txt shows the episode recall limit inside the detectable ceiling" $?
grep -q "both limits reachable" "$EV/floor.txt" 2>/dev/null
chk "floor.txt shows every patient able to meet both plan limits with the true physiology" $?
grep -q "the grid at the shipped point reproduces the reference's submitted episodes: yes" "$EV/detector_sweep.txt" 2>/dev/null
chk "detector_sweep.txt reproduces the shipped episodes at the shipped operating point" $?
grep -qE "^oracle +reward 1 \(expected 1\) ok" "$EV/harness.txt" 2>/dev/null && ! grep -q "MISMATCH" "$EV/harness.txt" && grep -q "byte-identical" "$EV/harness.txt"
chk "harness.txt: oracle reward 1 twice byte-identical, and every probe as expected" $?
grep -q "every file reproduced byte for byte" "$EV/regenerate.txt" 2>/dev/null
chk "regenerate.txt records byte-for-byte regeneration" $?
grep -q "^0 FAIL lines" "$EV/consistency.txt" 2>/dev/null
chk "consistency.txt has no FAIL line" $?


# every count the README states about its own evidence is recomputed from the evidence (an authoring review
# blocked once on a README that said eighteen ablation variants when ablations.txt had sixteen)
python3 -I - "$TASK" <<'PYCOUNT' > /dev/null 2>&1
import csv, re, sys
t = sys.argv[1]
words = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split()
r = open(f"{t}/README.md", encoding="utf-8").read()
rl = r.lower()
abl = open(f"{t}/authoring/evidence/ablations.txt", encoding="utf-8").read().splitlines()
rows = [l.split()[0] for l in abl if re.match(r"^[a-z_]+ +[0-9.]+ +[0-9.]+ ", l)]
variants = [x for x in rows if x != "reference"]
n_fail = sum(1 for l in abl if re.match(r"^[a-z_]+ +[0-9.]+ ", l) and "FAILS" in l)
bad = []
for m in re.finditer(r"\b(\w+) variants are measured", rl):
    if m.group(1) != words[len(variants)]:
        bad.append(("variants", m.group(1), len(variants)))
for m in re.finditer(r"\b(\w+) fail\. the (\w+) that pass", rl):
    if m.group(1) != words[n_fail] or m.group(2) != words[len(variants) - n_fail]:
        bad.append(("fail/pass", m.groups(), n_fail))
for m in re.finditer(r"the reference and (\w+) variants", rl):
    if m.group(1) != words[len(variants)]:
        bad.append(("table", m.group(1), len(variants)))
bt = open(f"{t}/authoring/evidence/blind_trials.txt", encoding="utf-8").read()
trials = sorted({int(x) for x in re.findall(r"^\s*Trials? (\d+)", bt, re.M)} | {int(y) for x in re.findall(r"^\s*Trials (\d+) and (\d+)", bt, re.M) for y in x})
for m in re.finditer(r"trials 2 to (\d+)", rl):
    if int(m.group(1)) != max(trials):
        bad.append(("trials", m.group(1), max(trials)))
if trials != list(range(1, max(trials) + 1)):
    bad.append(("trial numbering", trials))
print(bad)
sys.exit(1 if bad else 0)
PYCOUNT
chk "the ablation and blind-trial counts stated in README match the evidence" $?

python3 -I - "$TASK" <<'PYRUN' > /dev/null 2>&1
import re, sys
t = sys.argv[1]
run = open(f"{t}/authoring/evidence/reference_run.txt", encoding="utf-8").read()
secs, mb = re.search(r"wall time (\d+) s; peak resident memory of the solver (\d+) MB", run).groups()
r = open(f"{t}/README.md", encoding="utf-8").read()
stated = re.findall(r"(\d+) s (?:with a peak resident set of|and) (\d+) MB", r)
h = open(f"{t}/authoring/evidence/harness.txt", encoding="utf-8").read()
g = re.search(r"graded the oracle in ([0-9.]+) s", h).group(1)
ok = stated and all(x == (secs, mb) for x in stated) and f"in {g} s" in r
sys.exit(0 if ok else 1)
PYRUN
chk "the run time, memory and grading time stated in README match reference_run.txt and harness.txt" $?

python3 -I "$TASK/authoring/threshold_check.py" "$TASK" > /dev/null 2>&1
chk "every graded limit reads the same in the verifier, its docstrings and the instruction" $?

# A verifier that reads the truth with a default grades against whatever the default happens to be when the
# key is missing, instead of failing. One such fallback shipped once: the per-patient transplant bound on a
# reported unrecorded medicine fell back to a cohort-wide date, so dates months before a patient's transplant
# were accepted. Reads of the submission may and must have defaults; reads of _TRUTH may not.
# the only .get( allowed in the verifier is on the parsed submission object itself (data.get(...)): every other
# receiver (the truth, or any value drawn from it in a loop) must be indexed, so a missing key fails loudly
! grep -nE '\.get\(' "$TASK/tests/test_outputs.py" | grep -vE '^[0-9]+:.*\bdata\.get\(' | grep -q .
chk "the verifier never reads tests/truth.json with a default (no .get( except data.get()" $?
! grep -nE 'if all\(".*" in _TRUTH' "$TASK/tests/test_outputs.py"
chk "the verifier has no conditional fallback for a missing truth key" $?
python3 -I - "$TASK" <<'PYTX' > /dev/null 2>&1
import json, sys
t = json.load(open(f"{sys.argv[1]}/tests/truth.json", encoding="utf-8"))
need = {"t_half", "ec50", "state", "plan_vk", "plan_mult"}
ok = (all(need <= set(v) and len(v["plan_vk"]) == len(v["plan_mult"]) == t["plan_days"] and len(v["state"]) == 3
          for v in t["patients"].values())
      and all({"patient", "start", "cause", "days"} <= set(h) for h in t["hidden"]) and len(t["hidden"]) > 0)
sys.exit(0 if ok else 1)
PYTX
chk "the truth carries every patient's parameters, end-of-record state and plan-block inputs, and the hidden episodes" $?
! grep -rn "nproc" "$TASK/solution" "$TASK/tests" "$TASK/environment" > /dev/null 2>&1; chk "no bare nproc anywhere the task runs" $?
grep -q "OPENBLAS_NUM_THREADS" "$TASK/solution/solve.py"; chk "the reference pins BLAS to one thread before importing numpy" $?
! grep -qE "^\s*(import|from) .*(tests|truth)" "$TASK/solution/solve.py"; chk "the reference imports nothing from tests/ or the truth" $?
! grep -q "truth" "$TASK/solution/solve.py"; chk "the reference never mentions the truth" $?

NT=$(grep -c "^def test_" "$TASK/tests/test_outputs.py")
NW=$(python3 -c "
import re,sys
n=$NT
words={4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten',11:'eleven',12:'twelve'}
t=open('$TASK/README.md',encoding='utf-8').read().lower()
w=words.get(n)
bad=[k for k,v in words.items() if k!=n and (v+' tests') in t]
sys.exit(0 if (w and (w+' tests') in t and not bad) else 1)
") ; NW=$?
chk "README says there are $NT tests, and no other count" $NW

NR=$(grep -c "^| \`test_" "$TASK/README.md")
[ "$NR" -eq "$NT" ]; chk "the README table lists all $NT tests (found $NR)" $?

echo
if [ "$fails" -eq 0 ]; then echo "0 FAIL lines"; else echo "$fails FAIL lines"; fi
} | tee "$EV/static_checks.txt"
exit 0
