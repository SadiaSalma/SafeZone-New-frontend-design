"use client";
/**
 * Frontend (web) · Task 26 · BarList.tsx - "what is stolen most" as horizontal bars.
 * One colour (the theme's primary), 4 px rounded ends, the value at the end of each bar,
 * the name on the left in normal text colour. Built from plain HTML, so it reads well
 * in both languages and on phones.
 */
export function BarList({ rows, unit }: { rows: { label: string; value: number }[]; unit: string }) {
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => (
        <li key={row.label} className="grid grid-cols-[minmax(0,9rem)_1fr] items-center gap-3 text-sm">
          <span className="truncate text-ink">{row.label}</span>
          <span className="flex items-center gap-2">
            <span className="h-3 rounded-r-[4px] bg-primary" style={{ width: `${Math.max(3, (row.value / max) * 100)}%` }}
                  aria-hidden />
            <span className="shrink-0 text-xs text-ink-soft">{row.value} <span className="sr-only">{unit}</span></span>
          </span>
        </li>
      ))}
    </ul>
  );
}
