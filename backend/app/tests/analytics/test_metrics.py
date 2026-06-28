from __future__ import annotations

import time

from app.analytics.spreads import compute_spreads
from app.analytics.trend import compute_trends
from app.analytics.volatility import compute_volatility
from app.analytics.cross_exchange import compute_cross_exchange
from app.analytics.volume_anomaly import compute_volume_anomalies
from app.analytics.liquidity import compute_liquidity
from app.analytics.worker import _family_snapshots
from app.schemas.market import BookLevel, BookTopEvent, CandleEvent, OrderBookDepthEvent, TradeEvent
from app.services.market_state import MarketState


def _trade(symbol: str, trade_id: int, price: float, quantity: float, trade_time: int) -> TradeEvent:
    return TradeEvent(
        symbol=symbol,
        trade_id=trade_id,
        price=price,
        quantity=quantity,
        buyer_maker=False,
        event_time=trade_time,
        trade_time=trade_time,
        received_at=trade_time,
        ingest_latency_ms=1,
    )


def _book(symbol: str, bid: float, ask: float, received_at: int) -> BookTopEvent:
    mid = (bid + ask) / 2
    spread = ask - bid
    return BookTopEvent(
        symbol=symbol,
        bid_price=bid,
        bid_quantity=10,
        ask_price=ask,
        ask_quantity=10,
        spread=spread,
        spread_bps=(spread / mid) * 10_000,
        event_time=received_at,
        received_at=received_at,
        ingest_latency_ms=1,
    )


def _candle(symbol: str, open_time: int, open_price: float, high: float, low: float, close: float) -> CandleEvent:
    return CandleEvent(
        symbol=symbol,
        interval="1m",
        open_time=open_time,
        close_time=open_time + 59_999,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100,
        quote_volume=100 * close,
        trade_count=20,
        is_closed=True,
        received_at=open_time + 59_999,
    )


def test_trend_spread_and_volatility_rankings_from_fake_market_data() -> None:
    now = int(time.time() * 1000)
    state = MarketState(["AAAUSDT", "BBBUSDT"])

    for idx in range(20):
        event_time = now - (20 - idx) * 10_000
        state.apply(_trade("AAAUSDT", idx, 100 + idx, 2, event_time))
        state.apply(_trade("BBBUSDT", idx, 100 - idx * 0.2, 1, event_time))
        state.apply(_book("AAAUSDT", 100 + idx, 100.01 + idx, event_time))
        state.apply(_book("BBBUSDT", 100 + idx, 100.10 + idx, event_time))
        state.apply(_candle("AAAUSDT", event_time, 100, 101 + idx * 0.1, 99, 100 + idx * 0.2))
        state.apply(_candle("BBBUSDT", event_time, 100, 100.2, 99.8, 100))

    trends = compute_trends(state)
    spreads = compute_spreads(state)
    volatility = compute_volatility(state)

    assert trends[0]["symbol"] == "AAAUSDT"
    assert spreads[0]["symbol"] == "AAAUSDT"
    assert volatility[0]["symbol"] == "AAAUSDT"
    assert trends[0]["windows"]["1m"]["sample_count"] > 0
    assert spreads[0]["sample_count"] > 0
    assert volatility[0]["sample_count"] > 0


def test_cross_exchange_ranks_tightest_exchange_and_price_leader() -> None:
    now = int(time.time() * 1000)
    state = MarketState(["AAAUSDT"])

    binance_trade = _trade("AAAUSDT", 1, 100.0, 1, now - 1000)
    coinbase_trade = _trade("AAAUSDT", 2, 100.2, 1, now - 500)
    coinbase_trade.exchange = "coinbase"
    binance_book = _book("AAAUSDT", 99.99, 100.01, now - 1000)
    coinbase_book = _book("AAAUSDT", 100.0, 100.1, now - 500)
    coinbase_book.exchange = "coinbase"

    state.apply(binance_trade)
    state.apply(coinbase_trade)
    state.apply(binance_book)
    state.apply(coinbase_book)

    rows = compute_cross_exchange(state)

    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["tightest_exchange"]["exchange"] == "binance"
    assert rows[0]["price_discovery_leader"]["exchange"] == "coinbase"
    assert rows[0]["price_dispersion_bps"] is not None


def test_volume_anomaly_scores_current_volume_against_prior_buckets() -> None:
    now = int(time.time() * 1000)
    state = MarketState(["AAAUSDT"])

    trade_id = 0
    for minute in range(6, 1, -1):
        state.apply(_trade("AAAUSDT", trade_id, 100, 1, now - minute * 60_000))
        trade_id += 1

    for index in range(20):
        state.apply(_trade("AAAUSDT", trade_id + index, 100, 2, now - 10_000 + index))

    rows = compute_volume_anomalies(state)

    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["current_volume"] > rows[0]["baseline_mean"]
    assert rows[0]["z_score"] is not None


def test_liquidity_computes_depth_buckets_and_imbalance() -> None:
    now = int(time.time() * 1000)
    state = MarketState(["AAAUSDT"])
    depth = OrderBookDepthEvent(
        symbol="AAAUSDT",
        bids=[
            BookLevel(price=99.99, quantity=10),
            BookLevel(price=99.95, quantity=20),
            BookLevel(price=99.5, quantity=30),
        ],
        asks=[
            BookLevel(price=100.01, quantity=5),
            BookLevel(price=100.05, quantity=10),
            BookLevel(price=100.5, quantity=15),
        ],
        event_time=now,
        received_at=now,
        update_id=1,
    )

    state.apply(depth)
    rows = compute_liquidity(state)

    assert rows[0]["symbol"] == "AAAUSDT"
    assert rows[0]["depth"]["10bps"]["total_notional"] > 0
    assert rows[0]["order_book_imbalance"] is not None
    assert rows[0]["order_book_imbalance"] > 0


def test_family_snapshots_decompose_summary_for_history_storage() -> None:
    summary = {
        "computed_at": 123,
        "trend_rankings": [{"symbol": "AAAUSDT"}],
        "spread_rankings": [],
        "volatility_rankings": [],
        "liquidity": [],
        "volume_anomalies": [],
        "cross_exchange": [],
    }

    snapshots = _family_snapshots(summary)

    families = {snapshot["metric_family"] for snapshot in snapshots}
    assert "trends" in families
    assert "liquidity" in families
    assert "cross_exchange" in families
    assert snapshots[0]["payload"]["computed_at"] == 123
