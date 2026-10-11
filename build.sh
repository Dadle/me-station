#!/usr/bin/env bash
# Rebuilds the scenes.  ./build.sh            -> me_station.blend + me_station_demo.blend
#                       ./build.sh --chars    -> also regenerate chars/*.blend first (needs setup_makehuman.sh)
set -euo pipefail
cd "$(dirname "$0")"
BLENDER=${BLENDER:-blender}
[ -d downloads/textures ] || { echo "run ./setup_assets.sh first"; exit 1; }
if [ "${1:-}" = "--chars" ]; then
  $BLENDER -b --python build_characters.py 2>&1 | grep -E "^(BUILT|POSED|SAVED)|Traceback"
fi
$BLENDER -b --python build_station.py -- "$PWD/me_station.blend" 2>&1 | grep -E "SAVED|Traceback|Error:" | grep -v "Shadow buffer"
$BLENDER -b me_station.blend --python make_demo.py 2>&1 | grep -E "SAVED|Traceback|Error:" | grep -v "Shadow buffer"
echo "done: ./run_demo.sh or ./run_station.sh"
