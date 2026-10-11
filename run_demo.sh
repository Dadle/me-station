#!/usr/bin/env bash
# High-FPS demo build (no ray tracing / haze / bloom, cheaper shadows, no subdivision).
cd "$(dirname "$0")"
[ -f me_station_demo.blend ] || ./build.sh
ME_DEMO=1 exec blender me_station_demo.blend --python walk_start.py "$@"
