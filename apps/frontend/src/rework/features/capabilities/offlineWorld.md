# Offline country basemap

`offlineWorld.json` contains the geometries of the [Natural Earth 1:110m Admin 0 Countries dataset](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/) version 5.1.1. Natural Earth [places its map data in the public domain](https://www.naturalearthdata.com/about/terms-of-use/).

The source shapefile was converted to GeoJSON with pyshp 3.1.9. The export keeps country geometries, removes all properties, and uses compact JSON. It is bundled with the chat renderer so a map can appear after the browser loses network access.
