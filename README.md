# warfarin-dose-plan: reviewer notes

An anticoagulation clinic supervises twelve adults on warfarin who test their INR at home. From six months of
records (2026-01-05 to 2026-07-05: the diary dose of every day, every home INR result - twice weekly, with a
retest four days after any result outside 2.0-3.0 - a clinic log of antibiotic courses and amiodarone, past and
planned, and the clinic's protocol, which states the conventions and its dose-response model) the task is to do
two things: report the missed doses and unrecorded antibiotic courses nobody recorded, and set every patient's
daily warfarin dose for the next eight weeks, during which one patient starts amiodarone and another takes an
antibiotic course, while the patient who started amiodarone in the record stays on it. The deliverable is
`/app/dose_plan.json`; the verifier matches the reported episodes to the actual ones and simulates each patient
through the plan block under the submitted doses with the patient's actual half-life, EC50, state and vitamin K
variation.

This is the routine work of an anticoagulation clinic that supports self-testing: read the INR record against the
diary, recognise non-adherence and undisclosed interacting medicines, and dose each patient for the coming weeks.
Nothing in the environment checks any of it.

## Difficulty

The decisive point is that **the episode report has no safe answer**. The record hides 32 episodes: 18 spells of 2
to 4 consecutive days without warfarin while the diary records the dose, and 14 courses of 7 to 14 days of the
antibiotics the clinic warns about, prescribed elsewhere. A missed spell lowers the INR by a few tenths for a few
days and a course raises it by about half a unit over a week or two - and the protocol states that every
patient's dietary vitamin K varies from day to day as a correlated (AR(1), coefficient 0.85) process, which moves
the INR by similar amounts in both directions, seen only through twice-weekly meter results with about 5% error.

- Report generously and precision fails; report only the certain and recall fails; nothing scores either. On the
  reference's operating grid (`detector_sweep.txt`: the likelihood-ratio score a candidate needs to join each
  patient's model) 2 of 15 thresholds clear both limits, at 2.8 and 2.85: one step lower (2.75) and 34 episodes
  are reported with precision 0.706, lower still 0.58-0.67; one step higher (2.9) and the recall falls to 0.625
  with precision 0.741, higher still to 0.03-0.59. The shipped point (2.82) reports 31 episodes, 24 of them
  correct (precision 0.774, recall 0.750; the limits are 0.75 and 0.60).
- False candidates are not confined to the frontier: the fourth strongest candidate of all (score 4.28, an
  antibiotic course in P09) is vitamin K variation, and 7 of the 31 reported episodes are false, two of them
  scoring above 3.7. A careful report that keeps only candidates scoring at least 3 has 19 correct of 25
  (recall 0.594); the recall limit needs 20 of 32. So the safe episodes are not enough.
- With every actual episode offered to the true model (`feasibility.txt`: the expected score of each episode with
  the patient's true half-life, EC50 and vitamin K spread and every other episode known), 6 of the 32 reach 5, 10
  reach 4 and 22 reach 3; the recall limit is inside that ceiling.

Around that, the plan is the ordinary expert work, and each piece is measured (ablations):

- **The vitamin K variation the protocol states.** Treating it as independent from day to day
  (`white_vitamin_k`) reports 42 episodes with 24 correct (precision 0.571); ignoring it and keeping only the meter
  error (`meter_noise_only`) reports 67 with 25 correct (precision 0.373). Its correlation is what tells a week of
  low intake from a missed spell.
- **The half-life.** Fixing every patient's half-life at 40 h (`fixed_half_life`) gives precision 0.700 and recall
  0.656; dropping the protocol's 20-70 h range as a prior (`no_half_life_prior`) gives 0.690 and 0.625 - the
  episode shapes depend on it. Taking the meter error as 6% instead of the stated 5% (`meter_six_percent`) gives
  precision 0.733.
- **The episodes.** Reporting none (`no_episode_model`) fails both episode limits; the doses, designed from the
  record's end, do not depend on them here (lowest time in range 0.893).
- **The interactions in the plan.** Ignoring the planned amiodarone start and antibiotic course
  (`ignore_planned_events`) leaves P09 at 32.1% in range; treating P04's amiodarone as stopping with the record
  (`amiodarone_stops`) leaves P04 at 16.1% in range with 8.9% of mornings unsafe. Repeating each patient's last
  week of doses leaves P09 at 62% in range.
- **There is no feedback.** Nothing in the environment scores the report or the doses.

Ten variants are measured in `authoring/evidence/ablations.txt` beside the reference itself, each the reference
pipeline with one step done naively or one choice changed, refitted from scratch and scored with the verifier's
own code. Eight fail. The two that pass - trying every course length rather than every other one
(`finer_course_lengths`) and aiming the dose design five days ahead instead of three (`lookahead_five`) - show
that the search grid and the design horizon are free choices; other detection thresholds are not refitted as
ablations, `detector_sweep.txt` scores every one on the reference's fits.

## Hidden truth and data

`authoring/generate.py` is the single definition of the truth (seeded; two runs write identical files), simulated
with `authoring/simcore.py` (the verifier's copy, `tests/simcore.py`, is identical):

- **Patients:** each with an S-warfarin half-life (22 to 70 h, around 40) and an EC50 that puts their steady-state
  INR at 2.5 on 1.5 to 11 mg/day; their own day-to-day vitamin K spread (0.12 to 0.22 on the log scale, AR(1)
  with coefficient 0.85). All were stable on their dose before the record began.
- **Record:** the protocol's model, one step per day; tests on two fixed weekdays (8% not done), a retest four
  days after any result outside 2.0-3.0, meter error 5% log-normal, rounded to 0.1. The clinic adjusted each
  weekly dose by the protocol's algorithm after every result.
- **Interactions:** the warned antibiotics multiply exposure by 1.60 in every patient (nine recorded courses);
  amiodarone's full factor is 1.65, building up over two weeks (P04 from 2026-03-21, continuing).
- **Episodes:** 18 missed spells (2 to 4 days) and 14 unrecorded courses (7 to 14 days), at least 12 days from any
  recorded course, amiodarone start or other episode of the same patient.
- **Plan block (2026-07-06 to 2026-08-30):** the vitamin K process continues; P09 starts amiodarone on 2026-07-13
  and P02 takes an antibiotic course from 2026-07-27 to 2026-08-02.

The truth (`tests/truth.json`) holds each patient's half-life, EC50 and vitamin K spread, the model state at the
end of the record, the plan block's vitamin K factor and interaction multiplier of every day, and the start, cause
and length of every hidden episode. Nothing of it is in the agent image.

## Reference solution

`solution/solve.py` (128 s with a peak resident set of 76 MB on the 2-CPU machine recorded in `harness.txt`; against an agent budget of 8 h and
4 GB):

1. **Fit.** Each patient by maximum likelihood on the log INR results. For given half-life and EC50 the model is
   simulated with the diary doses and the known interactions; the vitamin K factor enters through its exact linear
   response (the derivative of each test's log INR with respect to each day's log factor, in closed form), so the
   residuals are Gaussian with covariance J Sigma J' + meter error (5%, plus the rounding), Sigma the stated AR(1)
   with the patient's own spread. A log-normal prior on the half-life (median 40 h, the protocol's 20-70 h range)
   keeps it identified. The antibiotic multiplier and amiodarone's full factor are shared and profiled on a grid.
2. **Episodes.** Per patient, forward selection on likelihood-ratio tests: every candidate missed spell (2 to 4
   days) and unrecorded course (7, 9, 11 or 13 days) at every start is scored with the patient's fit, the best is
   refitted, and candidates join while their signed root likelihood ratio is at least 2.82.
3. **Doses.** For each plan day the dose (0.5 mg steps) that brings the predicted INR three days ahead closest to
   2.5, with the fitted model from the fitted end-of-record state (the reported episodes included), the planned
   amiodarone start and antibiotic course, P04's continuing amiodarone, and the vitamin K factor at its median.

The reference imports nothing from `tests/`, pins BLAS to one thread, and its output is byte-identical between
runs.

## Verification

`tests/test_outputs.py` reads `/app/dose_plan.json` as passive JSON (no submitted code runs). Parsing fails closed:
a missing file, a symlink, more than 4 MiB, malformed JSON, NaN or Infinity (all three stated in the
instruction), wrong keys, a dose row unknown, repeated or missing, a dose that is not a multiple of 0.5 from 0 to
20 mg or not a number, an episode outside the record, with an unknown patient or cause, or repeated for a patient
and start all fail the format test and every other test.

A reported episode is correct when an actual episode of the same patient and cause started within 3 days of it,
each actual episode crediting at most one report (the largest such one-to-one pairing). The doses are graded by
simulating each patient through the 56 plan days with `tests/simcore.py` from the state at the end of the record,
with the truth's half-life, EC50, vitamin K factor and interaction multiplier of every day (the planned events
included), taking the INR each morning after a plan dose.

There are five tests:

| test | requirement |
|---|---|
| `test_file_format` | the artifact follows the format |
| `test_episode_precision` | at least 75% of the reported episodes correct |
| `test_episode_recall` | at least 60% of the actual episodes found |
| `test_time_in_range` | each patient: INR 2.0-3.0 on at least 80% of the plan mornings |
| `test_unsafe_inr` | each patient: INR above 4.0 or below 1.5 on at most 3% of the plan mornings |

The verifier graded the oracle in 1.2 s (`harness.txt`). `authoring/harness_checks.sh` runs the unmodified
`tests/test.sh` on the oracle (twice, byte-identical output), on no submission, and on 29 probes
(`authoring/probes.py`): each carries the correct answer for every criterion but one - the precision and recall
limits at and one past the boundary, the true episodes just inside and just outside the 3-day tolerance, the causes
swapped, doses too high and too low for one patient, every format violation - and every one lands as expected,
each failing probe on its own test where the format allows.

## Calibration

| quantity | reference | limit | floor or naive |
|---|---|---|---|
| episode precision | 0.774 | 0.75 | 0.706 one threshold step lower |
| episode recall | 0.750 | 0.60 | 0.594 keeping only candidates scoring at least 3 |
| lowest time in range (per patient) | 0.893 (P02) | 0.80 | 0.911 with the true physiology; 0.62 (P09) repeating each patient's last week |
| highest unsafe share (per patient) | 0.000 | 0.03 | 0.000 with the true physiology |

Evidence files (`authoring/evidence/`): `ablations.txt`, `detector_sweep.txt`, `feasibility.txt`, `floor.txt`,
`consistency.txt`, `harness.txt`, `reference_run.txt`, `reference_output.json`, `regenerate.txt`,
`static_checks.txt`, `blind_trials.txt`.

## History

1. First submission. During authoring two blind trials were run (`blind_trials.txt`). The data were first
   generated with single missed doses and short courses against a larger vitamin K variation and a twice-weekly
   schedule; with the true model only one episode reached a score of 3, so the episodes were lengthened (missed
   spells of 2 to 4 days, courses of 7 to 14 days) until the frontier held both true and false candidates. The first
   trial on the shipped data, with limits then at 0.70 precision, 0.60 recall and 75% time in range, passed
   narrowly (28 reported, 20 correct: precision 0.714, recall 0.625) and estimated its own chance of passing at
   60-78%. The limits were then set at 0.75 precision and 80% time in range, where that submission fails on
   precision and the reference passes (0.774); the recall limit was left at 0.60. The second trial, on the shipped
   data and limits, built a reversible-jump MCMC over every patient's parameters and episodes and chose how many
   episodes to report from the posterior chance of meeting both limits (which it put at 0.45): 24 reported, 18
   correct (precision 0.750, recall 0.5625), so it fails on recall alone, with every patient's plan passing.

## Task metadata explanations

### Difficulty

The episode report has no safe answer: of 32 unrecorded episodes, missed spells of 2 to 4 days lower the INR by a
few tenths and undisclosed antibiotic courses raise it by about half a unit, against a record whose dietary vitamin
K moves the INR by similar amounts in both directions from day to day, seen only through twice-weekly meter
results. Reporting generously fails the precision limit and reporting cautiously fails the recall limit; nothing in
the environment scores either, and one of the strongest candidates is vitamin K variation. Around that the solver
must identify each patient's half-life and EC50 from the record, estimate the antibiotic and amiodarone factors
from the recorded courses and the one patient on amiodarone, and dose every patient for eight weeks, including a
new amiodarone start and an antibiotic course, so that each meets the time-in-range and safety limits in
simulation.

### Solution

Fit the clinic's model to each patient by maximum likelihood on the log INR results, with the vitamin K variation
entering through its exact linear response so that the residual covariance is known for any half-life and EC50,
and the antibiotic and amiodarone factors shared across patients. Find episodes by forward selection on
likelihood-ratio tests over every candidate missed spell and unrecorded course, joining at a score of 2.82. Design
each day's dose so that the predicted INR three days ahead is closest to 2.5, with the fitted model, the planned
events and the continuing amiodarone.

### Verification

The verifier reads the JSON as passive data. Reported episodes are matched one-to-one to the actual episodes of the
same patient and cause starting within 3 days; at least 75% must be correct and at least 60% of the actual episodes
found. The doses are graded by simulating each patient through the 56 plan days with the clinic's model and the
patient's actual half-life, EC50, end-of-record state, vitamin K factor and planned interactions: each patient's
INR must be within 2.0-3.0 on at least 80% of the mornings and above 4.0 or below 1.5 on at most 3%.
