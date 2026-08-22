"""Fasting windows derived from meal timestamps.

Everything in this module is arithmetic on times you already logged. No model,
no cost, and — importantly — no physiological claims that timestamps cannot
support. See `phase_label()` for where the line is drawn and why.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from statistics import median, pstdev


@dataclass(frozen=True)
class Fast:
    start: dt.datetime          # last bite of the previous eating period
    end: dt.datetime | None     # first bite after it; None if still running
    hours: float
    crossed_midnight: bool

    @property
    def running(self) -> bool:
        return self.end is None


@dataclass(frozen=True)
class EatingWindow:
    day: dt.date
    first: dt.datetime
    last: dt.datetime
    hours: float
    midpoint: dt.time
    n_meals: int


# Anything shorter than this is a second helping, not the end of a fast.
MIN_FAST_HOURS = 3.0


def fasts_from(times: list[dt.datetime], now: dt.datetime | None = None) -> list[Fast]:
    """Gaps between consecutive intakes, above a floor that ignores grazing."""
    ts = sorted(times)
    out: list[Fast] = []
    for a, b in zip(ts, ts[1:]):
        h = (b - a).total_seconds() / 3600
        if h >= MIN_FAST_HOURS:
            out.append(Fast(a, b, h, a.date() != b.date()))
    if ts and now:
        h = (now - ts[-1]).total_seconds() / 3600
        if h >= MIN_FAST_HOURS:
            out.append(Fast(ts[-1], None, h, ts[-1].date() != now.date()))
    return out


def window_stability(windows: list[EatingWindow]) -> tuple[float, float]:
    """Median window length and the standard deviation of its midpoint, hours.

    Midpoint variance is the more useful of the two. A person eating a stable
    10-hour window from 09:00 and a person averaging the same 10 hours by
    alternating 07:00 and 13:00 starts are not doing the same thing, and only
    the second one is fighting their own circadian timing every other day.
    """
    if not windows:
        return 0.0, 0.0
    lens = [w.hours for w in windows]
    mids = [w.midpoint.hour + w.midpoint.minute / 60 for w in windows]
    return median(lens), (pstdev(mids) if len(mids) > 1 else 0.0)


def tre_class(midpoint: dt.time) -> str:
    """Early / midday / late, by clock position of the eating midpoint.

    Boundaries follow how the trial literature splits its arms, not physiology:
    early windows finish mid-afternoon, late windows start after noon. Treat
    the label as a bucket, not a diagnosis.
    """
    h = midpoint.hour + midpoint.minute / 60
    if h < 13.0:
        return "early"
    if h < 16.0:
        return "midday"
    return "late"


# --------------------------------------------------------------- the honest bit


def phase_label(hours: float) -> tuple[str, str]:
    """A population-average description of a fasting duration. Not a measurement.

    This function exists because you asked for "moments of fat burning" and the
    honest answer is that meal timestamps cannot deliver it. Substrate
    oxidation is measured by indirect calorimetry — a mask, a gas analyser, a
    lab. Nothing here observes your respiratory quotient, your ketones, or your
    glycogen.

    What the timeline below reflects is what happens on average, in fasted
    adults, at rest, in studies. Your own numbers move that timeline by hours
    depending on your last meal's composition, your glycogen state, your
    training, and your individual metabolism.

    And the more important caveat: **a fasting phase is not a fat-loss rate.**
    Fat oxidised in hour 14 that is replaced by dietary fat in hour 15 is a
    round trip, not a loss. Twenty-four-hour fat balance is set by energy
    balance. If you want to know whether you are losing fat, read
    `insight.fat_loss_rate()`, which uses your weight trend and your intake.
    Not this.
    """
    if hours < 4:
        return "fed", "absorbing the last meal"
    if hours < 8:
        return "post-absorptive", "liver glycogen covering blood glucose"
    if hours < 12:
        return "early fasted", "glycogen falling, fat oxidation rising on average"
    if hours < 18:
        return "fasted", "fat oxidation typically dominant at rest"
    if hours < 30:
        return "extended", "ketone production usually measurable by now"
    return "prolonged", "beyond the range this tool should comment on"


def summarise(fasts: list[Fast], windows: list[EatingWindow]) -> dict[str, float | str]:
    overnight = [f.hours for f in fasts if f.crossed_midnight and not f.running]
    med_len, mid_sd = window_stability(windows)
    mids = [w.midpoint.hour + w.midpoint.minute / 60 for w in windows]
    mean_mid = sum(mids) / len(mids) if mids else 0.0
    return {
        "n_days": len(windows),
        "median_overnight_fast_h": round(median(overnight), 1) if overnight else 0.0,
        "longest_fast_h": round(max((f.hours for f in fasts), default=0.0), 1),
        "median_window_h": round(med_len, 1),
        "midpoint_sd_h": round(mid_sd, 2),
        "mean_midpoint": f"{int(mean_mid):02d}:{int((mean_mid % 1) * 60):02d}",
        "tre_class": tre_class(dt.time(int(mean_mid), int((mean_mid % 1) * 60))) if mids else "unknown",
    }
