#!/usr/bin/env bash
# Simulate a GPS fix for testing JonTracker.
# Usage:
#   ./sim.sh <lat> <lon> [message]
#
# Examples:
#   ./sim.sh 37.8401 -119.5132                    # Tuolumne Meadows
#   ./sim.sh 36.4567 -118.2954 "at Forester Pass" # Highest PCT point

set -e

LAT="${1:?Usage: sim.sh <lat> <lon> [message]}"
LON="${2:?Usage: sim.sh <lat> <lon> [message]}"
MSG="${3:-}"

PAYLOAD="lat=${LAT}&lon=${LON}"
[ -n "$MSG" ] && PAYLOAD="${PAYLOAD}&message=${MSG}"

RESPONSE=$(curl -sf -X POST http://localhost:5000/api/simulate \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "$PAYLOAD")

echo "$RESPONSE" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('ok'):
    print(f\"  Simulated: {d['lat']}, {d['lon']}\")
else:
    print(f\"  Error: {d}\")
    sys.exit(1)
"
