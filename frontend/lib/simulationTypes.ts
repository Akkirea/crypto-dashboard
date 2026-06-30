export type SimulationConfig = {
  mode: string;
  read_only: boolean;
  live_trading_enabled: boolean;
  order_execution_enabled: boolean;
  symbols: string[];
  intervals: string[];
  default_exchange: string;
  fill_model: {
    price_source: string;
    fee_bps: number;
    slippage_bps: number;
    latency_ms: number;
  };
  data_sources: Record<string, string>;
};

export type SimulationSnapshot = {
  type: "simulation_market_snapshot";
  read_only: boolean;
  health: {
    status: string;
    connected: boolean;
    latency_ms: number | null;
    message_counts: Record<string, number>;
  };
  symbols: string[];
  prices: Record<string, number>;
  books: Record<
    string,
    {
      bid_price: number;
      ask_price: number;
      spread_bps: number | null;
      received_at: number;
    }
  >;
};

export type SimulationCandle = {
  exchange: string;
  symbol: string;
  interval: string;
  open_time: string;
  close_time: string;
  open: string | number;
  high: string | number;
  low: string | number;
  close: string | number;
  volume: string | number;
  is_closed: boolean;
};

export type SimulationTrade = {
  exchange: string;
  symbol: string;
  trade_id: number;
  price: string | number;
  quantity: string | number;
  buyer_maker: boolean | null;
  trade_time: string;
  ingest_latency_ms: number | null;
};
