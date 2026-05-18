export interface Market {
  condition_id: string;
  token_id_yes: string;
  token_id_no: string;
  name: string;
  volume_24h: number;
  category: string;
}

export interface Surge {
  id: number;
  timestamp: string;
  market_id: string;
  token_id: string;
  market_name: string;
  direction: "up" | "down";
  magnitude: number;
  window_seconds: number;
  price_at_detection: number;
  traded: boolean;
}

export interface Position {
  id: number;
  market_id: string;
  token_id: string;
  market_name: string;
  direction: "up" | "down";
  entry_price: number;
  entry_fee: number;
  entry_time: string;
  shares: number;
  position_size: number;
  trailing_peak: number;
  max_favorable_excursion: number;
  current_price?: number;
  unrealized_pnl?: number;
}

export interface Trade {
  id: number;
  surge_id: number | null;
  market_id: string;
  token_id: string;
  market_name: string;
  direction: "up" | "down";
  entry_price: number;
  entry_fee: number;
  entry_time: string;
  exit_price: number | null;
  exit_fee: number | null;
  exit_time: string | null;
  exit_reason: string | null;
  shares: number;
  position_size: number;
  pnl: number | null;
  peak_price: number | null;
  max_favorable_excursion: number | null;
}

export interface BalanceEntry {
  id: number;
  timestamp: string;
  balance: number;
  trade_id: number | null;
  change: number;
  reason: string;
}

export interface EngineStatus {
  balance: number;
  starting_balance: number;
  open_positions: number;
  daily_pnl: number;
  daily_trades: number;
  paused: boolean;
  uptime_seconds: number;
}

export interface WsStatus {
  state: "connected" | "reconnecting" | "disconnected";
  uptime_seconds: number;
  reconnect_count: number;
  messages_per_sec: number;
  subscribed_tokens: number;
  last_message_at: string | null;
  total_messages: number;
  events_by_type: Record<string, number>;
}

export interface DetectorStats {
  surges_up: number;
  surges_down: number;
  active_windows: number;
  cooldowns_active: number;
}

export interface DailyStats {
  date: string;
  trades: number;
  wins: number;
  losses: number;
  pnl: number;
  balance: number;
}

export interface MarketStats {
  total_markets: number;
  total_volume: number;
  total_tokens: number;
  categories: Record<string, number>;
}

export interface Alert {
  timestamp: string;
  type: string;
  message: string;
  sent: boolean;
  error?: string;
}

export interface AlertsStatus {
  enabled: boolean;
  configured: boolean;
  chat_id: string;
}

export interface BacktestStats {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  gross_profit: number;
  gross_loss: number;
  avg_pnl: number;
  avg_win: number;
  avg_loss: number;
  best_trade: number;
  worst_trade: number;
  balance: number;
  starting_balance: number;
  max_drawdown: number;
  profit_factor: number;
  avg_hold_seconds: number;
  trades_per_day: Record<string, number>;
  pnl_by_market: Record<string, number>;
  total_surges: number;
  traded_surges: number;
  surge_conversion_rate: number;
  avg_mfe: number;
  today_pnl: number;
  today_trades: number;
}

export interface SimulationResult {
  params: { threshold: number; trailing_stop: number; take_profit: number };
  original: { total_trades: number; total_pnl: number; wins: number; losses: number; win_rate: number };
  simulated: { total_trades: number; total_pnl: number; wins: number; losses: number; win_rate: number };
}
