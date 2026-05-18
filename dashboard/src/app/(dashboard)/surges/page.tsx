"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAPI } from "@/lib/api";
import type { Surge } from "@/lib/types";
import { SurgeTable } from "@/components/data/surge-table";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { fmtMagnitude, relTime } from "@/lib/format";

const PAGE_SIZE = 50;

export default function SurgesPage() {
  const [page, setPage] = useState(0);

  const { data: surges = [], isLoading } = useQuery<Surge[]>({
    queryKey: ["surges", page],
    queryFn: () =>
      fetchAPI<Surge[]>(`surges?limit=${PAGE_SIZE}&offset=${page * PAGE_SIZE}`),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const { data: liveSurges = [] } = useQuery<Surge[]>({
    queryKey: ["surges-live"],
    queryFn: () => fetchAPI<Surge[]>("surges/live"),
    refetchInterval: 2_000,
    staleTime: 1_000,
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${liveSurges.length > 0 ? "bg-status-win animate-pulse" : "bg-text-muted"}`} />
            Live Surges ({liveSurges.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {liveSurges.length === 0 ? (
            <div className="text-center py-8 text-text-secondary">
              No live surges detected yet. Waiting for price movements...
            </div>
          ) : (
            <div className="space-y-2 max-h-[300px] overflow-y-auto">
              {liveSurges.map((s, i) => (
                <div
                  key={`${s.timestamp}-${i}`}
                  className="flex items-center justify-between py-2 px-3 rounded bg-surface/50 border border-border-glass/50"
                >
                  <div className="flex items-center gap-3">
                    <Badge variant={s.direction === "up" ? "up" : "down"}>
                      {s.direction === "up" ? "↑" : "↓"}
                    </Badge>
                    <span className="text-sm text-text-primary truncate max-w-[300px]">
                      {s.market_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm">
                    <span className="font-mono text-text-primary">
                      {fmtMagnitude(s.magnitude)}
                    </span>
                    <span className="text-text-secondary">
                      {relTime(s.timestamp)}
                    </span>
                    <Badge variant={s.traded ? "win" : "muted"}>
                      {s.traded ? "Traded" : "Skipped"}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            Surges{!isLoading && ` (page ${page + 1})`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <SurgeTable data={surges} loading={isLoading} />
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
              Showing {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + surges.length}
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => p + 1)}
              disabled={surges.length < PAGE_SIZE}
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
