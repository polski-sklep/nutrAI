from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from anthropic import AsyncAnthropic

from ..config import CACHE_READ_MULT, CACHE_WRITE_MULT, PRICES, settings

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def price(model: str, usage: Any) -> float:
    """Exact cost of one call, from the usage block the API returns.

    Estimating this from your own token counts is a mistake: cache hits, tool
    system prompts and image patches all land in `usage` and nowhere else.
    """
    p_in, p_out = PRICES.get(model, PRICES["claude-sonnet-5"])
    plain = getattr(usage, "input_tokens", 0) or 0
    cread = getattr(usage, "cache_read_input_tokens", 0) or 0
    cwrite = getattr(usage, "cache_creation_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return (
        plain * p_in
        + cread * p_in * CACHE_READ_MULT
        + cwrite * p_in * CACHE_WRITE_MULT
        + out * p_out
    ) / 1_000_000


@dataclass
class ToolResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int
    cost_usd: float
    stop_reason: str | None = None


async def call_tool(
    *,
    model: str,
    tool: dict[str, Any],
    system: list[dict[str, Any]] | str,
    content: list[dict[str, Any]],
    max_tokens: int = 1200,
) -> ToolResult:
    """One request, one forced tool call, one validated object back.

    `tool_choice={"type":"tool"}` is doing real work here. Asking for JSON in
    prose and parsing it is the single most common source of silent breakage in
    pipelines like this: it fails on the day the model writes a preamble.

    No `temperature`. It used to be pinned to 0.0 for reproducibility, and the
    Claude 5 models reject the parameter outright:

        400 invalid_request_error: `temperature` is deprecated for this model.

    Which killed every parse on the first live call. What actually buys
    determinism here is the forced tool call and a schema with no free-text
    field to wander into — temperature was never the load-bearing part.
    """
    t0 = time.perf_counter()
    msg = await client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": content}],
    )
    latency = int((time.perf_counter() - t0) * 1000)

    data: dict[str, Any] = {}
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use":
            data = dict(block.input)  # type: ignore[arg-type]
            break

    u = msg.usage
    return ToolResult(
        data=data,
        model=model,
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        latency_ms=latency,
        cost_usd=price(model, u),
        stop_reason=msg.stop_reason,
    )


def cached(text: str) -> dict[str, Any]:
    """Mark a system block cacheable (5-minute TTL).

    Worth it for the parse instructions, which are identical on every call and
    run to a few hundred tokens. A cache read costs 10% of input. It pays for
    itself on the second log of any given meal-time cluster.
    """
    return {"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}
