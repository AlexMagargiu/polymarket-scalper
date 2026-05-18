"use client";

import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import { fmtDuration } from "@/lib/format";
import type { WsStatus } from "@/lib/types";

interface HealthResponse {
  status: string;
  uptime_seconds: number;
  version: string;
}

const PAGE_TITLES: Record<string, string> = {
  "/":          "Overview",
  "/markets":   "Markets",
  "/surges":    "Surges",
  "/trades":    "Trades",
  "/positions": "Positions",
  "/backtest":  "Backtest",
  "/settings":  "Settings",
};

export function Header() {
  const pathname = usePathname();
  const title = PAGE_TITLES[pathname] || "Dashboard";

  const { data: wsStatus } = useQuery<WsStatus>({
    queryKey: ["ws-status"],
    queryFn: () => fetchAPI<WsStatus>("ws/status"),
    refetchInterval: 5_000,
    staleTime: 3_000,
  });

  const { data: health } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => fetchAPI<HealthResponse>("health"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const state = wsStatus?.state ?? "disconnected";
  const dotColor = ({
    connected: "bg-status-win",
    reconnecting: "bg-status-open",
    disconnected: "bg-status-loss",
  } as Record<string, string>)[state] ?? "bg-status-loss";
  const stateLabel = ({
    connected: "Connected",
    reconnecting: "Reconnecting...",
    disconnected: "Disconnected",
  } as Record<string, string>)[state] ?? "Disconnected";

  return (
    <header className="flex items-center justify-between h-14 px-4 border-b border-border-glass bg-raised/50 backdrop-blur-sm">
      <h1 className="text-lg font-semibold text-text-primary">{title}</h1>
      <div className="flex items-center gap-3 text-sm text-text-secondary">
        {health?.uptime_seconds != null && (
          <span className="text-xs text-text-muted">
            Up {fmtDuration(health.uptime_seconds)}
          </span>
        )}
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${dotColor}`} />
          <span>{stateLabel}</span>
          {wsStatus?.messages_per_sec != null && state === "connected" && (
            <span className="text-xs text-text-muted ml-1">
              {wsStatus.messages_per_sec.toFixed(0)} msg/s
            </span>
          )}
        </div>
      </div>
    </header>
  );
}
