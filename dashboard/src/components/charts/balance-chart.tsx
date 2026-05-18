"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type UTCTimestamp,
} from "lightweight-charts";

interface BalanceChartProps {
  data: { time: string; value: number }[];
  height?: number;
  color?: string;
}

function toUTC(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function toChartData(raw: { time: string; value: number }[]) {
  return raw
    .map((d) => ({ time: toUTC(d.time), value: d.value }))
    .sort((a, b) => (a.time as number) - (b.time as number));
}

export function BalanceChart({
  data,
  height = 300,
  color = "#4DA3FF",
}: BalanceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#16213A" },
        textColor: "#8B9FC0",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
    });

    seriesRef.current = chart.addSeries(AreaSeries, {
      lineColor: color,
      lineWidth: 2,
      topColor: color + "66",
      bottomColor: color + "00",
    });
    chartRef.current = chart;

    const ro = new ResizeObserver((entries) => {
      const { width } = entries[0].contentRect;
      chart.applyOptions({ width });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [height, color]);

  useEffect(() => {
    if (!seriesRef.current) return;
    seriesRef.current.setData(toChartData(data));
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />;
}
