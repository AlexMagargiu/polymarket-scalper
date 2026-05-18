"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import type { Position, Trade } from "@/lib/types";
import { PositionTable } from "@/components/data/position-table";
import { TradeTable } from "@/components/data/trade-table";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Tab = "open" | "closed";

export default function PositionsPage() {
  const [tab, setTab] = useState<Tab>("open");

  const { data: openPositions = [], isLoading: openLoading } = useQuery<
    Position[]
  >({
    queryKey: ["positions-open"],
    queryFn: () => fetchAPI<Position[]>("positions"),
    refetchInterval: 2_000,
    staleTime: 1_000,
    enabled: tab === "open",
  });

  const { data: closedTrades = [], isLoading: closedLoading } = useQuery<
    Trade[]
  >({
    queryKey: ["positions-closed"],
    queryFn: () => fetchAPI<Trade[]>("positions/history?limit=50"),
    refetchInterval: 30_000,
    staleTime: 15_000,
    enabled: tab === "closed",
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            Positions
            <div className="flex gap-1">
              <Button
                variant={tab === "open" ? "default" : "outline"}
                size="sm"
                onClick={() => setTab("open")}
              >
                Open{!openLoading && ` (${openPositions.length})`}
              </Button>
              <Button
                variant={tab === "closed" ? "default" : "outline"}
                size="sm"
                onClick={() => setTab("closed")}
              >
                Closed
              </Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {tab === "open" ? (
            <PositionTable data={openPositions} loading={openLoading} />
          ) : (
            <TradeTable data={closedTrades} loading={closedLoading} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
