/**
 * Frontend (web) · Task 12 · areas.ts - the shapes of the area data the backend sends,
 * plus a tiny helper that turns map shapes (longitude/latitude) into SVG drawing paths.
 *
 * Why SVG and not a map library here? The thana/ward outlines are only ~150 shapes,
 * so drawing them ourselves is fast, works offline, and can be coloured freely
 * (later: the danger map in Task 28 colours each thana by its score).
 */
export type AreaType = "thana" | "ward";

export type Area = {
  code: string;
  name_en: string;
  name_bn: string;
  type: AreaType;
  size_km2: number | null;
};

export type PoliceStation = {
  code: string;
  name_en: string;
  name_bn: string;
  phone: string;
  lat: number;
  lng: number;
  distance_m?: number;
};

export type AreaDetail = Area & {
  wards?: Area[];
  thanas?: Area[];
  police_stations?: PoliceStation[];
};

export type Lookup = {
  lat: number;
  lng: number;
  inside_dhaka: boolean;
  thana: Area | null;
  ward: Area | null;
  nearest_police_stations: PoliceStation[];
};

type Ring = number[][];
type Geometry = { type: "Polygon"; coordinates: Ring[] } | { type: "MultiPolygon"; coordinates: Ring[][] };
export type AreaFeature = { type: "Feature"; geometry: Geometry; properties: Area };
export type AreaShapes = { type: "FeatureCollection"; features: AreaFeature[] };

/** Pick the name in the visitor's language. */
export function areaName(item: { name_en: string; name_bn: string }, lang: "en" | "bn") {
  return lang === "bn" && item.name_bn ? item.name_bn : item.name_en;
}

/** 850 -> "850 m", 2300 -> "2.3 km" */
export function distanceText(metres: number) {
  return metres < 1000 ? `${Math.round(metres)} m` : `${(metres / 1000).toFixed(1)} km`;
}

/**
 * A "projection" squeezes the round Earth onto a flat picture.
 * Near Dhaka, 1 degree of longitude is shorter than 1 degree of latitude
 * (by cos(23.8°) ≈ 0.915), so we shrink x by that much - otherwise the city looks stretched.
 */
export function makeProjection(features: AreaFeature[], width: number) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const squeeze = Math.cos((23.8 * Math.PI) / 180);
  for (const f of features) {
    for (const [lng, lat] of allPoints(f.geometry)) {
      minX = Math.min(minX, lng * squeeze);
      maxX = Math.max(maxX, lng * squeeze);
      minY = Math.min(minY, lat);
      maxY = Math.max(maxY, lat);
    }
  }
  const scale = width / (maxX - minX);
  const height = (maxY - minY) * scale;
  const point = (lng: number, lat: number): [number, number] => [
    (lng * squeeze - minX) * scale,
    (maxY - lat) * scale, // the SVG's y grows downwards, latitude grows upwards
  ];
  const path = (geometry: Geometry) => {
    const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
    return polygons
      .flatMap((rings) =>
        rings.map((ring) => "M" + ring.map(([lng, lat]) => point(lng, lat).map((v) => v.toFixed(1)).join(",")).join("L") + "Z"),
      )
      .join("");
  };
  return { width, height, point, path };
}

function allPoints(geometry: Geometry): Ring {
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  return polygons.flat(2) as unknown as Ring;
}
