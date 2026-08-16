"""The improvement loop: evidence pack -> proposal -> human gate -> versioned write.

This is the one place a large model earns its cost, because the task is
genuinely judgement under uncertainty rather than extraction. It runs weekly at
most, on a few thousand tokens of pre-aggregated SQL — never on raw logs.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from .. import db
from ..config import CORE_NUTRIENTS, MODEL_PLAN
from ..llm.client import cached, call_tool
from ..llm.schemas import PLAN_SYSTEM, PLAN_TOOL


async def evidence_pack(user_id: int, day: dt.date) -> str:
    """Aggregate first, then send. The model never sees an individual log line.

    28 days of raw entries is roughly 20k tokens and adds nothing a median does
    not already say. This pack is under 1,500 and is strictly more legible.
    """
    p = await db.pool()
    med7 = await db.window_medians(user_id, 7, CORE_NUTRIENTS)
    med28 = await db.window_medians(user_id, 28, CORE_NUTRIENTS)
    prog = await p.fetch("SELECT * FROM day_progress($1,$2)", user_id, day)
    targets = {r["nutrient_id"]: r for r in prog}

    lines = ["# Evidence pack", f"generated: {day}", "", "## Nutrient medians vs target"]
    lines.append("nutrient_id | name | unit | median_7d | median_28d | min | max | status_7d")
    for nid in CORE_NUTRIENTS:
        t = targets.get(nid)
        if not t:
            continue
        m7 = med7.get(nid, 0.0)
        lo = float(t["min_amount"]) if t["min_amount"] is not None else None
        hi = float(t["max_amount"]) if t["max_amount"] is not None else None
        status = "ok"
        if hi is not None and m7 > hi:
            status = f"over by {m7-hi:.0f}"
        elif lo is not None and m7 < lo:
            status = f"under by {lo-m7:.0f}"
        lines.append(
            f"{nid} | {t['nutrient_name']} | {t['unit']} | {m7:.1f} | "
            f"{med28.get(nid,0):.1f} | {lo if lo is not None else '-'} | "
            f"{hi if hi is not None else '-'} | {status}"
        )

    # Logging completeness. A model told only about the days you logged will
    # confidently describe a diet you do not eat.
    days_logged = await p.fetchval(
        """SELECT count(DISTINCT local_date) FROM log_entry
            WHERE user_id = $1 AND status='confirmed' AND local_date > $2::date - 28""",
        user_id, day,
    )
    entries_per_day = await p.fetchval(
        """SELECT round(avg(c),1) FROM (
             SELECT local_date, count(*) c FROM log_entry
              WHERE user_id=$1 AND status='confirmed' AND local_date > $2::date - 28
           GROUP BY local_date) x""",
        user_id, day,
    )
    lines += [
        "",
        "## Coverage",
        f"days with any log in last 28: {days_logged}/28",
        f"mean entries per logged day: {entries_per_day}",
    ]

    heavy = await p.fetch(
        """SELECT e.name, count(*) AS n, round(avg(ln.amount)) AS kcal
             FROM log_entry e JOIN log_nutrient ln ON ln.entry_id=e.id AND ln.nutrient_id=1008
            WHERE e.user_id=$1 AND e.status='confirmed' AND e.local_date > $2::date - 28
         GROUP BY e.name ORDER BY count(*)*avg(ln.amount) DESC LIMIT 12""",
        user_id, day,
    )
    lines += ["", "## Highest total-energy contributors (28d)", "dish | times | mean_kcal"]
    lines += [f"{r['name']} | {r['n']} | {r['kcal']}" for r in heavy]

    weights = await p.fetch(
        """SELECT local_date, value FROM body_metric
            WHERE user_id=$1 AND kind='weight_kg' AND local_date > $2::date - 28
         ORDER BY local_date""",
        user_id, day,
    )
    if weights:
        lines += ["", "## Weight (kg)"]
        lines.append(", ".join(f"{r['local_date']}:{float(r['value']):.2f}" for r in weights))

    # How much of the intake above was measured rather than guessed. A model
    # told that sodium is 40% over, on a fortnight where two-thirds of the mass
    # was eyeballed, should temper the finding — and cannot unless it is told.
    conf = await p.fetch(
        """SELECT local_date, pct_measured FROM v_day_mass_confidence
            WHERE user_id=$1 AND local_date > $2::date - 28 ORDER BY local_date""",
        user_id, day,
    )
    if conf:
        mean_conf = sum(float(r["pct_measured"] or 0) for r in conf) / len(conf)
        lines += ["", "## Measurement quality",
                  f"mean share of daily mass weighed or stated: {mean_conf:.0f}%",
                  "the rest was estimated from a description or a photo"]

    acts = await p.fetch(
        """SELECT kind, count(*) AS n, sum(minutes) AS mins,
                  count(*) FILTER (WHERE intensity IN ('hard','max')) AS hard
             FROM activity WHERE user_id=$1 AND local_date > $2::date - 28
         GROUP BY kind ORDER BY 2 DESC""",
        user_id, day,
    )
    if acts:
        lines += ["", "## Training (28d)", "kind | sessions | minutes | hard_or_max"]
        lines += [f"{r['kind']} | {r['n']} | {r['mins'] or 0} | {r['hard']}" for r in acts]
        lines.append("energy targets are NOT raised by training here; this is context only")

    supps = await p.fetch(
        """SELECT s.name, count(sl.*) AS taken
             FROM supplement s
             LEFT JOIN supplement_log sl ON sl.supplement_id = s.id
                   AND sl.local_date > $2::date - 28
            WHERE s.user_id = $1 AND s.active
         GROUP BY s.name ORDER BY 2 DESC""",
        user_id, day,
    )
    if supps:
        lines += ["", "## Supplements taken in last 28 days", "name | days_taken"]
        lines += [f"{r['name']} | {r['taken']}" for r in supps]
        lines.append("micronutrient medians above already include these")

    ratings = await p.fetch(
        """SELECT kind, count(*) AS n, round(avg(value),1) AS mean
             FROM observation
            WHERE user_id=$1 AND local_date > $2::date - 28
         GROUP BY kind ORDER BY 1""",
        user_id, day,
    )
    if ratings:
        lines += ["", "## Self-ratings (28d, 1-10)", "kind | n | mean"]
        lines += [f"{r['kind']} | {r['n']} | {r['mean']}" for r in ratings]
        lines.append("correlations are computed elsewhere and are NOT in this pack; "
                     "do not assert a relationship between these and intake")

    return "\n".join(lines)


async def propose(user_id: int, day: dt.date) -> tuple[dict[str, Any], float]:
    pack = await evidence_pack(user_id, day)
    res = await call_tool(
        model=MODEL_PLAN,
        tool=PLAN_TOOL,
        system=[cached(PLAN_SYSTEM)],
        content=[{"type": "text", "text": pack}],
        max_tokens=2500,
    )
    await db.record_llm_call(
        user_id=user_id, purpose="plan", model=res.model,
        input_tokens=res.input_tokens, output_tokens=res.output_tokens,
        cache_read_tokens=res.cache_read_tokens, cache_write_tokens=res.cache_write_tokens,
        latency_ms=res.latency_ms, cost_usd=res.cost_usd,
    )
    await db.put_pending(user_id, "plan_proposal", res.data)
    return res.data, res.cost_usd


def render_proposal(data: dict[str, Any]) -> str:
    lines = ["*What the data says*"]
    for f in data.get("findings", []):
        lines.append(f"• {f['statement']}  _({f['confidence']})_")
        lines.append(f"  {f['evidence']}")
    lines.append("")
    lines.append("*Proposed changes*")
    for r in data.get("recommendations", []):
        lines.append(f"*{r['n']}.* {r['action']}")
        lines.append(f"    → {r['expected_effect']}")
        lines.append(f"    risk: {r['risk']}")
        for tc in r.get("target_changes", []) or []:
            bits = []
            if tc.get("min_amount") is not None:
                bits.append(f"min {tc['min_amount']}")
            if tc.get("max_amount") is not None:
                bits.append(f"max {tc['max_amount']}")
            lines.append(f"    target {tc['nutrient_id']}: {', '.join(bits)}")
    gap = data.get("what_the_data_cannot_tell_you")
    if gap:
        lines += ["", f"_limits: {gap}_"]
    lines += ["", "Reply `apply 1 3` to take some, `apply all`, or ignore this."]
    return "\n".join(lines)


async def apply_recommendations(user_id: int, data: dict[str, Any], numbers: set[int], day: dt.date) -> list[str]:
    """Close the old target row and open a new one from tomorrow.

    Never UPDATE a target in place. The question 'did the change I made in
    August actually do anything' is unanswerable if the target history has been
    overwritten by the change itself.
    """
    p = await db.pool()
    applied: list[str] = []
    effective = day + dt.timedelta(days=1)
    async with p.acquire() as con, con.transaction():
        for rec in data.get("recommendations", []):
            if rec["n"] not in numbers:
                continue
            for tc in rec.get("target_changes", []) or []:
                nid = int(tc["nutrient_id"])
                await con.execute(
                    """UPDATE target SET effective_to = $3
                        WHERE user_id=$1 AND nutrient_id=$2 AND effective_to IS NULL""",
                    user_id, nid, effective,
                )
                await con.execute(
                    """INSERT INTO target
                         (user_id, nutrient_id, min_amount, max_amount, period,
                          effective_from, rationale)
                       VALUES ($1,$2,$3,$4,'day',$5,$6)""",
                    user_id, nid, tc.get("min_amount"), tc.get("max_amount"),
                    effective, json.dumps({"rec": rec["n"], "why": tc.get("rationale")}),
                )
            applied.append(f"{rec['n']}. {rec['action']}")
    return applied
