"use client";

import { useState, useMemo } from "react";
import type { Position } from "@/lib/types";
import { fmt$, fmtSign$, fmtPrice, relTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronUp, ChevronDown } from "lucide-react";

type SortKey = keyof Position;
type SortDir = "asc" | "desc";

const columns: {
  key: SortKey;
  header: string;
  align: "left" | "right";
}[] = [
  { key: "entry_time", header: "Opened", align: "left" },
  { key: "market_name", header: "Market", align: "left" },
  { key: "direction", header: "Dir", align: "left" },
  { key: "entry_price", header: "Entry", align: "right" },
  { key: "current_price", header: "Current", align: "right" },
  { key: "unrealized_pnl", header: "Unrealized P&L", align: "right" },
  { key: "trailing_peak", header: "Trail Peak", align: "right" },
  { key: "position_size", header: "Size", align: "right" },
];

function truncate(s: string | null, max: number): string {
  if (!s) return "-";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

interface PositionTableProps {
  data: Position[];
  loading?: boolean;
}

export function PositionTable({ data, loading }: PositionTableProps) {
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
        No open positions
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
          {sorted.map((p) => {
            const priceUp = (p.unrealized_pnl ?? 0) > 0;
            const priceDown = (p.unrealized_pnl ?? 0) < 0;

            return (
              <tr
                key={p.id}
                className="border-b border-border-glass/50 hover:bg-surface/50 transition-colors"
              >
                <td className="px-3 py-2 text-text-secondary">
                  {relTime(p.entry_time)}
                </td>
                <td className="px-3 py-2 text-text-primary">
                  {truncate(p.market_name, 40)}
                </td>
                <td className="px-3 py-2">
                  <Badge variant={p.direction === "up" ? "up" : "down"}>
                    {p.direction.toUpperCase()}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-primary">
                  {fmtPrice(p.entry_price)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono font-medium ${
                    priceUp ? "text-status-win" : priceDown ? "text-status-loss" : "text-text-primary"
                  }`}
                >
                  {fmtPrice(p.current_price)}
                </td>
                <td
                  className={`px-3 py-2 text-right font-mono font-medium ${
                    p.unrealized_pnl != null
                      ? p.unrealized_pnl >= 0
                        ? "text-status-win"
                        : "text-status-loss"
                      : "text-text-secondary"
                  }`}
                >
                  {fmtSign$(p.unrealized_pnl)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-primary">
                  {fmtPrice(p.trailing_peak)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-primary">
                  {fmt$(p.position_size)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
