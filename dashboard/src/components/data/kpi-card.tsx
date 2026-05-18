import { Skeleton } from "@/components/ui/skeleton";

export function KPICard({
  label,
  value,
  tone,
  loading,
  children,
}: {
  label: string;
  value: string | null;
  tone: "green" | "red" | "cyan" | "amber";
  loading: boolean;
  children?: React.ReactNode;
}) {
  const toneClass = {
    green: "bg-tone-green",
    red: "bg-tone-red",
    cyan: "bg-tone-cyan",
    amber: "bg-tone-amber",
  }[tone];

  return (
    <div className={`rounded-lg border border-border-glass p-4 ${toneClass}`}>
      {loading ? (
        <Skeleton className="h-8 w-24 mb-1" />
      ) : (
        <div className="text-2xl font-bold font-mono tabular-nums text-text-primary">
          {value}
        </div>
      )}
      <div className="text-xs uppercase tracking-wider text-text-secondary mt-1">
        {label}
      </div>
      {children}
    </div>
  );
}
