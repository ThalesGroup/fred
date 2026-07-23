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

// Interactive Leaflet renderer for a `GeoPart` (#1977 builtin `geo` kind).
// Only ever reached via a dynamic import from GeoPartRenderer — `leaflet`
// touches `window`/`document` at module-load time, which crashes under the
// node-environment unit tests, so this module must never be imported eagerly.

import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import L from "leaflet";
import type { Layer, PathOptions } from "leaflet";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import "leaflet/dist/leaflet.css";
import styles from "./GeoMap.module.css";

export interface GeoMapProps {
  geojson: Record<string, unknown>;
  popupProperty?: string | null;
  fitBounds?: boolean;
  style?: Record<string, unknown> | null;
}

const FALLBACK_CENTER: [number, number] = [50, 8];
const FALLBACK_ZOOM = 4;

// `properties` values are agent-supplied and may be untrusted (e.g. RAG content).
// `color` flows into SVG markup and Leaflet path styles, so only hex / rgb(a) /
// hsl(a) values are accepted; anything else falls back to the theme accent.
const SAFE_COLOR = /^#[0-9a-f]{3,8}$|^(rgb|hsl)a?\([\d.,%\s/]+\)$/i;

function isFeatureCollection(value: Record<string, unknown>): boolean {
  return value.type === "FeatureCollection" && Array.isArray(value.features);
}

// Self-contained SVG pin via L.divIcon. Leaflet's default PNG marker icons don't
// survive Vite bundling (broken image), so an inline SVG avoids the external asset.
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

export function GeoMap({ geojson, popupProperty, fitBounds = true, style }: GeoMapProps) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [accent, setAccent] = useState<string>("#6366f1");

  useEffect(() => {
    const source = rootRef.current ?? document.documentElement;
    const value = getComputedStyle(source).getPropertyValue("--primary").trim();
    if (value) setAccent(value);
  }, []);

  const data = useMemo(() => {
    if (!isFeatureCollection(geojson)) return null;
    const candidate = geojson as unknown as FeatureCollection;
    // `isFeatureCollection` only checks the envelope shape — a feature's own
    // geometry/coordinates can still be malformed (this data may be
    // agent-supplied, e.g. RAG content). Leaflet throws deep inside its own
    // parsing for that case, outside any try/catch in the render path below,
    // which would crash the component tree instead of showing the error box.
    // Attempting the same L.geoJSON() parse react-leaflet's <GeoJSON> does
    // internally catches that here instead.
    try {
      L.geoJSON(candidate as never);
    } catch {
      return null;
    }
    return candidate;
  }, [geojson]);
  const baseStyle = (style ?? {}) as Record<string, unknown>;

  if (!data) {
    return (
      <div ref={rootRef} className={styles.block}>
        <div className={styles.error}>
          <span className={styles.errorLabel}>{t("chatbot.uiParts.geoError")}</span>
        </div>
      </div>
    );
  }

  const safeColor = (c: unknown): string => (typeof c === "string" && SAFE_COLOR.test(c.trim()) ? c.trim() : accent);

  const styleFn = (feature?: Feature<Geometry>): PathOptions => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    const color = safeColor(props.color ?? baseStyle.color);
    return {
      color,
      weight: (baseStyle.weight as number) ?? 2,
      opacity: (baseStyle.opacity as number) ?? 0.9,
      fillColor: color,
      fillOpacity: (props.fillOpacity as number) ?? (baseStyle.fillOpacity as number) ?? 0.15,
    };
  };

  const pointToLayer = (feature: Feature<Geometry>, latlng: L.LatLng): Layer => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    return L.marker(latlng, { icon: buildPinIcon(safeColor(props.color ?? baseStyle.color)) });
  };

  const onEachFeature = (feature: Feature<Geometry>, layer: Layer) => {
    const props = (feature?.properties ?? {}) as Record<string, unknown>;
    const label = popupProperty ? props[popupProperty] : (props.name ?? props.title);
    if (label != null && label !== "") {
      // Bind a text node, not a string: layer.bindPopup(string) treats its input
      // as HTML, so an agent-supplied name/title could inject markup. textContent
      // escapes everything.
      const el = document.createElement("span");
      el.textContent = String(label);
      layer.bindPopup(el);
    }
  };

  return (
    <div ref={rootRef} className={styles.block} role="figure" aria-label={t("chatbot.uiParts.geoAria")}>
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
        {fitBounds && <FitBounds data={data} />}
      </MapContainer>
    </div>
  );
}

export default GeoMap;
