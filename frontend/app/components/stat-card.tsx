import { InfoHint } from "@/app/components/info-hint";

const ACCENTS = {
  default: {
    card: "border-neutral-800 bg-neutral-900/60",
    label: "text-neutral-500",
    value: "text-neutral-100",
  },
  good: {
    card: "border-emerald-500/25 bg-emerald-500/5",
    label: "text-emerald-300/80",
    value: "text-emerald-200",
  },
  warn: {
    card: "border-amber-500/25 bg-amber-500/5",
    label: "text-amber-300/80",
    value: "text-amber-200",
  },
  info: {
    card: "border-sky-500/25 bg-sky-500/5",
    label: "text-sky-300/80",
    value: "text-sky-200",
  },
} as const;

export type StatCardAccent = keyof typeof ACCENTS;

export function StatCard({
  label,
  value,
  hint,
  info,
  accent = "default",
}: {
  label: string;
  value: string;
  hint?: string;
  info?: string;
  accent?: StatCardAccent;
}) {
  const styles = ACCENTS[accent];
  return (
    <div className={`rounded-xl border p-4 ${styles.card}`}>
      <div className="flex items-center">
        <p className={`text-xs uppercase tracking-wider ${styles.label}`}>{label}</p>
        {info ? <InfoHint title={label} text={info} /> : null}
      </div>
      <p className={`mt-2 text-xl font-medium tabular-nums ${styles.value}`}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-neutral-500">{hint}</p> : null}
    </div>
  );
}
