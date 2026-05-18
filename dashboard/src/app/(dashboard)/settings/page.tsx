"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import { relTime } from "@/lib/format";
import type { Alert, AlertsStatus } from "@/lib/types";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Send, CheckCircle, XCircle } from "lucide-react";

const CONFIG = {
  "Surge Threshold": "10c",
  "Detection Window": "30-60s",
  "Trailing Stop": "10c reversal",
  "Take Profit": "90c hard exit",
  "Position Size": "$25",
  "Starting Balance": "$5,000",
  "Max Concurrent": "10 positions",
  "Max Per Market": "3 positions",
  "Daily Loss Limit": "$500",
  "Max Daily Trades": "100",
  "Fee Rate": "2% (taker, both sides)",
  "Min Volume 24h": "$10,000",
  "Direction": "Bidirectional (up + down)",
  "Overnight": "Hold, exit on reversal",
};

export default function SettingsPage() {
  const queryClient = useQueryClient();

  const { data: alertsStatus } = useQuery<AlertsStatus>({
    queryKey: ["alerts-status"],
    queryFn: () => fetchAPI<AlertsStatus>("alerts/status"),
    refetchInterval: 30_000,
  });

  const { data: alerts } = useQuery<Alert[]>({
    queryKey: ["alerts"],
    queryFn: () => fetchAPI<Alert[]>("alerts"),
    refetchInterval: 10_000,
  });

  const testMutation = useMutation({
    mutationFn: () =>
      fetch("/api/alerts/test", { method: "POST" }).then((r) => r.json()),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  return (
    <div className="space-y-6">
      {/* Trading Parameters */}
      <div className="rounded-lg border border-border-glass bg-raised p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-4">
          Trading Parameters
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {Object.entries(CONFIG).map(([key, val]) => (
            <div
              key={key}
              className="flex justify-between items-center py-2 px-3 rounded bg-surface"
            >
              <span className="text-sm text-text-secondary">{key}</span>
              <span className="text-sm font-mono text-text-primary">{val}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Telegram Status */}
      <Card>
        <CardHeader>
          <CardTitle>Telegram Alerts</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Badge variant={alertsStatus?.enabled ? "win" : "loss"}>
                {alertsStatus?.enabled ? "Connected" : "Disabled"}
              </Badge>
              {alertsStatus?.chat_id && (
                <span className="text-sm text-muted-foreground">
                  Chat: {alertsStatus.chat_id}
                </span>
              )}
            </div>
            <Button
              size="sm"
              onClick={() => testMutation.mutate()}
              disabled={testMutation.isPending || !alertsStatus?.enabled}
            >
              <Send className="h-4 w-4" />
              {testMutation.isPending ? "Sending..." : "Send Test"}
            </Button>
          </div>
          {testMutation.data && (
            <div
              className={`mt-3 text-sm ${testMutation.data.success ? "text-status-win" : "text-status-loss"}`}
            >
              {testMutation.data.success
                ? "Test alert sent successfully"
                : "Failed to send test alert"}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Recent Alerts */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Alerts ({alerts?.length ?? 0})</CardTitle>
        </CardHeader>
        <CardContent>
          {!alerts || alerts.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No alerts sent yet
            </div>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {alerts.map((a, i) => (
                <div
                  key={`${a.timestamp}-${i}`}
                  className="flex items-center justify-between py-2 px-3 rounded bg-surface/50 border border-border-glass/50"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {a.sent ? (
                      <CheckCircle className="h-4 w-4 shrink-0 text-status-win" />
                    ) : (
                      <XCircle className="h-4 w-4 shrink-0 text-status-loss" />
                    )}
                    <Badge variant="muted">{a.type}</Badge>
                    <span className="text-sm text-foreground truncate">
                      {a.message}
                    </span>
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap ml-4">
                    {relTime(a.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
