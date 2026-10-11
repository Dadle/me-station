#!/usr/bin/env bash
# Opens the Mass Effect-style station in Blender, straight into first-person walk mode.
cd "$(dirname "$0")"
[ -f me_station.blend ] || ./build.sh
exec blender me_station.blend --python walk_start.py "$@"
