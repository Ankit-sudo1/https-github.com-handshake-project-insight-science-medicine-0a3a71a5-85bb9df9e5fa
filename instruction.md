This is a clinical haematology (oral anticoagulation) problem. Our anticoagulation clinic supervises twelve adults on warfarin who test their INR at home, and must set every patient's daily dose for the next eight weeks. The records from 2026-01-05 to 2026-07-05 are in /app/data/: patients.csv (sex, age, indication), doses.csv (the dose each patient's diary records for every day), inr.csv (every home INR result), clinic_log.csv (antibiotic courses and amiodarone, past and planned), plan_days.csv (one row per patient and day of the plan block, 2026-07-06 to 2026-08-30) and protocol.md (the records, the interactions and the clinic's dose model). Do not modify /app/data/.

Two things are needed.

1. Unrecorded episodes. Some events were recorded nowhere: missed doses (a spell of 2 to 4 consecutive days on which the patient took no warfarin although the diary records the dose) and unrecorded interactions (a course of 7 to 14 days of one of the antibiotics the clinic warns about, prescribed elsewhere and missing from clinic_log.csv). From the record, report every such episode: the patient, the date it started and its cause, "missed_dose" or "unrecorded_interaction".

2. The dose plan. For each row of plan_days.csv, give the dose the patient takes that evening.

Policies throughout: the patients and their meters behave as protocol.md states. Each patient's half-life and EC50 are the same over the record and the plan block; the vitamin K factor varies as stated. The planned events in clinic_log.csv happen as listed. In the plan block patients take exactly the planned doses, and no missed dose or unrecorded interaction occurs.

Write /app/dose_plan.json as a regular file (not a symlink) of at most 4 MiB: one standard JSON object (no NaN or Infinity) with exactly two keys. "episodes" is a list, possibly empty, of objects with exactly the keys patient (as in patients.csv), start ("YYYY-MM-DD", within the record) and cause (one of the two strings above), at most one per patient per start. "doses" is a list with exactly one object per row of plan_days.csv, each with exactly the keys patient, date (as in the file) and dose_mg (a multiple of 0.5 from 0 to 20).

The plan is judged by simulating each patient through the plan block with the clinic's model, the patient's actual half-life, EC50, state at the end of the record and vitamin K factor, and the planned events, taking the INR on each of the 56 mornings that follow a plan dose. The submission is accepted when all of the following hold:
- a reported episode is correct when an actual unrecorded episode of the same patient and cause started within 3 days of its date, each actual episode crediting at most one report; at least 75% of the reported episodes must be correct and at least 60% of the actual ones found, so reporting nothing is not accepted;
- for each patient separately, the INR is within 2.0-3.0 on at least 80% of those mornings;
- for each patient separately, the INR is above 4.0 or below 1.5 on at most 3% of those mornings.

Neither part can be checked in the environment. Any method is acceptable.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
