"use client";
/**
 * Frontend (web) · Task 12 · DhakaMap.tsx - an interactive outline map of Dhaka.
 *
 *  - every thana (or ward) is one shape; hover shows its name, click selects it
 *  - the selected area glows in the theme colour
 *  - an optional pin shows "you are here" (from the Find-my-area button)
 *  - `fillFor` lets other pages colour each area (the danger map in Task 28)
 *
 * Works with the keyboard too: Tab to a shape, Enter to select it.
 */
import { useMemo, useState } from "react";
import { areaName, makeProjection, type Area, type AreaFeature } from "@/lib/areas";
import { usePrefs } from "@/components/PreferencesProvider";

type Props = {
  features: AreaFeature[];
  selected?: string | null;
  onSelect?: (area: Area) => void;
  pin?: { lat: number; lng: number } | null;
  fillFor?: (area: Area) => string | undefined;
};

const WIDTH = 600;

export function DhakaMap({ features, selected, onSelect, pin, fillFor }: Props) {
  const { lang } = usePrefs();
  const [hover, setHover] = useState<{ area: Area; x: number; y: number } | null>(null);
  const map = useMemo(() => makeProjection(features, WIDTH), [features]);
  const pinAt = pin ? map.point(pin.lng, pin.lat) : null;

  return (
    <div className="relative" onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${map.width} ${map.height}`} className="h-auto w-full" role="group" aria-label="Dhaka map">
        {features.map((f) => {
          const area = f.properties;
          const isSelected = area.code === selected;
          return (
            <path
              key={area.code}
              d={map.path(f.geometry)}
              tabIndex={0}
              role="button"
              aria-label={areaName(area, lang)}
              aria-pressed={isSelected}
              onClick={() => onSelect?.(area)}
              onKeyDown={(e) => e.key === "Enter" && onSelect?.(area)}
              onMouseMove={(e) => {
                const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
                setHover({ area, x: e.clientX - box.left, y: e.clientY - box.top });
              }}
              style={{ fill: isSelected ? "var(--primary)" : fillFor?.(area) }}
              className={`cursor-pointer stroke-[1.2] transition-[fill,opacity] duration-300 outline-none focus-visible:stroke-[3] ${
                isSelected
                  ? "stroke-white"
                  : "fill-primary/15 stroke-primary/60 hover:fill-primary/45 focus-visible:fill-primary/45"
              }`}
            />
          );
        })}

        {/* Names of the bigger areas, so the map is readable without hovering */}
        {features.length < 60 &&
          features.map((f) => {
            if ((f.properties.size_km2 ?? 0) < 4) return null;
            const ring = f.geometry.type === "Polygon" ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0];
            const [lng, lat] = ring.reduce(([a, b], [x, y]) => [a + x / ring.length, b + y / ring.length], [0, 0]);
            const [x, y] = map.point(lng, lat);
            return (
              <text key={`label-${f.properties.code}`} x={x} y={y} textAnchor="middle"
                    className="pointer-events-none fill-ink/70 text-[10px] font-medium">
                {areaName(f.properties, lang)}
              </text>
            );
          })}

        {pinAt && (
          <g transform={`translate(${pinAt[0]} ${pinAt[1]})`} className="pointer-events-none">
            <circle r="16" className="fill-accent/30">
              <animate attributeName="r" values="6;20;6" dur="2s" repeatCount="indefinite" />
              <animate attributeName="opacity" values="0.9;0;0.9" dur="2s" repeatCount="indefinite" />
            </circle>
            <circle r="6" className="fill-accent stroke-white" strokeWidth="2" />
          </g>
        )}
      </svg>

      {hover && (
        <div
          className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-full bg-ink px-3 py-1 text-xs font-medium whitespace-nowrap text-bg shadow-lg"
          style={{ left: hover.x, top: hover.y - 10 }}
        >
          {areaName(hover.area, lang)}
          {hover.area.size_km2 ? ` · ${hover.area.size_km2} km²` : ""}
        </div>
      )}
    </div>
  );
}
