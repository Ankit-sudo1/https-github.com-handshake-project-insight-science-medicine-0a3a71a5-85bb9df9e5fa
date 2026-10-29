# Riverside Anticoagulation Clinic: self-testing conventions and dose model

## Records
Dates are calendar days. Patients take their warfarin each evening and record the dose in their diary
(doses.csv lists the dose the diary records for every day). They test their INR at home in the morning with a
point-of-care meter, on two fixed weekdays, and again four days after any result outside 2.0-3.0. A meter result
is the true INR times a log-normal error of about 5% (independent between tests), rounded to 0.1. A missing
scheduled test was not done. All patients were stable on their dose before the record began.

The clinic adjusts the weekly dose after each result: below 1.8 by +10%, 1.8-1.9 by +5%, 3.1-3.5 by -5%,
3.6-4.5 by -10%, above 4.5 by -15% and the next dose omitted; the week's dose is spread over the days in 0.5 mg
steps.

## Interactions
- The antibiotics the clinic warns about multiply warfarin exposure by the same factor in every patient on each
  day of the course. Courses the clinic knew of are in clinic_log.csv.
- Amiodarone's effect builds up: on day k of treatment (k = 1 on the first day) exposure is multiplied by
  1 + (A - 1)(1 - exp(-k / 14)), with the same full factor A in every patient; it continues once started.
- Each patient's vitamin K intake varies from day to day: a factor v whose logarithm follows an AR(1) process
  with coefficient 0.85, each patient with their own spread.

## The clinic's model
One step per day. With dose_d the dose actually taken on the evening of day d (mg), m_d the interaction
multiplier and v_d the vitamin K factor of that day:

    a      = 2 ** (-24 / t_half)
    E      = a E + (1 - a) m_d dose_d
    S      = 1 / (1 + E / (EC50 v_d))
    Ff     = Ff + (S - Ff) (1 - exp(-24 / 12)),    Fs = Fs + (S - Fs) (1 - exp(-24 / 60))
    INR    = (0.4 Ff + 0.6 Fs) ** -0.9             (the next morning)

Each patient has their own half-life t_half (hours; S-warfarin, typically 20 to 70) and EC50 (mg/day). At steady
state on a constant dose with m = v = 1, E equals the dose and Ff = Fs = S.

## Targets
The therapeutic range is INR 2.0-3.0 for every patient here. Time in therapeutic range (TTR) is the share of days
on which the INR is within it; an INR above 4.0 carries a bleeding risk and one below 1.5 a thrombotic risk.
