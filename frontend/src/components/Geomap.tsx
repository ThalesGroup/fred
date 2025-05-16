import React from 'react';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import { ShipList } from "../slices/shipStructures";

interface GeomapPagesLayoutProps {
    data: ShipList;
}

export const GeomapLayout: React.FC<GeomapPagesLayoutProps> = ({ data }) => {
    const firstShipLocation = data.ships[0]?.location;
    const defaultCenter: [number, number] = firstShipLocation
        ? parseLocation(firstShipLocation)
        : [0, 0];

    return (
        <MapContainer center={defaultCenter} zoom={7} style={{ height: '70%', width: '100%' }}>
            <TileLayer
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            {data.ships.map((ship, index) => {
                const pos = parseLocation(ship.location);
                if (!pos) return null;

                return (
                    <Marker key={index} position={pos}>
                        <Popup>
                            <div>
                                <strong>Protocol:</strong> {ship.protocol}<br />
                                <strong>Frequency:</strong> {ship.frequency} Hz<br />
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
    const [latStr, lonStr] = location.split(',').map(s => s.trim());
    const lat = parseFloat(latStr);
    const lon = parseFloat(lonStr);
    if (isNaN(lat) || isNaN(lon)) return null;
    return [lat, lon];
}