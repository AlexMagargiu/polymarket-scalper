export function fmt$(v: number | null | undefined): string {
  return v != null ? `$${v.toFixed(2)}` : "-";
}

export function fmtPct(v: number | null | undefined, decimals = 1): string {
  return v != null ? `${v.toFixed(decimals)}%` : "-";
}

export function fmtSign$(v: number | null | undefined): string {
  if (v == null) return "-";
  return v >= 0 ? `+$${v.toFixed(2)}` : `-$${Math.abs(v).toFixed(2)}`;
}

export function fmtPrice(v: number | null | undefined): string {
  if (v == null) return "-";
  return `${(v * 100).toFixed(0)}c`;
}

export function fmtDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export function relTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtMagnitude(v: number): string {
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}c`;
}
