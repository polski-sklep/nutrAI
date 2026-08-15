import datetime as dt

import pytest

from nutrai.core import fasting, insight

TZ = dt.timezone.utc


def t(day, hour, minute=0):
    return dt.datetime(2026, 8, day, hour, minute, tzinfo=TZ)


def test_second_helping_is_not_a_fast():
    """14:41 mince and 14:45 second helping is one meal, not two fasts."""
    times = [t(10, 14, 41), t(10, 14, 45), t(10, 19, 0)]
    fasts = fasting.fasts_from(times)
    assert len(fasts) == 1
    assert fasts[0].hours == pytest.approx(4.25, abs=0.01)


def test_overnight_fast_is_flagged():
    fasts = fasting.fasts_from([t(10, 21, 30), t(11, 13, 30)])
    assert len(fasts) == 1
    assert fasts[0].crossed_midnight
    assert fasts[0].hours == pytest.approx(16.0)


def test_running_fast_needs_now():
    times = [t(11, 13, 0)]
    assert fasting.fasts_from(times) == []
    running = fasting.fasts_from(times, now=t(11, 22, 0))
    assert len(running) == 1 and running[0].running and running[0].hours == 9.0


def test_eating_window_and_midpoint():
    w = fasting.eating_window(dt.date(2026, 8, 10), [t(10, 8, 0), t(10, 13, 0), t(10, 20, 0)])
    assert w is not None
    assert w.hours == 12.0
    assert w.midpoint == dt.time(14, 0)
    assert w.n_meals == 3


def test_single_meal_day_has_no_window():
    assert fasting.eating_window(dt.date(2026, 8, 10), [t(10, 13, 0)]) is None


def test_tre_class_is_about_position_not_length():
    assert fasting.tre_class(dt.time(11, 30)) == "early"
    assert fasting.tre_class(dt.time(14, 0)) == "midday"
    assert fasting.tre_class(dt.time(17, 30)) == "late"


def test_stability_separates_same_length_different_position():
    """Two people, identical 10-hour median windows. Only one is stable."""
    steady = [
        fasting.eating_window(dt.date(2026, 8, d), [t(d, 9, 0), t(d, 19, 0)]) for d in (10, 11, 12)
    ]
    erratic = [
        fasting.eating_window(dt.date(2026, 8, 10), [t(10, 7, 0), t(10, 17, 0)]),
        fasting.eating_window(dt.date(2026, 8, 11), [t(11, 13, 0), t(11, 23, 0)]),
        fasting.eating_window(dt.date(2026, 8, 12), [t(12, 7, 0), t(12, 17, 0)]),
    ]
    len_a, sd_a = fasting.window_stability(steady)
    len_b, sd_b = fasting.window_stability(erratic)
    assert len_a == len_b == 10.0
    assert sd_a == 0.0
    assert sd_b > 2.0


def test_phase_label_never_claims_measurement():
    for h in (1, 6, 10, 15, 20, 40):
        name, gloss = fasting.phase_label(h)
        assert name and gloss
        for banned in ("you are burning", "grams of fat", "your ketones are"):
            assert banned not in gloss.lower()


# ------------------------------------------------------------------ insight


def test_correlation_refuses_below_the_threshold():
    xs = list(range(10))
    ys = list(range(10))
    f = insight.correlate("focus", xs, ys)
    assert f.rho is None and not f.usable
    assert "not enough data" in f.verdict
    assert "10 of 20" in f.verdict


def test_perfect_relationship_is_found_when_n_suffices():
    xs = [float(i) for i in range(24)]
    ys = [float(i) for i in range(24)]
    f = insight.correlate("focus", xs, ys)
    assert f.rho == pytest.approx(1.0)
    assert f.p is not None and f.p < 0.01
    assert f.usable


def test_noise_is_reported_as_noise():
    import random

    rng = random.Random(7)
    xs = [rng.random() for _ in range(40)]
    ys = [rng.random() for _ in range(40)]
    f = insight.correlate("focus", xs, ys)
    assert not f.usable
    assert "no reliable relationship" in f.verdict


def test_clock_confound_is_surfaced():
    """Focus rises through the morning and fasting hours rise with it. The
    finding is the clock, and the tool has to say so."""
    xs = [float(h) for h in range(8, 20)] * 2      # hours fasted
    clock = list(xs)                                # perfectly collinear
    ys = [float(h) for h in range(8, 20)] * 2
    f = insight.correlate("focus", xs, ys, clock_hours=clock)
    assert f.usable
    assert "time of day" in f.caveat


def test_spearman_is_rank_based():
    xs = [1, 2, 3, 4, 5]
    ys = [1, 4, 9, 16, 250]     # monotone but wildly non-linear
    assert insight.spearman(xs, ys) == pytest.approx(1.0)


def test_fat_loss_rate_needs_a_real_span():
    short = [(dt.date(2026, 8, d), 75.0 - d * 0.05) for d in range(1, 9)]
    assert insight.fat_loss_rate(short, [2000] * 8) is None


def test_fat_loss_rate_backs_out_tdee():
    # 0.5 kg/week loss on a median 1,900 kcal intake.
    weights = [(dt.date(2026, 7, 1) + dt.timedelta(days=i), 76.0 - i * (0.5 / 7)) for i in range(0, 28, 2)]
    r = insight.fat_loss_rate(weights, [1900.0] * 26)
    assert r is not None
    assert r.kg_per_week == pytest.approx(-0.5, abs=0.02)
    assert r.implied_deficit_kcal == pytest.approx(550, abs=15)
    assert r.implied_tdee_kcal == pytest.approx(2450, abs=15)


def test_fat_loss_rate_flags_too_fast():
    weights = [(dt.date(2026, 7, 1) + dt.timedelta(days=i), 76.0 - i * 0.25) for i in range(0, 20, 2)]
    r = insight.fat_loss_rate(weights, [1500.0] * 18)
    assert r is not None and "lean mass" in r.note


def test_fat_loss_rate_calls_maintenance_maintenance():
    weights = [(dt.date(2026, 7, 1) + dt.timedelta(days=i), 75.0) for i in range(0, 28, 2)]
    r = insight.fat_loss_rate(weights, [2400.0] * 26)
    assert r is not None and "maintenance" in r.note
