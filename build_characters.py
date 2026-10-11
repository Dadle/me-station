"""
Generate the two Asari characters with MPFB (MakeHuman Plugin for Blender).

Run:  blender -b --python build_characters.py            (builds both)
      blender -b --python build_characters.py -- Vessa   (one character)

Each character is written to chars/<Name>.blend inside a collection named <Name>,
containing the armature (MakeHuman "default" rig), textured body, eyes, eyelashes,
clothes and a bone-parented procedural head crest. Skin is a photo texture hue-shifted
to Asari blue so pores and shading survive.
"""
import bpy, bmesh, glob, os, sys, math, random
from mathutils import Vector, Matrix

from bl_ext.user_default.mpfb.services.humanservice import HumanService
from bl_ext.user_default.mpfb.services.animationservice import AnimationService

D = bpy.utils.extension_path_user('bl_ext.user_default.mpfb') + "/data"
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
OUT = os.path.join(HERE, "chars")
os.makedirs(OUT, exist_ok=True)
Dg = math.radians

CHARS = {
    "Vessa": dict(
        skin="young_caucasian_female", hue=0.055, sat=1.75, val=0.82, tint=(0.36, 0.62, 1.0), tint_fac=0.55,
        crest_color=(0.17, 0.30, 0.62),
        clothes=["tiomegamanx_skintight_body_suit_female", "punkduck_female_knee_boots"],
        pose="drednicolson_arms_akimbo", pose2="callharvey3d_standingnatural", gesture="callharvey3d_salute",
        line="Commander. Relay traffic out of Arcturus is up forty percent. Somebody is moving a fleet, and they are not telling the Council.",
        phenotype={"gender": 0.0, "age": 0.5, "muscle": 0.58, "weight": 0.45, "proportions": 0.8, "height": 0.66,
                   "cupsize": 0.5, "firmness": 0.7, "race": {"asian": 0.25, "caucasian": 0.5, "african": 0.25}},
        iris=(0.15, 0.55, 0.95), eyelashes="eyelashes02", eye_tex="blue",
    ),
    "Liora": dict(
        skin="toigo_light_skin_female_with_violet_makeup", hue=0.10, sat=1.6, val=0.78, tint=(0.52, 0.52, 1.0), tint_fac=0.5,
        crest_color=(0.26, 0.24, 0.62),
        clothes=["matcreator_mc-bodysuit-2021", "matcreator_mc-scifi-armor_jupiter7"],
        pose="callharvey3d_standingnatural", pose2="callharvey3d_curious", gesture="standing05",
        line="Oh! Sorry, I was lost in the nav data. Looking for the observation deck? Straight through the east corridor. You cannot miss the view.",
        phenotype={"gender": 0.0, "age": 0.55, "muscle": 0.5, "weight": 0.5, "proportions": 0.7, "height": 0.6,
                   "cupsize": 0.55, "firmness": 0.6, "race": {"asian": 0.5, "caucasian": 0.3, "african": 0.2}},
        iris=(0.55, 0.3, 0.9), eyelashes="eyelashes03", eye_tex="purple", armor_tint=(0.58, 0.63, 0.75),
    ),
}


def find(sub, name, ext):
    g = glob.glob(f"{D}/{sub}/{name}/*.{ext}")
    if not g:
        raise FileNotFoundError(f"{sub}/{name}/*.{ext}")
    return os.path.basename(g[0])


def ensure_bvh_addon():
    try:
        bpy.ops.preferences.addon_enable(module="io_anim_bvh")
    except Exception as ex:
        print("bvh addon:", ex)
    try:
        bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.io_anim_bvh")
    except Exception:
        pass


def tint_skin(body, cfg):
    """Insert hue shift + blue multiply between the diffuse texture and the rest of the skin group."""
    mat = body.data.materials[0]
    group = None
    for n in mat.node_tree.nodes:
        if n.type == 'GROUP':
            group = n.node_tree
    if group is None:
        print("no skin group"); return
    tex = group.nodes.get("DiffuseTexture")
    if tex is None:
        print("no diffuse texture node"); return
    targets = [(l.to_node, l.to_socket) for l in group.links if l.from_node == tex and l.from_socket.name == "Color"]
    hs = group.nodes.new("ShaderNodeHueSaturation")
    hs.inputs["Hue"].default_value = cfg["hue"]
    hs.inputs["Saturation"].default_value = cfg["sat"]
    hs.inputs["Value"].default_value = cfg["val"]
    mix = group.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs[0].default_value = cfg["tint_fac"]
    mix.inputs[7].default_value = (*cfg["tint"], 1)
    group.links.new(tex.outputs["Color"], hs.inputs["Color"])
    group.links.new(hs.outputs["Color"], mix.inputs[6])
    for node, sock in targets:
        group.links.new(mix.outputs[2], sock)
    # a little more sheen on the skin
    gnode = [n for n in mat.node_tree.nodes if n.type == 'GROUP'][0]
    for name, val in (("Roughness", 0.42), ("Clearcoat", 0.08), ("SSS strength", 0.6)):
        if name in gnode.inputs:
            gnode.inputs[name].default_value = val


def texture_eyes(eye_obj, texname):
    """Replace the procedural eye shader (renders black in EEVEE) with MakeHuman's photo eye texture."""
    g = glob.glob(f"{D}/eyes/materials/{texname}*.png") or glob.glob(f"{D}/eyes/materials/brown*.png")
    if not g:
        print("no eye texture"); return
    m = bpy.data.materials.new(f"{eye_obj.name}_eye")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(g[0], check_existing=True)
    nt.links.new(img.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.06
    p.inputs["Coat Weight"].default_value = 1.0
    nt.links.new(img.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 0.35
    p.inputs["Coat Roughness"].default_value = 0.02
    p.inputs["Specular IOR Level"].default_value = 0.7
    eye_obj.data.materials.clear()
    eye_obj.data.materials.append(m)


def set_eye_color(eye_obj, iris):
    m = eye_obj.data.materials[0]
    for n in m.node_tree.nodes:
        if n.type == 'GROUP':
            if "IrisMajorColor" in n.inputs:
                n.inputs["IrisMajorColor"].default_value = (*iris, 1)
                n.inputs["IrisMinorColor"].default_value = (iris[0] * 0.35, iris[1] * 0.35, iris[2] * 0.5, 1)
                n.inputs["PupilSize"].default_value = 0.28


def crest_material(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = 0.45
    p.inputs["Subsurface Weight"].default_value = 0.12
    p.inputs["Subsurface Radius"].default_value = (0.4, 0.5, 1.0)
    p.inputs["Coat Weight"].default_value = 0.1
    # skin-like mottling + fine bump
    tc = nt.nodes.new("ShaderNodeTexCoord")
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 60; n1.inputs["Detail"].default_value = 6
    n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 400; n2.inputs["Detail"].default_value = 4
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.4; cr.color_ramp.elements[0].color = (color[0] * 0.75, color[1] * 0.75, color[2] * 0.8, 1)
    cr.color_ramp.elements[1].position = 0.65; cr.color_ramp.elements[1].color = (min(1, color[0] * 1.15), min(1, color[1] * 1.15), min(1, color[2] * 1.1), 1)
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.15; bump.inputs["Distance"].default_value = 0.002
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    return m


def build_crest(name, body, rig, color):
    """Ridges that hug the real skull: directions are raycast from a point inside the head onto the
    evaluated body mesh, then offset outward. Seven ridges sweep from the forehead over the top and
    down the back; the outer ones flare out into short tapered tails (Asari crest)."""
    dg = bpy.context.evaluated_depsgraph_get()
    body_ev = body.evaluated_get(dg)
    head_b = rig.data.bones["head"]
    eye_l = rig.data.bones["eye.L"].head_local
    centre = Vector((0.0, head_b.head_local.y - 0.005, eye_l.z + 0.03))
    me = bpy.data.meshes.new(f"{name}_Crest")
    bm = bmesh.new()
    radii = []
    N = 13
    for phi_deg in (0, 9, -9, 18, -18, 27, -27, 36, -36, 44, -44):
        phi = Dg(phi_deg)
        lateral = abs(phi_deg) / 44.0
        prev = None
        for i in range(N):
            t = i / (N - 1)
            theta = Dg(-52 + 192 * t)   # forehead hairline -> crown -> nape
            d = Vector((math.sin(phi), math.cos(phi) * math.sin(theta), math.cos(phi) * math.cos(theta))).normalized()
            hit, loc, nrm, idx = body_ev.ray_cast(centre, d, distance=0.6)
            if not hit:
                loc = centre + d * 0.1
            # thick, overlapping ridges that merge into a scalloped crest; thin at the hairline
            r = 0.004 + 0.016 * math.sin(math.pi * min(1.0, 0.12 + t * 0.95)) * (1 - 0.15 * lateral)
            flare = 0.0
            if t > 0.74:
                k = (t - 0.74) / 0.26
                flare = k * (0.004 + 0.012 * lateral)
                r *= 1.0 - 0.5 * k
            pt = loc + d * (r * 0.35 + flare)
            if t > 0.74:
                k = (t - 0.74) / 0.26
                pt = Vector((pt.x * (1 + 0.15 * k * lateral), pt.y + 0.01 * k, pt.z - 0.02 * k * (1 + 0.3 * lateral)))
            v = bm.verts.new(pt); radii.append(max(0.004, r))
            if prev:
                bm.edges.new((prev, v))
            prev = v
    bm.to_mesh(me); bm.free()
    crest = bpy.data.objects.new(f"{name}_Crest", me)
    bpy.context.scene.collection.objects.link(crest)
    sk = crest.modifiers.new("Skin", 'SKIN'); sk.use_smooth_shade = True; sk.branch_smoothing = 0.0
    for i, svx in enumerate(me.skin_vertices[0].data):
        svx.radius = (radii[i] * 1.15, radii[i] * 0.9)
        svx.use_root = (i % N == 0)
    ss = crest.modifiers.new("Sub", 'SUBSURF'); ss.levels = 2; ss.render_levels = 3
    me.materials.append(crest_material(f"{name}_CrestSkin", color))
    # bone parent to head (compensate for tail-space parenting)
    crest.parent = rig
    crest.parent_type = 'BONE'
    crest.parent_bone = "head"
    crest.matrix_parent_inverse = (rig.matrix_world @ head_b.matrix_local @ Matrix.Translation((0, head_b.length, 0))).inverted()
    return crest


def build(name):
    cfg = CHARS[name]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ensure_bvh_addon()
    info = HumanService._create_default_human_info_dict()
    info["name"] = name
    info["phenotype"] = cfg["phenotype"]
    info["rig"] = "default"
    info["eyes"] = "high-poly.mhclo"
    info["eyelashes"] = find("eyelashes", cfg["eyelashes"], "mhclo")
    info["skin_mhmat"] = find("skins", cfg["skin"], "mhmat")
    info["skin_material_type"] = "ENHANCED_SSS"
    info["eyes_material_type"] = "PROCEDURAL_EYES"
    info["clothes"] = [find("clothes", c, "mhclo") for c in cfg["clothes"]]
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 2
    settings["material_instances"] = "NEVER"
    body = HumanService.deserialize_from_dict(info, settings)
    rig = body.parent
    rig.name = name
    print("BUILT", name, body.name, rig.name)

    tint_skin(body, cfg)
    for o in bpy.data.objects:
        if o.type == 'MESH' and o.name.endswith("high-poly"):
            texture_eyes(o, cfg["eye_tex"])
        if o.type == 'MESH':
            for md in o.modifiers:
                if md.type == 'SUBSURF':
                    md.levels = 1
                    md.render_levels = 2
            for p in o.data.polygons:
                p.use_smooth = True

    if cfg.get("armor_tint"):
        for o in bpy.data.objects:
            if o.type == 'MESH' and "armor" in o.name.lower():
                for m in o.data.materials:
                    nt = m.node_tree
                    p = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
                    if not p: continue
                    links = [l for l in nt.links if l.to_node == p and l.to_socket.name == "Base Color"]
                    for l in links:
                        mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
                        mix.inputs[0].default_value = 1.0; mix.inputs[7].default_value = (*cfg["armor_tint"], 1)
                        nt.links.new(l.from_socket, mix.inputs[6]); nt.links.new(mix.outputs[2], p.inputs["Base Color"])
                    p.inputs["Metallic"].default_value = 0.35
                    p.inputs["Roughness"].default_value = 0.45
                    p.inputs["Coat Weight"].default_value = 0.3
    crest = build_crest(name, body, rig, cfg["crest_color"])

    # idle = blend between two MakeHuman library poses (hold A, ease to B, hold B, ease back), 144-frame loop
    def capture():
        out = {}
        for b in rig.pose.bones:
            out[b.name] = b.rotation_quaternion.copy() if b.rotation_mode == 'QUATERNION' else b.rotation_euler.to_quaternion()
        return out
    poses = []
    for key in ("pose", "pose2"):
        bvh = glob.glob(f"{D}/poses/{cfg[key]}/*.bvh")
        if not bvh:
            print("no bvh for", cfg[key]); continue
        try:
            AnimationService.import_bvh_file_as_pose(rig, bvh[0])
            poses.append(capture()); print("POSED", name, cfg[key])
        except Exception as ex:
            print("POSE FAILED", cfg[key], ex)
    qg = None
    gb = glob.glob(f"{D}/poses/{cfg['gesture']}/*.bvh")
    if gb:
        try:
            AnimationService.import_bvh_file_as_pose(rig, gb[0]); qg = capture(); print("POSED", name, cfg["gesture"])
        except Exception as ex:
            print("POSE FAILED", cfg["gesture"], ex)
    if poses:
        qa = poses[0]; qb = poses[-1]
        for b in rig.pose.bones:
            b.rotation_mode = 'QUATERNION'
        keys = [(1, qa), (44, qa), (76, qb), (112, qb), (145, qa)]
        if qg:
            # gesture clip (frames 200-296): ease in, hold with a little wave/nod motion, ease out
            from mathutils import Quaternion as Q
            def variant(src, amount):
                out = dict(src)
                for bn in ("lowerarm01.R", "lowerarm02.R", "lowerarm01.L", "lowerarm02.L"):
                    if bn in out: out[bn] = out[bn] @ Q((0, 0, 1), amount)
                if "head" in out: out["head"] = out["head"] @ Q((1, 0, 0), -amount * 0.6)
                return out
            keys += [(200, qa), (222, qg), (236, variant(qg, 0.14)), (250, qg), (264, variant(qg, 0.14)), (278, qg), (296, qa)]
        for frame, src in keys:
            for b in rig.pose.bones:
                b.rotation_quaternion = src[b.name]
                b.keyframe_insert("rotation_quaternion", frame=frame)
        rig["me_line"] = cfg["line"]
        rig["me_gesture"] = [200, 296]
        act = rig.animation_data.action
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        for kp in fc.keyframe_points:
                            kp.interpolation = 'BEZIER'; kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
                        fc.modifiers.new('CYCLES')
        bpy.context.scene.frame_set(1)

    # collect everything in a collection named after the character
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    for o in list(bpy.data.objects):
        if o.type in ('MESH', 'ARMATURE', 'EMPTY'):
            for c in o.users_collection:
                c.objects.unlink(o)
            coll.objects.link(o)
    rig.data.display_type = 'STICK'
    out = os.path.join(OUT, f"{name}.blend")
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    print("SAVED", out)


if __name__ == "__main__":
    names = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else list(CHARS)
    for n in names:
        build(n)
