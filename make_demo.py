"""Derive a high-FPS demo build from me_station.blend.
Run:  blender -b me_station.blend --python make_demo.py
Writes me_station_demo.blend next to it.

What it does:
  * bakes the two characters' idle loop (frames 1-144) into absolute shape keys, replacing the
    live armature + shape-key evaluation that dominated frame time
  * merges all static geometry by material into a handful of objects (fewer draw/sync calls)
  * cheaper EEVEE: lighter shadows, no viewport subdivision (bloom, haze and ray tracing stay on)
"""
import bpy, os, re
from mathutils import Vector, Matrix
sc = bpy.context.scene
HERE = os.path.dirname(bpy.data.filepath)
LOOP = 144

def sel(objs, active=None):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.hide_viewport = False; o.hide_set(False); o.select_set(True)
    bpy.context.view_layer.objects.active = active or objs[0]

# ---------------------------------------------------------------- characters -> baked shape keys
import numpy as np
chars = [o for o in bpy.data.objects if o.name.startswith(("Vessa", "Liora")) and o.type != 'LIGHT']
char_meshes = [o for o in chars if o.type == 'MESH']
for o in char_meshes:
    for md in o.modifiers:
        if md.type == 'SUBSURF': md.levels = 0
cc = bpy.data.collections.get("Characters") or sc.collection
import json
rigs = {o.name: o for o in chars if o.type == 'ARMATURE'}
def char_of(o):
    return next(r for r in rigs if o.name.startswith(r))
meta = {}
for rn, r in rigs.items():
    g = list(r.get("me_gesture", [200, 296]))
    meta[rn] = {"pos": list(r.matrix_world.translation), "yaw": r.rotation_euler.z, "line": r.get("me_line", "..."),
                "gesture_frames": g}
FRAMES = list(range(1, LOOP + 1)) + list(range(meta[next(iter(meta))]["gesture_frames"][0], meta[next(iter(meta))]["gesture_frames"][1] + 1))
sc.frame_set(1)
dg = bpy.context.evaluated_depsgraph_get()
baked = {}
for o in char_meshes:
    ev = o.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    me.transform(ev.matrix_world)
    cpos = Vector(meta[char_of(o)]["pos"]); cpos.z = 0.0
    me.transform(Matrix.Translation(-cpos))          # origin at the character's feet so she can turn
    n = bpy.data.objects.new(o.name.replace(".", "_") + "_baked", me)
    n.location = cpos
    n["me_char"] = char_of(o)
    cc.objects.link(n)
    n.shape_key_add(name="Basis", from_mix=False)
    for pg in me.polygons: pg.use_smooth = True
    baked[o.name] = (n, len(me.vertices))
for f in FRAMES:
    sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    for o in char_meshes:
        n, nv = baked[o.name]
        ev = o.evaluated_get(dg)
        eme = ev.to_mesh()
        if len(eme.vertices) != nv:
            print("vertex count mismatch", o.name, len(eme.vertices), nv); ev.to_mesh_clear(); continue
        co = np.empty(nv * 3, dtype=np.float32); eme.vertices.foreach_get("co", co)
        M = np.array(ev.matrix_world, dtype=np.float32)
        arr = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3] - np.array(n.location, dtype=np.float32)
        sk = n.shape_key_add(name=f"f{f:03d}", from_mix=False)
        sk.data.foreach_set("co", arr.astype(np.float32).ravel())
        ev.to_mesh_clear()
# shape-key index i has eval_time 10*i (Basis = 0): idle keys 1..LOOP, gesture keys follow
g0 = LOOP + 1; g1 = len(FRAMES)
for rn in meta:
    meta[rn]["gesture_eval"] = [10.0 * g0, 10.0 * g1]
sc["me_chars"] = json.dumps(meta)
print("character meta", meta)
for n, nv in baked.values():
    key = n.data.shape_keys
    key.use_relative = False
    key.eval_time = 10.0; key.keyframe_insert("eval_time", frame=1)
    key.eval_time = 10.0 * LOOP; key.keyframe_insert("eval_time", frame=LOOP)
    if key.animation_data and key.animation_data.action:
        for layer in key.animation_data.action.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
                        fc.modifiers.new('CYCLES')
for o in chars:
    bpy.data.objects.remove(o, do_unlink=True)
print("characters baked:", [n.name for n, _ in baked.values()])
# tangent-space normal maps on deforming meshes force per-frame tangent recomputation (measured:
# 12 fps with, 30 fps without), so strip NormalMap nodes from the character materials.
seen = set()
def strip_normalmaps(nt):
    if nt is None or nt.as_pointer() in seen: return
    seen.add(nt.as_pointer())
    for n in list(nt.nodes):
        if n.type == 'GROUP': strip_normalmaps(n.node_tree)
    for n in list(nt.nodes):
        if n.type == 'NORMAL_MAP': nt.nodes.remove(n)
for n, _ in baked.values():
    for m in n.data.materials:
        if m: strip_normalmaps(m.node_tree)
    n.vertex_groups.clear()
print("normal maps stripped from", len(seen), "node trees")
sc.frame_start = 1; sc.frame_end = LOOP

# ---------------------------------------------------------------- merge static geometry by material
def animated_chain(o):
    while o:
        if o.animation_data and o.animation_data.action: return True
        o = o.parent
    return False
static = []
for cn in ("Station", "Props", "Space"):
    c = bpy.data.collections.get(cn)
    if not c: continue
    for o in c.all_objects:
        if o.type in ('MESH', 'FONT', 'CURVE') and not animated_chain(o) and o.instance_type == 'NONE' and not (o.parent and o.parent.instance_type == 'VERTS') and "me_blind" not in o and "me_button" not in o:
            static.append(o)
groups = {}
for o in static:
    mats = o.data.materials
    key = mats[0].name if len(mats) == 1 and mats[0] else "__none__"
    groups.setdefault(key, []).append(o)
merged = bpy.data.collections.new("StaticMerged"); sc.collection.children.link(merged)
for key, objs in groups.items():
    sel(objs)
    bpy.ops.object.convert(target='MESH')
    objs = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    if not objs: continue
    sel(objs)
    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
    sel(objs)
    bpy.ops.object.join()
    j = bpy.context.view_layer.objects.active
    j.name = f"Static_{key}"
    for c in j.users_collection: c.objects.unlink(j)
    merged.objects.link(j)
print("merged groups:", len(groups))
# drop now-empty parent empties that have no children/animation
for o in list(bpy.data.objects):
    if o.type == 'EMPTY' and not o.children and not animated_chain(o) and o.name != "TexSpace":
        bpy.data.objects.remove(o, do_unlink=True)

# ---------------------------------------------------------------- cheaper EEVEE
ev = sc.eevee
ev.use_raytracing = True      # measured: no fps cost in the demo
ev.use_fast_gi = False
ev.use_shadows = True
ev.shadow_ray_count = 1
ev.shadow_step_count = 2
ev.shadow_resolution_scale = 0.5
ev.shadow_pool_size = '512'
ev.taa_samples = 4
# volumetric haze and the bloom compositor stay on: measured free on the GPU
keep = ("Hub_Top", "Sun", "Lounge_Top", "PlanetFill", "_Key", "Hub_Wash", "Corr_")
for o in bpy.data.objects:
    if o.type == 'LIGHT':
        o.data.use_shadow = any(k in o.name for k in keep)
for o in bpy.data.objects:
    for md in o.modifiers:
        if md.type == 'SUBSURF':
            md.levels = 0; md.render_levels = 1
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = 'RENDERED'
                    try: sp.shading.use_compositor = 'ALWAYS'
                    except Exception: pass
sc.render.fps = 60
out = os.path.join(HERE, "me_station_demo.blend")
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
print("SAVED", out, "objects:", len(bpy.data.objects))
