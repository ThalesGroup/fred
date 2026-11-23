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

// Render the built-in GeoPart with the bundled offline basemap.

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import offlineWorldRaw from "./offlineBasemap/offlineWorld.json?raw";
import offlineRoadsRaw from "./offlineBasemap/offlineRoads.json?raw";
import offlineLakesRaw from "./offlineBasemap/offlineLakes.json?raw";
import offlineRiversRaw from "./offlineBasemap/offlineRivers.json?raw";
import offlineCitiesRaw from "./offlineBasemap/offlineCities.json?raw";
import offlineRelief from "./offlineBasemap/offlineRelief.webp?inline";
import type { GeoPart } from "../../../../slices/runtime/runtimeOpenApi";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import type { UiPartRendererProps } from "../types";
import styles from "./GeoPartRenderer.module.css";

type RoadGeometry = { type: string; coordinates: number[][] | number[][][] };
type RoadCollection = {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: RoadGeometry; properties: object }[];
};
type CityCollection = {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: { name: string; scalerank: number };
  }[];
};
type Basemap = {
  world: Parameters<typeof L.geoJSON>[0];
  roads: RoadCollection;
  lakes: Parameters<typeof L.geoJSON>[0];
  rivers: Parameters<typeof L.geoJSON>[0];
  cities: CityCollection;
  roadBounds: Float32Array;
};
const MERCATOR_LATITUDE_LIMIT = 85.05112878;
let cachedBasemap: Basemap | undefined;

// One compact bounds index lets each chat map draw only roads in its viewport.
function getBasemap(): Basemap {
  if (cachedBasemap) return cachedBasemap;
  const roads = JSON.parse(offlineRoadsRaw) as RoadCollection;
  const roadBounds = new Float32Array(roads.features.length * 4);
  for (let i = 0; i < roads.features.length; i++) {
    const geometry = roads.features[i].geometry;
    const lines =
      geometry.type === "MultiLineString"
        ? (geometry.coordinates as number[][][])
        : [geometry.coordinates as number[][]];
    let west = 180;
    let south = 90;
    let east = -180;
    let north = -90;
    for (const line of lines) {
      for (const [longitude, latitude] of line) {
        west = Math.min(west, longitude);
        south = Math.min(south, latitude);
        east = Math.max(east, longitude);
        north = Math.max(north, latitude);
      }
    }
    roadBounds.set([west, south, east, north], i * 4);
  }
  cachedBasemap = {
    world: JSON.parse(offlineWorldRaw) as Basemap["world"],
    roads,
    lakes: JSON.parse(offlineLakesRaw) as Basemap["lakes"],
    rivers: JSON.parse(offlineRiversRaw) as Basemap["rivers"],
    cities: JSON.parse(offlineCitiesRaw) as CityCollection,
    roadBounds,
  };
  return cachedBasemap;
}

function pointDetails(properties: Record<string, unknown>, popupProperty?: string) {
  const details = Object.entries(properties).filter(
    ([key, value]) =>
      key !== "name" &&
      key !== "color" &&
      key !== "fillOpacity" &&
      (typeof value === "string" || typeof value === "number" || typeof value === "boolean"),
  );
  return popupProperty
    ? details.sort(([a], [b]) => Number(b === popupProperty) - Number(a === popupProperty))
    : details;
}

function hoverDetails(details: [string, unknown][]) {
  return details.slice(0, 2).map(([key, value]) => {
    const text = String(value);
    return [key, text.length > 120 ? `${text.slice(0, 119)}...` : text] as [string, string];
  });
}

function pointContent(label: string | undefined, details: [string, unknown][]) {
  const content = document.createElement("div");
  if (label) {
    const heading = document.createElement("strong");
    heading.className = styles.geoPointTitle;
    heading.textContent = label;
    content.append(heading);
  }
  for (const [key, value] of details) {
    const row = document.createElement("div");
    row.className = styles.geoPointSubtitle;
    row.textContent = key === "description" || key === "details" ? String(value) : `${key}: ${String(value)}`;
    content.append(row);
  }
  return content;
}

function pointLabel(label: string) {
  const content = document.createElement("span");
  content.className = styles.geoPointTitle;
  content.textContent = label;
  return content;
}

/** Render a typed GeoPart with Leaflet's browser API. */
export function GeoPartRenderer({ part }: UiPartRendererProps) {
  const { t } = useTranslation();
  const geo = part as unknown as GeoPart;
  const featureList = Array.isArray(geo.geojson?.features) ? geo.geojson.features : [];
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const savedView = useRef<{ center: L.LatLng; zoom: number } | null>(null);
  const enlargeTrigger = useRef<HTMLButtonElement | null>(null);
  const [enlarged, setEnlarged] = useState(false);
  const [hasRendered, setHasRendered] = useState(false);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  function rememberView() {
    if (mapRef.current) {
      savedView.current = { center: mapRef.current.getCenter(), zoom: mapRef.current.getZoom() };
    }
  }

  function closeEnlarged() {
    rememberView();
    setEnlarged(false);
    enlargeTrigger.current?.focus();
  }

  useEffect(() => {
    setStatus("loading");
    if (!container) return;
    let map: L.Map | undefined;
    let cancelled = false;
    // Leaflet reads window when imported, so load it after the map mounts.
    void import("leaflet")
      .then((L) => {
        if (cancelled) return;
        try {
          const basemap = getBasemap();
          const featureBounds = L.geoJSON(geo.geojson as Parameters<typeof L.geoJSON>[0]).getBounds();
          const useMercator =
            !featureBounds.isValid() ||
            (featureBounds.getSouth() >= -MERCATOR_LATITUDE_LIMIT &&
              featureBounds.getNorth() <= MERCATOR_LATITUDE_LIMIT);
          map = L.map(container, {
            crs: useMercator ? L.CRS.EPSG3857 : L.CRS.EPSG4326,
            scrollWheelZoom: true,
            zoomAnimation: false,
            preferCanvas: true,
          });
          mapRef.current = map;
          map.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/">Natural Earth</a>');
          if (useMercator) {
            L.imageOverlay(
              offlineRelief,
              [
                [-MERCATOR_LATITUDE_LIMIT, -180],
                [MERCATOR_LATITUDE_LIMIT, 180],
              ],
              { interactive: false, opacity: 0.4 },
            ).addTo(map);
          }
          L.geoJSON(basemap.world, {
            interactive: false,
            style: { color: "#718984", weight: 0.7, fillColor: "#e8eadb", fillOpacity: 0.8 },
          }).addTo(map);
          L.geoJSON(basemap.lakes, {
            interactive: false,
            style: { color: "#89aeb7", weight: 0.5, fillColor: "#bddbe2", fillOpacity: 0.8 },
          }).addTo(map);
          L.geoJSON(basemap.rivers, {
            interactive: false,
            style: { color: "#9cc3d0", weight: 0.8 },
          }).addTo(map);
          const roadLayer = L.geoJSON(undefined, {
            interactive: false,
            style: { color: "#b88c65", weight: 0.8, opacity: 0.5 },
          }).addTo(map);
          const cityLayer = L.geoJSON(undefined, {
            interactive: false,
            pointToLayer: (feature, latlng) =>
              L.marker(latlng, {
                interactive: false,
                keyboard: false,
                icon: L.divIcon({
                  className: styles.geoCity,
                  html: `<span>${String(feature.properties?.name ?? "").replace(
                    /[&<>"']/g,
                    (char) =>
                      ({
                        "&": "&amp;",
                        "<": "&lt;",
                        ">": "&gt;",
                        '"': "&quot;",
                        "'": "&#39;",
                      })[char] ?? char,
                  )}</span>`,
                }),
              }),
          }).addTo(map);
          const userPointPane = map.createPane("geoUserPoints");
          userPointPane.style.zIndex = "650";
          const userPointRenderer = L.canvas({ pane: "geoUserPoints" });
          let pointIndex = 0;
          const labelledCoordinates = new Set<string>();
          const layer = L.geoJSON(geo.geojson as Parameters<typeof L.geoJSON>[0], {
            pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 7, renderer: userPointRenderer }),
            style: (feature) => {
              const color = feature?.properties?.color;
              const fillOpacity = feature?.properties?.fillOpacity;
              return {
                color: typeof color === "string" && /^#[0-9a-fA-F]{3,8}$/.test(color) ? color : "#6366f1",
                fillOpacity:
                  typeof fillOpacity === "number" && fillOpacity >= 0 && fillOpacity <= 1 ? fillOpacity : 0.3,
              };
            },
            onEachFeature: (feature, featureLayer) => {
              const properties = feature.properties ?? {};
              const rawLabel = properties.name;
              const label = typeof rawLabel === "string" || typeof rawLabel === "number" ? String(rawLabel) : undefined;
              const details = pointDetails(properties, geo.popup_property ?? undefined);
              if (label || details.length) {
                featureLayer.bindPopup(pointContent(label, details));
              }
              const pointCoordinates = feature.geometry?.type === "Point" ? feature.geometry.coordinates : undefined;
              const coordinateKey = pointCoordinates ? JSON.stringify(pointCoordinates) : undefined;
              if (coordinateKey && label && !labelledCoordinates.has(coordinateKey)) {
                labelledCoordinates.add(coordinateKey);
                const directions = ["right", "left", "top", "bottom"] as const;
                const direction = directions[pointIndex++ % directions.length];
                featureLayer.bindTooltip(pointLabel(label), {
                  permanent: true,
                  interactive: false,
                  direction,
                  offset: direction === "top" ? [0, -22] : direction === "bottom" ? [0, 22] : [6, 0],
                  className: styles.geoPointLabel,
                });
                const [longitude, latitude] = pointCoordinates;
                const hoverPreview = details.length
                  ? hoverDetails(details)
                  : Number.isFinite(latitude) && Number.isFinite(longitude)
                    ? ([["lat", `${latitude.toFixed(4)}°, lon ${longitude.toFixed(4)}°`]] as [string, string][])
                    : [];
                if (hoverPreview.length) {
                  featureLayer.on("mouseover", () => featureLayer.setTooltipContent(pointContent(label, hoverPreview)));
                  featureLayer.on("mouseout", () => featureLayer.setTooltipContent(pointLabel(label)));
                }
              }
            },
          }).addTo(map);
          const bounds = layer.getBounds();
          if (savedView.current) {
            map.setView(savedView.current.center, savedView.current.zoom);
            savedView.current = null;
          } else if (bounds.isValid() && geo.fit_bounds !== false) {
            map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
          } else if (bounds.isValid()) map.setView(bounds.getCenter(), 10);
          else map.setView([0, 0], 2);
          const updateBasemap = () => {
            if (!map) return;
            const zoom = map.getZoom();
            const view = map.getBounds().pad(0.2);
            roadLayer.clearLayers();
            if (zoom >= 5) {
              const west = view.getWest();
              const south = view.getSouth();
              const east = view.getEast();
              const north = view.getNorth();
              const visible = basemap.roads.features.filter((_, index) => {
                const offset = index * 4;
                return (
                  basemap.roadBounds[offset] <= east &&
                  basemap.roadBounds[offset + 2] >= west &&
                  basemap.roadBounds[offset + 1] <= north &&
                  basemap.roadBounds[offset + 3] >= south
                );
              });
              roadLayer.addData({ type: "FeatureCollection", features: visible } as Parameters<
                typeof roadLayer.addData
              >[0]);
            }
            cityLayer.clearLayers();
            const rank = zoom < 5 ? 1 : zoom < 7 ? 3 : 5;
            const cities = basemap.cities.features.filter(
              (feature) =>
                feature.properties.scalerank <= rank &&
                view.contains([feature.geometry.coordinates[1], feature.geometry.coordinates[0]]),
            );
            cityLayer.addData({ type: "FeatureCollection", features: cities } as Parameters<
              typeof cityLayer.addData
            >[0]);
          };
          map.on("moveend", updateBasemap);
          updateBasemap();
          setHasRendered(true);
          setStatus("ready");
        } catch {
          map?.remove();
          mapRef.current = null;
          map = undefined;
          setStatus("error");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("error");
      });

    return () => {
      cancelled = true;
      map?.remove();
      mapRef.current = null;
    };
  }, [geo.geojson, geo.fit_bounds, geo.popup_property, container]);

  const mapView = (
    <div
      ref={setContainer}
      className={`${styles.geoMap} ${enlarged ? styles.geoMapLarge : ""}`}
      role="region"
      aria-busy={status === "loading"}
      aria-label={t("chatbot.uiParts.geoAria")}
    />
  );
  const locations = featureList.length > 0 && (
    <details className={styles.geoDetails} open={status === "error"}>
      <summary>{t("chatbot.uiParts.geoLocations")}</summary>
      <ol className={styles.geoFeatureList}>
        {featureList.map((feature, index) => {
          const properties = feature.properties ?? {};
          const label = properties.name;
          const details = pointDetails(properties, geo.popup_property ?? undefined);
          return (
            <li key={index}>
              {typeof label === "string" || typeof label === "number"
                ? label
                : t("chatbot.uiParts.geoFeature", { index: index + 1 })}
              {details.length > 0 && (
                <ul>
                  {details.map(([key, value]) => (
                    <li key={key}>
                      {key === "description" || key === "details" ? String(value) : `${key}: ${String(value)}`}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </details>
  );

  return (
    <div className={styles.geoPanel}>
      {status === "error" && !enlarged && <p role="status">{t("chatbot.uiParts.geoUnavailable")}</p>}
      <div className={styles.geoMapFrame}>
        {enlarged ? <div className={styles.geoMap} aria-hidden="true" /> : mapView}
        {hasRendered && status !== "error" && (
          <IconButton
            type="button"
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "fullscreen" }}
            className={styles.geoExpandButton}
            aria-label={t("chatbot.uiParts.geoEnlarge")}
            title={t("chatbot.uiParts.geoEnlarge")}
            aria-haspopup="dialog"
            onClick={(event) => {
              enlargeTrigger.current = event.currentTarget;
              rememberView();
              setEnlarged(true);
            }}
          />
        )}
      </div>
      {!enlarged && locations}
      <Dialog
        open={enlarged}
        title={t("chatbot.uiParts.geoAria")}
        cancelLabel={t("chatbot.uiParts.geoClose")}
        confirmLabel={t("chatbot.uiParts.geoClose")}
        onCancel={closeEnlarged}
        onConfirm={closeEnlarged}
        hideConfirm
        maxWidth={1200}
        scrollMode="children"
        className={styles.geoDialog}
      >
        <div className={styles.geoLargeBody}>
          {status === "error" && <p role="status">{t("chatbot.uiParts.geoUnavailable")}</p>}
          {enlarged && mapView}
          <div className={styles.geoLargeLocations}>{enlarged && locations}</div>
        </div>
      </Dialog>
    </div>
  );
}
