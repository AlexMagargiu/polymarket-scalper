"use client";

import { useState, useMemo } from "react";
import type { Trade } from "@/lib/types";
import { fmt$, fmtSign$, fmtPrice, fmtMagnitude, relTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronUp, ChevronDown } from "lucide-react";

type SortKey = keyof Trade;
type SortDir = "asc" | "desc";

const columns: {
  key: SortKey;
  header: string;
  align: "left" | "right";
}[] = [
  { key: "entry_time", header: "Time", align: "left" },
  { key: "market_name", header: "Market", align: "left" },
  { key: "direction", header: "Dir", align: "left" },
  { key: "entry_price", header: "Entry", align: "right" },
  { key: "exit_price", header: "Exit", align: "right" },
  { key: "position_size", header: "Size", align: "right" },
  { key: "exit_reason", header: "Reason", align: "left" },
  { key: "max_favorable_excursion", header: "MFE", align: "right" },
  { key: "entry_fee", header: "Fees", align: "right" },
  { key: "pnl", header: "P&L", align: "right" },
];

function truncate(s: string | null, max: number): string {
  if (!s) return "-";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

interface TradeTableProps {
  data: Trade[];
  loading?: boolean;
  onTradeClick?: (trade: Trade) => void;
}

export function TradeTable({ data, loading, onTradeClick }: TradeTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("entry_time");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    return [...data].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="text-center py-12 text-text-secondary">
        No trades found
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border-glass text-text-secondary">
            {columns.map((col) => (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                className={`cursor-pointer select-none px-3 py-2 font-medium ${col.align === "right" ? "text-right" : "text-left"}`}
              >
                <span className="inline-flex items-center gap-1">
                  {col.header}
                  {sortKey === col.key &&
                    (sortDir === "asc" ? (
                      <ChevronUp className="h-3 w-3" />
                    ) : (
                      <ChevronDown className="h-3 w-3" />
                    ))}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((t) => (
            <tr
              key={t.id}
              onClick={() => onTradeClick?.(t)}
              className={`border-b border-border-glass/50 hover:bg-surface/50 transition-colors ${onTradeClick ? "cursor-pointer" : ""}`}
            >
              <td className="px-3 py-2 text-text-secondary">
                {relTime(t.entry_time)}
              </td>
              <td className="px-3 py-2 text-text-primary">
                {truncate(t.market_name, 40)}
              </td>
              <td className="px-3 py-2">
                <Badge variant={t.direction === "up" ? "up" : "down"}>
                  {t.direction.toUpperCase()}
                </Badge>
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmtPrice(t.entry_price)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmtPrice(t.exit_price)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmt$(t.position_size)}
              </td>
              <td className="px-3 py-2">
                {t.exit_reason ? (
                  <Badge variant="muted">{t.exit_reason}</Badge>
                ) : (
                  "-"
                )}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {t.max_favorable_excursion != null
                  ? fmtMagnitude(t.max_favorable_excursion)
                  : "-"}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-secondary">
                {fmt$((t.entry_fee ?? 0) + (t.exit_fee ?? 0))}
              </td>
              <td
                className={`px-3 py-2 text-right font-mono font-medium ${
                  t.pnl != null
                    ? t.pnl >= 0
                      ? "text-status-win"
                      : "text-status-loss"
                    : "text-text-secondary"
                }`}
              >
                {fmtSign$(t.pnl)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
