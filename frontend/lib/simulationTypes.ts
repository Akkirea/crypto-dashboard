export type SimulationConfig = {
  mode: string;
  read_only: boolean;
  live_trading_enabled: boolean;
  order_execution_enabled: boolean;
  simulated_execution_enabled: boolean;
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

export type SimulationPosition = {
  portfolio_id: string;
  exchange: string;
  symbol: string;
  quantity: string | number;
  avg_entry_price: string | number;
  realized_pnl: string | number;
  mark_price?: string | number;
  market_value?: string | number;
  unrealized_pnl?: string | number;
  updated_at: string;
};

export type SimulationPortfolio = {
  id: string;
  cash_balance: string | number;
  initial_cash: string | number;
  realized_pnl: string | number;
  unrealized_pnl: string | number;
  equity: string | number;
  positions: SimulationPosition[];
};

export type SimulationOrder = {
  id: number;
  portfolio_id: string;
  exchange: string;
  symbol: string;
  side: "buy" | "sell";
  order_type: "market";
  status: "submitted" | "filled" | "rejected" | "cancelled";
  requested_quantity: string | number;
  filled_quantity: string | number;
  fill_price: string | number | null;
  fee: string | number;
  submitted_at: string;
  filled_at: string | null;
  rejection_reason: string | null;
};

export type SimulationFill = {
  id: number;
  order_id: number;
  portfolio_id: string;
  exchange: string;
  symbol: string;
  side: "buy" | "sell";
  price: string | number;
  quantity: string | number;
  notional: string | number;
  fee: string | number;
  created_at: string;
};
