# Offline chat basemap

The chat map bundles a Natural Earth basemap with the frontend. It makes no tile-server request and remains available after the application has loaded and the browser loses connectivity. The raster relief is embedded in the JavaScript bundle, rather than fetched when a map is opened.

| Local file           | Natural Earth source                           |             Size |
| -------------------- | ---------------------------------------------- | ---------------: |
| `offlineWorld.json`  | 1:10m Admin 0 countries and coastlines         | 11,312,232 bytes |
| `offlineRoads.json`  | 1:10m roads                                    | 19,148,105 bytes |
| `offlineLakes.json`  | 1:50m lakes                                    |    440,870 bytes |
| `offlineRivers.json` | 1:50m rivers and lake centerlines              |    570,470 bytes |
| `offlineCities.json` | 1:50m populated places                         |    160,584 bytes |
| `offlineRelief.webp` | 1:50m Natural Earth I shaded relief with water |  1,525,522 bytes |

Total: 33,157,783 bytes on disk. These assets are part of the frontend build. The vector files were exported from Natural Earth's shapefiles as compact GeoJSON with pyshp 3.1.9, retaining only the coordinates and the city name/rank. The relief was resized to 8192 x 4096, reprojected to an 8192 x 8192 Web Mercator raster, and encoded as WebP. Roads are filtered to the visible map bounds at zoom 5 or above; country contours, lakes and rivers use Leaflet's canvas renderer. The map uses EPSG:3857 so the relief and vectors align without distorting local proportions. For locations beyond Mercator's 85.051-degree latitude limit, the map uses EPSG:4326 and omits the relief to keep polar coordinates distinct.

Sources: [1:10m cultural vectors](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/), [1:50m cultural vectors](https://www.naturalearthdata.com/downloads/50m-cultural-vectors/), [1:50m physical vectors](https://www.naturalearthdata.com/downloads/50m-physical-vectors/), [1:50m raster relief](https://www.naturalearthdata.com/downloads/50m-raster-data/50m-natural-earth-1/). Natural Earth [places the data in the public domain](https://www.naturalearthdata.com/about/terms-of-use/).
