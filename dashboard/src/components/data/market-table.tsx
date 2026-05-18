"use client";

import { useState, useMemo } from "react";
import type { Market } from "@/lib/types";
import { fmt$ } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ChevronUp, ChevronDown } from "lucide-react";

type SortKey = keyof Market;
type SortDir = "asc" | "desc";

const columns: {
  key: SortKey;
  header: string;
  align: "left" | "right";
}[] = [
  { key: "name", header: "Market", align: "left" },
  { key: "category", header: "Category", align: "left" },
  { key: "volume_24h", header: "24h Volume", align: "right" },
  { key: "token_id_yes", header: "YES Token", align: "left" },
  { key: "token_id_no", header: "NO Token", align: "left" },
];

function truncate(s: string | null, max: number): string {
  if (!s) return "-";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

interface MarketTableProps {
  data: Market[];
  loading?: boolean;
}

export function MarketTable({ data, loading }: MarketTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("volume_24h");
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
        No markets found
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
          {sorted.map((m) => (
            <tr
              key={m.condition_id}
              className="border-b border-border-glass/50 hover:bg-surface/50 transition-colors"
            >
              <td className="px-3 py-2 text-text-primary">
                {truncate(m.name, 60)}
              </td>
              <td className="px-3 py-2">
                <Badge variant="default">{m.category || "—"}</Badge>
              </td>
              <td className="px-3 py-2 text-right font-mono text-text-primary">
                {fmt$(m.volume_24h)}
              </td>
              <td className="px-3 py-2 font-mono text-text-secondary text-xs">
                {truncate(m.token_id_yes, 12)}
              </td>
              <td className="px-3 py-2 font-mono text-text-secondary text-xs">
                {truncate(m.token_id_no, 12)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
