"use client";
/**
 * Frontend (web) · Task 26 · ColumnChart.tsx - a small, calm column chart in plain SVG.
 *
 * Chart rules we follow (from the project's data-visualisation guide):
 *  - one series = one colour (the theme's primary); the highlighted column (e.g. the busiest hour)
 *    is the strong step of the same colour - never a different hue
 *  - columns at most 24 px wide, 4 px rounded tops, square at the baseline, a 2 px gap between them
 *  - hairline gridlines, recessive axis text; text never uses the data colour
 *  - a value label only on the highlighted column; every value is in the hover tooltip
 *    and in a hidden table for screen readers
 */
import { useId, useState } from "react";

type Props = {
  values: number[];
  labels: string[]; // one per column (shown every `labelEvery` columns)
  highlight?: number | null; // index of the column to emphasise
  labelEvery?: number;
  height?: number;
  unit: string; // e.g. "thefts" - used in the tooltip and the table
  title: string; // for screen readers
};

const W = 640;
const PAD = { top: 22, right: 8, bottom: 26, left: 30 };

function niceMax(max: number) {
  if (max <= 4) return 4;
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  return Math.ceil(max / step) * step;
}

export function ColumnChart({ values, labels, highlight = null, labelEvery = 1, height = 200, unit, title }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const id = useId();
  const max = niceMax(Math.max(...values, 0));
  const innerW = W - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / values.length;
  const barW = Math.min(24, slot - 2); // 2 px gap between neighbours
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const ticks = [0, max / 2, max];

  function column(i: number, v: number) {
    const x = PAD.left + i * slot + (slot - barW) / 2;
    const top = y(v);
    const base = PAD.top + innerH;
    const r = Math.min(4, (base - top) / 2, barW / 2);
    if (base - top < 0.5) return "";
    return `M${x},${base}V${top + r}Q${x},${top} ${x + r},${top}H${x + barW - r}Q${x + barW},${top} ${x + barW},${top + r}V${base}Z`;
  }

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${height}`} className="h-auto w-full" role="img" aria-labelledby={`${id}-t`}>
        <title id={`${id}-t`}>{title}</title>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(tick)} y2={y(tick)} stroke="var(--line)" strokeWidth="1" />
            <text x={PAD.left - 6} y={y(tick) + 4} textAnchor="end" className="fill-ink-soft text-[10px]">{Math.round(tick)}</text>
          </g>
        ))}
        {values.map((v, i) => (
          <g key={i}>
            <path d={column(i, v)} style={{ fill: "var(--primary)", opacity: highlight === null || i === highlight ? 1 : 0.45 }}
                  className="transition-opacity" />
            {/* a hit area as tall as the chart, so even an empty hour can be hovered */}
            <rect x={PAD.left + i * slot} y={PAD.top} width={slot} height={innerH} fill="transparent"
                  onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}
                  tabIndex={0} onFocus={() => setHover(i)} onBlur={() => setHover(null)}
                  aria-label={`${labels[i]}: ${v} ${unit}`} />
            {i % labelEvery === 0 && (
              <text x={PAD.left + i * slot + slot / 2} y={height - 8} textAnchor="middle" className="fill-ink-soft text-[10px]">
                {labels[i]}
              </text>
            )}
          </g>
        ))}
        {highlight !== null && values[highlight] > 0 && (
          <text x={PAD.left + highlight * slot + slot / 2} y={y(values[highlight]) - 6} textAnchor="middle"
                className="fill-ink text-[11px] font-semibold">{values[highlight]}</text>
        )}
      </svg>

      {hover !== null && (
        <div className="pointer-events-none absolute -translate-x-1/2 rounded-lg bg-ink px-2.5 py-1.5 text-xs whitespace-nowrap text-bg shadow-lg"
             style={{ left: `${((PAD.left + hover * slot + slot / 2) / W) * 100}%`, top: 0 }}>
          <strong>{values[hover]}</strong> {unit} · {labels[hover]}
        </div>
      )}

      {/* The same numbers as a table, for screen readers */}
      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>{values.map((v, i) => <tr key={i}><th scope="row">{labels[i]}</th><td>{v}</td></tr>)}</tbody>
      </table>
    </div>
  );
}
