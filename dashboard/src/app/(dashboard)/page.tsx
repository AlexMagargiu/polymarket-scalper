"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import { KPICard } from "@/components/data/kpi-card";
import { BalanceChart } from "@/components/charts/balance-chart";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { fmt$, fmtSign$, fmtPct, fmtDuration, relTime } from "@/lib/format";
import type { BalanceEntry, DetectorStats, EngineStatus, MarketStats, WsStatus } from "@/lib/types";

interface HealthResponse {
  status: string;
  uptime_seconds: number;
  version: string;
}

interface BalanceResponse {
  balance: number;
  starting_balance: number;
  change: number;
  history: BalanceEntry[];
}

interface StatsResponse {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  best_trade: number;
  worst_trade: number;
  today_pnl: number;
  today_trades: number;
}

export default function OverviewPage() {
  const { data: health } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => fetchAPI<HealthResponse>("health"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: bal, isLoading: balLoading } = useQuery<BalanceResponse>({
    queryKey: ["balance"],
    queryFn: () => fetchAPI<BalanceResponse>("balance"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: stats, isLoading: statsLoading } = useQuery<StatsResponse>({
    queryKey: ["stats"],
    queryFn: () => fetchAPI<StatsResponse>("stats"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: marketStats, isLoading: marketsLoading } = useQuery<MarketStats>({
    queryKey: ["market-stats"],
    queryFn: () => fetchAPI<MarketStats>("markets/stats"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: wsStatus } = useQuery<WsStatus>({
    queryKey: ["ws-status"],
    queryFn: () => fetchAPI<WsStatus>("ws/status"),
    refetchInterval: 5_000,
    staleTime: 3_000,
  });

  const { data: detectorStats } = useQuery<DetectorStats>({
    queryKey: ["detector-stats"],
    queryFn: () => fetchAPI<DetectorStats>("detector/stats"),
    refetchInterval: 10_000,
    staleTime: 5_000,
  });

  const { data: engineStatus } = useQuery<EngineStatus>({
    queryKey: ["engine-status"],
    queryFn: () => fetchAPI<EngineStatus>("engine/status"),
    refetchInterval: 5_000,
    staleTime: 3_000,
  });

  const balance = bal?.balance ?? null;
  const change = bal?.change ?? 0;
  const todayPnl = stats?.today_pnl ?? null;
  const winRate = stats?.win_rate ?? null;
  const totalTrades = stats?.total_trades ?? null;
  const todayTrades = stats?.today_trades ?? null;
  const totalPnl = stats?.total_pnl ?? null;

  const chartData = (bal?.history ?? []).map((e) => ({
    time: e.timestamp,
    value: e.balance,
  }));

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPICard
          label="Balance"
          value={balance != null ? fmt$(balance) : null}
          tone={change >= 0 ? "green" : "red"}
          loading={balLoading}
        />
        <KPICard
          label="Today P&L"
          value={todayPnl != null ? fmtSign$(todayPnl) : null}
          tone={todayPnl != null && todayPnl >= 0 ? "green" : "red"}
          loading={statsLoading}
        />
        <KPICard
          label="Win Rate"
          value={winRate != null ? fmtPct(winRate * 100) : null}
          tone="cyan"
          loading={statsLoading}
        />
        <KPICard
          label="Total Trades"
          value={totalTrades != null ? totalTrades.toString() : null}
          tone="cyan"
          loading={statsLoading}
        />
        <KPICard
          label="Markets"
          value={marketStats ? marketStats.total_markets.toString() : null}
          tone="cyan"
          loading={marketsLoading}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <KPICard
          label="Open Positions"
          value={engineStatus ? engineStatus.open_positions.toString() : null}
          tone="amber"
          loading={!engineStatus}
        />
        <KPICard
          label="Engine Daily P&L"
          value={engineStatus ? fmtSign$(engineStatus.daily_pnl) : null}
          tone={engineStatus && engineStatus.daily_pnl >= 0 ? "green" : "red"}
          loading={!engineStatus}
        />
        <KPICard
          label="Daily Trades"
          value={engineStatus ? engineStatus.daily_trades.toString() : null}
          tone="cyan"
          loading={!engineStatus}
        />
        <KPICard
          label={engineStatus?.paused ? "PAUSED" : "Engine Status"}
          value={engineStatus?.paused ? "Loss Limit" : "Active"}
          tone={engineStatus?.paused ? "red" : "green"}
          loading={!engineStatus}
        />
        <KPICard
          label="Bot Uptime"
          value={health?.uptime_seconds != null ? fmtDuration(health.uptime_seconds) : null}
          tone="cyan"
          loading={!health}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Balance</CardTitle>
        </CardHeader>
        <CardContent>
          {chartData.length > 1 ? (
            <BalanceChart data={chartData} />
          ) : (
            <div className="h-[300px] flex items-center justify-center text-text-secondary">
              Not enough data for chart
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="WS Messages/sec"
          value={wsStatus ? wsStatus.messages_per_sec.toFixed(0) : null}
          tone="cyan"
          loading={!wsStatus}
        />
        <KPICard
          label="Tokens Subscribed"
          value={wsStatus ? wsStatus.subscribed_tokens.toString() : null}
          tone="cyan"
          loading={!wsStatus}
        />
        <KPICard
          label="Reconnects"
          value={wsStatus ? wsStatus.reconnect_count.toString() : null}
          tone={wsStatus && wsStatus.reconnect_count > 0 ? "amber" : "cyan"}
          loading={!wsStatus}
        />
        <KPICard
          label="Last Message"
          value={wsStatus?.last_message_at ? relTime(wsStatus.last_message_at) : null}
          tone="cyan"
          loading={!wsStatus}
        />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Surges Detected"
          value={detectorStats ? detectorStats.surges_detected.toString() : null}
          tone="green"
          loading={!detectorStats}
        />
        <KPICard
          label="Trends Fired"
          value={detectorStats ? detectorStats.trends_fired.toString() : null}
          tone="amber"
          loading={!detectorStats}
        />
        <KPICard
          label="Active Windows"
          value={detectorStats ? detectorStats.active_windows.toString() : null}
          tone="cyan"
          loading={!detectorStats}
        />
        <KPICard
          label="Cooldowns"
          value={detectorStats ? detectorStats.cooldowns_active.toString() : null}
          tone={detectorStats && detectorStats.cooldowns_active > 0 ? "amber" : "cyan"}
          loading={!detectorStats}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <KPICard
          label="Today Trades"
          value={todayTrades != null ? todayTrades.toString() : null}
          tone="amber"
          loading={statsLoading}
        />
        <KPICard
          label="Total P&L"
          value={totalPnl != null ? fmtSign$(totalPnl) : null}
          tone={totalPnl != null && totalPnl >= 0 ? "green" : "red"}
          loading={statsLoading}
        />
      </div>
    </div>
  );
}
