"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import type { Trade } from "@/lib/types";
import { TradeTable } from "@/components/data/trade-table";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 50;

export default function TradesPage() {
  const [page, setPage] = useState(0);

  const { data: trades = [], isLoading } = useQuery<Trade[]>({
    queryKey: ["trades", page],
    queryFn: () =>
      fetchAPI<Trade[]>(`trades?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            Trades{!isLoading && ` (page ${page + 1})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <TradeTable data={trades} loading={isLoading} />
          <div className="flex items-center justify-between mt-4 pt-4 border-t border-border-glass">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            <span className="text-xs text-text-secondary">
              Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + trades.length}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={trades.length < PAGE_SIZE}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
