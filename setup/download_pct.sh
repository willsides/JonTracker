#!/usr/bin/env bash
# Download the PCT trail as GeoJSON and place it where JonTracker expects it.
# Run from the jontracker directory: bash setup/download_pct.sh
#
# Source: PCTA official data page — https://www.pcta.org/discover-the-trail/maps/pct-data/
# The trail is also available in OpenStreetMap export tools or as a direct download
# from various mirror repositories.
#
# HOW TO GET THE FILE:
#   Option A (easiest): Download from PCTA
#     1. Go to: https://www.pcta.org/discover-the-trail/maps/pct-data/
#     2. Download "PCT - All" as KML or GPX
#     3. Convert to GeoJSON with ogr2gdal or mapshaper.org
#     4. Save as: static/pct.geojson
#
#   Option B: Convert from a downloaded GPX/KML manually
#     sudo apt install gdal-bin
#     ogr2ogr -f GeoJSON static/pct.geojson your_downloaded_file.gpx

set -e

DEST="$(dirname "$0")/../static/pct.geojson"

if [ -f "$DEST" ]; then
  echo "pct.geojson already exists at $DEST"
  echo "Delete it and re-run to replace."
  exit 0
fi

# Check for gdal (needed if converting from GPX/KML)
if command -v ogr2ogr &>/dev/null; then
  echo "ogr2ogr is available for format conversion."
else
  echo "Tip: install gdal-bin for GPX/KML → GeoJSON conversion:"
  echo "  sudo apt install gdal-bin"
fi

echo ""
echo "To add the PCT trail overlay, place a GeoJSON file at:"
echo "  $DEST"
echo ""
echo "The JonTracker server will auto-detect it and display the trail on the map."
echo "See comments in this file for download/conversion instructions."
