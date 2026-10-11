#!/usr/bin/env bash
# Downloads the CC0 environment assets the build scripts expect (about 1 GB):
#   downloads/textures/<Id>/   ambientCG 2K JPG PBR sets
#   downloads/models/<id>/     Poly Haven .blend models with their textures
set -euo pipefail
cd "$(dirname "$0")"
TEX="MetalPlates006 Metal046A Metal032 Metal009 Metal061A Plastic010 Plastic013A Plastic004 Rubber001 Leather030 Fabric031 Fabric004 DiamondPlate008C Metal028"
MODELS="potted_plant_01 potted_plant_02 plastic_crate_01 plastic_crate_03 industrial_pastic_container korean_fire_extinguisher_01 medical_box utility_box_02 modern_arm_chair_01"

mkdir -p downloads/textures downloads/models
for id in $TEX; do
  d=downloads/textures/$id
  if [ -f "$d/${id}_2K-JPG_Color.jpg" ]; then echo "texture $id: ok"; continue; fi
  echo "texture $id: downloading"
  mkdir -p "$d"
  curl -sS -L --retry 3 -A "me-station-setup" -o "$d/$id.zip" "https://ambientcg.com/get?file=${id}_2K-JPG.zip"
  unzip -q -o "$d/$id.zip" -d "$d" && rm -f "$d/$id.zip"
done

for id in $MODELS; do
  d=downloads/models/$id
  if [ -f "$d/$id.blend" ]; then echo "model $id: ok"; continue; fi
  echo "model $id: downloading"
  mkdir -p "$d/textures"
  curl -sS -L --retry 3 "https://api.polyhaven.com/files/$id" | python3 -c '
import json, sys, subprocess, os
d = json.load(sys.stdin)["blend"]
res = "2k" if "2k" in d else sorted(d)[0]
b = d[res]["blend"]
dest = sys.argv[1]
def get(url, path):
    subprocess.run(["curl", "-sS", "-L", "--retry", "3", "-o", path, url], check=True)
get(b["url"], os.path.join(dest, sys.argv[2] + ".blend"))
for rel, info in b.get("include", {}).items():
    os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
    get(info["url"], os.path.join(dest, rel))
' "$d" "$id"
done
echo "assets ready"
