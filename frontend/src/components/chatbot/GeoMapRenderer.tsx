import { Paper } from "@mui/material";
import L, { LatLngExpression } from "leaflet";
import "leaflet/dist/leaflet.css"; // CRITICAL: Import Leaflet CSS
import React from "react";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";

// Import the GeoPart type from your OpenAPI generated file
import type { GeoPart } from "../../slices/agentic/agenticOpenApi.ts";

// --- ⚠️ CRITICAL FIX for Leaflet Marker Icons in React/Webpack/Vite ---
// If you see missing markers, this block is essential.
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  // Standard Leaflet marker images
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});
// ---------------------------------------------------------------------

type GeoMapRendererProps = {
  part: GeoPart;
};

// --- Utility Component to Fit Bounds ---
// This component must be a child of MapContainer to access the 'map' instance via useMap().
const MapBoundFitter: React.FC<{ geojson: GeoPart["geojson"]; fitBounds: boolean }> = ({ geojson, fitBounds }) => {
  const map = useMap();

  React.useEffect(() => {
    if (fitBounds && geojson && geojson.features && geojson.features.length > 0) {
      // L.geoJSON() handles parsing the GeoJSON object to calculate the bounds
      const bounds = L.geoJSON(geojson as any).getBounds();
      if (bounds.isValid()) {
        // Fly to the calculated bounds with a small padding
        map.flyToBounds(bounds, { padding: L.point(50, 50) });
      }
    }
  }, [map, geojson, fitBounds]); // Dependencies on map, data, and fit flag

  return null;
};
// ---------------------------------------

export const GeoMapRenderer: React.FC<GeoMapRendererProps> = ({ part }) => {
  // Note: GeoJSON is expected to be { [key: string]: any; } which works as GeoJSON
  const { geojson, popup_property, style, fit_bounds = true } = part;

  // Fallback/initial center (e.g., Marseille, France)
  const INITIAL_CENTER: LatLngExpression = [43.296, 5.385];

  const mapStyle = { height: "350px", width: "100%" };

  // Calculate initial bounds to prevent flash of a default map view
  const initialBounds = L.geoJSON(geojson as any).getBounds();

  return (
    <Paper elevation={3} sx={{ my: 2, overflow: "hidden", borderRadius: 2 }}>
      <MapContainer
        // Set center/zoom if initial bounds are invalid, otherwise bounds will take over
        center={initialBounds.isValid() ? undefined : INITIAL_CENTER}
        zoom={10}
        scrollWheelZoom={false}
        style={mapStyle}
        // Use bounds for initial view (React-Leaflet best practice)
        bounds={fit_bounds && initialBounds.isValid() ? initialBounds : undefined}
        // Fixes rendering issue when container is initially hidden or zero-size
        whenReady={() => {
          // Access the map instance via document query or a ref if needed
          // But for most cases, this can be left empty or used for side effects
        }}
      >
        {/* Standard OSM Tile Layer (The actual map images) */}
        <TileLayer
          attribution='&copy; <a href="http://osm.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* 🌟 RENDER GEOJSON DATA 🌟 */}
        <GeoJSON
          data={geojson as any}
          style={style as any} // Pass optional GeoJSON styling
          onEachFeature={(feature, layer) => {
            // 1. Handle Popups if popup_property is set
            if (popup_property && feature.properties && feature.properties[popup_property]) {
              const popupText = String(feature.properties[popup_property]);
              layer.bindPopup(popupText);
            }

            // 2. Add custom styling for specific features (e.g., making vessels red)
            if (feature.properties?.type === "Tanker" && (layer as L.Path).setStyle) {
              (layer as L.Path).setStyle({ color: "#FF0000" });
            }
          }}
        />

        {/* Component to re-fit bounds dynamically after data load */}
        <MapBoundFitter geojson={geojson} fitBounds={fit_bounds} />
      </MapContainer>
    </Paper>
  );
};

// Export GeoMapRenderer for use in MessageCard
export default GeoMapRenderer;
