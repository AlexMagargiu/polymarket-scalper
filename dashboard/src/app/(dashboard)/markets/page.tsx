"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import type { Market, MarketStats } from "@/lib/types";
import { MarketTable } from "@/components/data/market-table";
import { KPICard } from "@/components/data/kpi-card";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { fmt$ } from "@/lib/format";

export default function MarketsPage() {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");

  const { data: markets, isLoading: marketsLoading } = useQuery<Market[]>({
    queryKey: ["markets"],
    queryFn: () => fetchAPI<Market[]>("markets"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: stats, isLoading: statsLoading } = useQuery<MarketStats>({
    queryKey: ["market-stats"],
    queryFn: () => fetchAPI<MarketStats>("markets/stats"),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const categoryKeys = useMemo(() => {
    if (!stats?.categories) return [];
    return Object.keys(stats.categories).sort();
  }, [stats]);

  const filtered = useMemo(() => {
    let result = markets ?? [];
    if (search) {
      const s = search.toLowerCase();
      result = result.filter((m) => m.name.toLowerCase().includes(s));
    }
    if (category) {
      result = result.filter((m) => m.category === category);
    }
    return result;
  }, [markets, search, category]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <KPICard
          label="Markets Monitored"
          value={stats ? stats.total_markets.toString() : null}
          tone="cyan"
          loading={statsLoading}
        />
        <KPICard
          label="Total 24h Volume"
          value={stats ? fmt$(stats.total_volume) : null}
          tone="green"
          loading={statsLoading}
        />
        <KPICard
          label="Tokens Subscribed"
          value={stats ? stats.total_tokens.toString() : null}
          tone="cyan"
          loading={statsLoading}
        />
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <Input
          placeholder="Search markets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setCategory("")}
            className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              category === ""
                ? "bg-accent-primary/20 text-accent-primary"
                : "bg-surface text-text-secondary hover:text-text-primary"
            }`}
          >
            All
          </button>
          {categoryKeys.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat === category ? "" : cat)}
              className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                category === cat
                  ? "bg-accent-primary/20 text-accent-primary"
                  : "bg-surface text-text-secondary hover:text-text-primary"
              }`}
            >
              {cat || "Uncategorized"}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            {filtered.length} market{filtered.length !== 1 ? "s" : ""}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <MarketTable data={filtered} loading={marketsLoading} />
        </CardContent>
      </Card>
    </div>
  );
}
