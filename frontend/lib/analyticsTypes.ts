export type AnalyticsWindow = "1m" | "5m" | "15m" | "1h";

export type TrendWindowMetrics = {
  price_change_pct: number | null;
  volume: number;
  volume_change_pct: number | null;
  sample_count: number;
};

export type TrendRow = {
  symbol: string;
  latest_price: number | null;
  momentum_score: number;
  rank: number;
  windows: Record<AnalyticsWindow, TrendWindowMetrics>;
};

export type SpreadRow = {
  symbol: string;
  exchange: string;
  latest_spread_bps: number | null;
  average_spread_bps: number | null;
  spread_volatility_bps: number | null;
  widening_ratio: number | null;
  sample_count: number;
  tightness_rank: number;
};

export type VolatilityRow = {
  symbol: string;
  window: AnalyticsWindow;
  realized_volatility_pct: number | null;
  average_candle_range_pct: number | null;
  regime: "quiet" | "normal" | "elevated" | "extreme" | "insufficient_data";
  sample_count: number;
  volatility_rank: number;
};

export type AnalyticsSummary = {
  type: "analytics_summary";
  trend_rankings: TrendRow[];
  spread_rankings: SpreadRow[];
  volatility_rankings: VolatilityRow[];
  cross_exchange: CrossExchangeRow[];
  volume_anomalies: VolumeAnomalyRow[];
  liquidity: LiquidityRow[];
  leaders: {
    trend: TrendRow | null;
    tightest_spread: SpreadRow | null;
    most_volatile: VolatilityRow | null;
  };
};

export type CrossExchangeVenue = {
  exchange: string;
  symbol: string;
  latest_price: number | null;
  bid_price: number | null;
  ask_price: number | null;
  spread_bps: number | null;
  last_trade_time: number | null;
  last_seen_at: number | null;
  stale: boolean;
};

export type CrossExchangeRow = {
  symbol: string;
  venues: CrossExchangeVenue[];
  price_dispersion_bps: number | null;
  tightest_exchange: CrossExchangeVenue | null;
  price_discovery_leader: {
    exchange: string;
    last_trade_time: number;
    lead_ms: number;
    method: string;
  } | null;
};

export type AnalyticsEvent = {
  event_type: string;
  exchange: string;
  symbol: string;
  severity: "info" | "warning" | "critical";
  metric_name: string;
  metric_value: number | null;
  baseline_value: number | null;
  window: string | null;
  payload: Record<string, unknown>;
  occurred_at: number | string;
};

export type VolumeAnomalyRow = {
  exchange: string;
  symbol: string;
  window: string;
  current_volume: number;
  baseline_mean: number;
  baseline_std: number;
  z_score: number | null;
  volume_ratio: number | null;
  sample_count: number;
};

export type LiquidityDepthBucket = {
  bid_notional: number;
  ask_notional: number;
  total_notional: number;
};

export type LiquidityRow = {
  exchange: string;
  symbol: string;
  best_bid: number | null;
  best_ask: number | null;
  mid_price: number | null;
  top_bid_notional: number | null;
  top_ask_notional: number | null;
  order_book_imbalance: number | null;
  depth: Record<string, LiquidityDepthBucket>;
  collapse: {
    drop_pct: number | null;
    baseline_notional: number | null;
    current_notional: number | null;
  };
  sample_count: number;
  last_update_at: number | null;
};

export type AnalyticsHistorySnapshot = {
  metric_family: string;
  exchange: string;
  window: string | null;
  payload: AnalyticsSummary | {
    computed_at?: number;
    rows?: unknown[];
  };
  computed_at: number | string;
};
