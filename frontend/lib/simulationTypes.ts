export type BacktestStrategy = "sma_cross" | "momentum_breakout";
export type SimulationInterval = "1m" | "5m" | "15m" | "1h";

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
  backtesting?: {
    enabled: boolean;
    strategies: string[];
    data_source: string;
  };
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

export type BacktestResult = {
  type: "backtest_result";
  read_only: boolean;
  run_id?: number;
  id?: number;
  created_at?: string;
  strategy: BacktestStrategy;
  symbol: string;
  interval: string;
  parameters: {
    short_window?: number;
    long_window?: number;
    momentum_window?: number;
    breakout_bps?: number;
    exit_window?: number;
    fee_bps: number;
    slippage_bps: number;
    initial_cash: number;
  };
  sample: {
    candle_count: number;
    start: string | null;
    end: string | null;
  };
  summary: {
    initial_cash: string | number;
    final_equity: string | number;
    cash: string | number;
    position_quantity: string | number;
    position_mark: string | number;
    realized_pnl: string | number;
    total_return_pct: string | number | null;
    max_drawdown_pct: string | number;
    trade_count: number;
    closed_trade_count: number;
    win_rate_pct: string | number | null;
    total_fees?: string | number;
    total_slippage?: string | number;
    gross_profit?: string | number;
    gross_loss?: string | number;
    average_win?: string | number | null;
    average_loss?: string | number | null;
    profit_factor?: string | number | null;
    exposure_pct?: string | number | null;
    buy_hold_return_pct?: string | number | null;
    alpha_vs_buy_hold_pct?: string | number | null;
  };
  trades: Array<{
    time: string;
    side: "buy" | "sell";
    price: string | number;
    quantity: string | number;
    fee: string | number;
    slippage?: string | number;
    notional: string | number;
    realized_pnl: string | number;
    reason: string;
  }>;
  equity_curve: Array<{
    time: string;
    equity: string | number;
    cash: string | number;
    quantity: string | number;
    mark_price: string | number;
  }>;
};

export type BacktestRunSummary = {
  id: number;
  exchange: string;
  symbol: string;
  interval: string;
  strategy: BacktestStrategy;
  status: string;
  parameters: BacktestResult["parameters"];
  sample: BacktestResult["sample"];
  summary: BacktestResult["summary"];
  trade_count: number;
  created_at: string;
};

export type AutomationStatus = {
  read_only: boolean;
  live_trading_enabled: false;
  automated_simulation_enabled: boolean;
  config: {
    portfolio_id: string;
    exchange: string;
    symbol: string;
    interval: SimulationInterval;
    strategy: BacktestStrategy;
    enabled: boolean;
    poll_seconds: number;
    notional: string | number;
    max_position_notional: string | number;
    short_window: number;
    long_window: number;
    momentum_window: number;
    breakout_bps: string | number;
    exit_window: number;
    stop_loss_bps: string | number;
    trailing_stop_bps: string | number;
    take_profit_bps: string | number;
    min_holding_minutes: string | number;
    max_holding_minutes: string | number;
    cooldown_minutes: string | number;
    max_spread_bps: string | number;
  };
  last_signal: AutomationSignal | null;
  last_error: string | null;
};

export type AutomationSignal = {
  id: number;
  portfolio_id: string;
  exchange: string;
  symbol: string;
  strategy: BacktestStrategy;
  signal: "buy" | "sell" | "hold";
  status: "executed" | "rejected" | "skipped" | "observed";
  reason: string | null;
  candle_time: string | null;
  order_id: number | null;
  payload: Record<string, unknown>;
  created_at: string;
};
