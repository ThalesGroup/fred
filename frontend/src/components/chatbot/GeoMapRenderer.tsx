import { Paper } from "@mui/material";
import L, { LatLngExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import React from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import type { GeoPart } from "../../slices/agentic/agenticOpenApi.ts";

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

type GeoMapRendererProps = { part: GeoPart };

// -- WHY: Keep renderer generic. Let *data* control styling when provided.
// Accepted per-feature hints:
// - properties.style: Leaflet PathOptions (preferred)
// - properties.color, properties.fillColor, properties.weight, properties.opacity, properties.fillOpacity
// - points: properties.radius (number)
function featureStyleFromProps(feature: GeoJSON.Feature | undefined): L.PathOptions | undefined {
  const p = (feature?.properties ?? {}) as Record<string, unknown>;
  if (!p) return undefined;

  // Highest authority: properties.style object (leaflet PathOptions)
  if (p.style && typeof p.style === "object") {
    return p.style as L.PathOptions;
  }

  // Lightweight hints (optional, all safe fallbacks)
  const color = typeof p.color === "string" ? (p.color as string) : undefined;
  const fillColor = typeof p.fillColor === "string" ? (p.fillColor as string) : undefined;
  const weight = typeof p.weight === "number" ? (p.weight as number) : undefined;
  const opacity = typeof p.opacity === "number" ? (p.opacity as number) : undefined;
  const fillOpacity = typeof p.fillOpacity === "number" ? (p.fillOpacity as number) : undefined;

  if (color || fillColor || weight || opacity || fillOpacity) {
    return { color, fillColor, weight, opacity, fillOpacity };
  }

  return undefined; // Leaflet defaults
}

// -- WHY: For points, default to circleMarker for consistent, styleable dots.
// Honor properties.radius and properties.style if present.
function pointToLayerGeneric(feature: GeoJSON.Feature<GeoJSON.Point, any>, latlng: L.LatLng): L.Layer {
  const p = (feature.properties ?? {}) as Record<string, unknown>;
  const styleOverride =
    typeof p.style === "object"
      ? (p.style as Partial<L.CircleMarkerOptions>)
      : undefined;
  const fallbackStyle = featureStyleFromProps(feature) as Partial<L.CircleMarkerOptions> | undefined;
  const base: Partial<L.CircleMarkerOptions> = styleOverride ?? fallbackStyle ?? {};
  const radius = typeof p.radius === "number" ? (p.radius as number) : 6;
  const circleOptions: L.CircleMarkerOptions = { ...base, radius } as L.CircleMarkerOptions;
  return L.circleMarker(latlng, circleOptions);
}

// -- WHY: Popup content should be predictable and data-driven.
// Priority: popup_property -> properties.name -> compact JSON(props)
function bindPopupGeneric(layer: L.Layer, feature: GeoJSON.Feature | undefined, popupProperty?: string) {
  if (!feature) return;
  const p = (feature.properties ?? {}) as Record<string, unknown>;
  let text: string | undefined;

  if (popupProperty && p && p[popupProperty] != null) {
    text = String(p[popupProperty]);
  } else if (p && p.name != null) {
    text = String(p.name);
  } else if (p && Object.keys(p).length > 0) {
    try {
      text = JSON.stringify(p, Object.keys(p).sort()).slice(0, 300);
    } catch {
      // ignore JSON issues; leave no popup
    }
  }

  if (text) {
    (layer as L.Layer & { bindPopup?: (s: string) => void }).bindPopup?.(text);
  }
}

// -- WHY: Fit map to provided data without flashing default view.
const MapBoundFitter: React.FC<{
  geojson: GeoPart["geojson"];
  fitBounds: boolean;
}> = ({ geojson, fitBounds }) => {
  const map = useMap();
  React.useEffect(() => {
    if (!fitBounds) return;
    if (!geojson || !(geojson as any).features?.length) return;
    const bounds = L.geoJSON(geojson as any).getBounds();
    if (bounds.isValid()) {
      map.flyToBounds(bounds, { padding: L.point(50, 50) });
    }
  }, [map, geojson, fitBounds]);
  return null;
};

export const GeoMapRenderer: React.FC<GeoMapRendererProps> = ({ part }) => {
  const { geojson, popup_property, style, fit_bounds = true } = part;
  const INITIAL_CENTER: LatLngExpression = [43.296, 5.385];
  const mapStyle = { height: "350px", width: "100%" };
  const initialBounds = L.geoJSON(geojson as any).getBounds();

  return (
    <Paper elevation={3} sx={{ my: 2, overflow: "hidden", borderRadius: 2 }}>
      <MapContainer
        center={initialBounds.isValid() ? undefined : INITIAL_CENTER}
        zoom={10}
        scrollWheelZoom={false}
        style={mapStyle}
        bounds={fit_bounds && initialBounds.isValid() ? initialBounds : undefined}
      >
        <TileLayer
          attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        <GeoJSON
          // NOTE: keep component generic; "style" may be a static PathOptions OR a function(feature) -> PathOptions
          data={geojson as any}
          style={(f) =>
            // Prefer caller-provided style if it's a function; else fall back to per-feature props.
            typeof style === "function"
              ? (style as (feat: GeoJSON.Feature) => L.PathOptions | undefined)(f as GeoJSON.Feature)
              : ((style as L.PathOptions | undefined) ?? featureStyleFromProps(f as GeoJSON.Feature))
          }
          pointToLayer={(feature, latlng) => pointToLayerGeneric(feature as GeoJSON.Feature<GeoJSON.Point>, latlng)}
          onEachFeature={(feature, layer) => {
            bindPopupGeneric(layer, feature as GeoJSON.Feature, popup_property);
            // No domain hardcoding here; feature-level `properties.style` drives any special visuals.
          }}
        />

        <MapBoundFitter geojson={geojson} fitBounds={fit_bounds} />
      </MapContainer>
    </Paper>
  );
};

export default GeoMapRenderer;
