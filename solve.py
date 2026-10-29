"""Reference solution for warfarin-dose-plan.

1. Rebuild each patient's record: the diary doses, the INR results, the recorded antibiotic courses and amiodarone.
2. Fit the clinic's model to each patient by maximum likelihood on the log INR results. For given half-life and
   EC50 the model is simulated with the diary doses and the known interactions; the day-to-day vitamin K factor
   (log AR(1), coefficient 0.85) enters to first order through its exact linear response (the derivative of the
   log INR at each test with respect to each day's log factor, in closed form), so the residuals are Gaussian with
   covariance J Sigma J' + meter noise. Unknowns per patient: half-life, EC50, the vitamin K spread. Shared: the
   antibiotic multiplier and amiodarone's full multiplier, profiled on a grid over the joint likelihood.
3. Unrecorded episodes: per patient forward selection on likelihood-ratio tests over every candidate missed-dose
   spell (2 to 4 days) and unrecorded antibiotic course (7 to 14 days) at every start, each refitted with the
   patient's parameters; a candidate joins while its signed root likelihood ratio is at least Z_ADD.
4. Dose plan: for each plan day the dose (0.5 mg steps) that brings the predicted INR three days ahead closest to
   2.5, with the fitted model, the planned interactions and the vitamin K factor at its median.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
import numpy as np  # noqa: E402
import scipy.optimize as so  # noqa: E402

GAMMA = 0.9
B_FAST = math.exp(-24.0 / 12.0)
B_SLOW = math.exp(-24.0 / 60.0)
W_FAST = 0.4
AMIO_ONSET = 14.0
VK_PHI = 0.85
METER_SD = 0.05
ROUND_VAR = 0.1 ** 2 / 12.0
Z_ADD = 2.82
MISSED_LENGTHS = (2, 3, 4)
COURSE_LENGTHS = (7, 9, 11, 13)
TARGET = 2.5
AMIO_CONTINUES = True           # the protocol: amiodarone continues once started
LOOKAHEAD = 3                   # days ahead the dose design aims the INR at the target
T_HALF_PRIOR = (40.0, 0.35)       # the protocol's 20-70 h half-life range, as a log-normal prior


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class Patient:
    def __init__(self, pid, start, ndays, doses, tests, courses, amio_start):
        self.pid, self.start, self.n = pid, start, ndays
        self.doses = np.array(doses)
        self.tdays = np.array([d for d, _ in tests])
        self.y = np.log(np.array([v for _, v in tests]))
        self.courses = courses              # recorded (first day, days)
        self.amio = amio_start              # first day on amiodarone, or None
        # variance of a reading's log from rounding to 0.1
        self.rvar = ROUND_VAR / np.exp(2 * self.y)

    def mult(self, abx, amio_full, extra=()):
        m = np.ones(self.n)
        for d0, k in self.courses:
            m[d0:d0 + k] *= abx
        for kind, d0, k in extra:
            if kind == "unrecorded_interaction":
                m[d0:d0 + k] *= abx
        if self.amio is not None:
            dd = np.arange(self.n) - self.amio
            m *= np.where(dd >= 0, 1.0 + (amio_full - 1.0) * (1.0 - np.exp(-(dd + 1) / AMIO_ONSET)), 1.0)
        return m

    def taken(self, extra=()):
        x = self.doses.copy()
        for kind, d0, k in extra:
            if kind == "missed_dose":
                x[d0:d0 + k] = 0.0
        return x


def simulate(p, t_half, ec50, doses, mult):
    """Morning log INR every day (v = 1), and dlogINR(test day)/dlog v(day) for every test and earlier day."""
    a = 2.0 ** (-24.0 / t_half)
    n = len(doses)
    e = mult[0] * float(np.mean(doses[:7]))     # steady state on the first week's mean dose before the record
    s0 = 1.0 / (1.0 + e / ec50)
    ff = fs = s0
    loginr = np.empty(n)
    S = np.empty(n)
    F = np.empty(n)
    for d in range(n):
        F[d] = W_FAST * ff + (1 - W_FAST) * fs
        loginr[d] = -GAMMA * math.log(F[d])
        e = a * e + (1 - a) * mult[d] * doses[d]
        s = 1.0 / (1.0 + e / ec50)
        S[d] = s
        ff += (s - ff) * (1 - B_FAST)
        fs += (s - fs) * (1 - B_SLOW)
    # linear response: a unit change of log v on day d changes S_d by S_d (1 - S_d), which feeds Ff and Fs from the
    # next morning on with geometric decay
    t = p.tdays
    lag = t[:, None] - 1 - np.arange(n)[None, :]
    ok = lag >= 0
    lagc = np.where(ok, lag, 0)
    dS = S * (1 - S)
    dF = (W_FAST * (1 - B_FAST) * B_FAST ** lagc + (1 - W_FAST) * (1 - B_SLOW) * B_SLOW ** lagc) * dS[None, :]
    J = np.where(ok, -GAMMA * dF / F[t][:, None], 0.0)
    return loginr, J


AR_CACHE = {}


def ar_cov(n):
    if n not in AR_CACHE:
        i = np.arange(n)
        AR_CACHE[n] = VK_PHI ** np.abs(i[:, None] - i[None, :])
    return AR_CACHE[n]


def nll(p, theta, abx, amio, extra=()):
    t_half, ec50, vk_sd = math.exp(theta[0]), math.exp(theta[1]), math.exp(theta[2])
    if not (5.0 < t_half < 200.0 and 0.05 < ec50 < 50.0 and 1e-3 < vk_sd < 2.0):
        return 1e9
    prior = 0.5 * ((theta[0] - math.log(T_HALF_PRIOR[0])) / T_HALF_PRIOR[1]) ** 2
    loginr, J = simulate(p, t_half, ec50, p.taken(extra), p.mult(abx, amio, extra))
    r = p.y - loginr[p.tdays]
    C = vk_sd ** 2 * (J @ ar_cov(p.n) @ J.T) + np.diag(METER_SD ** 2 + p.rvar)
    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        return 1e9
    z = np.linalg.solve(L, r)
    return 0.5 * float(z @ z) + float(np.log(np.diag(L)).sum()) + prior


def fit(p, abx, amio, extra=(), theta0=None):
    if theta0 is None:
        dose = float(np.mean(p.doses))
        s = TARGET ** (-1 / GAMMA)
        theta0 = np.array([math.log(40.0), math.log(dose / (1 / s - 1)), math.log(0.12)])
    res = so.minimize(lambda th: nll(p, th, abx, amio, extra), theta0, method="Nelder-Mead",
                      options=dict(xatol=1e-4, fatol=1e-4, maxiter=600))
    return res.x, res.fun


def candidates(p):
    for d0 in range(3, p.n - 1):
        for k in MISSED_LENGTHS:
            if d0 + k <= p.n and float(p.doses[d0:d0 + k].sum()) > 0:
                yield ("missed_dose", d0, k)
        for k in COURSE_LENGTHS:
            if d0 + k <= p.n and all(d0 + k + 5 < c0 or d0 > c0 + ck + 5 for c0, ck in p.courses) \
                    and (p.amio is None or d0 + k < p.amio - 5 or d0 > p.amio + 40):
                yield ("unrecorded_interaction", min(d0, p.n - k), k)


def detect(p, abx, amio, z_add=Z_ADD, z_floor=2.5):
    """Forward selection: returns the sequence [(kind, d0, k, z)] down to z_floor and the final theta."""
    extra, seq = [], []
    theta, base = fit(p, abx, amio)
    while True:
        best = None
        for c in candidates(p):
            if any(abs(c[1] - e[1]) < 10 for e in extra):
                continue
            v = nll(p, theta, abx, amio, extra + [c])
            if best is None or v < best[0]:
                best = (v, c)
        if best is None:
            break
        th2, v2 = fit(p, abx, amio, extra + [best[1]], theta)
        z = math.sqrt(max(0.0, 2 * (base - v2)))
        if z < z_floor:
            break
        extra.append(best[1])
        seq.append((*best[1], z))
        theta, base = th2, v2
    return seq


def design(t_half, ec50, state, mult):
    a = 2.0 ** (-24.0 / t_half)

    def step(st, dose, m):
        e = a * st[0] + (1 - a) * m * dose
        s = 1.0 / (1.0 + e / ec50)
        return (e, st[1] + (s - st[1]) * (1 - B_FAST), st[2] + (s - st[2]) * (1 - B_SLOW))

    doses, st = [], state
    n = len(mult)
    for d in range(n):
        best = None
        for k in range(0, 41):
            dose = 0.5 * k
            s = step(st, dose, mult[d])
            for j in range(1, LOOKAHEAD + 1):
                s = step(s, dose, mult[min(n - 1, d + j)])
            err = abs(-GAMMA * math.log(W_FAST * s[1] + (1 - W_FAST) * s[2]) - math.log(TARGET))
            if best is None or err < best[0] - 1e-12:
                best = (err, dose)
        doses.append(best[1])
        st = step(st, best[1], mult[d])
    return doses


def final_state(p, t_half, ec50, abx, amio, extra):
    doses, mult = p.taken(extra), p.mult(abx, amio, extra)
    a = 2.0 ** (-24.0 / t_half)
    e = mult[0] * float(np.mean(doses[:7]))
    s0 = 1.0 / (1.0 + e / ec50)
    ff = fs = s0
    for d in range(p.n):
        e = a * e + (1 - a) * mult[d] * doses[d]
        s = 1.0 / (1.0 + e / ec50)
        ff += (s - ff) * (1 - B_FAST)
        fs += (s - fs) * (1 - B_SLOW)
    return (e, ff, fs)


def load(d):
    pats = [r["patient"] for r in read_csv(os.path.join(d, "patients.csv"))]
    doses = {}
    first = None
    for r in read_csv(os.path.join(d, "doses.csv")):
        day = dt.date.fromisoformat(r["date"])
        first = day if first is None or day < first else first
        doses.setdefault(r["patient"], []).append((day, float(r["dose_mg"])))
    n = max(len(v) for v in doses.values())
    tests = {}
    for r in read_csv(os.path.join(d, "inr.csv")):
        tests.setdefault(r["patient"], []).append(((dt.date.fromisoformat(r["date"]) - first).days, float(r["inr"])))
    log = read_csv(os.path.join(d, "clinic_log.csv"))
    out = {}
    plan_events = {}
    for pid in pats:
        dd = [x for _, x in sorted(doses[pid])]
        courses, amio = [], None
        for r in log:
            if r["patient"] != pid:
                continue
            a = (dt.date.fromisoformat(r["start_date"]) - first).days
            if r["event"] == "antibiotic course":
                courses.append((a, (dt.date.fromisoformat(r["end_date"]) - first).days - a + 1))
            elif r["event"].startswith("amiodarone started"):
                amio = a
            else:
                plan_events.setdefault(pid, []).append((r["event"], a - n, r["end_date"] and
                                                        (dt.date.fromisoformat(r["end_date"]) - first).days - n))
        out[pid] = Patient(pid, first, n, dd, sorted(tests[pid]), courses, amio)
    plan = read_csv(os.path.join(d, "plan_days.csv"))
    return out, first, n, plan, plan_events


def analyse(d, verbose=False, z_add=None):
    z_add = Z_ADD if z_add is None else z_add
    pats, first, n, plan, plan_events = load(d)
    # shared multipliers: profile on a grid with the patients' parameters refitted
    grid_abx = np.arange(1.2, 2.21, 0.1)
    best = None
    for abx in grid_abx:
        tot = sum(fit(p, abx, 1.0)[1] for p in pats.values() if p.courses and p.amio is None)
        if best is None or tot < best[0]:
            best = (tot, abx)
    abx = float(best[1])
    amio_p = [p for p in pats.values() if p.amio is not None]
    best = None
    for amio in np.arange(1.1, 2.61, 0.1):
        tot = sum(fit(p, abx, amio)[1] for p in amio_p)
        if best is None or tot < best[0]:
            best = (tot, amio)
    amio = float(best[1])
    if verbose:
        print(f"antibiotic multiplier {abx:.2f}, amiodarone {amio:.2f}", flush=True)
    res = {}
    for pid, p in pats.items():
        seq = detect(p, abx, amio)
        chosen = [s[:3] for s in seq if s[3] >= z_add]
        theta, _ = fit(p, abx, amio, chosen)
        res[pid] = dict(seq=seq, chosen=chosen, theta=theta)
        if verbose:
            print(pid, "t_half %.1f ec50 %.2f vk_sd %.3f" % tuple(np.exp(theta)),
                  [(k, (first + dt.timedelta(days=d0)).isoformat(), n_, round(z, 1)) for k, d0, n_, z in seq], flush=True)
    return dict(pats=pats, first=first, n=n, plan=plan, plan_events=plan_events, abx=abx, amio=amio, res=res)


def write(an, out_path):
    pats, first, n = an["pats"], an["first"], an["n"]
    episodes = []
    settings = {}
    plan_days = {}
    for r in an["plan"]:
        plan_days.setdefault(r["patient"], []).append(r["date"])
    for pid, p in pats.items():
        r = an["res"][pid]
        for kind, d0, k in r["chosen"]:
            episodes.append(dict(patient=pid, start=(first + dt.timedelta(days=d0)).isoformat(), cause=kind))
        t_half, ec50, _ = np.exp(r["theta"])
        state = final_state(p, t_half, ec50, an["abx"], an["amio"], r["chosen"])
        days = sorted(plan_days[pid])
        m = np.ones(len(days))
        if p.amio is not None and AMIO_CONTINUES:   # amiodarone started in the record continues in the plan block
            dd = np.arange(len(days)) + n - p.amio
            m *= 1.0 + (an["amio"] - 1.0) * (1.0 - np.exp(-(dd + 1) / AMIO_ONSET))
        for ev, a, b in an["plan_events"].get(pid, []):
            if ev.startswith("amiodarone"):
                dd = np.arange(len(days)) - a
                m *= np.where(dd >= 0, 1.0 + (an["amio"] - 1.0) * (1.0 - np.exp(-(dd + 1) / AMIO_ONSET)), 1.0)
            elif ev.startswith("antibiotic"):
                m[a:b + 1] *= an["abx"]
        settings[pid] = dict(zip(days, design(t_half, ec50, state, m)))
    out = dict(episodes=sorted(episodes, key=lambda e: (e["patient"], e["start"])),
               doses=[dict(patient=r["patient"], date=r["date"], dose_mg=settings[r["patient"]][r["date"]])
                      for r in an["plan"]])
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=0)
        fh.write("\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="/app/data")
    ap.add_argument("--out", default="/app/dose_plan.json")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    write(analyse(a.data, a.verbose), a.out)


if __name__ == "__main__":
    main()
