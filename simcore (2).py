"""The clinic's warfarin dose-response model (protocol.md, "The clinic's model"), shared by the generator and the
verifier (tests/simcore.py is an identical copy).

One step per day. Day d's dose is taken that evening; the INR of day d is the morning value, before that dose.
    a      = 2 ** (-24 / t_half)                                     (t_half in hours)
    E      = a E + (1 - a) m_d dose_d                                (exposure, mg/day equivalent)
    S      = 1 / (1 + E / (EC50 v_d))                                (clotting-factor synthesis)
    Ff     = Ff + (S - Ff) (1 - exp(-24 / 12)),  Fs = Fs + (S - Fs) (1 - exp(-24 / 60))
    INR    = (0.4 Ff + 0.6 Fs) ** -0.9                               (next morning)
m_d is the interaction multiplier of that day and v_d the vitamin K factor of that day.
"""
import math

GAMMA = 0.9
TAU_FAST_H, TAU_SLOW_H = 12.0, 60.0
W_FAST = 0.4
B_FAST = math.exp(-24.0 / TAU_FAST_H)
B_SLOW = math.exp(-24.0 / TAU_SLOW_H)
AMIO_ONSET_DAYS = 14.0          # amiodarone's effect builds up as 1 - exp(-days on it / 14)


def _finite(x, name):
    if not (isinstance(x, (int, float)) and math.isfinite(x)):
        raise ValueError(f"{name} must be a finite number")
    return float(x)


def inr_of(state):
    ff, fs = state[1], state[2]
    return (W_FAST * ff + (1.0 - W_FAST) * fs) ** -GAMMA


def steady_state(t_half, ec50, dose, v=1.0, m=1.0):
    """State (E, Ff, Fs) at steady state on a constant daily dose."""
    e = m * dose
    s = 1.0 / (1.0 + e / (ec50 * v))
    return [e, s, s]


def step(state, t_half, ec50, dose, m, v):
    """Advance one day: the evening dose of that day, returning the next morning's state."""
    dose = _finite(dose, "dose")
    if dose < 0:
        raise ValueError("dose must not be negative")
    a = 2.0 ** (-24.0 / t_half)
    e = a * state[0] + (1.0 - a) * m * dose
    s = 1.0 / (1.0 + e / (ec50 * v))
    ff = state[1] + (s - state[1]) * (1.0 - B_FAST)
    fs = state[2] + (s - state[2]) * (1.0 - B_SLOW)
    return [e, ff, fs]


def amiodarone_factor(days_on, full):
    """Interaction multiplier on day `days_on` (0 = first day) of an amiodarone course whose full effect is `full`."""
    if days_on < 0:
        return 1.0
    return 1.0 + (full - 1.0) * (1.0 - math.exp(-(days_on + 1) / AMIO_ONSET_DAYS))


def run(state, t_half, ec50, doses, mult, vk):
    """INR each morning for len(doses) days starting with the morning of the first day, and the final state."""
    inr = []
    st = list(state)
    for d in range(len(doses)):
        inr.append(inr_of(st))
        st = step(st, t_half, ec50, doses[d], mult[d], vk[d])
    return inr, st
