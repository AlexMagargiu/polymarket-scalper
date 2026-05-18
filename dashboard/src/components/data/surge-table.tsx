"use client";

import { useState, useMemo } from "react";
import type { Surge } from "@/lib/types";
import { fmtMagnitude, fmtDuration, fmtPrice, relTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronUp, ChevronDown } from "lucide-react";

type SortKey = keyof Surge;
type SortDir = "asc" | "desc";

const columns: {
  key: SortKey;
  header: string;
  align: "left" | "right";
}[] = [
  { key: "timestamp", header: "Time", align: "left" },
  { key: "market_name", header: "Market", align: "left" },
  { key: "direction", header: "Dir", align: "left" },
  { key: "magnitude", header: "Magnitude", align: "right" },
  { key: "window_seconds", header: "Window", align: "right" },
  { key: "price_at_detection", header: "Price", align: "right" },
  { key: "traded", header: "Traded", align: "left" },
];

function truncate(s: string | null, max: number): string {
  if (!s) return "-";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

interface SurgeTableProps {
  data: Surge[];
  loading?: boolean;
}

export function SurgeTable({ data, loading }: SurgeTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
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
        No surges detected yet
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
          {sorted.map((s) => (
            <tr
              key={s.id}
              className="border-b border-border-glass/50 hover:bg-surface/50 transition-colors"
            >
              <td className="px-3 py-2 text-text-secondary">
                {relTime(s.timestamp)}
              </td>
              <td className="px-3 py-2 text-text-primary">
                {truncate(s.market_name, 40)}
              </td>
              <td className="px-3 py-2">
                <Badge variant={s.direction === "up" ? "up" : "down"}>
                  {s.direction.toUpperCase()}
                </Badge>
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmtMagnitude(s.magnitude)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmtDuration(s.window_seconds)}
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmtPrice(s.price_at_detection)}
              </td>
              <td className="px-3 py-2">
                <Badge variant={s.traded ? "win" : "muted"}>
                  {s.traded ? "Yes" : "No"}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
