from __future__ import annotations

from app.ingest.bybit_ws import BybitMarketDataClient
from app.ingest.kraken_ws import KrakenMarketDataClient
from app.schemas.market import BookTopEvent, OrderBookDepthEvent, TradeEvent
from app.services.market_state import MarketState


async def _noop(event):  # pragma: no cover
    return None


def test_bybit_adapter_normalizes_ticker_trade_and_orderbook() -> None:
    client = BybitMarketDataClient(MarketState(["BTCUSDT"]), _noop)

    ticker = client._normalize(
        {
            "topic": "tickers.BTCUSDT",
            "ts": 1_700_000_000_000,
            "data": {
                "lastPrice": "60000",
                "bid1Price": "59999",
                "bid1Size": "1",
                "ask1Price": "60001",
                "ask1Size": "2",
            },
        }
    )
    trades = client._normalize(
        {
            "topic": "publicTrade.BTCUSDT",
            "data": [{"T": 1_700_000_000_001, "p": "60000", "v": "0.1", "S": "Buy", "i": "42"}],
        }
    )
    depth = client._normalize(
        {
            "topic": "orderbook.50.BTCUSDT",
            "type": "snapshot",
            "ts": 1_700_000_000_002,
            "data": {"u": 1, "b": [["59999", "1"]], "a": [["60001", "2"]]},
        }
    )

    assert any(isinstance(event, BookTopEvent) for event in ticker)
    assert any(isinstance(event, TradeEvent) for event in ticker)
    assert isinstance(trades[0], TradeEvent)
    assert isinstance(depth[0], OrderBookDepthEvent)


def test_kraken_adapter_normalizes_ticker_trade_and_book() -> None:
    client = KrakenMarketDataClient(MarketState(["BTCUSDT"]), _noop)

    ticker = client._normalize(
        {
            "channel": "ticker",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "bid": 59999,
                    "ask": 60001,
                    "last": 60000,
                    "timestamp": "2026-06-28T00:00:00.000000Z",
                }
            ],
        }
    )
    trade = client._normalize(
        {
            "channel": "trade",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "price": 60000,
                    "qty": 0.1,
                    "side": "buy",
                    "trade_id": 1,
                    "timestamp": "2026-06-28T00:00:00.000000Z",
                }
            ],
        }
    )
    book = client._normalize(
        {
            "channel": "book",
            "data": [
                {
                    "symbol": "BTC/USD",
                    "bids": [{"price": 59999, "qty": 1}],
                    "asks": [{"price": 60001, "qty": 2}],
                    "timestamp": "2026-06-28T00:00:00.000000Z",
                }
            ],
        }
    )

    assert any(isinstance(event, BookTopEvent) for event in ticker)
    assert any(isinstance(event, TradeEvent) for event in ticker)
    assert isinstance(trade[0], TradeEvent)
    assert isinstance(book[0], OrderBookDepthEvent)
