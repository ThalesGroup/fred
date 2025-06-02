// Copyright Thales 2025
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

import React from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { ShipList } from "../slices/shipStructures";

interface GeomapPagesLayoutProps {
  data: ShipList;
}

export const GeomapLayout: React.FC<GeomapPagesLayoutProps> = ({ data }) => {
  const firstShipLocation = data.ships[0]?.location;
  const defaultCenter: [number, number] = firstShipLocation ? parseLocation(firstShipLocation) : [0, 0];

  return (
    <MapContainer center={defaultCenter} zoom={7} style={{ height: "70%", width: "100%" }}>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      {data.ships.map((ship, index) => {
        const pos = parseLocation(ship.location);
        if (!pos) return null;

        return (
          <Marker key={index} position={pos}>
            <Popup>
              <div>
                <strong>Protocol:</strong> {ship.protocol}
                <br />
                <strong>Frequency:</strong> {ship.frequency} Hz
                <br />
                <strong>Bandwidth:</strong> {ship.bandwidth} Hz
              </div>
            </Popup>
          </Marker>
        );
      })}
    </MapContainer>
  );
};

function parseLocation(location: string): [number, number] | null {
  const [latStr, lonStr] = location.split(",").map((s) => s.trim());
  const lat = parseFloat(latStr);
  const lon = parseFloat(lonStr);
  if (isNaN(lat) || isNaN(lon)) return null;
  return [lat, lon];
}
