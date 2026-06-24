// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Renders a fenced GeoJSON block on an interactive Leaflet map. Wired into the
// markdown renderer next to MindMapBlock and MermaidBlock so ANY agent whose
// reply contains a ```geojson fence (or a ```json fence holding a GeoJSON
// FeatureCollection) gets a map instead of a raw code block.

import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import type { Layer, PathOptions } from "leaflet";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import "leaflet/dist/leaflet.css";
import styles from "./GeoMapBlock.module.css";

interface GeoMapBlockProps {
  code: string;
  language?: string;
}

// Default fallback view (roughly central Europe) used only when the data has no
// resolvable bounds (e.g. an empty FeatureCollection).
const FALLBACK_CENTER: [number, number] = [50, 8];
const FALLBACK_ZOOM = 4;

// Self-contained SVG pin rendered via L.divIcon. We deliberately avoid Leaflet's
// default PNG marker icons: their image paths don't survive Vite bundling and show
// as broken images. An inline SVG has no external asset, so it always renders.
function buildPinIcon(color: string) {
  const html = `
    <svg viewBox="0 0 24 36" width="24" height="36" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 8.25 12 24 12 24s12-15.75 12-24C24 5.37 18.63 0 12 0z"
            fill="${color}" stroke="#ffffff" stroke-width="1.5"/>
      <circle cx="12" cy="12" r="4.5" fill="#ffffff"/>
    </svg>`;
  return L.divIcon({
    html,
    className: styles.pin,
    iconSize: [24, 36],
    iconAnchor: [12, 36],
    popupAnchor: [0, -30],
  });
}

interface ParseResult {
  data: FeatureCollection | null;
  error: string | null;
}

/** Parse a fenced block into a GeoJSON FeatureCollection, or report why it can't. */
export function parseFeatureCollection(code: string): ParseResult {
  let value: unknown;
  try {
    value = JSON.parse(code);
  } catch (e) {
    return { data: null, error: `Invalid JSON: ${(e as Error).message}` };
  }
  if (!value || typeof value !== "object" || (value as { type?: string }).type !== "FeatureCollection") {
    return { data: null, error: "Expected a GeoJSON FeatureCollection." };
  }
  return { data: value as FeatureCollection, error: null };
}

/**
 * Cheap detector used by the markdown renderer to decide whether a generic
 * ```json fence is actually a GeoJSON FeatureCollection worth rendering as a map.
 */
export function isGeoJsonFeatureCollection(code: string): boolean {
  return parseFeatureCollection(code).data !== null;
}

/** Fits the map to the data's bounds once, after the GeoJSON layer mounts. */
function FitBounds({ data }: { data: FeatureCollection }) {
  const map = useMap();
  useEffect(() => {
    try {
      const bounds = L.geoJSON(data as never).getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [24, 24] });
      }
    } catch {
      // Malformed geometry — keep the fallback view rather than throwing.
    }
  }, [data, map]);
  return null;
}

export function GeoMapBlock({ code, language = "geojson" }: GeoMapBlockProps) {
  const parsed = useMemo(() => parseFeatureCollection(code), [code]);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [accent, setAccent] = useState<string>("#6366f1");

  // Resolve the theme accent once mounted so geometries match the design system.
  useEffect(() => {
    const source = rootRef.current ?? document.documentElement;
    const value = getComputedStyle(source).getPropertyValue("--primary").trim();
    if (value) setAccent(value);
  }, []);

  const { data, error: errorMessage } = parsed;

  if (!data) {
    return (
      <div ref={rootRef} className={styles.block}>
        <div className={styles.header}>
          <span className={styles.lang}>{language}</span>
        </div>
        <div className={styles.error}>
          <span className={styles.errorLabel}>Map could not be rendered</span>
          <p className={styles.errorText}>{errorMessage}</p>
        </div>
      </div>
    );
  }

  const styleFn = (feature?: Feature<Geometry>): PathOptions => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    const color = (props.color as string) || accent;
    return {
      color,
      weight: 2,
      opacity: 0.9,
      fillColor: color,
      fillOpacity: (props.fillOpacity as number) ?? 0.15,
    };
  };

  const pointToLayer = (feature: Feature<Geometry>, latlng: L.LatLng): Layer => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    const color = (props.color as string) || accent;
    return L.marker(latlng, { icon: buildPinIcon(color) });
  };

  const onEachFeature = (feature: Feature<Geometry>, layer: Layer) => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    const label = props.name ?? props.title;
    if (label != null && label !== "") {
      layer.bindPopup(String(label));
    }
  };

  return (
    <div ref={rootRef} className={styles.block}>
      <div className={styles.header}>
        <span className={styles.lang}>{language}</span>
        <strong className={styles.title}>Map</strong>
      </div>
      <div className={styles.content}>
        <MapContainer className={styles.map} center={FALLBACK_CENTER} zoom={FALLBACK_ZOOM} scrollWheelZoom={false}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={data as never}
            style={styleFn as (feature?: Feature<Geometry>) => PathOptions}
            pointToLayer={pointToLayer as (feature: Feature<Geometry>, latlng: L.LatLng) => Layer}
            onEachFeature={onEachFeature as (feature: Feature<Geometry>, layer: Layer) => void}
          />
          <FitBounds data={data} />
        </MapContainer>
      </div>
    </div>
  );
}
