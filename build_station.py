"""
Mass Effect–style space station interior, generated procedurally for Blender 5.x.  (v2: PBR, props, fog, bloom)

Run:  blender -b --python build_station.py -- /path/to/output.blend

Requires (already in this repo):
  downloads/textures/<Id>/<Id>_2K-JPG_*.jpg      ambientCG CC0 PBR sets
  downloads/models/<id>/<id>.blend + textures/   Poly Haven CC0 props
  chars/Vessa.blend, chars/Liora.blend           MPFB characters (build_characters.py)
"""
import bpy, bmesh, math, random, sys, os, glob
from mathutils import Vector, Euler, Matrix, Quaternion

random.seed(7)
TAU = math.tau
D = math.radians
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
TEXDIR = os.path.join(HERE, "downloads", "textures")
MODELDIR = os.path.join(HERE, "downloads", "models")
CHARDIR = os.path.join(HERE, "chars")

# ----------------------------------------------------------------------------
# Scene reset
# ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "Station"
scene.render.engine = 'BLENDER_EEVEE'
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 144
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

ev = scene.eevee
ev.use_shadows = True
ev.use_raytracing = True
ev.shadow_ray_count = 2
ev.shadow_step_count = 4
ev.shadow_pool_size = '1024'
ev.taa_samples = 16
ev.taa_render_samples = 64
ev.use_fast_gi = True
ev.volumetric_tile_size = '8'
ev.volumetric_samples = 48
ev.use_volume_custom_range = True
ev.volumetric_start = 0.1
ev.volumetric_end = 80.0
ev.use_volumetric_shadows = True
scene.view_settings.view_transform = 'AgX'
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except Exception as ex:
    print("look:", ex)

COLL = {}
def coll(name):
    if name not in COLL:
        c = bpy.data.collections.new(name)
        scene.collection.children.link(c)
        COLL[name] = c
    return COLL[name]

for n in ("Station", "Props", "Holograms", "Characters", "Lights", "Space", "Camera", "Models"):
    coll(n)

def action_fcurves(act):
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out.extend(cb.fcurves)
    return out

def link(ob, c="Station"):
    for uc in ob.users_collection:
        uc.objects.unlink(ob)
    coll(c).objects.link(ob)
    return ob

# World-space reference for box-projected textures (so scaled objects don't stretch textures)
TEXSPACE = bpy.data.objects.new("TexSpace", None)
scene.collection.objects.link(TEXSPACE)
TEXSPACE.hide_viewport = True; TEXSPACE.hide_render = True

# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
MATS = {}
IMG_CACHE = {}
def load_img(path, srgb):
    key = (path, srgb)
    if key in IMG_CACHE:
        return IMG_CACHE[key]
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
    IMG_CACHE[key] = im
    return im

def tex_path(tex_id, kind):
    g = glob.glob(os.path.join(TEXDIR, tex_id, f"*_{kind}.jpg"))
    return g[0] if g else None

def mat(name, color, metallic=0.0, rough=0.5, emit=None, estr=0.0, alpha=1.0,
        blended=False, coat=0.0, spec=0.5):
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Specular IOR Level"].default_value = spec
    p.inputs["Alpha"].default_value = alpha
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = estr
    if blended or alpha < 1:
        m.surface_render_method = 'BLENDED'
        m.use_transparent_shadow = True
    MATS[name] = m
    return m

def pbr(name, tex_id, tile=1.0, tint=None, rough=1.0, metallic=None, bump=0.5, coat=0.0, spec=0.5, emit=None, estr=0.0):
    """PBR material from an ambientCG set, box-projected in world space (no UVs needed)."""
    if name in MATS:
        return MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Coat Weight"].default_value = coat
    p.inputs["Specular IOR Level"].default_value = spec
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = estr
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.object = TEXSPACE
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1 / tile)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    def img_node(kind, srgb):
        path = tex_path(tex_id, kind)
        if not path:
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = load_img(path, srgb)
        n.projection = 'BOX'; n.projection_blend = 0.3
        n.interpolation = 'Linear'
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        return n
    col = img_node("Color", True)
    if col:
        if tint:
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
            mix.inputs[0].default_value = 1.0; mix.inputs[7].default_value = (*tint, 1)
            nt.links.new(col.outputs["Color"], mix.inputs[6])
            nt.links.new(mix.outputs[2], p.inputs["Base Color"])
        else:
            nt.links.new(col.outputs["Color"], p.inputs["Base Color"])
    elif tint:
        p.inputs["Base Color"].default_value = (*tint, 1)
    rg = img_node("Roughness", False)
    if rg:
        mm = nt.nodes.new("ShaderNodeMath"); mm.operation = 'MULTIPLY'; mm.inputs[1].default_value = rough
        mm.use_clamp = True
        nt.links.new(rg.outputs["Color"], mm.inputs[0])
        nt.links.new(mm.outputs[0], p.inputs["Roughness"])
    else:
        p.inputs["Roughness"].default_value = min(1.0, 0.5 * rough)
    if metallic is None:
        mt = img_node("Metalness", False)
        if mt:
            nt.links.new(mt.outputs["Color"], p.inputs["Metallic"])
    else:
        p.inputs["Metallic"].default_value = metallic
    nm = img_node("NormalGL", False)
    if nm:
        nmap = nt.nodes.new("ShaderNodeNormalMap"); nmap.inputs["Strength"].default_value = bump
        nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], p.inputs["Normal"])
    MATS[name] = m
    return m

ORANGE = (1.0, 0.42, 0.08)
CYAN = (0.25, 0.75, 1.0)
BLUEDEEP = (0.10, 0.35, 1.0)

M_HULL    = pbr("HullDark", "Metal046A", tile=2.0, tint=(0.72, 0.75, 0.82), rough=1.0, bump=0.6)
M_HULL2   = pbr("HullCeiling", "Metal061A", tile=2.5, tint=(0.6, 0.62, 0.68), rough=1.1, bump=0.5)
M_PANEL   = pbr("PanelWhite", "Plastic010", tile=1.4, tint=(0.88, 0.9, 0.94), rough=0.9, metallic=0.05, bump=0.4, coat=0.5)
M_PANEL2  = pbr("PanelGrey", "Plastic004", tile=1.4, tint=(0.55, 0.58, 0.63), rough=1.0, metallic=0.1, bump=0.4)
M_PANELD  = pbr("PanelDark", "Plastic013A", tile=1.0, tint=(0.32, 0.34, 0.40), rough=0.8, metallic=0.2, bump=0.3, coat=0.3)
M_FLOOR   = pbr("FloorPlates", "MetalPlates006", tile=1.6, tint=(0.8, 0.82, 0.9), rough=1.0, bump=0.8)
M_FLOOR2  = pbr("FloorDiamond", "DiamondPlate008C", tile=1.0, tint=(0.45, 0.47, 0.52), rough=1.0, bump=0.8)
M_GRATE   = pbr("FloorGrate", "DiamondPlate008C", tile=0.5, tint=(0.3, 0.31, 0.35), rough=1.0, bump=1.0)
M_TRIM    = pbr("TrimRubber", "Rubber001", tile=1.0, tint=(0.35, 0.35, 0.38), rough=1.0, metallic=0.0, bump=0.5)
M_RAIL    = pbr("RailSteel", "Metal009", tile=1.0, tint=(0.8, 0.82, 0.86), rough=0.9, metallic=1.0, bump=0.3)
M_PIPE    = pbr("PipeSteel", "Metal061A", tile=1.0, tint=(0.55, 0.56, 0.6), rough=1.0, bump=0.5)
M_SEAT    = pbr("SeatLeather", "Leather030", tile=0.8, tint=(0.35, 0.42, 0.75), rough=1.0, metallic=0.0, bump=0.6)
M_CUSHION = pbr("SeatFabric", "Fabric031", tile=0.5, tint=(0.3, 0.36, 0.6), rough=1.0, metallic=0.0, bump=0.6)
M_CRATE   = pbr("CrateBrushed", "Metal032", tile=1.0, tint=(0.72, 0.74, 0.78), rough=1.0, bump=0.3)
M_CRATE2  = pbr("CrateDark", "Metal046A", tile=1.0, tint=(0.35, 0.37, 0.42), rough=1.0, bump=0.6)
M_DOOR    = pbr("DoorMetal", "Metal028", tile=1.5, tint=(0.75, 0.77, 0.85), rough=1.0, bump=0.5)
M_CARBON  = pbr("Carbon", "Fabric004", tile=0.4, tint=(0.5, 0.52, 0.6), rough=0.7, metallic=0.4, bump=0.5, coat=0.6)
M_GLOW_C  = mat("GlowCyan", CYAN, 0, 0.5, CYAN, 12.0)
M_GLOW_O  = mat("GlowOrange", ORANGE, 0, 0.5, ORANGE, 10.0)
M_GLOW_W  = mat("GlowWhite", (1, 0.97, 0.9), 0, 0.5, (1, 0.97, 0.9), 8.0)
M_GLOW_B  = mat("GlowBlueSoft", BLUEDEEP, 0, 0.5, BLUEDEEP, 4.0)
M_GLOW_R  = mat("GlowRed", (1, 0.15, 0.08), 0, 0.5, (1, 0.15, 0.08), 8.0)
M_GLOW_G  = mat("GlowGreen", (0.2, 1, 0.4), 0, 0.5, (0.2, 1, 0.4), 6.0)
_pr = M_GLOW_R.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
for _f, _v in ((1, 1.5), (18, 10.0), (36, 1.5)):
    _pr.default_value = _v; _pr.keyframe_insert("default_value", frame=_f)
for _fc in action_fcurves(M_GLOW_R.node_tree.animation_data.action): _fc.modifiers.new('CYCLES')
M_HOLO_O  = mat("HoloOrange", (0.015, 0.02, 0.035), 0, 0.3, ORANGE, 0.07, alpha=0.86, blended=True)
M_HOLO_C  = mat("HoloCyan", (0.012, 0.02, 0.04), 0, 0.3, CYAN, 0.07, alpha=0.86, blended=True)
M_HOLO_K  = mat("HoloBacking", (0.01, 0.012, 0.02), 0, 0.4, alpha=0.85, blended=True)
M_GLASS   = mat("Glass", (0.75, 0.85, 1.0), 0.0, 0.02, alpha=0.05, blended=True)
M_PLANET  = mat("Planet", (0.15, 0.45, 0.75), 0, 0.9)
M_CABLE_K = mat("CableBlack", (0.02, 0.02, 0.025), 0, 0.5)
M_VENT_K  = mat("VentBlack", (0.01, 0.01, 0.012), 0.3, 0.8)

def hazard_material():
    m = bpy.data.materials.new("HazardStripes")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.object = TEXSPACE
    mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Rotation"].default_value = (0, 0, D(45)); mp.inputs["Scale"].default_value = (10, 10, 10)
    wv = nt.nodes.new("ShaderNodeTexWave"); wv.wave_type = 'BANDS'; wv.bands_direction = 'X'; wv.wave_profile = 'SAW'
    wv.inputs["Scale"].default_value = 1.0
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.interpolation = 'CONSTANT'
    cr.color_ramp.elements[0].position = 0.0; cr.color_ramp.elements[0].color = (0.9, 0.35, 0.05, 1)
    cr.color_ramp.elements[1].position = 0.5; cr.color_ramp.elements[1].color = (0.05, 0.05, 0.06, 1)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], wv.inputs["Vector"])
    nt.links.new(wv.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.6
    MATS["HazardStripes"] = m
    return m
M_HAZARD = hazard_material()

def screen_material(name, color, strength=5.0):
    """UI screen: quantised data cells that scroll, a header band, side bar and faint grid."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (0.01, 0.012, 0.02, 1)
    p.inputs["Roughness"].default_value = 0.2
    p.inputs["Coat Weight"].default_value = 1.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])
    def mathn(op, a=None, b=None, bval=None):
        n = nt.nodes.new("ShaderNodeMath"); n.operation = op
        if a is not None: nt.links.new(a, n.inputs[0])
        if b is not None: nt.links.new(b, n.inputs[1])
        if bval is not None: n.inputs[1].default_value = bval
        return n.outputs[0]
    X, Z = sep.outputs["X"], sep.outputs["Z"]
    NX, NZ = 18.0, 14.0
    cx = mathn('FLOOR', mathn('MULTIPLY', X, bval=NX))
    scroll = nt.nodes.new("ShaderNodeValue"); scroll.name = "Scroll"; scroll.outputs[0].default_value = 0.0
    cz = mathn('FLOOR', mathn('ADD', mathn('MULTIPLY', Z, bval=NZ), scroll.outputs[0]))
    comb = nt.nodes.new("ShaderNodeCombineXYZ"); nt.links.new(cx, comb.inputs["X"]); nt.links.new(cz, comb.inputs["Y"])
    wnz = nt.nodes.new("ShaderNodeTexWhiteNoise"); wnz.noise_dimensions = '3D'; nt.links.new(comb.outputs["Vector"], wnz.inputs["Vector"])
    cell = mathn('GREATER_THAN', wnz.outputs["Value"], bval=0.6)
    def pad(sock, n, lo, hi):
        fr = mathn('FRACT', mathn('MULTIPLY', sock, bval=n))
        return mathn('MULTIPLY', mathn('GREATER_THAN', fr, bval=lo), mathn('LESS_THAN', fr, bval=hi))
    cells = mathn('MULTIPLY', mathn('MULTIPLY', cell, pad(X, NX, 0.08, 0.92)), pad(Z, NZ, 0.28, 0.72))
    body = mathn('MULTIPLY', cells, mathn('LESS_THAN', Z, bval=0.86))
    hdr = mathn('MULTIPLY', mathn('GREATER_THAN', Z, bval=0.86), mathn('LESS_THAN', Z, bval=0.875))
    side = mathn('MULTIPLY', mathn('LESS_THAN', X, bval=0.035), mathn('LESS_THAN', Z, bval=0.86))
    grid = nt.nodes.new("ShaderNodeTexBrick"); grid.inputs["Scale"].default_value = 1.0
    grid.inputs["Mortar Size"].default_value = 0.006; grid.inputs["Brick Width"].default_value = 1.0 / 6; grid.inputs["Row Height"].default_value = 1.0 / 4
    grid.inputs["Color1"].default_value = (0, 0, 0, 1); grid.inputs["Color2"].default_value = (0, 0, 0, 1); grid.inputs["Mortar"].default_value = (1, 1, 1, 1); grid.offset = 0.0
    gxz = nt.nodes.new("ShaderNodeCombineXYZ"); nt.links.new(X, gxz.inputs["X"]); nt.links.new(Z, gxz.inputs["Y"])
    nt.links.new(gxz.outputs["Vector"], grid.inputs["Vector"])
    total = mathn('ADD', mathn('ADD', mathn('ADD', body, mathn('MULTIPLY', hdr, bval=0.9)), mathn('MULTIPLY', side, bval=0.9)), mathn('MULTIPLY', grid.outputs["Fac"], bval=0.12))
    p.inputs["Emission Color"].default_value = (*color, 1)
    nt.links.new(mathn('MULTIPLY', total, bval=strength), p.inputs["Emission Strength"])
    scroll.outputs[0].default_value = 0.0
    scroll.outputs[0].keyframe_insert("default_value", frame=1)
    scroll.outputs[0].default_value = 20.0
    scroll.outputs[0].keyframe_insert("default_value", frame=600)
    if nt.animation_data and nt.animation_data.action:
        for fc in action_fcurves(nt.animation_data.action):
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
            fc.modifiers.new('CYCLES')
    return m
M_SCREEN_O = screen_material("ScreenOrange", ORANGE, 4.0)
M_SCREEN_C = screen_material("ScreenCyan", CYAN, 4.0)

def planet_pattern(m):
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 3.0; n1.inputs["Detail"].default_value = 10.0
    n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 9.0; n2.inputs["Detail"].default_value = 8.0; n2.inputs["Roughness"].default_value = 0.7
    cr = nt.nodes.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position = 0.40; cr.color_ramp.elements[0].color = (0.06, 0.25, 0.65, 1)
    cr.color_ramp.elements[1].position = 0.52; cr.color_ramp.elements[1].color = (0.15, 0.5, 0.8, 1)
    for pos, col in ((0.56, (0.7, 0.62, 0.42, 1)), (0.63, (0.22, 0.4, 0.2, 1)), (0.72, (0.45, 0.42, 0.3, 1)), (0.8, (0.92, 0.94, 0.98, 1))):
        e = cr.color_ramp.elements.new(pos); e.color = col
    clouds = nt.nodes.new("ShaderNodeValToRGB")
    clouds.color_ramp.elements[0].position = 0.6; clouds.color_ramp.elements[0].color = (0, 0, 0, 1)
    clouds.color_ramp.elements[1].position = 0.78; clouds.color_ramp.elements[1].color = (0.9, 0.9, 0.9, 1)
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MIX'
    mix.inputs[7].default_value = (0.95, 0.96, 1.0, 1)
    nt.links.new(n1.outputs["Fac"], cr.inputs["Fac"])
    nt.links.new(n2.outputs["Fac"], clouds.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], mix.inputs[6])
    nt.links.new(clouds.outputs["Color"], mix.inputs[0])
    nt.links.new(mix.outputs[2], p.inputs["Base Color"])
planet_pattern(M_PLANET)

def holo_pattern(m):
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.object = TEXSPACE
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = 'BANDS'; wv.bands_direction = 'Z'
    wv.inputs["Scale"].default_value = 60.0
    mx = nt.nodes.new("ShaderNodeMath"); mx.operation = 'MULTIPLY_ADD'
    mx.inputs[1].default_value = 0.12; mx.inputs[2].default_value = p.inputs["Alpha"].default_value
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    nt.links.new(wv.outputs["Fac"], mx.inputs[0])
    nt.links.new(mx.outputs[0], p.inputs["Alpha"])
holo_pattern(M_HOLO_O); holo_pattern(M_HOLO_C)

# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------
def set_smooth(ob, smooth=True):
    for p in ob.data.polygons:
        p.use_smooth = smooth

def box(name, loc, size, m, rot=(0, 0, 0), bevel=0.0, c="Station", parent=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.scale = size
    ob.rotation_euler = rot
    me.materials.append(m)
    if bevel > 0:
        md = ob.modifiers.new("Bevel", 'BEVEL')
        md.width = bevel; md.segments = 3; md.limit_method = 'ANGLE'
        md.use_clamp_overlap = True
    link(ob, c)
    if parent:
        ob.parent = parent
    return ob

def cyl(name, loc, r, h, m, verts=32, rot=(0, 0, 0), c="Station", parent=None, smooth=True, rz=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=h)
    if rz:
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(rz, 3, 'Z'))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc; ob.rotation_euler = rot
    me.materials.append(m)
    link(ob, c)
    if smooth and verts > 12:
        set_smooth(ob)
    if parent:
        ob.parent = parent
    return ob

def sphere(name, loc, r, m, c="Station", parent=None, seg=32, ring=16, scale=(1, 1, 1)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=r)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc; ob.scale = scale
    me.materials.append(m)
    link(ob, c)
    set_smooth(ob)
    if parent:
        ob.parent = parent
    return ob

def torus(name, loc, R, r, m, c="Station", parent=None, rot=(0, 0, 0), segs=64, rings=12):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = []
    for i in range(segs):
        a = TAU * i / segs
        for j in range(rings):
            b = TAU * j / rings
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b)
            verts.append(bm.verts.new((x, y, z)))
    for i in range(segs):
        for j in range(rings):
            v1 = verts[i * rings + j]
            v2 = verts[((i + 1) % segs) * rings + j]
            v3 = verts[((i + 1) % segs) * rings + (j + 1) % rings]
            v4 = verts[i * rings + (j + 1) % rings]
            bm.faces.new((v1, v2, v3, v4))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc; ob.rotation_euler = rot
    me.materials.append(m)
    link(ob, c)
    set_smooth(ob)
    if parent:
        ob.parent = parent
    return ob

def polyprism(name, pts2d, z0, z1, m, c="Station", parent=None, loc=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bot = [bm.verts.new((x, y, z0)) for x, y in pts2d]
    top = [bm.verts.new((x, y, z1)) for x, y in pts2d]
    bm.faces.new(bot[::-1])
    bm.faces.new(top)
    n = len(pts2d)
    for i in range(n):
        bm.faces.new((bot[i], bot[(i + 1) % n], top[(i + 1) % n], top[i]))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    me.materials.append(m)
    link(ob, c)
    if parent:
        ob.parent = parent
    return ob

def shutter(name, loc, w, z0, z1, rotz, parent, slats=4, lead_bottom=True, c="Station"):
    """One shutter half: `slats` louvre boxes with grooves, side rails, and an emissive leading edge.
    Built in pane-local space (x along the pane, y depth, z up); object origin at z=0 so a z offset slides it."""
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    def add_box(cx, cy, cz, sx, sy, sz, mi):
        r = bmesh.ops.create_cube(bm, size=1.0)
        vs = r["verts"]
        bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=vs)
        bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=vs)
        for f in bm.faces:
            if f.material_index == 0 and all(v in vs for v in f.verts): f.material_index = mi
    h = (z1 - z0) / slats
    for i in range(slats):
        zc = z0 + h * (i + 0.5)
        add_box(0, 0, zc, w, 0.05, h - 0.03, 0)
        add_box(0, -0.03, zc + h * 0.25, w - 0.1, 0.012, 0.012, 1)        # subtle groove highlight
    for sx in (-1, 1):
        add_box(sx * (w / 2 - 0.03), 0, (z0 + z1) / 2, 0.06, 0.08, z1 - z0, 2)
    lead_z = z0 + 0.015 if lead_bottom else z1 - 0.015
    add_box(0, 0, lead_z, w, 0.09, 0.03, 1)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location = loc; ob.rotation_euler = (0, 0, rotz)
    me.materials.append(M_PANELD); me.materials.append(M_GLOW_O); me.materials.append(M_TRIM)
    md = ob.modifiers.new("Bevel", 'BEVEL'); md.width = 0.008; md.segments = 2; md.limit_method = 'ANGLE'
    link(ob, c); ob.parent = parent
    return ob

def empty(name, loc=(0, 0, 0), rot=(0, 0, 0), c="Station"):
    ob = bpy.data.objects.new(name, None)
    ob.location = loc; ob.rotation_euler = rot
    ob.empty_display_size = 0.5
    link(ob, c)
    return ob

def text(name, body, loc, rot, size, m, c="Props", parent=None, align='CENTER', extrude=0.004):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = 'CENTER'
    cu.materials.append(m)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc; ob.rotation_euler = rot
    link(ob, c)
    if parent:
        ob.parent = parent
    return ob

def light(name, kind, loc, color, energy, size=1.0, rot=(0, 0, 0), c="Lights", parent=None, radius=0.3, spot=70):
    la = bpy.data.lights.new(name, kind)
    la.color = color
    la.energy = energy
    if kind == 'AREA':
        la.shape = 'RECTANGLE' if isinstance(size, tuple) else 'SQUARE'
        if isinstance(size, tuple):
            la.size, la.size_y = size
        else:
            la.size = size
    elif kind == 'POINT':
        la.shadow_soft_size = radius
    elif kind == 'SPOT':
        la.shadow_soft_size = radius
        la.spot_size = D(spot)
        la.spot_blend = 0.5
    ob = bpy.data.objects.new(name, la)
    ob.location = loc; ob.rotation_euler = rot
    link(ob, c)
    if parent:
        ob.parent = parent
    return ob

def pipe_run(name, p0, p1, r, m=M_PIPE, parent=None, c="Props", flanges=0.0):
    v = Vector(p1) - Vector(p0)
    L = v.length
    mid = (Vector(p0) + Vector(p1)) / 2
    ob = cyl(name, mid, r, L, m, verts=16, c=c, parent=parent)
    rot = v.to_track_quat('Z', 'Y').to_euler()
    ob.rotation_euler = rot
    if flanges > 0:
        n = int(L // flanges)
        for k in range(1, n + 1):
            t = (k * flanges) / L
            if t >= 0.98: break
            pos = Vector(p0) + v * t
            torus(f"{name}_fl{k}", pos, r * 1.05, r * 0.35, M_TRIM, c=c, parent=parent, rot=rot, segs=20, rings=8)
    return ob

def vent(name, loc, rot, w, h, parent=None, slats=6, c="Props"):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("frame", (0, 0, 0), (w, 0.06, h), M_TRIM, bevel=0.01, parent=e, c=c)
    box("back", (0, 0.015, 0), (w - 0.08, 0.02, h - 0.08), M_VENT_K, parent=e, c=c)
    for k in range(slats):
        z = -h / 2 + 0.06 + (h - 0.12) * (k + 0.5) / slats
        box(f"slat{k}", (0, -0.02, z), (w - 0.1, 0.03, 0.025), M_PANEL2, rot=(D(35), 0, 0), parent=e, c=c)
    return e

def sconce(name, loc, rot, parent=None, m_glow=M_GLOW_W, c="Props"):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("housing", (0, 0, 0), (0.16, 0.1, 0.5), M_TRIM, bevel=0.015, parent=e, c=c)
    box("lens", (0, -0.045, 0), (0.08, 0.02, 0.42), m_glow, parent=e, c=c)
    return e

def cable_tray(name, p0, p1, w, parent=None, c="Props"):
    v = Vector(p1) - Vector(p0); L = v.length; mid = (Vector(p0) + Vector(p1)) / 2
    rot = v.to_track_quat('X', 'Z').to_euler()
    box(name, mid, (L, w, 0.03), M_PIPE, rot=rot, parent=parent, c=c)
    for s in (-1, 1):
        off = Vector((0, s * w / 2, 0.04)); off.rotate(rot)
        box(f"{name}_lip{s}", mid + off, (L, 0.03, 0.08), M_PIPE, rot=rot, parent=parent, c=c)
    for k, (yy, rr, mm) in enumerate(((-w * 0.3, 0.012, mat("CableRed", (0.5, 0.05, 0.03), 0, 0.5)), (0.0, 0.015, M_CABLE_K), (w * 0.3, 0.01, mat("CableBlue", (0.05, 0.1, 0.45), 0, 0.5)))):
        off = Vector((0, yy, 0.03)); off.rotate(rot)
        cb = cyl(f"{name}_cable{k}", mid + off, rr, L * 0.98, mm, verts=10, parent=parent, c=c)
        cb.rotation_euler = v.to_track_quat('Z', 'Y').to_euler()

def wall_screen(name, loc, rot, w, h, m_screen=M_SCREEN_O, parent=None, c="Props", title=None):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("frame", (0, 0, 0), (w + 0.12, 0.08, h + 0.12), M_TRIM, bevel=0.015, parent=e, c=c)
    box("screen", (0, -0.045, 0), (w, 0.01, h), m_screen, parent=e, c=c)
    glow = M_GLOW_O if m_screen is M_SCREEN_O else M_GLOW_C
    box("bar", (0, -0.052, h / 2 - 0.03), (w - 0.1, 0.004, 0.02), glow, parent=e, c=c)
    if title:
        text(f"{name}_title", title, (-w / 2 + 0.06, -0.056, h / 2 - 0.1), (D(90), 0, 0), 0.075, glow, parent=e, c=c, align='LEFT', extrude=0.0)
        text(f"{name}_sub", "DECK 02  //  LIVE FEED  //  SA-7731", (-w / 2 + 0.06, -0.056, h / 2 - 0.165), (D(90), 0, 0), 0.03, M_GLOW_W, parent=e, c=c, align='LEFT', extrude=0.0)
        box(f"{name}_pill", (w / 2 - 0.16, -0.054, h / 2 - 0.1), (0.2, 0.004, 0.05), M_GLOW_G, parent=e, c=c)
        text(f"{name}_pilltxt", "ONLINE", (w / 2 - 0.16, -0.058, h / 2 - 0.1), (D(90), 0, 0), 0.03, mat("InkDark", (0.01, 0.01, 0.012), 0, 0.6), parent=e, c=c, extrude=0.0)
    return e

def locker(name, loc, rot, parent=None, c="Props"):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("body", (0, 0, 1.0), (0.9, 0.45, 2.0), M_PANEL2, bevel=0.02, parent=e, c=c)
    for s in (-1, 1):
        box(f"door{s}", (s * 0.225, -0.235, 1.0), (0.42, 0.02, 1.9), M_PANEL, bevel=0.01, parent=e, c=c)
        box(f"handle{s}", (s * 0.06, -0.26, 1.05), (0.02, 0.02, 0.2), M_RAIL, parent=e, c=c)
        box(f"led{s}", (s * 0.225, -0.248, 1.85), (0.2, 0.004, 0.02), M_GLOW_C if s > 0 else M_GLOW_O, parent=e, c=c)
    box("vents", (0, -0.248, 0.25), (0.7, 0.004, 0.15), M_TRIM, parent=e, c=c)
    return e

def emergency_light(name, loc, rot, parent=None, c="Props"):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("housing", (0, 0, 0), (0.3, 0.12, 0.14), M_TRIM, bevel=0.015, parent=e, c=c)
    box("lens", (0, -0.055, 0), (0.22, 0.02, 0.08), M_GLOW_R, parent=e, c=c)
    return e

def status_panel(name, loc, rot, parent=None, c="Props", ok=True):
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("plate", (0, 0, 0), (0.3, 0.05, 0.45), M_TRIM, bevel=0.01, parent=e, c=c)
    for k in range(3):
        box(f"led{k}", (0, -0.03, 0.14 - 0.12 * k), (0.2, 0.01, 0.07), (M_GLOW_G if ok else M_GLOW_R) if k == 0 else M_GLOW_C, parent=e, c=c)
    return e

MODEL_CACHE = {}
def import_model(model_id, name, loc, rotz, height=None, scale=None, c="Models", parent=None):
    """Append all meshes from a Poly Haven .blend (first time), reuse mesh data afterwards."""
    path = os.path.join(MODELDIR, model_id, f"{model_id}.blend")
    if not os.path.exists(path):
        print("missing model", model_id); return None
    if model_id not in MODEL_CACHE:
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = [n for n in src.objects]
        objs = [o for o in dst.objects if o is not None and o.type == 'MESH']
        MODEL_CACHE[model_id] = objs
        for o in objs:
            o.name = f"{model_id}_{o.name}_src"
    srcs = MODEL_CACHE[model_id]
    e = empty(name, loc, (0, 0, rotz), c=c)
    if parent: e.parent = parent
    pts = []
    for o in srcs:
        for cb in o.bound_box:
            pts.append(o.matrix_world @ Vector(cb))
    zmin = min(p.z for p in pts); zmax = max(p.z for p in pts)
    s = scale or (height / max(1e-6, zmax - zmin) if height else 1.0)
    for o in srcs:
        inst = bpy.data.objects.new(f"{name}_{o.name}", o.data)
        inst.matrix_world = o.matrix_world
        inst.location = (o.matrix_world.translation.x * s, o.matrix_world.translation.y * s, (o.matrix_world.translation.z - zmin) * s)
        inst.scale = (o.scale.x * s, o.scale.y * s, o.scale.z * s)
        inst.rotation_euler = o.rotation_euler
        for md in o.modifiers:
            if md.type == 'SUBSURF':
                nm = inst.modifiers.new(md.name, md.type)
                nm.levels = min(md.levels, 1); nm.render_levels = min(md.render_levels, 2)
        link(inst, c)
        inst.parent = e
    return e

# ----------------------------------------------------------------------------
# HUB (octagonal CIC)
# ----------------------------------------------------------------------------
HUB_R = 9.0
HUB_H = 5.0
WALL_T = 0.4
CORR_W = 3.6
CORR_H = 3.6
SEG_LEN = 2 * HUB_R * math.tan(D(22.5))
OPENINGS = {0: "lounge", 2: "dock", 4: "airlock"}
hub = empty("Hub")

circum = HUB_R / math.cos(D(22.5))
octpts = [(circum * math.cos(D(22.5 + 45 * i)), circum * math.sin(D(22.5 + 45 * i))) for i in range(8)]
polyprism("Hub_Floor", octpts, -0.3, 0.0, M_FLOOR, parent=hub)
polyprism("Hub_Ceiling", octpts, HUB_H, HUB_H + 0.3, M_HULL2, parent=hub)

def wall_segment(parent, name, length, height, has_opening, open_w, open_h, base_loc, rotz, light_floor=True, detail=True):
    """ME-style wall: dark backing, white inset panels, light strips, vents, sconces. Local X along wall, +Y into room."""
    seg = empty(name, base_loc, (0, 0, rotz))
    seg.parent = parent
    T = WALL_T
    def band(nm, x0, x1, z0, z1, depth, m, bevel=0.02):
        return box(f"{name}_{nm}", ((x0 + x1) / 2, -T / 2 + depth / 2, (z0 + z1) / 2), (x1 - x0, depth, z1 - z0), m, bevel=bevel, parent=seg)
    halves = [(-length / 2, length / 2)]
    if has_opening:
        halves = [(-length / 2, -open_w / 2), (open_w / 2, length / 2)]
    for hi, (x0, x1) in enumerate(halves):
        band("back", x0, x1, 0, height, T, M_HULL, bevel=0)
        band("low", x0 + 0.05, x1 - 0.05, 0.22, 1.05, T + 0.06, M_PANELD)
        band("lowtrim", x0 + 0.05, x1 - 0.05, 1.0, 1.05, T + 0.09, M_TRIM, bevel=0)
        w = x1 - x0 - 0.3
        n = max(1, int(w // 2.2))
        pw = w / n
        for i in range(n):
            px0 = x0 + 0.15 + i * pw + 0.06
            px1 = px0 + pw - 0.12
            band(f"panel{i}", px0, px1, 1.15, 3.35, T + 0.08, M_PANEL, bevel=0.03)
            band(f"seam{i}", px0 + 0.1, px1 - 0.1, 2.62, 2.64, T + 0.085, M_TRIM, bevel=0)
        band("up", x0 + 0.05, x1 - 0.05, 3.45, height - 0.1, T + 0.05, M_PANEL2)
        if light_floor:
            band("strip_floor", x0 + 0.02, x1 - 0.02, 0.08, 0.14, T + 0.09, M_GLOW_C, bevel=0)
            band("grate", x0 + 0.02, x1 - 0.02, 0.0, 0.02, T + 0.9, M_GRATE, bevel=0)
        band("strip_mid", x0 + 0.1, x1 - 0.1, 1.08, 1.12, T + 0.10, M_GLOW_O, bevel=0)
        band("strip_top", x0 + 0.02, x1 - 0.02, 3.37, 3.43, T + 0.09, M_GLOW_C, bevel=0)
        if detail and (x1 - x0) > 2.5:
            cx = (x0 + x1) / 2
            vent(f"{name}_vent{hi}", (cx, T / 2 + 0.06, 4.2), (0, 0, 0), 1.2, 0.5, parent=seg, c="Props")
            sconce(f"{name}_sconce{hi}a", (x0 + 0.35, T / 2 + 0.08, 2.3), (0, 0, 0), parent=seg, c="Props")
            sconce(f"{name}_sconce{hi}b", (x1 - 0.35, T / 2 + 0.08, 2.3), (0, 0, 0), parent=seg, c="Props")
            pipe_run(f"{name}_cond{hi}", (x0 + 0.2, T / 2 + 0.1, 3.7), (x1 - 0.2, T / 2 + 0.1, 3.7), 0.04, parent=seg, flanges=1.5)
    if has_opening:
        band("lintel", -open_w / 2 - 0.3, open_w / 2 + 0.3, open_h, height, T + 0.1, M_HULL, bevel=0.03)
        band("lintel_glow", -open_w / 2 - 0.2, open_w / 2 + 0.2, open_h + 0.05, open_h + 0.12, T + 0.14, M_GLOW_O, bevel=0)
        band("lintel_plate", -open_w / 2 - 0.1, open_w / 2 + 0.1, open_h + 0.2, height - 0.3, T + 0.12, M_PANELD, bevel=0.02)
        for s in (-1, 1):
            box(f"{name}_jamb{s}", (s * (open_w / 2 + 0.15), 0.05, open_h / 2), (0.3, T + 0.3, open_h), M_TRIM, bevel=0.03, parent=seg)
            box(f"{name}_jambglow{s}", (s * (open_w / 2 + 0.02), 0.1, open_h / 2), (0.04, 0.08, open_h - 0.2), M_GLOW_C, parent=seg)
            box(f"{name}_hazard{s}", (s * (open_w / 2 + 0.15), 0.21, 0.5), (0.3, 0.01, 1.0), M_HAZARD, parent=seg)
            status_panel(f"{name}_status{s}", (s * (open_w / 2 + 0.55), T / 2 + 0.03, 1.6), (0, 0, 0), parent=seg)
        box(f"{name}_threshold", (0, 0, 0.005), (open_w, T + 0.2, 0.01), M_HAZARD, parent=seg)
    return seg

for i in range(8):
    a = D(45 * i)
    base = (HUB_R * math.cos(a), HUB_R * math.sin(a), 0)
    wall_segment(hub, f"HubWall{i}", SEG_LEN, HUB_H, i in OPENINGS, CORR_W, CORR_H, base, a + D(90))

for i in range(8):
    a = D(22.5 + 45 * i)
    r = circum - 0.35
    p = empty(f"HubPillar{i}", (r * math.cos(a), r * math.sin(a), 0), (0, 0, a))
    p.parent = hub
    box("pillar_core", (0, 0, HUB_H / 2), (0.7, 0.7, HUB_H), M_HULL, bevel=0.04, parent=p)
    box("pillar_face", (-0.36, 0, HUB_H / 2), (0.06, 0.5, HUB_H - 1.0), M_PANELD, bevel=0.02, parent=p)
    box("pillar_strip", (-0.40, 0, HUB_H / 2), (0.03, 0.12, HUB_H - 1.2), M_GLOW_C, parent=p)
    box("pillar_cap", (0, 0, HUB_H - 0.3), (0.9, 0.9, 0.3), M_TRIM, bevel=0.03, parent=p)
    box("pillar_base", (0, 0, 0.12), (0.9, 0.9, 0.24), M_TRIM, bevel=0.03, parent=p)
    box("pillar_base2", (0, 0, 0.3), (0.8, 0.8, 0.12), M_PANELD, bevel=0.02, parent=p)

for i in range(8):
    a = D(22.5 + 45 * i)
    rib = box(f"CeilRib{i}", ((circum - 0.6) / 2 * math.cos(a), (circum - 0.6) / 2 * math.sin(a), HUB_H - 0.2), (circum - 0.6, 0.35, 0.4), M_HULL, rot=(0, 0, a), bevel=0.03, parent=hub)
    g = box(f"CeilRibGlow{i}", (0, 0, 0), (1, 1, 1), M_GLOW_B, parent=rib)
    g.scale = (0.9, 0.2, 0.08); g.location = (0, 0, -0.52)
for i in range(8):
    a = D(45 * i)
    r = 6.8
    box(f"CeilPanel{i}", (r * math.cos(a), r * math.sin(a), HUB_H - 0.08), (3.2, 2.6, 0.16), M_PANEL2, rot=(0, 0, a), bevel=0.03, parent=hub)
    vent(f"CeilVent{i}", (r * math.cos(a), r * math.sin(a), HUB_H - 0.2), (D(90), 0, a), 0.8, 0.4, parent=hub, slats=5)
cyl("CeilDome", (0, 0, HUB_H - 0.15), 4.2, 0.3, M_PANELD, verts=64, parent=hub)
torus("CeilRingLight", (0, 0, HUB_H - 0.33), 4.0, 0.09, M_GLOW_W, parent=hub)
torus("CeilRingLight2", (0, 0, HUB_H - 0.33), 3.0, 0.05, M_GLOW_C, parent=hub)
torus("CeilRingHousing", (0, 0, HUB_H - 0.28), 4.0, 0.16, M_TRIM, parent=hub)
cyl("CeilHub", (0, 0, HUB_H - 0.4), 1.2, 0.5, M_HULL, verts=48, parent=hub)
cyl("CeilHubGlow", (0, 0, HUB_H - 0.67), 0.9, 0.06, M_GLOW_O, verts=48, parent=hub)
torus("CeilConduit", (0, 0, HUB_H - 0.55), 6.5, 0.08, M_PIPE, parent=hub)
torus("CeilConduit2", (0, 0, HUB_H - 0.62), 6.8, 0.05, M_PIPE, parent=hub)
torus("CeilConduit3", (0, 0, HUB_H - 0.5), 6.2, 0.04, M_CABLE_K, parent=hub)
for k in range(16):
    a = TAU * k / 16
    torus(f"CeilConduitFl{k}", (6.5 * math.cos(a), 6.5 * math.sin(a), HUB_H - 0.55), 0.085, 0.03, M_TRIM, parent=hub, rot=(D(90), 0, a), segs=16, rings=8)

for i in range(8):
    a = D(45 * i)
    r = HUB_R - WALL_T / 2 - 0.35
    box(f"FloorTrim{i}", (r * math.cos(a), r * math.sin(a), 0.01), (SEG_LEN - 1.2, 0.08, 0.02), M_GLOW_B, rot=(0, 0, a + D(90)), parent=hub)
for i in OPENINGS:
    a = D(45 * i)
    for s in (-1, 1):
        off = s * 1.5
        p0 = Vector((4.9 * math.cos(a) + off * math.cos(a + D(90)), 4.9 * math.sin(a) + off * math.sin(a + D(90)), 0.012))
        p1 = Vector((8.5 * math.cos(a) + off * math.cos(a + D(90)), 8.5 * math.sin(a) + off * math.sin(a + D(90)), 0.012))
        mid = (p0 + p1) / 2
        box(f"Guide{i}_{s}", mid, ((p1 - p0).length, 0.05, 0.006), M_GLOW_B, rot=(0, 0, a), parent=hub)
text("Deck_Decal", "02", (-5.45, 0, 0.012), (0, 0, D(-90)), 1.1, M_GLOW_O, parent=hub, extrude=0.0)
text("Deck_Decal2", "CIC", (5.45, 0, 0.012), (0, 0, D(90)), 0.9, M_GLOW_C, parent=hub, extrude=0.0)

cyl("Platform_Step1", (0, 0, 0.08), 4.6, 0.16, M_FLOOR2, verts=48, parent=hub)
cyl("Platform_Step2", (0, 0, 0.24), 4.1, 0.16, M_FLOOR2, verts=48, parent=hub)
cyl("Platform_Top", (0, 0, 0.40), 3.6, 0.16, M_FLOOR, verts=48, parent=hub)
torus("Platform_Glow1", (0, 0, 0.17), 4.6, 0.025, M_GLOW_C, parent=hub)
torus("Platform_Glow2", (0, 0, 0.33), 4.1, 0.025, M_GLOW_C, parent=hub)
torus("Platform_Glow3", (0, 0, 0.49), 3.6, 0.025, M_GLOW_O, parent=hub)
torus("Platform_Edge1", (0, 0, 0.16), 4.6, 0.02, M_TRIM, parent=hub)
torus("Platform_Edge2", (0, 0, 0.32), 4.1, 0.02, M_TRIM, parent=hub)
for i in range(24):
    a = TAU * i / 24
    deg = (math.degrees(a)) % 360
    if min(abs(deg - d) for d in (0, 90, 180, 360)) < 12:
        continue
    r = 3.3
    cyl(f"RailPost{i}", (r * math.cos(a), r * math.sin(a), 0.48 + 0.5), 0.03, 1.0, M_RAIL, verts=12, parent=hub)
    cyl(f"RailFoot{i}", (r * math.cos(a), r * math.sin(a), 0.5), 0.06, 0.04, M_TRIM, verts=12, parent=hub)
for (a0, a1) in ((12, 78), (102, 168), (192, 348)):
    pts = []
    n = 24
    for k in range(n + 1):
        a = D(a0 + (a1 - a0) * k / n)
        pts.append((3.3 * math.cos(a), 3.3 * math.sin(a)))
    for zz, mm, rr in ((1.48, M_RAIL, 0.03), (1.0, M_GLOW_C, 0.015), (1.25, M_RAIL, 0.012)):
        me = bpy.data.meshes.new("RailBar")
        bm = bmesh.new()
        vs = [bm.verts.new((x, y, zz)) for x, y in pts]
        for k in range(len(vs) - 1):
            bm.edges.new((vs[k], vs[k + 1]))
        bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new(f"RailBar_{a0}_{int(zz*100)}", me)
        ob.parent = hub
        link(ob, "Station")
        md = ob.modifiers.new("Skin", 'SKIN'); md.use_smooth_shade = True
        for sv in me.skin_vertices[0].data:
            sv.radius = (rr, rr)
        me.materials.append(mm)
        sd = ob.modifiers.new("Sub", 'SUBSURF'); sd.levels = 1; sd.render_levels = 2

cyl("MapTable", (0, 0, 0.48 + 0.45), 1.7, 0.9, M_HULL, verts=64, parent=hub)
cyl("MapTableBand", (0, 0, 0.48 + 0.45), 1.72, 0.3, M_PANELD, verts=64, parent=hub)
cyl("MapTableTop", (0, 0, 0.48 + 0.92), 1.75, 0.06, M_TRIM, verts=64, parent=hub)
torus("MapTableGlow", (0, 0, 0.48 + 0.86), 1.72, 0.03, M_GLOW_O, parent=hub)
cyl("MapTableInner", (0, 0, 0.48 + 0.95), 1.5, 0.02, mat("MapSurface", (0.02, 0.03, 0.06), 0.2, 0.3, (0.1, 0.3, 0.8), 0.35, coat=0.8), verts=64, parent=hub)
torus("MapTableInnerRing", (0, 0, 0.48 + 0.962), 1.49, 0.006, M_GLOW_C, parent=hub)
torus("MapTableInnerRing2", (0, 0, 0.48 + 0.962), 0.5, 0.004, M_GLOW_B, parent=hub)
for k in range(8):
    a = TAU * k / 8
    box(f"MapTableFin{k}", (1.78 * math.cos(a), 1.78 * math.sin(a), 0.48 + 0.4), (0.08, 0.3, 0.8), M_TRIM, rot=(0, 0, a), bevel=0.01, parent=hub)
    box(f"MapTableKey{k}", (1.64 * math.cos(a + TAU / 16), 1.64 * math.sin(a + TAU / 16), 0.48 + 0.94), (0.16, 0.42, 0.012), M_SCREEN_O, rot=(0, D(-18), a + TAU / 16), parent=hub, c="Holograms")
    box(f"MapTableKeyFrame{k}", (1.64 * math.cos(a + TAU / 16), 1.64 * math.sin(a + TAU / 16), 0.48 + 0.935), (0.18, 0.45, 0.01), M_TRIM, rot=(0, D(-18), a + TAU / 16), parent=hub, c="Props")
# ---------------------------------------------------------------- GALAXY MAP CENTREPIECE
def cyc(ob, linear=True):
    ad = ob.animation_data
    if not ad or not ad.action: return
    for fc in action_fcurves(ad.action):
        if linear:
            for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.modifiers.new('CYCLES')

def spin(ob, frames, axis='Z', start=0.0, reverse=False):
    rot = [0.0, 0.0, 0.0]; i = "XYZ".index(axis)
    rot[i] = start; ob.rotation_euler = rot; ob.keyframe_insert("rotation_euler", frame=1)
    rot[i] = start + (-TAU if reverse else TAU); ob.rotation_euler = rot; ob.keyframe_insert("rotation_euler", frame=1 + frames)
    cyc(ob)

def emissive_blend(name, color, strength, alpha):
    m = mat(name, color, 0, 0.3, color, strength, alpha=alpha, blended=True)
    m.use_backface_culling = False
    return m

def arc_ribbon(name, r0, r1, a0, a1, z, m, parent, c="Holograms"):
    steps = max(4, int(abs(a1 - a0) / 4))
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    inner, outer = [], []
    for i in range(steps + 1):
        a = D(a0 + (a1 - a0) * i / steps)
        inner.append(bm.verts.new((r0 * math.cos(a), r0 * math.sin(a), z)))
        outer.append(bm.verts.new((r1 * math.cos(a), r1 * math.sin(a), z)))
    for i in range(steps):
        bm.faces.new((inner[i], outer[i], outer[i + 1], inner[i + 1]))
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); me.materials.append(m); link(ob, c); ob.parent = parent
    return ob

def haze_material(name):
    """Procedural spiral-galaxy haze seen from above: 3 arms matching the star distribution."""
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    em = nt.nodes.new("ShaderNodeEmission"); tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mixs = nt.nodes.new("ShaderNodeMixShader")
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sep.inputs[0])
    def mathn(op, a=None, b=None, bval=None, cval=None):
        n = nt.nodes.new("ShaderNodeMath"); n.operation = op
        if a is not None: nt.links.new(a, n.inputs[0])
        if b is not None: nt.links.new(b, n.inputs[1])
        if bval is not None: n.inputs[1].default_value = bval
        if cval is not None: n.inputs[2].default_value = cval
        return n.outputs[0]
    X, Y = sep.outputs["X"], sep.outputs["Y"]
    r = mathn('SQRT', mathn('ADD', mathn('MULTIPLY', X, X), mathn('MULTIPLY', Y, Y)))
    theta = mathn('ARCTAN2', Y, X)
    spiral = mathn('COSINE', mathn('MULTIPLY', mathn('SUBTRACT', theta, mathn('MULTIPLY', r, bval=2.4)), bval=3.0))
    arm = mathn('POWER', mathn('MULTIPLY_ADD', spiral, bval=0.5, cval=0.5), bval=2.2)
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 3.5; noise.inputs["Detail"].default_value = 9.0; noise.inputs["Roughness"].default_value = 0.65
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    noise2 = nt.nodes.new("ShaderNodeTexNoise"); noise2.inputs["Scale"].default_value = 14.0; noise2.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise2.inputs["Vector"])
    cloud = mathn('MULTIPLY', mathn('MULTIPLY_ADD', noise.outputs["Fac"], bval=1.3, cval=0.15), mathn('MULTIPLY_ADD', noise2.outputs["Fac"], bval=0.6, cval=0.6))
    armn = mathn('MULTIPLY', arm, cloud)
    fall = mathn('POWER', mathn('MAXIMUM', mathn('SUBTRACT', mathn('MULTIPLY', r, bval=-1.0 / 1.42), bval=-1.0), bval=0.0), bval=1.6)
    # SUBTRACT(-r/1.42, -1) = 1 - r/1.42
    core = mathn('MULTIPLY', mathn('EXPONENT', mathn('MULTIPLY', r, bval=-5.0)), bval=2.2)
    bright = mathn('ADD', mathn('MULTIPLY', armn, fall), core)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0; ramp.color_ramp.elements[0].color = (1.0, 0.92, 0.75, 1)
    ramp.color_ramp.elements[1].position = 1.0; ramp.color_ramp.elements[1].color = (0.12, 0.25, 0.8, 1)
    for pos, col in ((0.18, (1.0, 0.62, 0.22, 1)), (0.5, (0.45, 0.7, 1.0, 1)), (0.8, (0.2, 0.45, 1.0, 1))):
        e = ramp.color_ramp.elements.new(pos); e.color = col
    nt.links.new(mathn('DIVIDE', r, bval=1.45), ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], em.inputs["Color"])
    nt.links.new(mathn('MULTIPLY', bright, bval=7.0), em.inputs["Strength"])
    nt.links.new(mathn('MINIMUM', mathn('MULTIPLY', bright, bval=1.4), bval=1.0), mixs.inputs[0])
    nt.links.new(tr.outputs[0], mixs.inputs[1]); nt.links.new(em.outputs[0], mixs.inputs[2])
    nt.links.new(mixs.outputs[0], out.inputs["Surface"])
    m.surface_render_method = 'BLENDED'; m.use_transparent_shadow = True; m.use_backface_culling = False
    return m

def core_material(name, color, strength, alpha_scale):
    m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"]); out = nt.nodes["Material Output"]
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1); em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mixs = nt.nodes.new("ShaderNodeMixShader")
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.5
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = alpha_scale
    nt.links.new(lw.outputs["Facing"], mul.inputs[0]); nt.links.new(mul.outputs[0], mixs.inputs[0])
    nt.links.new(tr.outputs[0], mixs.inputs[1]); nt.links.new(em.outputs[0], mixs.inputs[2]); nt.links.new(mixs.outputs[0], out.inputs["Surface"])
    m.surface_render_method = 'BLENDED'; m.use_transparent_shadow = True
    return m

def galaxy_map(parent):
    c = "Holograms"
    rnd = random.Random(42)
    holo = empty("GalaxyMap", (0, 0, 1.45), c=c); holo.parent = parent
    spin(holo, 1200)                                   # whole galaxy, one turn per 50 s
    ZP = 0.42                                          # galactic plane height above the table top
    # --- haze body (three stacked discs = pseudo volume)
    M_HAZE = haze_material("GalaxyHaze")
    for k, (dz, sc_, nm) in enumerate(((0.0, 1.0, "mid"), (-0.05, 0.92, "low"), (0.05, 0.92, "high"))):
        d = cyl(f"Galaxy_Haze_{nm}", (0, 0, ZP + dz), 1.45, 0.002, M_HAZE, verts=96, parent=holo, c=c)
        d.scale = (sc_, sc_, 1)
    # --- stars (three brightness classes, instanced)
    def star_cloud(name, count, m, radius, zspread, core_bias):
        me = bpy.data.meshes.new(name); bm = bmesh.new()
        for k in range(count):
            rr = rnd.random() ** core_bias * 1.38
            arm = (k % 3) * TAU / 3
            ang = arm + rr * 2.4 + rnd.gauss(0, 0.22 + 0.1 * rr)
            zz = ZP + rnd.gauss(0, zspread) * (1.45 - rr) * 0.9
            bm.verts.new((rr * math.cos(ang), rr * math.sin(ang), zz))
        bm.to_mesh(me); bm.free()
        pts = bpy.data.objects.new(name, me); pts.parent = holo; link(pts, c); pts.instance_type = 'VERTS'
        inst = sphere(name + "_inst", (0, 0, 0), radius, m, c=c, seg=6, ring=4); inst.parent = pts
        return pts
    star_cloud("Galaxy_StarsGold", 3600, mat("StarGold", (1, 0.55, 0.15), 0, 0.5, (1.0, 0.55, 0.15), 4.5), 0.0038, 0.05, 0.55)
    star_cloud("Galaxy_StarsWhite", 1400, mat("StarWhite", (1, 0.95, 0.85), 0, 0.5, (1.0, 0.95, 0.85), 6.0), 0.0048, 0.06, 0.5)
    star_cloud("Galaxy_StarsBlue", 450, mat("StarBlue", (0.35, 0.65, 1), 0, 0.5, (0.35, 0.65, 1.0), 8.0), 0.0058, 0.08, 0.7)
    # --- core
    sphere("Galaxy_Core", (0, 0, ZP), 0.12, core_material("GalaxyCore", (1.0, 0.85, 0.6), 5.0, 1.0), c=c, parent=holo, seg=32, ring=16, scale=(1, 1, 0.8))
    sphere("Galaxy_CoreHalo", (0, 0, ZP), 0.32, core_material("GalaxyHalo", (1.0, 0.7, 0.4), 1.6, 0.4), c=c, parent=holo, seg=32, ring=16, scale=(1, 1, 0.6))
    sphere("Galaxy_CoreHalo2", (0, 0, ZP), 0.55, core_material("GalaxyHalo2", (0.45, 0.65, 1.0), 0.9, 0.25), c=c, parent=holo, seg=32, ring=16, scale=(1, 1, 0.4))
    cyl("Galaxy_Axis", (0, 0, ZP + 0.45), 0.003, 1.3, M_GLOW_C, verts=8, parent=holo, c=c)
    cyl("Galaxy_Beam", (0, 0, ZP + 0.5), 0.045, 1.0, core_material("GalaxyBeam", (0.6, 0.8, 1.0), 1.2, 0.5), verts=24, parent=holo, c=c)
    # large tilted gyroscope rings sweeping around the whole galaxy (visible from eye level)
    for k, (tilt, frames, rev, m) in enumerate(((65, 600, False, M_GLOW_C), (-55, 900, True, M_GLOW_O))):
        gp = empty(f"Galaxy_GyroPivot{k}", (0, 0, ZP), (0, 0, 0), c=c); gp.parent = holo
        torus(f"Galaxy_GyroRing{k}", (0, 0, 0), 1.5, 0.004, m, parent=gp, c=c, rot=(D(tilt), 0, 0), segs=96, rings=6)
        for j in range(3):
            a = TAU * j / 3
            sphere(f"Galaxy_GyroBead{k}_{j}", (1.5 * math.cos(a), 1.5 * math.sin(a) * math.cos(D(tilt)), 1.5 * math.sin(a) * math.sin(D(tilt))), 0.018, M_GLOW_W, c=c, parent=gp, seg=10, ring=6)
        spin(gp, frames, reverse=rev)
    # --- mass relay network: 16 systems on the arms, nearest-neighbour routes with travelling pulses
    systems = []
    for k in range(16):
        rr = 0.3 + (k / 16) * 1.0 + rnd.uniform(-0.05, 0.05)
        ang = (k % 3) * TAU / 3 + rr * 2.4 + rnd.gauss(0, 0.12)
        systems.append(Vector((rr * math.cos(ang), rr * math.sin(ang), ZP + rnd.uniform(-0.01, 0.01))))
    edges = set()
    for i, p in enumerate(systems):
        near = sorted(((p - q).length, j) for j, q in enumerate(systems) if j != i)[:2]
        for _, j in near: edges.add(tuple(sorted((i, j))))
    me = bpy.data.meshes.new("Galaxy_Routes"); bm = bmesh.new()
    vs = [bm.verts.new(p) for p in systems]
    for i, j in edges: bm.edges.new((vs[i], vs[j]))
    bm.to_mesh(me); bm.free()
    routes = bpy.data.objects.new("Galaxy_Routes", me); routes.parent = holo; link(routes, c)
    sk = routes.modifiers.new("Skin", 'SKIN'); sk.use_smooth_shade = True
    for sv in me.skin_vertices[0].data: sv.radius = (0.0035, 0.0035)
    me.materials.append(mat("RouteCyan", CYAN, 0, 0.5, CYAN, 5.0))
    M_PULSE = mat("RoutePulse", (1, 1, 1), 0, 0.5, (1.0, 1.0, 1.0), 10.0)
    for n, (i, j) in enumerate(sorted(edges)):
        if n % 2: continue
        pu = sphere(f"Galaxy_Pulse{n}", systems[i], 0.012, M_PULSE, c=c, parent=holo, seg=8, ring=5)
        dur = rnd.randint(40, 90)
        pu.keyframe_insert("location", frame=1)
        pu.location = systems[j]; pu.keyframe_insert("location", frame=1 + dur)
        pu.location = systems[i]; pu.keyframe_insert("location", frame=1 + 2 * dur)
        cyc(pu)
    M_SYS = mat("SysMarker", CYAN, 0, 0.5, (0.6, 0.9, 1.0), 12.0)
    for k, p in enumerate(systems):
        sphere(f"Galaxy_Sys{k}", p, 0.016, M_SYS, c=c, parent=holo, seg=10, ring=6)
        torus(f"Galaxy_SysRing{k}", p, 0.04, 0.0025, M_GLOW_C, parent=holo, c=c, segs=24, rings=5)
    # --- selected system: pulsing ring, riser, info card with orbit icon
    sel = systems[5]
    ring = torus("Galaxy_SelRing", sel, 0.08, 0.004, M_GLOW_O, parent=holo, c=c, segs=32, rings=6)
    ring.scale = (0.7, 0.7, 1); ring.keyframe_insert("scale", frame=1)
    ring.scale = (1.4, 1.4, 1); ring.keyframe_insert("scale", frame=25)
    ring.scale = (0.7, 0.7, 1); ring.keyframe_insert("scale", frame=48); cyc(ring, linear=False)
    torus("Galaxy_SelRing2", sel, 0.055, 0.003, M_GLOW_O, parent=holo, c=c, segs=32, rings=6)
    cyl("Galaxy_SelRiser", (sel.x, sel.y, sel.z + 0.3), 0.002, 0.6, M_GLOW_O, verts=6, parent=holo, c=c)
    card = empty("Galaxy_SelCard", (sel.x, sel.y, sel.z + 0.66), (0, 0, math.atan2(sel.y, sel.x) + D(90)), c=c); card.parent = holo
    box("bg", (0, 0, 0), (0.62, 0.004, 0.22), M_HOLO_K, parent=card, c=c)
    box("rule", (0, -0.004, 0.07), (0.56, 0.003, 0.004), M_GLOW_O, parent=card, c=c)
    box("edge", (-0.31, 0, 0), (0.006, 0.006, 0.24), M_GLOW_O, parent=card, c=c)
    text("title", "ARCTURUS STREAM  //  SOL RELAY", (-0.28, -0.006, 0.085), (D(90), 0, 0), 0.034, M_GLOW_O, parent=card, c=c, align='LEFT', extrude=0.0)
    text("body", "SYSTEM 2175-A   DIST 12.4 kLY\nRELAY: ONLINE   TRAFFIC: 31 VESSELS\nSTATUS: ALLIANCE CONTROLLED", (-0.28, -0.006, -0.02), (D(90), 0, 0), 0.026, M_GLOW_W, parent=card, c=c, align='LEFT', extrude=0.0)
    orb = empty("Galaxy_SelOrbit", (0.2, -0.02, -0.01), (0, 0, 0), c=c); orb.parent = card
    sphere("planet", (0, 0, 0), 0.028, mat("HoloPlanet", (0.3, 0.6, 1), 0, 0.4, (0.35, 0.65, 1.0), 5.0), c=c, parent=orb, seg=16, ring=10)
    torus("orbit", (0, 0, 0), 0.055, 0.002, M_GLOW_W, parent=orb, c=c, rot=(D(70), 0, 0), segs=32, rings=5)
    moon = empty("Galaxy_SelMoonPivot", (0, 0, 0), (D(70), 0, 0), c=c); moon.parent = orb
    sphere("moon", (0.055, 0, 0), 0.007, M_GLOW_W, c=c, parent=moon, seg=8, ring=5)
    spin(moon, 96); spin(orb, 400, axis='Y')
    # --- radar sweep + ping rings
    M_SWEEP = emissive_blend("HoloSweep", CYAN, 3.0, 0.22)
    sweep = empty("Galaxy_Sweep", (0, 0, 0), (0, 0, 0), c=c); sweep.parent = holo
    for k, (a0, a1, al) in enumerate(((0, 6, 1.0), (6, 14, 0.6), (14, 26, 0.3))):
        arc_ribbon(f"sweep{k}", 0.12, 1.44, -a1, -a0, ZP + 0.004, emissive_blend(f"HoloSweep{k}", CYAN, 3.0 * al, 0.22 * al), sweep)
    cyl("Galaxy_SweepEdge", (0, 0, ZP + 0.004), 0.002, 1.32, M_GLOW_C, verts=6, parent=sweep, c=c, rot=(0, D(90), 0))
    bpy.data.objects["Galaxy_SweepEdge"].location = (0.72, 0, ZP + 0.004)
    spin(sweep, 240, reverse=True)
    for k in range(2):
        ping = torus(f"Galaxy_Ping{k}", (0, 0, ZP + 0.002), 1.0, 0.004, M_GLOW_C, parent=holo, c=c, segs=64, rings=5)
        ping.scale = (0.05, 0.05, 1); ping.keyframe_insert("scale", frame=1 + 60 * k)
        ping.scale = (1.44, 1.44, 1); ping.keyframe_insert("scale", frame=120 + 60 * k)
        cyc(ping)
    # --- rim HUD: tick marks and counter-rotating arcs at three radii
    for k in range(72):
        a = TAU * k / 72
        big = (k % 9 == 0)
        box(f"Galaxy_Tick{k}", (1.52 * math.cos(a), 1.52 * math.sin(a), ZP), (0.05 if big else 0.025, 0.006 if big else 0.003, 0.004), M_GLOW_O if big else M_GLOW_C, rot=(0, 0, a), parent=holo, c=c)
    hud1 = empty("Galaxy_HUD1", (0, 0, 0), (0, 0, 0), c=c); hud1.parent = holo
    for k in range(3): arc_ribbon(f"hud1_{k}", 1.56, 1.585, k * 120, k * 120 + 70, ZP - 0.01, M_GLOW_O, hud1)
    spin(hud1, 900)
    hud2 = empty("Galaxy_HUD2", (0, 0, 0), (0, 0, 0), c=c); hud2.parent = holo
    for k in range(2): arc_ribbon(f"hud2_{k}", 1.61, 1.625, k * 180, k * 180 + 120, ZP - 0.02, M_GLOW_C, hud2)
    spin(hud2, 700, reverse=True)
    hud3 = empty("Galaxy_HUD3", (0, 0, 0), (0, 0, 0), c=c); hud3.parent = holo
    for k in range(8): arc_ribbon(f"hud3_{k}", 1.65, 1.66, k * 45, k * 45 + 28, ZP - 0.03, M_GLOW_W, hud3)
    spin(hud3, 1500)
    # --- rising data motes around the core
    M_MOTE = mat("DataMote", CYAN, 0, 0.5, (0.7, 0.9, 1.0), 10.0)
    for k in range(28):
        a = TAU * k / 28 + rnd.random(); rr = rnd.uniform(0.16, 0.34)
        mo = sphere(f"Galaxy_Mote{k}", (rr * math.cos(a), rr * math.sin(a), ZP + 0.05), 0.006, M_MOTE, c=c, parent=holo, seg=6, ring=4)
        dur = rnd.randint(70, 130); off = rnd.randint(0, dur)
        mo.keyframe_insert("location", frame=1 - off)
        mo.location = (rr * 0.6 * math.cos(a), rr * 0.6 * math.sin(a), ZP + 1.2); mo.keyframe_insert("location", frame=1 - off + dur)
        cyc(mo)
    # --- floating readout columns at the rim (rotate with the map)
    lines = [("SECTOR SCAN", "ARMS 3  //  SYS 10,412\nRELAYS 46  //  ACTIVE 41\nTHREAT LEVEL: LOW"),
             ("FLEET TRACK", "SSV NORMANDY  //  DOCKED\nSSV KILIMANJARO  //  TRANSIT\nMSV CORNUCOPIA  //  HOLD"),
             ("NAV BEACONS", "WIDOW  //  ONLINE\nSERPENT NEBULA  //  ONLINE\nATTICAN TRAVERSE  //  DEGRADED"),
             ("COMM BUFFER", "LINK 98%  //  LATENCY 0.4 s\nPACKETS 1.2e6  //  LOSS 0.01%\nENCRYPTION: QEC-7")]
    for k, (ttl, body) in enumerate(lines):
        a = TAU * k / 4 + 0.75
        rd = empty(f"Galaxy_Readout{k}", (1.3 * math.cos(a), 1.3 * math.sin(a), ZP + 0.98 + 0.06 * (k % 2)), (0, 0, a + D(90)), c=c); rd.parent = holo
        box("bg", (0, 0, 0), (0.6, 0.004, 0.2), M_HOLO_K, parent=rd, c=c)
        box("rule", (0, 0.004, 0.062), (0.54, 0.003, 0.004), M_GLOW_C if k % 2 else M_GLOW_O, parent=rd, c=c)
        text("ttl", ttl, (0.27, 0.006, 0.078), (D(90), 0, D(180)), 0.032, M_GLOW_C if k % 2 else M_GLOW_O, parent=rd, c=c, align='LEFT', extrude=0.0)
        text("body", body, (0.27, 0.006, -0.03), (D(90), 0, D(180)), 0.024, M_GLOW_W, parent=rd, c=c, align='LEFT', extrude=0.0)
        rd.rotation_euler = (0, 0, a - D(90))   # face outward
        cyl("stem", (0, 0, -0.1 - 0.45 / 2), 0.002, 0.45, M_GLOW_C, verts=6, parent=rd, c=c)
    # --- region labels on backing plates
    for k, lbl in enumerate(("SERPENT NEBULA", "WIDOW", "ARCTURUS STREAM", "ATTICAN TRAVERSE", "TERMINUS SYSTEMS", "HADES GAMMA")):
        a = TAU * k / 6 + 0.4
        lx, ly, lz = 1.12 * math.cos(a), 1.12 * math.sin(a), ZP + 0.26 + 0.05 * (k % 3)
        box(f"Galaxy_LabelBg{k}", (lx + 0.004 * math.cos(a), ly + 0.004 * math.sin(a), lz), (0.034 * len(lbl) + 0.05, 0.004, 0.065), M_HOLO_K, rot=(0, 0, a + D(90)), parent=holo, c=c)
        text(f"Galaxy_Label{k}", lbl, (lx, ly, lz), (D(90), 0, a + D(90)), 0.042, M_GLOW_C, parent=holo, c=c, extrude=0.0)
        cyl(f"Galaxy_LabelStem{k}", (lx, ly, (lz + ZP) / 2), 0.0015, lz - ZP - 0.05, M_GLOW_C, verts=6, parent=holo, c=c)
    return holo

holo = galaxy_map(hub)
# approach-pattern floor holograms at each corridor mouth
for i in OPENINGS:
    a = D(45 * i)
    ap = empty(f"Approach{i}", ((HUB_R - 1.7) * math.cos(a), (HUB_R - 1.7) * math.sin(a), 0.02), (0, 0, a), c="Holograms"); ap.parent = hub
    inner = empty(f"Approach{i}_spin", (0, 0, 0), (0, 0, 0), c="Holograms"); inner.parent = ap
    for k in range(3): arc_ribbon(f"ap{i}_arc{k}", 0.78, 0.86, k * 120, k * 120 + 75, 0.0, M_GLOW_O, inner)
    spin(inner, 300, reverse=(i % 2 == 0))
    torus(f"Approach{i}_ring", (0, 0, 0), 0.95, 0.008, M_GLOW_C, parent=ap, c="Holograms", segs=64, rings=5)
    for s_ in (-1, 1):
        box(f"Approach{i}_chev{s_}", (0.55, s_ * 0.28, 0), (0.16, 0.03, 0.004), M_GLOW_C, rot=(0, 0, s_ * D(35)), parent=ap, c="Holograms")
    text(f"Approach{i}_txt", {0: "OBSERVATION DECK", 2: "DOCKING BAY 07", 4: "AIRLOCK 01"}[i], (0, -0.6, 0.002), (0, 0, D(90)), 0.09, M_GLOW_O, parent=ap, c="Holograms", extrude=0.0)
# scrolling news ticker above the bench wall
seg6 = bpy.data.objects["HubWall6"]
box("Ticker_channel", (0, WALL_T / 2 + 0.11, 3.1), (7.0, 0.04, 0.2), M_TRIM, bevel=0.01, parent=seg6, c="Props")
box("Ticker_bg", (0, WALL_T / 2 + 0.125, 3.1), (6.9, 0.004, 0.16), M_HOLO_K, parent=seg6, c="Holograms")
tk = text("Ticker_text", "CITADEL NEWS NET  ▶  COUNCIL CONVENES ON TERMINUS TRAFFIC   //   SSV NORMANDY DOCKED AT BAY 07   //   RELAY 314 MAINTENANCE 0400   //   PRESIDIUM CURFEW LIFTED", (-1.2, WALL_T / 2 + 0.135, 3.1), (D(90), 0, D(180)), 0.085, M_GLOW_O, parent=seg6, c="Holograms", extrude=0.0)
tk.keyframe_insert("location", frame=1)
tk.location = (1.2, WALL_T / 2 + 0.135, 3.1); tk.keyframe_insert("location", frame=600)
cyc(tk)
# rim projectors on the table and a breathing map light
for k in range(6):
    a = TAU * k / 6 + 0.3
    pr = empty(f"MapProjector{k}", (1.62 * math.cos(a), 1.62 * math.sin(a), 0.48 + 0.98), (0, 0, a), c="Props"); pr.parent = hub
    box("base", (0, 0, 0.02), (0.1, 0.08, 0.04), M_TRIM, bevel=0.005, parent=pr, c="Props")
    cyl("lens", (-0.03, 0, 0.06), 0.02, 0.05, M_TRIM, verts=12, parent=pr, c="Props", rot=(0, D(-55), 0))
    sphere("glow", (-0.045, 0, 0.08), 0.012, M_GLOW_C, c="Props", parent=pr, seg=10, ring=6)
mg = light("Map_Glow", 'POINT', (0, 0, 2.1), ORANGE, 160, c="Lights", radius=1.2)
mg.data.energy = 140; mg.data.keyframe_insert("energy", frame=1)
mg.data.energy = 260; mg.data.keyframe_insert("energy", frame=48)
mg.data.energy = 140; mg.data.keyframe_insert("energy", frame=96)
for fc in action_fcurves(mg.data.animation_data.action): fc.modifiers.new('CYCLES')
mc = light("Map_Glow2", 'POINT', (0, 0, 2.4), CYAN, 60, c="Lights", radius=1.5)

# ----------------------------------------------------------------------------
# PROPS
# ----------------------------------------------------------------------------
def console(name, loc, rotz, parent=None, holo_m=M_HOLO_O, wide=1.4):
    e = empty(name, loc, (0, 0, rotz), c="Props")
    if parent: e.parent = parent
    orange = holo_m is M_HOLO_O
    box("base", (0, 0, 0.45), (wide, 0.55, 0.9), M_HULL, bevel=0.03, parent=e, c="Props")
    box("base_face", (0, -0.26, 0.45), (wide - 0.1, 0.04, 0.7), M_PANELD, bevel=0.015, parent=e, c="Props")
    box("base_glow", (0, -0.285, 0.12), (wide - 0.1, 0.02, 0.05), M_GLOW_C, parent=e, c="Props")
    box("top", (0, -0.05, 0.95), (wide - 0.05, 0.6, 0.08), M_CARBON, rot=(D(-18), 0, 0), bevel=0.02, parent=e, c="Props")
    box("keyframe", (0, -0.12, 0.995), (wide - 0.26, 0.34, 0.012), M_TRIM, rot=(D(-18), 0, 0), parent=e, c="Props")
    box("keys", (0, -0.12, 1.0), (wide - 0.3, 0.3, 0.015), M_SCREEN_O if orange else M_SCREEN_C, rot=(D(-18), 0, 0), parent=e, c="Props")
    holo_panel(f"{name}_panel", (0, 0.15, 1.5), (D(12), 0, 0), wide - 0.3, 0.55, orange, parent=e)
    light(f"{name}_L", 'POINT', (0, -0.3, 1.3), ORANGE if orange else CYAN, 12, parent=e, radius=0.3)
    return e

def holo_panel(name, loc, rot, w, h, orange=True, parent=None, title="SYS // NAV // COMM"):
    """Floating holographic instrument panel: dark translucent backing, bright title, bar chart,
    gauge ring, data bars and a slowly spinning gyro hologram. Local X across, Z up, -Y toward viewer."""
    c = "Holograms"
    glow = M_GLOW_O if orange else M_GLOW_C
    e = empty(name, loc, rot, c=c)
    if parent: e.parent = parent
    box("bg", (0, 0, 0), (w, 0.004, h), M_HOLO_O if orange else M_HOLO_C, parent=e, c=c)
    box("frame_l", (-w / 2, 0, 0), (0.015, 0.015, h + 0.04), glow, parent=e, c=c)
    box("frame_r", (w / 2, 0, 0), (0.015, 0.015, h + 0.04), glow, parent=e, c=c)
    box("hdr_line", (0, -0.006, h / 2 - 0.085), (w - 0.06, 0.003, 0.004), glow, parent=e, c=c)
    text("title", title, (-w / 2 + 0.03, -0.008, h / 2 - 0.045), (D(90), 0, 0), 0.042, glow, parent=e, c=c, align='LEFT', extrude=0.0)
    text("status", "LINK 98%  ◉", (w / 2 - 0.03, -0.008, h / 2 - 0.045), (D(90), 0, 0), 0.03, M_GLOW_G, parent=e, c=c, align='RIGHT', extrude=0.0)
    # bar chart (left third)
    rnd = random.Random(hash(name) & 0xffff)
    bx0 = -w / 2 + 0.05
    for k in range(6):
        hh = 0.05 + rnd.random() * 0.2
        box(f"bar{k}", (bx0 + 0.02 + k * 0.045, -0.008, -h / 2 + 0.06 + hh / 2), (0.028, 0.004, hh), glow, parent=e, c=c)
    box("bar_base", (bx0 + 0.13, -0.008, -h / 2 + 0.055), (0.29, 0.003, 0.004), glow, parent=e, c=c)
    # gauge (centre)
    torus("gauge", (0, -0.008, -h / 2 + 0.19), 0.085, 0.006, glow, parent=e, c=c, rot=(D(90), 0, 0), segs=40, rings=6)
    torus("gauge_in", (0, -0.008, -h / 2 + 0.19), 0.06, 0.003, M_GLOW_W, parent=e, c=c, rot=(D(90), 0, 0), segs=40, rings=6)
    text("gauge_txt", f"{70 + int(rnd.random() * 29)}%", (0, -0.01, -h / 2 + 0.19), (D(90), 0, 0), 0.04, M_GLOW_W, parent=e, c=c, extrude=0.0)
    # data bars (right third)
    for k in range(5):
        ww = 0.08 + rnd.random() * 0.14
        box(f"data{k}", (w / 2 - 0.05 - ww / 2, -0.008, h / 2 - 0.15 - k * 0.055), (ww, 0.004, 0.018), glow if k % 2 else M_GLOW_W, parent=e, c=c)
    # spinning gyro hologram (above the gauge, between chart and data)
    g = empty(f"{name}_gyro", (0, -0.03, 0.08), (0, 0, 0), c=c); g.parent = e
    torus("gyro1", (0, 0, 0), 0.055, 0.004, M_GLOW_C if orange else M_GLOW_O, parent=g, c=c, segs=32, rings=6)
    torus("gyro2", (0, 0, 0), 0.04, 0.004, M_GLOW_W, parent=g, c=c, rot=(D(90), 0, 0), segs=32, rings=6)
    sphere("gyro_core", (0, 0, 0), 0.012, glow, c=c, parent=g, seg=12, ring=8)
    g.rotation_euler = (D(20), 0, 0); g.keyframe_insert("rotation_euler", frame=1)
    g.rotation_euler = (D(20), TAU, TAU); g.keyframe_insert("rotation_euler", frame=360)
    for fc in action_fcurves(g.animation_data.action):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.modifiers.new('CYCLES')
    return e

def bench(name, loc, rotz, parent=None, length=2.4):
    e = empty(name, loc, (0, 0, rotz), c="Props")
    if parent: e.parent = parent
    box("seat", (0, 0, 0.42), (length, 0.6, 0.12), M_PANEL, bevel=0.03, parent=e, c="Props")
    box("cushion", (0, 0.02, 0.50), (length - 0.1, 0.5, 0.06), M_SEAT, bevel=0.02, parent=e, c="Props")
    box("back", (0, 0.32, 0.75), (length, 0.08, 0.55), M_PANEL, rot=(D(-8), 0, 0), bevel=0.03, parent=e, c="Props")
    box("backpad", (0, 0.27, 0.75), (length - 0.1, 0.05, 0.42), M_CUSHION, rot=(D(-8), 0, 0), bevel=0.02, parent=e, c="Props")
    box("leg", (0, 0, 0.18), (length - 0.3, 0.35, 0.36), M_HULL, bevel=0.02, parent=e, c="Props")
    box("legglow", (0, -0.17, 0.06), (length - 0.5, 0.02, 0.03), M_GLOW_C, parent=e, c="Props")
    return e

def crate(name, loc, rotz, parent=None, size=(1.0, 0.7, 0.7), dark=False):
    e = empty(name, loc, (0, 0, rotz), c="Props")
    if parent: e.parent = parent
    box("body", (0, 0, size[2] / 2), size, M_CRATE2 if dark else M_CRATE, bevel=0.04, parent=e, c="Props")
    box("lid", (0, 0, size[2] + 0.03), (size[0] - 0.1, size[1] - 0.1, 0.06), M_TRIM, bevel=0.02, parent=e, c="Props")
    box("stripe", (0, -size[1] / 2, size[2] * 0.55), (size[0] - 0.2, 0.01, 0.06), M_GLOW_O, parent=e, c="Props")
    box("latch", (0, -size[1] / 2 - 0.01, size[2] * 0.3), (0.2, 0.03, 0.12), M_TRIM, bevel=0.01, parent=e, c="Props")
    for s in (-1, 1):
        box(f"rib{s}", (s * (size[0] / 2 - 0.12), 0, size[2] / 2), (0.05, size[1] + 0.02, size[2] - 0.1), M_TRIM, bevel=0.01, parent=e, c="Props")
    text(f"{name}_lbl", "SA-7731", (0, -size[1] / 2 - 0.012, size[2] * 0.78), (D(90), 0, 0), 0.07, M_TRIM, parent=e, c="Props", extrude=0.0)
    return e

for i in (1, 3, 5, 7):
    a = D(45 * i)
    r = HUB_R - WALL_T / 2 - 0.5
    for off in (-1.9, 1.9):
        cx = r * math.cos(a) + off * math.cos(a + D(90))
        cy = r * math.sin(a) + off * math.sin(a + D(90))
        console(f"HubConsole{i}_{off:+.0f}", (cx, cy, 0), a - D(90), parent=hub, holo_m=M_HOLO_O if i in (1, 5) else M_HOLO_C)
    wall_screen(f"HubScreen{i}", ((r + 0.38) * math.cos(a), (r + 0.38) * math.sin(a), 2.4), (0, 0, a - D(90)), 2.0, 1.0, M_SCREEN_O if i in (1, 5) else M_SCREEN_C, parent=hub, title="STATION STATUS" if i in (1, 5) else "TRAFFIC CONTROL")
a = D(45 * 6)
r = HUB_R - WALL_T / 2 - 0.5
bench("HubBench6", (r * math.cos(a), r * math.sin(a), 0), a - D(90), parent=hub, length=3.0)
wall_screen("HubScreen6", ((r + 0.38) * math.cos(a), (r + 0.38) * math.sin(a), 2.4), (0, 0, a - D(90)), 2.6, 1.2, M_SCREEN_C, parent=hub, title="CITADEL NEWS NET")
crate("HubCrate1", (-5.2, -6.0, 0), D(20), parent=hub)
crate("HubCrate2", (-6.1, -5.1, 0), D(-10), parent=hub, dark=True, size=(0.8, 0.8, 0.5))
crate("HubCrate3", (-5.6, -5.6, 0.7), D(35), parent=hub, size=(0.8, 0.6, 0.5))
crate("HubCrate4", (4.8, -6.4, 0), D(-15), parent=hub, size=(1.4, 0.8, 0.9))
import_model("plastic_crate_03", "HubPCrate1", (-4.6, -6.6, 0), D(15), parent=hub)
import_model("plastic_crate_03", "HubPCrate2", (-4.6, -6.6, 0.27), D(-5), parent=hub)
import_model("industrial_pastic_container", "HubCont1", (5.6, -5.4, 0), D(40), parent=hub)
import_model("korean_fire_extinguisher_01", "HubExt1", (-6.9, 4.3, 0), D(30), parent=hub)
import_model("medical_box", "HubMed1", (-5.1, -5.3, 1.2), D(10), parent=hub)
import_model("utility_box_02", "HubUtil1", (6.2, 6.0, 0), D(225), parent=hub)

def sign(name, body, segment, z=3.9, size=0.42, m=M_GLOW_O, offset=0.0):
    a = D(45 * segment)
    r = HUB_R - WALL_T / 2 - 0.08
    ox = offset * math.cos(a + D(90)); oy = offset * math.sin(a + D(90))
    return text(name, body, (r * math.cos(a) + ox, r * math.sin(a) + oy, z), (D(90), 0, a - D(90)), size, m, parent=hub)

sign("Sign_CIC", "COMBAT INFORMATION CENTER", 6, size=0.32)
sign("Sign_D2", "DECK 02", 1, size=0.4)
sign("Sign_D2b", "DECK 02", 5, size=0.4)
sign("Sign_Lounge", "OBSERVATION  ▶", 0, z=HUB_H - 0.55, size=0.3, m=M_GLOW_C)
sign("Sign_Dock", "DOCKING BAY 07", 2, z=HUB_H - 0.55, size=0.3, m=M_GLOW_C)
sign("Sign_Air", "AIRLOCK 01", 4, z=HUB_H - 0.55, size=0.3, m=M_GLOW_C)
sign("Sign_Sys", "SYSTEMS ALLIANCE", 3, size=0.3, m=M_GLOW_C)
sign("Sign_Citadel", "CITADEL SECURITY", 7, size=0.3, m=M_GLOW_C)

# ----------------------------------------------------------------------------
# CORRIDORS
# ----------------------------------------------------------------------------
def corridor(name, angle, length, start_r=HUB_R, far_label="", near_label="CIC"):
    base = (start_r * math.cos(angle), start_r * math.sin(angle), 0)
    e = empty(name, base, (0, 0, angle))
    W, H = CORR_W, CORR_H
    T = WALL_T
    box("floor", (length / 2, 0, -0.15), (length, W + 2 * T, 0.3), M_FLOOR, parent=e)
    box("ceil", (length / 2, 0, H + 0.15), (length, W + 2 * T, 0.3), M_HULL2, parent=e)
    for s in (-1, 1):
        y = s * (W / 2 + T / 2)
        box(f"wall{s}", (length / 2, y, H / 2), (length, T, H), M_HULL, parent=e)
        n = int(length // 2.0)
        for k in range(n):
            x0 = k * 2.0 + 0.25
            box(f"panel{s}_{k}", (x0 + 0.75, s * (W / 2 - 0.03), 2.0), (1.5, 0.06, 1.9), M_PANEL, bevel=0.03, parent=e)
            box(f"seam{s}_{k}", (x0 + 0.75, s * (W / 2 - 0.065), 2.5), (1.3, 0.01, 0.02), M_TRIM, parent=e)
            box(f"low{s}_{k}", (x0 + 0.75, s * (W / 2 - 0.02), 0.6), (1.5, 0.04, 0.7), M_PANELD, bevel=0.02, parent=e)
            box(f"lowglow{s}_{k}", (x0 + 0.75, s * (W / 2 - 0.045), 0.98), (1.3, 0.01, 0.03), M_GLOW_O, parent=e)
        box(f"grate{s}", (length / 2, s * (W / 2 - 0.25), 0.005), (length - 0.2, 0.4, 0.01), M_GRATE, parent=e)
        box(f"fstrip{s}", (length / 2, s * (W / 2 - 0.06), 0.05), (length - 0.2, 0.05, 0.03), M_GLOW_C, parent=e)
        box(f"cstrip{s}", (length / 2, s * (W / 2 - 0.08), H - 0.05), (length - 0.2, 0.05, 0.03), M_GLOW_O, parent=e)
    n = int(length // 2.0)
    for k in range(n + 1):
        x = k * 2.0
        if x > length: break
        for s in (-1, 1):
            box(f"rib{s}_{k}", (x, s * (W / 2 - 0.12), H / 2), (0.3, 0.24, H), M_TRIM, bevel=0.03, parent=e)
            box(f"ribface{s}_{k}", (x, s * (W / 2 - 0.245), H / 2), (0.2, 0.02, H - 0.4), M_PANELD, bevel=0.01, parent=e)
            box(f"ribglow{s}_{k}", (x, s * (W / 2 - 0.26), H / 2), (0.05, 0.02, H - 0.6), M_GLOW_B, parent=e)
            if k % 2 == 1 and x + 1.0 < length:
                sconce(f"sconce{s}_{k}", (x + 1.0, s * (W / 2 - 0.1), 2.6), (0, 0, D(90) if s > 0 else D(-90)), parent=e)
        box(f"ribtop_{k}", (x, 0, H - 0.12), (0.3, W, 0.24), M_TRIM, bevel=0.03, parent=e)
        box(f"ribtopglow_{k}", (x, 0, H - 0.25), (0.06, W - 0.6, 0.02), M_GLOW_W, parent=e)
    for yy, rr in ((-0.9, 0.08), (-0.7, 0.05), (0.8, 0.07)):
        pipe_run(f"conduit{yy}", (0.2, yy, H - 0.3), (length - 0.2, yy, H - 0.3), rr, parent=e, flanges=2.0)
    cable_tray("tray", (0.2, 0.3, H - 0.32), (length - 0.2, 0.3, H - 0.32), 0.25, parent=e)
    box("centerplate", (length / 2, 0, 0.005), (length - 0.4, 1.6, 0.01), M_FLOOR2, parent=e)
    for k in range(int(length // 4) + 1):
        x = 2.0 + k * 4.0
        if x > length - 1: break
        light(f"{name}_L{k}", 'AREA', (x, 0, H - 0.1), (0.9, 0.95, 1.0), 140, size=(1.2, 2.4), rot=(0, 0, 0), parent=e)
    for x, lbl in ((1.2, far_label + "  ▶"), (length - 1.2, "◀  " + near_label)):
        if not lbl.strip("▶◀ "): continue
        box(f"signbox{int(x)}", (x, 0, H - 0.5), (0.1, 1.8, 0.35), M_TRIM, bevel=0.01, parent=e)
        text(f"signtxt{int(x)}", lbl, (x - 0.06, 0, H - 0.5), (D(90), 0, D(-90)), 0.18, M_GLOW_C, parent=e, extrude=0.0)
        text(f"signtxt{int(x)}b", lbl, (x + 0.06, 0, H - 0.5), (D(90), 0, D(90)), 0.18, M_GLOW_C, parent=e, extrude=0.0)
    locker("lockers", (length * 0.45, -(W / 2 - 0.3), 0), (0, 0, D(-90)), parent=e)
    wall_screen("corrscreen", (length * 0.7, (W / 2 - 0.1), 2.0), (0, 0, D(90)), 1.2, 0.7, M_SCREEN_C, parent=e, title="DECK 02 MAP")
    emergency_light("emlight", (length - 0.6, (W / 2 - 0.12), 3.0), (0, 0, D(90)), parent=e)
    import_model("korean_fire_extinguisher_01", f"{name}_ext", (length * 0.3, (W / 2 - 0.35), 0), D(180), parent=e)
    return e

def blast_door(parent, x, name, label):
    W, H = CORR_W, CORR_H
    e = empty(name, (x, 0, 0))
    e.parent = parent
    box("frame", (0.2, 0, H / 2), (0.4, W + 0.9, H + 0.5), M_HULL, bevel=0.04, parent=e)
    box("frame_inner", (0.0, 0, H / 2), (0.1, W + 0.3, H + 0.2), M_TRIM, bevel=0.03, parent=e)
    box("frame_glow", (-0.03, 0, H / 2 + 0.05), (0.02, W + 0.1, H - 0.1), M_GLOW_O, parent=e)
    for s in (-1, 1):
        box(f"leaf{s}", (-0.0, s * (W / 4 + 0.01), H / 2 - 0.1), (0.25, W / 2 - 0.02, H - 0.2), M_DOOR, bevel=0.03, parent=e)
        box(f"leaf_detail{s}", (-0.13, s * (W / 4 + 0.01), 1.8), (0.02, W / 2 - 0.5, 1.2), M_PANEL, bevel=0.02, parent=e)
        box(f"leaf_rib{s}", (-0.14, s * (W / 4 + 0.01), 2.9), (0.03, W / 2 - 0.4, 0.3), M_PANELD, bevel=0.01, parent=e)
        box(f"leaf_chev{s}", (-0.14, s * (W / 4 + 0.01), 0.7), (0.02, W / 2 - 0.6, 0.12), M_GLOW_O, parent=e)
        box(f"leaf_hazard{s}", (-0.14, s * (W / 4 + 0.01), 0.3), (0.02, W / 2 - 0.3, 0.2), M_HAZARD, parent=e)
    box("seam", (-0.14, 0, H / 2 - 0.1), (0.01, 0.04, H - 0.4), M_GLOW_O, parent=e)
    box("lock", (-0.25, -(W / 2 + 0.2), 1.35), (0.06, 0.25, 0.35), M_HULL, bevel=0.01, parent=e)
    box("lock_screen", (-0.29, -(W / 2 + 0.2), 1.35), (0.01, 0.18, 0.25), M_SCREEN_O, parent=e)
    status_panel(f"{name}_status", (-0.25, (W / 2 + 0.2), 1.6), (0, 0, D(-90)), parent=e, ok=False)
    text(f"{name}_label", label, (-0.16, 0, H - 0.45), (D(90), 0, D(-90)), 0.26, M_GLOW_O, parent=e)
    text(f"{name}_sub", "PRESSURISED  //  AUTHORISED PERSONNEL ONLY", (-0.16, 0, H - 0.75), (D(90), 0, D(-90)), 0.09, M_GLOW_C, parent=e, extrude=0.0)
    light(f"{name}_light", 'POINT', (-1.0, 0, 2.2), ORANGE, 60, parent=e, radius=0.4)
    # rotating amber beacon above the door
    piv = empty(f"{name}_beacon", (-0.45, 0, H - 0.88), (0, 0, 0)); piv.parent = e
    box("housing", (0, 0, -0.05), (0.2, 0.2, 0.1), M_TRIM, bevel=0.01, parent=piv)
    sphere("dome", (0, 0, 0.03), 0.07, M_GLOW_O, c="Station", parent=piv, seg=16, ring=8, scale=(1, 1, 0.7))
    bl = light(f"{name}_beamlight", 'SPOT', (0, 0, 0), (1.0, 0.5, 0.1), 500, rot=(D(55), 0, 0), parent=piv, radius=0.1, spot=35)
    bl.data.use_shadow = False; bl.data.spot_blend = 0.4
    piv.rotation_euler = (0, 0, 0); piv.keyframe_insert("rotation_euler", frame=1)
    piv.rotation_euler = (0, 0, TAU); piv.keyframe_insert("rotation_euler", frame=150)
    for fc in action_fcurves(piv.animation_data.action):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.modifiers.new('CYCLES')
    return e

c_lounge = corridor("Corr_Lounge", D(0), 12.0, far_label="OBSERVATION DECK")
c_dock = corridor("Corr_Dock", D(90), 10.0, far_label="DOCKING BAY 07")
c_air = corridor("Corr_Airlock", D(180), 10.0, far_label="AIRLOCK 01")
blast_door(c_dock, 10.0, "Door_Dock", "DOCKING BAY 07")
blast_door(c_air, 10.0, "Door_Airlock", "AIRLOCK 01")
crate("CorrCrate1", (6.0, 1.2, 0), D(5), parent=c_dock, size=(0.9, 0.6, 0.6), dark=True)
crate("CorrCrate2", (6.9, 1.25, 0), D(-3), parent=c_dock, size=(0.7, 0.6, 0.5))
import_model("plastic_crate_01", "DockPCrate", (7.8, 1.3, 0), D(10), parent=c_dock)
import_model("plastic_crate_03", "AirPCrate", (3.0, 1.3, 0), D(-20), parent=c_air)
import_model("industrial_pastic_container", "AirCont", (3.8, 1.25, 0), D(5), parent=c_air)

# ----------------------------------------------------------------------------
# OBSERVATION LOUNGE
# ----------------------------------------------------------------------------
LX = HUB_R + 12.0
LR = 11.0
LH = 5.0
HALF = 42
lounge = empty("Lounge", (LX, 0, 0))
NP = 12                                     # window panes (wide, few mullions)
SILL = 0.65                                 # low sill
GTOP = LH - 0.3                             # glass top; header fills the rest to the ceiling
arc = [(LR * math.cos(D(a)), LR * math.sin(D(a))) for a in [(-HALF + (2 * HALF) * k / NP) for k in range(NP + 1)]]
yend = LR * math.sin(D(HALF)); xend = LR * math.cos(D(HALF))
floor_pts = [(0, -yend)] + arc + [(0, yend)]
polyprism("Lounge_Floor", floor_pts, -0.3, 0.0, M_FLOOR, parent=lounge)
polyprism("Lounge_Ceiling", floor_pts, LH, LH + 0.3, M_HULL2, parent=lounge)
wall_segment(lounge, "LoungeBack", 2 * yend, LH, True, CORR_W, CORR_H, (0, 0, 0), D(-90))
for s in (-1, 1):
    wall_segment(lounge, f"LoungeSide{s}", xend, LH, False, 0, 0, (xend / 2, s * yend, 0), 0.0 if s < 0 else D(180))
for k in range(NP):
    (x0, y0), (x1, y1) = arc[k], arc[k + 1]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    ang = math.atan2(y1 - y0, x1 - x0)
    w = math.hypot(x1 - x0, y1 - y0)
    box(f"Win_Glass{k}", (mx, my, (SILL + GTOP) / 2), (w, 0.04, GTOP - SILL), M_GLASS, rot=(0, 0, ang), parent=lounge)
    box(f"Win_Sill{k}", (mx, my, SILL / 2), (w + 0.05, 0.5, SILL), M_HULL, rot=(0, 0, ang), parent=lounge, bevel=0.02)
    box(f"Win_SillFace{k}", (mx, my, SILL / 2), (w - 0.1, 0.56, SILL - 0.25), M_PANELD, rot=(0, 0, ang), parent=lounge, bevel=0.02)
    box(f"Win_SillTop{k}", (mx, my, SILL), (w + 0.05, 0.56, 0.05), M_TRIM, rot=(0, 0, ang), parent=lounge)
    box(f"Win_SillGlow{k}", (mx - 0.25 * math.cos(ang), my - 0.25 * math.sin(ang), SILL + 0.04), (w - 0.1, 0.03, 0.02), M_GLOW_C, rot=(0, 0, ang), parent=lounge)
    box(f"Win_Head{k}", (mx, my, (GTOP + LH) / 2), (w + 0.05, 0.5, LH - GTOP), M_HULL, rot=(0, 0, ang), parent=lounge, bevel=0.02)
    box(f"Win_HeadGlow{k}", (mx - 0.22 * math.cos(ang), my - 0.22 * math.sin(ang), GTOP - 0.03), (w - 0.1, 0.04, 0.03), M_GLOW_W, rot=(0, 0, ang), parent=lounge)
    # louvered viewport shutters: upper half slides up into the header, lower half down into the sill
    zm = (SILL + GTOP) / 2
    for half, z0, z1, open_dz in (("U", zm, GTOP, GTOP - zm + 0.02), ("L", SILL, zm, -(zm - SILL) - 0.05)):
        sh = shutter(f"Win_Shutter{half}{k}", (mx, my, 0.0), w - 0.02, z0, z1, ang, lounge, lead_bottom=(half == "U"), slats=5)
        sh["me_blind"] = [0.0, open_dz]
# big red shutter button on a pedestal in front of the window
M_BTN = mat("ButtonRed", (0.9, 0.05, 0.03), 0.0, 0.3, (1.0, 0.1, 0.05), 2.0, coat=1.0)
ped = empty("ShutterPedestal", (7.6, -3.4, 0.0), (0, 0, 0), c="Props"); ped.parent = lounge
cyl("ped_base", (0, 0, 0.06), 0.42, 0.12, M_TRIM, verts=32, parent=ped, c="Props")
cyl("ped_column", (0, 0, 0.55), 0.22, 0.9, M_HULL, verts=32, parent=ped, c="Props")
cyl("ped_glow", (0, 0, 0.14), 0.24, 0.03, M_GLOW_C, verts=32, parent=ped, c="Props")
cyl("ped_top", (0, 0, 1.0), 0.34, 0.08, M_PANELD, verts=32, parent=ped, c="Props")
torus("ped_hazard", (0, 0, 1.045), 0.3, 0.02, M_HAZARD, parent=ped, c="Props", segs=48, rings=8)
cyl("ped_collar", (0, 0, 1.06), 0.17, 0.05, M_RAIL, verts=32, parent=ped, c="Props")
btn = sphere("ShutterButton", (0, 0, 1.07), 0.15, M_BTN, c="Props", parent=ped, seg=32, ring=16, scale=(1, 1, 0.6))
btn["me_button"] = "blinds"
text("ped_label", "VIEWPORT SHUTTERS", (-0.23, 0, 0.72), (D(90), 0, D(-90)), 0.05, M_GLOW_O, parent=ped, c="Props", extrude=0.0)
text("ped_label2", "PRESS TO OPEN", (-0.23, 0, 0.62), (D(90), 0, D(-90)), 0.04, M_GLOW_C, parent=ped, c="Props", extrude=0.0)
light("Shutter_BtnLight", 'POINT', (0, 0, 1.5), (1.0, 0.15, 0.1), 15, parent=ped, radius=0.3)
pf = bpy.data.objects.get("PlanetFill")

for k in range(NP + 1):
    x, y = arc[k]
    ang = math.atan2(y, x)
    box(f"Win_Mullion{k}", (x, y, LH / 2), (0.07, 0.26, LH), M_TRIM, rot=(0, 0, ang), parent=lounge, bevel=0.015)
    if k % 2 == 0:
        box(f"Win_MullGlow{k}", (x - 0.14 * math.cos(ang), y - 0.14 * math.sin(ang), LH / 2), (0.015, 0.04, LH - 1.4), M_GLOW_B, rot=(0, 0, ang), parent=lounge)
# seating pulled back toward the entrance and turned to face the window; nothing at the sill
bench("LoungeBench1", (4.6, -3.7, 0), D(90), parent=lounge, length=2.8)
bench("LoungeBench2", (4.6, 3.7, 0), D(90), parent=lounge, length=2.8)
bench("LoungeBench3", (3.6, 0, 0), D(90), parent=lounge, length=2.6)
cyl("LoungeTable", (4.9, 0, 0.3), 0.45, 0.6, M_HULL, verts=32, parent=lounge)
cyl("LoungeTableTop", (4.9, 0, 0.62), 0.6, 0.05, M_PANEL, verts=32, parent=lounge)
torus("LoungeTableGlow", (4.9, 0, 0.56), 0.47, 0.02, M_GLOW_O, parent=lounge)
import_model("modern_arm_chair_01", "LoungeChair1", (3.4, -2.3, 0), D(110), parent=lounge)
import_model("modern_arm_chair_01", "LoungeChair2", (3.4, 2.3, 0), D(70), parent=lounge)
import_model("potted_plant_01", "LoungePlant1", (1.0, 4.6, 0), D(20), parent=lounge)
import_model("potted_plant_02", "LoungePlant2", (1.0, -4.8, 0), D(-40), parent=lounge)
console("LoungeConsole", (2.0, -5.2, 0), D(-90 + 30), parent=lounge, holo_m=M_HOLO_C, wide=1.2)
box("LoungeCeilTrough", (5.0, 0, LH - 0.1), (6.0, 7.0, 0.2), M_PANEL2, parent=lounge)
box("LoungeCeilGlow", (5.0, 0, LH - 0.22), (5.6, 0.1, 0.04), M_GLOW_W, parent=lounge)
box("LoungeCeilGlow2", (5.0, -2.5, LH - 0.22), (5.6, 0.1, 0.04), M_GLOW_C, parent=lounge)
box("LoungeCeilGlow3", (5.0, 2.5, LH - 0.22), (5.6, 0.1, 0.04), M_GLOW_C, parent=lounge)
text("Sign_ObsDeck", "OBSERVATION DECK", (0.25, 3.5, 3.9), (D(90), 0, D(90)), 0.3, M_GLOW_O, parent=lounge)
text("Sign_ObsDeck2", "NO UNAUTHORISED ACCESS BEYOND THIS POINT", (0.25, -3.5, 1.3), (D(90), 0, D(90)), 0.14, M_GLOW_C, parent=lounge)
wall_screen("LoungeScreen", (0.3, 2.0, 2.4), (0, 0, D(90)), 1.8, 1.0, M_SCREEN_O, parent=lounge, title="ORBITAL TRAFFIC")

# ----------------------------------------------------------------------------
# SPACE
# ----------------------------------------------------------------------------
world = bpy.data.worlds.new("Space")
scene.world = world
world.use_nodes = True
wn = world.node_tree
bg = wn.nodes["Background"]
tc = wn.nodes.new("ShaderNodeTexCoord")
mp = wn.nodes.new("ShaderNodeMapping")
vor = wn.nodes.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = 260.0; vor.inputs["Randomness"].default_value = 1.0
stars = wn.nodes.new("ShaderNodeMath"); stars.operation = 'LESS_THAN'; stars.inputs[1].default_value = 0.035
starsp = wn.nodes.new("ShaderNodeMath"); starsp.operation = 'MULTIPLY'; starsp.inputs[1].default_value = 25.0
vor2 = wn.nodes.new("ShaderNodeTexVoronoi"); vor2.inputs["Scale"].default_value = 90.0
stars2 = wn.nodes.new("ShaderNodeMath"); stars2.operation = 'LESS_THAN'; stars2.inputs[1].default_value = 0.02
starsp2 = wn.nodes.new("ShaderNodeMath"); starsp2.operation = 'MULTIPLY'; starsp2.inputs[1].default_value = 60.0
vor3 = wn.nodes.new("ShaderNodeTexVoronoi"); vor3.inputs["Scale"].default_value = 600.0
stars3 = wn.nodes.new("ShaderNodeMath"); stars3.operation = 'LESS_THAN'; stars3.inputs[1].default_value = 0.03
starsp3 = wn.nodes.new("ShaderNodeMath"); starsp3.operation = 'MULTIPLY'; starsp3.inputs[1].default_value = 6.0
neb = wn.nodes.new("ShaderNodeTexNoise"); neb.inputs["Scale"].default_value = 1.6; neb.inputs["Detail"].default_value = 12
nebr = wn.nodes.new("ShaderNodeValToRGB")
nebr.color_ramp.elements[0].position = 0.35; nebr.color_ramp.elements[0].color = (0.002, 0.003, 0.012, 1)
nebr.color_ramp.elements[1].position = 0.78; nebr.color_ramp.elements[1].color = (0.03, 0.05, 0.18, 1)
e = nebr.color_ramp.elements.new(0.92); e.color = (0.16, 0.05, 0.2, 1)
add1 = wn.nodes.new("ShaderNodeMath"); add1.operation = 'ADD'
add3 = wn.nodes.new("ShaderNodeMath"); add3.operation = 'ADD'
mixc = wn.nodes.new("ShaderNodeMix"); mixc.data_type = 'RGBA'; mixc.blend_type = 'ADD'; mixc.inputs[0].default_value = 1.0
wn.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
for v_ in (vor, vor2, vor3, neb):
    wn.links.new(mp.outputs["Vector"], v_.inputs["Vector"])
wn.links.new(vor.outputs["Distance"], stars.inputs[0]); wn.links.new(stars.outputs[0], starsp.inputs[0])
wn.links.new(vor2.outputs["Distance"], stars2.inputs[0]); wn.links.new(stars2.outputs[0], starsp2.inputs[0])
wn.links.new(vor3.outputs["Distance"], stars3.inputs[0]); wn.links.new(stars3.outputs[0], starsp3.inputs[0])
wn.links.new(starsp.outputs[0], add1.inputs[0]); wn.links.new(starsp2.outputs[0], add1.inputs[1])
wn.links.new(add1.outputs[0], add3.inputs[0]); wn.links.new(starsp3.outputs[0], add3.inputs[1])
wn.links.new(neb.outputs["Fac"], nebr.inputs["Fac"])
wn.links.new(nebr.outputs["Color"], mixc.inputs[6])
wn.links.new(add3.outputs[0], mixc.inputs[7])
wn.links.new(mixc.outputs[2], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.0
# interior haze as volume meshes over the hub and corridors only (a world volume fogged the view
# outside the lounge window); kept in the Holograms collection so the walker ignores them
M_FOG = bpy.data.materials.new("InteriorHaze"); M_FOG.use_nodes = True
_fn = M_FOG.node_tree; _fn.nodes.remove(_fn.nodes["Principled BSDF"])
_vol = _fn.nodes.new("ShaderNodeVolumePrincipled")
_vol.inputs["Density"].default_value = 0.008
_vol.inputs["Anisotropy"].default_value = 0.35
_vol.inputs["Color"].default_value = (0.6, 0.75, 1.0, 1)
_fn.links.new(_vol.outputs["Volume"], _fn.nodes["Material Output"].inputs["Volume"])
fogpts = [((circum + 0.3) * math.cos(D(22.5 + 45 * i)), (circum + 0.3) * math.sin(D(22.5 + 45 * i))) for i in range(8)]
polyprism("Fog_Hub", fogpts, -0.05, HUB_H + 0.05, M_FOG, c="Holograms")
for nm, ang, length in (("Fog_CorrLounge", 0.0, 12.0), ("Fog_CorrDock", D(90), 10.0), ("Fog_CorrAirlock", D(180), 10.0)):
    fb = box(nm, (0, 0, 0), (length, CORR_W + 0.8, CORR_H + 0.1), M_FOG, rot=(0, 0, ang), c="Holograms")
    fb.location = ((HUB_R + length / 2) * math.cos(ang), (HUB_R + length / 2) * math.sin(ang), CORR_H / 2)

planet = sphere("Planet", (LX + 160, 55, -45), 85, M_PLANET, c="Space", seg=128, ring=64)
atmo_m = mat("Atmo", (0.3, 0.6, 1.0), 0, 0.5, (0.4, 0.65, 1.0), 3.0, alpha=0.3, blended=True)
nt = atmo_m.node_tree; p = nt.nodes["Principled BSDF"]
lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35
nt.links.new(lw.outputs["Fresnel"], p.inputs["Alpha"])
sphere("PlanetAtmo", (LX + 160, 55, -45), 88, atmo_m, c="Space", seg=96, ring=48)
sphere("Moon", (LX + 120, -70, 30), 9, pbr("MoonRock", "Metal046A", tile=40, tint=(0.9, 0.86, 0.8), rough=1.2, metallic=0.0, bump=1.0), c="Space", seg=48, ring=24)
ringpiv = empty("StationRingPivot", (LX + 70, -20, 10), (D(70), 0, D(20)), c="Space")
ring = torus("StationRing", (0, 0, 0), 40, 2.0, pbr("RingHull", "Metal028", tile=6.0, tint=(0.85, 0.87, 0.95), rough=1.0, bump=0.5), c="Space", parent=ringpiv)
ring.keyframe_insert("rotation_euler", frame=1); ring.rotation_euler = (0, 0, TAU); ring.keyframe_insert("rotation_euler", frame=6000)
for fc in action_fcurves(ring.animation_data.action):
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    fc.modifiers.new('CYCLES')
planet.keyframe_insert("rotation_euler", frame=1); planet.rotation_euler = (0, 0, TAU); planet.keyframe_insert("rotation_euler", frame=9000)
for fc in action_fcurves(planet.animation_data.action):
    for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
    fc.modifiers.new('CYCLES')
for k in range(40):
    a = TAU * k / 40
    box(f"RingLight{k}", (40 * math.cos(a), 40 * math.sin(a), 2.0), (0.6, 0.6, 0.6), M_GLOW_W, c="Space", parent=ring)
    box(f"RingPod{k}", (40 * math.cos(a), 40 * math.sin(a), -2.4), (2.5, 2.5, 1.2), M_HULL, c="Space", parent=ring, rot=(0, 0, a))
def ship(name, loc, scale=1.0, c="Space"):
    e = empty(name, loc, c=c)
    box("hull", (0, 0, 0), (14 * scale, 3 * scale, 2 * scale), pbr("ShipHull", "Metal028", tile=4.0, tint=(0.9, 0.92, 1.0), rough=1.0, bump=0.4), bevel=0.3, parent=e, c=c)
    box("bridge", (3 * scale, 0, 1.2 * scale), (4 * scale, 2 * scale, 1 * scale), M_HULL, bevel=0.2, parent=e, c=c)
    for s in (-1, 1):
        box(f"wing{s}", (-3 * scale, s * 4 * scale, 0), (5 * scale, 6 * scale, 0.5 * scale), M_DOOR, bevel=0.1, parent=e, c=c)
        box(f"engine{s}", (-7.2 * scale, s * 1.0 * scale, 0), (0.4 * scale, 1.2 * scale, 1.2 * scale), M_GLOW_C, parent=e, c=c)
    for k in range(6):
        box(f"win{k}", (3 * scale - k * 1.2 * scale, 1.55 * scale, 0.3 * scale), (0.5 * scale, 0.05, 0.3 * scale), M_GLOW_W, parent=e, c=c)
    return e
s1 = ship("Frigate1", (LX + 60, -40, -8), 1.0)
s1.keyframe_insert("location", frame=1)
s1.location = (LX + 60, 60, 4); s1.keyframe_insert("location", frame=1800)
s2 = ship("Frigate2", (LX + 110, 70, 20), 2.2)
s2.rotation_euler = (0, 0, D(-30)); s2.keyframe_insert("location", frame=1)
s2.location = (LX + 110, -60, 25); s2.keyframe_insert("location", frame=3000)
s3 = ship("Shuttle", (LX + 14.5, -45, 1.6), 0.22)
s3.rotation_euler = (0, 0, D(90)); s3.keyframe_insert("location", frame=1)
s3.location = (LX + 14.5, 45, 2.2); s3.keyframe_insert("location", frame=420)
s3.location = (LX + 14.5, -45, 1.6); s3.keyframe_insert("location", frame=421)
for o in (s1, s2, s3):
    for fc in action_fcurves(o.animation_data.action):
        for kp in fc.keyframe_points: kp.interpolation = 'LINEAR'
        fc.modifiers.new('CYCLES')
sun = light("Sun", 'SUN', (LX + 40, 30, 20), (1.0, 0.95, 0.85), 1.0, c="Lights")
sun.rotation_euler = (D(55), D(10), D(-50))
sun.data.angle = D(1.0)
sun.data.volume_factor = 0.0
# key light for everything outside the window, from the side so the planet shows a terminator;
# shadow-casting so it cannot leak into the station, and kept out of the volumetric haze
sun2 = light("Sun_Space", 'SUN', (LX + 5, 0, 10), (1.0, 0.93, 0.82), 2.0, c="Lights")
sun2.rotation_euler = Vector((0.5, 0.8, -0.3)).to_track_quat('-Z', 'Y').to_euler()
sun2.data.angle = D(2.0); sun2.data.volume_factor = 0.0
sun3 = light("Sun_Rim", 'SUN', (LX + 5, 0, 10), (0.5, 0.7, 1.0), 1.0, c="Lights")
sun3.rotation_euler = Vector((0.2, -0.9, 0.35)).to_track_quat('-Z', 'Y').to_euler()
sun3.data.angle = D(3.0); sun3.data.volume_factor = 0.0
pfl = light("PlanetFill", 'AREA', (LX + 10.5, 0, 2.5), (0.35, 0.6, 1.0), 60, size=(8, 4), rot=(0, D(-90), 0), c="Lights")
pfl["me_blind_light"] = [60.0, 400.0]
pfl.data.volume_factor = 0.0

# ----------------------------------------------------------------------------
# LIGHTS
# ----------------------------------------------------------------------------
light("Hub_Top", 'AREA', (0, 0, HUB_H - 0.5), (0.95, 0.97, 1.0), 4200, size=8.0, c="Lights")
for i in range(8):
    a = D(45 * i)
    r = HUB_R - 2.2
    light(f"Hub_Wash{i}", 'AREA', (r * math.cos(a), r * math.sin(a), HUB_H - 0.6), (0.9, 0.93, 1.0), 350, size=(3.0, 1.0), rot=(D(-55), 0, a + D(90)), c="Lights")
for i in range(8):
    a = D(45 * i)
    r = HUB_R - 1.6
    light(f"Hub_Wall{i}", 'SPOT', (r * math.cos(a), r * math.sin(a), HUB_H - 0.3), (0.85, 0.9, 1.0), 700, rot=(D(-35), 0, a + D(90)), c="Lights", radius=0.5)
    r2 = HUB_R - 1.2
    light(f"Hub_FloorGlow{i}", 'POINT', (r2 * math.cos(a), r2 * math.sin(a), 0.25), CYAN, 25, c="Lights", radius=0.6)
light("Lounge_Top", 'AREA', (LX + 5, 0, LH - 0.4), (0.95, 0.97, 1.0), 400, size=(5, 7), c="Lights")

# ----------------------------------------------------------------------------
# CHARACTERS (MPFB, from chars/*.blend)
# ----------------------------------------------------------------------------
def idle_animation(rig, seed=1, T=144):
    """Layer subtle breathing / sway / head motion on top of the rig's base pose using armature-space axes."""
    rnd = random.Random(seed)
    pb = rig.pose.bones
    for b in pb:
        if b.rotation_mode != 'QUATERNION':
            q = b.rotation_euler.to_quaternion()
            b.rotation_mode = 'QUATERNION'
            b.rotation_quaternion = q
    bpy.context.view_layer.update()
    base = {}
    frames = {}
    def rot_world(bname, axis, ang):
        if bname not in base: return
        ax = frames[bname] @ Vector(axis)
        pb[bname].rotation_quaternion = Quaternion(ax, ang) @ pb[bname].rotation_quaternion
    phase = rnd.random() * TAU
    X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    anim_bones = ("spine01", "spine02", "spine03", "spine04", "neck01", "neck02", "head", "clavicle.L", "clavicle.R", "upperarm01.L", "upperarm01.R", "root")
    for f in range(1, T + 2, 8):
        t = (f - 1) / T * TAU
        breathe = math.sin(t * 2 + phase)
        sway = math.sin(t + phase)
        look = math.sin(t * 0.5 + phase * 0.3)
        bpy.context.scene.frame_set(f)          # base pose may itself be animated (pose blend)
        for b in pb:
            base[b.name] = b.rotation_quaternion.copy()
            A = b.matrix.to_3x3() @ b.rotation_quaternion.to_matrix().inverted()
            frames[b.name] = A.inverted()
        rot_world("spine01", X, D(0.9) * breathe)
        rot_world("spine02", X, D(0.6) * breathe)
        rot_world("spine03", Y, D(0.7) * sway)
        rot_world("spine04", Y, D(0.5) * sway)
        rot_world("neck01", X, D(-0.6) * breathe)
        rot_world("neck02", Z, D(1.5) * look)
        rot_world("head", Z, D(3.5) * look)
        rot_world("head", X, D(1.2) * look)
        rot_world("clavicle.L", X, D(1.0) * breathe)
        rot_world("clavicle.R", X, D(1.0) * breathe)
        rot_world("upperarm01.L", X, D(0.8) * breathe)
        rot_world("upperarm01.R", X, D(0.8) * breathe)
        rot_world("upperarm01.L", Z, D(-0.9) * sway)
        rot_world("upperarm01.R", Z, D(-0.9) * sway)
        rot_world("root", Y, D(0.6) * sway)
        for bn in anim_bones:
            if bn in base:
                pb[bn].keyframe_insert("rotation_quaternion", frame=f)
    act = rig.animation_data.action
    for fc in action_fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
        if not fc.modifiers: fc.modifiers.new('CYCLES')
    bpy.context.scene.frame_set(1)

def load_character(name, loc, rotz, seed=1):
    path = os.path.join(CHARDIR, f"{name}.blend")
    if not os.path.exists(path):
        print("missing character", path); return None
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [name]
    cc = dst.collections[0]
    coll("Characters").children.link(cc)
    rig = next(o for o in cc.objects if o.type == 'ARMATURE')
    rig.location = loc
    rig.rotation_euler = (0, 0, rotz)
    for o in cc.objects:
        if o.type == 'MESH':
            for md in o.modifiers:
                if md.type == 'SUBSURF':
                    md.levels = 1; md.render_levels = 2
    bpy.context.view_layer.update()
    idle_animation(rig, seed)
    fx, fy = math.sin(rotz), -math.cos(rotz)   # character forward (MakeHuman faces -Y)
    light(f"{name}_Key", 'SPOT', (loc[0] + fx * 1.4 - fy * 0.8, loc[1] + fy * 1.4 + fx * 0.8, loc[2] + 3.2), (1.0, 0.95, 0.9), 650, rot=(0, 0, 0), c="Lights", radius=0.6, spot=55)
    key = bpy.data.objects[f"{name}_Key"]
    key.rotation_euler = (Vector((loc[0], loc[1], loc[2] + 1.3)) - key.location).to_track_quat('-Z', 'Y').to_euler()
    light(f"{name}_Rim", 'SPOT', (loc[0] - fx * 1.6, loc[1] - fy * 1.6, loc[2] + 3.0), (0.4, 0.7, 1.0), 300, c="Lights", radius=0.5, spot=60)
    rim = bpy.data.objects[f"{name}_Rim"]
    rim.rotation_euler = (Vector((loc[0], loc[1], loc[2] + 1.2)) - rim.location).to_track_quat('-Z', 'Y').to_euler()
    return rig

def face_toward(pos, target):
    return math.atan2(target[0] - pos[0], -(target[1] - pos[1]))

posA = (1.5, -2.2, 0.48)
charA = load_character("Vessa", posA, face_toward(posA, (0, 0, 0)), seed=3)
chB_a = D(45 * 1)
cbx = (HUB_R - WALL_T / 2 - 0.5) * math.cos(chB_a) + 1.9 * math.cos(chB_a + D(90)) - 0.75 * math.cos(chB_a)
cby = (HUB_R - WALL_T / 2 - 0.5) * math.sin(chB_a) + 1.9 * math.sin(chB_a + D(90)) - 0.75 * math.sin(chB_a)
charB = load_character("Liora", (cbx, cby, 0.0), chB_a + D(90), seed=11)

# ----------------------------------------------------------------------------
# COMPOSITOR BLOOM
# ----------------------------------------------------------------------------
try:
    ng = bpy.data.node_groups.new("StationComp", 'CompositorNodeTree')
    ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    rl = ng.nodes.new("CompositorNodeRLayers")
    glare = ng.nodes.new("CompositorNodeGlare")
    try:
        glare.inputs["Type"].default_value = 'Bloom'
    except Exception as ex:
        print("glare type:", ex)
    for sock, val in (("Threshold", 1.5), ("Strength", 0.12), ("Size", 0.6), ("Quality", 'HIGH')):
        try:
            glare.inputs[sock].default_value = val
        except Exception:
            pass
    out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(rl.outputs["Image"], glare.inputs["Image"])
    ng.links.new(glare.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = ng
    print("compositor bloom set")
except Exception as ex:
    print("compositor:", ex)

# ----------------------------------------------------------------------------
# CAMERA / VIEWPORT
# ----------------------------------------------------------------------------
cam_data = bpy.data.cameras.new("StartCam"); cam_data.lens = 24
cam = bpy.data.objects.new("StartCam", cam_data)
link(cam, "Camera")
cam.location = (-12.5, 0.0, 1.7)
cam.rotation_euler = (D(88), 0, D(-90))
scene.camera = cam
cam2 = bpy.data.objects.new("LoungeCam", bpy.data.cameras.new("LoungeCam")); cam2.data.lens = 22
link(cam2, "Camera"); cam2.location = (LX + 1.0, -3.0, 1.7); cam2.rotation_euler = (D(86), 0, D(-70))
cam3 = bpy.data.objects.new("MapCam", bpy.data.cameras.new("MapCam")); cam3.data.lens = 30
link(cam3, "Camera"); cam3.location = (4.0, -4.5, 1.75); cam3.rotation_euler = (D(80), 0, D(45))

for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = 'RENDERED'
                    sp.shading.use_scene_lights_render = True
                    sp.shading.use_scene_world_render = True
                    try:
                        sp.shading.use_compositor = 'ALWAYS'
                    except Exception:
                        pass
                    sp.overlay.show_overlays = False
                    sp.clip_start = 0.05
                    sp.clip_end = 2000
                    sp.lens = 70
                    r3d = sp.region_3d
                    r3d.view_perspective = 'PERSP'
                    r3d.view_location = (-9.5, 0, 1.7)
                    r3d.view_rotation = Euler((D(88), 0, D(-90))).to_quaternion()
                    r3d.view_distance = 3.0

scene.frame_set(1)
bpy.context.view_layer.update()

out = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else os.path.join(HERE, "me_station.blend")
bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
print("SAVED", out, "objects:", len(bpy.data.objects))
