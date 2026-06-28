export type SymbolName = "BTCUSDT" | "ETHUSDT" | "SOLUSDT";

export type TradeEvent = {
  type: "trade";
  exchange: "binance";
  symbol: SymbolName;
  trade_id: number;
  price: number;
  quantity: number;
  buyer_maker: boolean;
  event_time: number;
  trade_time: number;
  received_at: number;
  ingest_latency_ms: number | null;
};

export type BookTopEvent = {
  type: "book_top";
  exchange: "binance";
  symbol: SymbolName;
  bid_price: number;
  bid_quantity: number;
  ask_price: number;
  ask_quantity: number;
  spread: number;
  spread_bps: number | null;
  event_time: number;
  received_at: number;
  ingest_latency_ms: number | null;
};

export type CandleEvent = {
  type: "candle";
  exchange: "binance";
  symbol: SymbolName;
  interval: "1m" | "5m";
  open_time: number;
  close_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume: number;
  trade_count: number;
  is_closed: boolean;
  received_at: number;
};

export type HealthEvent = {
  type: "health";
  status: "healthy" | "degraded" | "stale" | "unhealthy";
  connected: boolean;
  reconnect_count: number;
  last_message_at: number | null;
  latency_ms: number | null;
  message_counts: Record<string, number>;
  client_count: number;
};

export type SnapshotMessage = {
  type: "snapshot";
  symbols: SymbolName[];
  prices: Partial<Record<SymbolName, number>>;
  books: Partial<Record<SymbolName, BookTopEvent>>;
  trades: Partial<Record<SymbolName, TradeEvent[]>>;
  candles: Partial<Record<SymbolName, Partial<Record<"1m" | "5m", CandleEvent>>>>;
  health: HealthEvent;
};

export type MarketMessage =
  | TradeEvent
  | BookTopEvent
  | CandleEvent
  | HealthEvent
  | SnapshotMessage;
