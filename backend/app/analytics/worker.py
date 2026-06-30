from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Optional

from app.analytics.scoring import analytics_summary
from app.config import settings
from app.db.pool import Database
from app.services.market_state import MarketState

logger = logging.getLogger(__name__)


class AnalyticsWorker:
    def __init__(self, state: MarketState, db: Database) -> None:
        self.state = state
        self.db = db
        self.latest_summary: Optional[dict[str, Any]] = None
        self.recent_events: deque[dict[str, Any]] = deque(maxlen=100)
        self._stop = asyncio.Event()
        self._last_event_key_at: dict[str, int] = {}
        self._last_system_success_at = 0.0

    async def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.compute_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("analytics worker iteration failed")
                await self.db.record_system_event(
                    "analytics",
                    "iteration_failed",
                    severity="error",
                    status="failed",
                    message=str(exc),
                )
            await asyncio.sleep(settings.analytics_interval_seconds)

    async def compute_once(self) -> dict[str, Any]:
        summary = analytics_summary(self.state)
        summary["computed_at"] = int(time.time() * 1000)
        self.latest_summary = summary

        events = self._detect_events(summary)
        for event in events:
            self.recent_events.appendleft(event)

        await self.db.save_analytics_snapshot("summary", summary)
        await self.db.save_analytics_snapshots(_family_snapshots(summary))
        await self.db.save_analytics_events(events)
        now = time.time()
        if now - self._last_system_success_at >= 60:
            self._last_system_success_at = now
            await self.db.record_system_event(
                "analytics",
                "iteration_completed",
                status="ok",
                message="analytics summary computed",
                payload={
                    "analytics_events": len(events),
                    "trend_rows": len(summary.get("trend_rankings", [])),
                    "spread_rows": len(summary.get("spread_rankings", [])),
                    "volatility_rows": len(summary.get("volatility_rankings", [])),
                },
            )
        return summary

    def _detect_events(self, summary: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        computed_at = summary.get("computed_at") or int(time.time() * 1000)

        for row in summary.get("spread_rankings", []):
            ratio = row.get("widening_ratio")
            if ratio is not None and ratio >= settings.spread_widening_alert_ratio:
                events.append(
                    self._event(
                        event_type="spread_widening",
                        symbol=row["symbol"],
                        severity="warning",
                        metric_name="widening_ratio",
                        metric_value=ratio,
                        baseline_value=1.0,
                        window="5m",
                        computed_at=computed_at,
                        payload=row,
                    )
                )

        for row in summary.get("volatility_rankings", []):
            regime = row.get("regime")
            if regime in settings.volatility_alert_regime_list:
                events.append(
                    self._event(
                        event_type="volatility_regime",
                        symbol=row["symbol"],
                        severity="warning" if regime == "elevated" else "critical",
                        metric_name="realized_volatility_pct",
                        metric_value=row.get("realized_volatility_pct"),
                        baseline_value=None,
                        window=row.get("window"),
                        computed_at=computed_at,
                        payload=row,
                    )
                )

        for row in summary.get("trend_rankings", []):
            score = row.get("momentum_score") or 0
            if abs(score) >= settings.trend_alert_abs_score:
                events.append(
                    self._event(
                        event_type="momentum_extreme",
                        symbol=row["symbol"],
                        severity="info",
                        metric_name="momentum_score",
                        metric_value=score,
                        baseline_value=0.0,
                        window="multi",
                        computed_at=computed_at,
                        payload=row,
                    )
                )

        for row in summary.get("volume_anomalies", []):
            z_score = row.get("z_score")
            if z_score is not None and z_score >= settings.volume_zscore_alert:
                events.append(
                    self._event(
                        event_type="volume_spike",
                        symbol=row["symbol"],
                        severity="warning",
                        metric_name="volume_z_score",
                        metric_value=z_score,
                        baseline_value=row.get("baseline_mean"),
                        window=row.get("window"),
                        computed_at=computed_at,
                        payload=row,
                    )
                )

        for row in summary.get("liquidity", []):
            drop_pct = row.get("collapse", {}).get("drop_pct")
            if drop_pct is not None and drop_pct >= settings.liquidity_collapse_alert_pct:
                events.append(
                    self._event(
                        event_type="liquidity_collapse",
                        symbol=row["symbol"],
                        severity="critical",
                        metric_name="depth_25bps_drop_pct",
                        metric_value=drop_pct,
                        baseline_value=row.get("collapse", {}).get("baseline_notional"),
                        window="depth25bps",
                        computed_at=computed_at,
                        payload=row,
                    )
                )

        return [event for event in events if self._should_emit(event, computed_at)]

    def _event(
        self,
        *,
        event_type: str,
        symbol: str,
        severity: str,
        metric_name: str,
        metric_value: Optional[float],
        baseline_value: Optional[float],
        window: Optional[str],
        computed_at: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": event_type,
            "exchange": "binance",
            "symbol": symbol,
            "severity": severity,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "baseline_value": baseline_value,
            "window": window,
            "payload": payload,
            "occurred_at": computed_at,
        }

    def _should_emit(self, event: dict[str, Any], computed_at: int) -> bool:
        key = f"{event['event_type']}:{event['symbol']}:{event.get('window')}"
        last_at = self._last_event_key_at.get(key)
        if last_at is not None and computed_at - last_at < 60_000:
            return False
        self._last_event_key_at[key] = computed_at
        return True


def _family_snapshots(summary: dict[str, Any]) -> list[dict[str, Any]]:
    computed_at = summary.get("computed_at")
    return [
        {
            "metric_family": "trends",
            "window": "multi",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("trend_rankings", []),
            },
        },
        {
            "metric_family": "spreads",
            "window": "5m",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("spread_rankings", []),
            },
        },
        {
            "metric_family": "volatility",
            "window": "5m",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("volatility_rankings", []),
            },
        },
        {
            "metric_family": "liquidity",
            "window": "depth25bps",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("liquidity", []),
            },
        },
        {
            "metric_family": "volume_anomalies",
            "window": "1m",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("volume_anomalies", []),
            },
        },
        {
            "metric_family": "cross_exchange",
            "window": "live",
            "payload": {
                "computed_at": computed_at,
                "rows": summary.get("cross_exchange", []),
            },
        },
    ]
