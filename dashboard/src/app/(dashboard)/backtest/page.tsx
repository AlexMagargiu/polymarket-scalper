"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { fetchAPI, postAPI } from "@/lib/api";
import { KPICard } from "@/components/data/kpi-card";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fmt$, fmtSign$, fmtPct, fmtDuration, fmtPrice } from "@/lib/format";
import type { BacktestStats, SimulationResult } from "@/lib/types";

function downloadCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  const keys = Object.keys(data[0]);
  const csv = [
    keys.join(","),
    ...data.map((row) =>
      keys.map((k) => {
        const v = row[k];
        if (v == null) return "";
        const s = String(v);
        return s.includes(",") || s.includes('"') || s.includes("\n")
          ? `"${s.replace(/"/g, '""')}"`
          : s;
      }).join(",")
    ),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BacktestPage() {
  const { data: stats, isLoading } = useQuery<BacktestStats>({
    queryKey: ["backtest-stats"],
    queryFn: () => fetchAPI<BacktestStats>("backtest/stats"),
    staleTime: 60_000,
  });

  const [threshold, setThreshold] = useState("0.10");
  const [trailingStop, setTrailingStop] = useState("0.10");
  const [takeProfit, setTakeProfit] = useState("0.90");

  const simMutation = useMutation({
    mutationFn: (params: { threshold: number; trailing_stop: number; take_profit: number }) =>
      postAPI<SimulationResult>("backtest/simulate", params),
  });

  const runSimulation = () => {
    simMutation.mutate({
      threshold: parseFloat(threshold) || 0.10,
      trailing_stop: parseFloat(trailingStop) || 0.10,
      take_profit: parseFloat(takeProfit) || 0.90,
    });
  };

  const exportTradesMutation = useMutation({
    mutationFn: () => fetchAPI<Record<string, unknown>[]>("backtest/export/trades"),
    onSuccess: (data) => downloadCSV(data, "trades.csv"),
  });

  const exportSurgesMutation = useMutation({
    mutationFn: () => fetchAPI<Record<string, unknown>[]>("backtest/export/surges"),
    onSuccess: (data) => downloadCSV(data, "surges.csv"),
  });

  const winRate = stats?.win_rate ?? null;
  const profitFactor = stats?.profit_factor ?? null;
  const sim = simMutation.data;

  const pnlByMarketEntries = stats?.pnl_by_market
    ? Object.entries(stats.pnl_by_market)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
        .slice(0, 10)
    : [];

  const tradesPerDayEntries = stats?.trades_per_day
    ? Object.entries(stats.trades_per_day).sort((a, b) => b[0].localeCompare(a[0]))
    : [];

  return (
    <div className="space-y-6">
      {/* KPI Row 1 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Win Rate"
          value={winRate != null ? fmtPct(winRate * 100) : null}
          tone={winRate != null && winRate >= 0.5 ? "green" : "red"}
          loading={isLoading}
        />
        <KPICard
          label="Profit Factor"
          value={profitFactor != null ? profitFactor.toFixed(2) : null}
          tone={profitFactor != null && profitFactor >= 1 ? "green" : "red"}
          loading={isLoading}
        />
        <KPICard
          label="Max Drawdown"
          value={stats?.max_drawdown != null ? fmt$(stats.max_drawdown) : null}
          tone="red"
          loading={isLoading}
        />
        <KPICard
          label="Avg Hold"
          value={stats?.avg_hold_seconds != null ? fmtDuration(stats.avg_hold_seconds) : null}
          tone="cyan"
          loading={isLoading}
        />
      </div>

      {/* KPI Row 2 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Total P&L"
          value={stats?.total_pnl != null ? fmtSign$(stats.total_pnl) : null}
          tone={stats?.total_pnl != null && stats.total_pnl >= 0 ? "green" : "red"}
          loading={isLoading}
        />
        <KPICard
          label="Avg Win"
          value={stats?.avg_win != null ? fmtSign$(stats.avg_win) : null}
          tone="green"
          loading={isLoading}
        />
        <KPICard
          label="Avg Loss"
          value={stats?.avg_loss != null ? fmtSign$(stats.avg_loss) : null}
          tone="red"
          loading={isLoading}
        />
        <KPICard
          label="Avg MFE"
          value={stats?.avg_mfe != null ? fmtPrice(stats.avg_mfe) : null}
          tone="cyan"
          loading={isLoading}
        />
      </div>

      {/* Surge Conversion */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <KPICard
          label="Total Surges"
          value={stats?.total_surges != null ? stats.total_surges.toString() : null}
          tone="cyan"
          loading={isLoading}
        />
        <KPICard
          label="Traded Surges"
          value={stats?.traded_surges != null ? stats.traded_surges.toString() : null}
          tone="amber"
          loading={isLoading}
        />
        <KPICard
          label="Conversion Rate"
          value={stats?.surge_conversion_rate != null ? fmtPct(stats.surge_conversion_rate * 100) : null}
          tone="cyan"
          loading={isLoading}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* P&L by Market */}
        <Card>
          <CardHeader>
            <CardTitle>P&L by Market (Top 10)</CardTitle>
          </CardHeader>
          <CardContent>
            {pnlByMarketEntries.length > 0 ? (
              <div className="space-y-2">
                {pnlByMarketEntries.map(([name, pnl]) => (
                  <div key={name} className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary truncate max-w-[70%]">{name}</span>
                    <span className={`font-mono tabular-nums ${pnl >= 0 ? "text-status-win" : "text-status-loss"}`}>
                      {fmtSign$(pnl)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-text-secondary text-sm">No trade data</p>
            )}
          </CardContent>
        </Card>

        {/* Trades per Day */}
        <Card>
          <CardHeader>
            <CardTitle>Trades per Day</CardTitle>
          </CardHeader>
          <CardContent>
            {tradesPerDayEntries.length > 0 ? (
              <div className="space-y-2 max-h-[300px] overflow-y-auto">
                {tradesPerDayEntries.map(([date, count]) => (
                  <div key={date} className="flex items-center justify-between text-sm">
                    <span className="text-text-secondary font-mono">{date}</span>
                    <span className="font-mono tabular-nums text-text-primary">{count}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-text-secondary text-sm">No trade data</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Parameter Simulation */}
      <Card>
        <CardHeader>
          <CardTitle>Parameter Simulation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="text-xs text-text-secondary block mb-1">Surge Threshold</label>
                <Input
                  type="number"
                  step="0.01"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary block mb-1">Trailing Stop</label>
                <Input
                  type="number"
                  step="0.01"
                  value={trailingStop}
                  onChange={(e) => setTrailingStop(e.target.value)}
                />
              </div>
              <div>
                <label className="text-xs text-text-secondary block mb-1">Take Profit</label>
                <Input
                  type="number"
                  step="0.01"
                  value={takeProfit}
                  onChange={(e) => setTakeProfit(e.target.value)}
                />
              </div>
            </div>

            <Button onClick={runSimulation} disabled={simMutation.isPending}>
              {simMutation.isPending ? "Simulating..." : "Run Simulation"}
            </Button>

            {sim && (
              <div className="grid grid-cols-2 gap-4 mt-4">
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-text-secondary">Original</h4>
                  <div className="text-sm space-y-1">
                    <div className="flex justify-between">
                      <span className="text-text-secondary">P&L</span>
                      <span className={`font-mono ${sim.original.total_pnl >= 0 ? "text-status-win" : "text-status-loss"}`}>
                        {fmtSign$(sim.original.total_pnl)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-secondary">Win Rate</span>
                      <span className="font-mono">{fmtPct(sim.original.win_rate * 100)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-secondary">Trades</span>
                      <span className="font-mono">{sim.original.total_trades}</span>
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <h4 className="text-sm font-semibold text-accent-primary">Simulated</h4>
                  <div className="text-sm space-y-1">
                    <div className="flex justify-between">
                      <span className="text-text-secondary">P&L</span>
                      <span className={`font-mono ${sim.simulated.total_pnl >= 0 ? "text-status-win" : "text-status-loss"}`}>
                        {fmtSign$(sim.simulated.total_pnl)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-secondary">Win Rate</span>
                      <span className="font-mono">{fmtPct(sim.simulated.win_rate * 100)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-secondary">Trades</span>
                      <span className="font-mono">{sim.simulated.total_trades}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {simMutation.isError && (
              <p className="text-status-loss text-sm">Simulation failed. Check that the bot is running.</p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Export */}
      <div className="flex gap-4">
        <Button
          variant="outline"
          onClick={() => exportTradesMutation.mutate()}
          disabled={exportTradesMutation.isPending}
        >
          {exportTradesMutation.isPending ? "Exporting..." : "Export Trades CSV"}
        </Button>
        <Button
          variant="outline"
          onClick={() => exportSurgesMutation.mutate()}
          disabled={exportSurgesMutation.isPending}
        >
          {exportSurgesMutation.isPending ? "Exporting..." : "Export Surges CSV"}
        </Button>
      </div>
    </div>
  );
}
