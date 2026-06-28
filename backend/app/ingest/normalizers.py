from __future__ import annotations

import time
from typing import Any, Optional, Union

from app.schemas.market import BookLevel, BookTopEvent, CandleEvent, OrderBookDepthEvent, TradeEvent


def _latency(event_time: Optional[int], received_at: int) -> Optional[int]:
    if not event_time:
        return None
    return max(0, received_at - event_time)


def normalize(
    stream: str, payload: dict[str, Any]
) -> Optional[Union[TradeEvent, BookTopEvent, CandleEvent, OrderBookDepthEvent]]:
    received_at = int(time.time() * 1000)

    if stream.endswith("@trade"):
        return TradeEvent(
            symbol=payload["s"],
            trade_id=int(payload["t"]),
            price=float(payload["p"]),
            quantity=float(payload["q"]),
            buyer_maker=bool(payload["m"]),
            event_time=int(payload["E"]),
            trade_time=int(payload["T"]),
            received_at=received_at,
            ingest_latency_ms=_latency(int(payload["E"]), received_at),
        )

    if stream.endswith("@bookticker"):
        bid = float(payload["b"])
        ask = float(payload["a"])
        mid = (bid + ask) / 2 if bid and ask else 0
        spread = max(0.0, ask - bid)
        return BookTopEvent(
            symbol=payload["s"],
            bid_price=bid,
            bid_quantity=float(payload["B"]),
            ask_price=ask,
            ask_quantity=float(payload["A"]),
            spread=spread,
            spread_bps=(spread / mid * 10_000) if mid else None,
            event_time=int(payload.get("E") or received_at),
            received_at=received_at,
            ingest_latency_ms=_latency(payload.get("E"), received_at),
        )

    if "@kline_" in stream:
        kline = payload["k"]
        return CandleEvent(
            symbol=kline["s"],
            interval=kline["i"],
            open_time=int(kline["t"]),
            close_time=int(kline["T"]),
            open=float(kline["o"]),
            high=float(kline["h"]),
            low=float(kline["l"]),
            close=float(kline["c"]),
            volume=float(kline["v"]),
            quote_volume=float(kline["q"]),
            trade_count=int(kline["n"]),
            is_closed=bool(kline["x"]),
            received_at=received_at,
        )

    if "@depth" in stream:
        symbol = stream.split("@", 1)[0].upper()
        event_time = int(payload.get("E") or received_at)
        return OrderBookDepthEvent(
            symbol=symbol,
            bids=[
                BookLevel(price=float(level[0]), quantity=float(level[1]))
                for level in payload.get("bids", [])
            ],
            asks=[
                BookLevel(price=float(level[0]), quantity=float(level[1]))
                for level in payload.get("asks", [])
            ],
            event_time=event_time,
            received_at=received_at,
            update_id=payload.get("lastUpdateId") or payload.get("u"),
            ingest_latency_ms=_latency(event_time, received_at),
        )

    return None
