#!/usr/bin/env bash
# Optional: only needed to regenerate or change the characters (chars/*.blend are committed).
# Installs the MPFB extension (MakeHuman Plugin for Blender) and the MakeHuman asset packs
# it needs (~1 GB) into MPFB's user data directory.
set -euo pipefail
BLENDER=${BLENDER:-blender}
VER=$($BLENDER --version | head -1 | awk '{print $2}' | cut -d. -f1,2)
echo "Blender $VER"
$BLENDER -b --command extension install mpfb -r user_default --enable 2>&1 | tail -2 || true
DATA=$($BLENDER -b --python-expr "import bpy; print('UHOME', bpy.utils.extension_path_user('bl_ext.user_default.mpfb'))" 2>/dev/null | grep UHOME | cut -d' ' -f2)/data
[ -n "$DATA" ] || { echo "MPFB not found: install it from Edit > Preferences > Get Extensions, then re-run"; exit 1; }
mkdir -p "$DATA" downloads/mh_packs
PACKS="makehuman_system_assets/makehuman_system_assets_cc0 skins01/skins01_cc0 skins03/skins03_cc0 suits02/suits02_cc0 suits03/suits03_cc-by shoes03/shoes03_ccby eyebrows01/eyebrows01_cc0 eyelashes01/eyelashes01_cc0 system_eye_materials01/system_eye_materials01_cc0 makehuman_system_poses/makehuman_system_poses_cc0 poses03/poses03_cc0"
for p in $PACKS; do
  f=downloads/mh_packs/$(basename $p).zip
  [ -s "$f" ] || curl -sS -L --retry 3 -o "$f" "https://files.makehumancommunity.org/asset_packs/$p.zip"
  unzip -q -o "$f" -d "$DATA"
  echo "pack $(basename $p): ok"
done
echo "MakeHuman data in $DATA"
