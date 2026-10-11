"""Launcher helper: opens the station in first-person walk mode.
Used by run_station.sh / run_demo.sh:  blender me_station.blend --python walk_start.py

Provides a custom walk operator (view3d.me_walk) instead of Blender's built-in walk navigation:
  * explicit key-state tracking with release handling, plus a watchdog that drops any key whose
    OS key-repeat stops arriving (fixes "keeps moving after I let go")
  * frame-rate independent speed, gravity, jump, Shift to run, Alt to creep
  * wall collision (slides along walls instead of walking through them)
Env: ME_DEMO=1 clamps textures / cheap AA, ME_SHOWFPS=1 shows stats and plays every frame,
     ME_NATIVE_WALK=1 uses Blender's own walk operator instead.
"""
import bpy, math, os, time, json
import numpy as np
import blf, gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Euler, Quaternion
from mathutils.bvhtree import BVHTree

prefs = bpy.context.preferences
prefs.inputs.navigation_mode = 'WALK'
w = prefs.inputs.walk_navigation
w.use_gravity = True
w.view_height = 1.70
w.walk_speed = 2.6
w.walk_speed_factor = 3.0
w.jump_height = 0.45
w.mouse_speed = 1.0
prefs.view.show_splash = False
if os.environ.get("ME_DEMO"):
    prefs.system.gl_texture_limit = 'CLAMP_1024'
    prefs.system.viewport_aa = 'FXAA'
    prefs.system.anisotropic_filter = 'FILTER_2'
SHOW_FPS = bool(os.environ.get("ME_SHOWFPS"))
NATIVE = bool(os.environ.get("ME_NATIVE_WALK"))

START_EYE = (-12.5, 0.0, 1.70)
START_ROT = Euler((math.radians(90), 0.0, math.radians(-90)))  # looking down +X toward the hub
if os.environ.get("ME_START"):           # "x,y,z,yaw_deg" (yaw 0 = looking +Y, -90 = +X)
    _v = [float(t) for t in os.environ["ME_START"].split(",")]
    START_EYE = tuple(_v[:3]); START_ROT = Euler((math.radians(90), 0.0, math.radians(_v[3])))


class Interaction:
    """Press-to-talk: each baked character has a gesture clip (shape keys after the idle loop),
    turns to face the player, and shows a subtitle line."""
    RANGE = 3.2
    DURATION = 5.5
    TURN_TIME = 0.6

    def __init__(self):
        self.chars = {}
        raw = bpy.context.scene.get("me_chars")
        if raw:
            self.chars = json.loads(raw)
        self.objs = {}
        for o in bpy.data.objects:
            cn = o.get("me_char")
            if cn and o.type == 'MESH' and o.data.shape_keys:
                self.objs.setdefault(cn, []).append(o)
        self.active = None
        self.saved = {}
        self.t0 = 0.0
        self.turn_target = 0.0
        self.turn_cur = {cn: 0.0 for cn in self.chars}
        self.prompt = None

    def nearest(self, eye, fwd):
        best = None
        for cn, m in self.chars.items():
            p = Vector(m["pos"]); p.z = eye.z
            d = (p - eye)
            dist = d.length
            if dist < self.RANGE and (dist < 0.5 or d.normalized().dot(fwd) > 0.35):
                if best is None or dist < best[1]:
                    best = (cn, dist)
        return best[0] if best else None

    def start(self, cn, eye):
        if self.active or cn not in self.objs:
            return
        self.active = cn
        self.t0 = time.time()
        m = self.chars[cn]
        for o in self.objs[cn]:
            key = o.data.shape_keys
            ad = key.animation_data
            self.saved[o.name] = ad.action if ad else None
            if ad: ad.action = None
        # yaw delta so the character faces the player (MakeHuman faces -Y, rotated by rig yaw)
        base = m["yaw"]
        fwd = Vector((math.sin(base), -math.cos(base)))
        to = Vector((eye.x - m["pos"][0], eye.y - m["pos"][1]))
        if to.length > 1e-3:
            ang = math.atan2(fwd.x * to.y - fwd.y * to.x, fwd.dot(to))
            self.turn_target = max(-math.radians(150), min(math.radians(150), ang))
        try:
            import aud
            dev = aud.Device()
            snd = aud.Sound.sine(880).limit(0, 0.07).fadein(0, 0.01).fadeout(0.05, 0.02)
            snd2 = aud.Sound.sine(1320).limit(0, 0.09).fadeout(0.05, 0.03)
            dev.play(snd.join(snd2).volume(0.4))
        except Exception:
            pass

    def update(self):
        now = time.time()
        if self.active:
            cn = self.active; m = self.chars[cn]
            t = now - self.t0
            g0, g1 = m["gesture_eval"]
            ev = min(g1, g0 + t * 24.0 * 10.0)
            for o in self.objs[cn]:
                o.data.shape_keys.eval_time = ev
            k = min(1.0, t / self.TURN_TIME)
            k = k * k * (3 - 2 * k)
            self.turn_cur[cn] = self.turn_target * k
            if t > self.DURATION:
                for o in self.objs[cn]:
                    ad = o.data.shape_keys.animation_data
                    if ad and self.saved.get(o.name): ad.action = self.saved[o.name]
                self.active = None
        for cn, cur in self.turn_cur.items():
            if cn != self.active and abs(cur) > 1e-4:
                cur *= 0.9
                if abs(cur) < 1e-3: cur = 0.0
                self.turn_cur[cn] = cur
            for o in self.objs.get(cn, []):
                o.rotation_euler = (0.0, 0.0, self.turn_cur[cn])

    def subtitle(self):
        if not self.active: return None
        t = time.time() - self.t0
        if t > self.DURATION - 0.3: return None
        return self.active, self.chars[self.active]["line"]


class Blinds:
    """Red button toggles the viewport shutters: halves slide into header/sill, planet light fades up."""
    RANGE = 3.8
    DURATION = 3.2
    def __init__(self):
        self.blinds = [(o, list(o["me_blind"])) for o in bpy.data.objects if "me_blind" in o]
        self.buttons = [o for o in bpy.data.objects if "me_button" in o]
        self.lights = [(o, list(o["me_blind_light"])) for o in bpy.data.objects if o.type == 'LIGHT' and "me_blind_light" in o]
        self.btn_rest = {o.name: o.location.z for o in self.buttons}
        self.open = False
        self.k = 0.0            # 0 closed .. 1 open
        self.t0 = None
        self.btn_mat = bpy.data.materials.get("ButtonRed")
        self.emit = None
        if self.btn_mat and self.btn_mat.node_tree:
            p = self.btn_mat.node_tree.nodes.get("Principled BSDF")
            if p: self.emit = p.inputs["Emission Strength"]
    def near(self, eye, fwd):
        for o in self.buttons:
            p = o.matrix_world.translation.copy(); p.z = eye.z
            d = p - eye
            if d.length < self.RANGE and (d.length < 0.6 or d.normalized().dot(fwd) > 0.2):
                return o
        return None
    def toggle(self):
        if self.t0 is not None: return
        self.open = not self.open
        self.t0 = time.time()
        try:
            import aud
            dev = aud.Device()
            click = aud.Sound.sine(220).limit(0, 0.06).fadeout(0.03, 0.03).volume(0.5)
            hum = aud.Sound.sine(95).limit(0, self.DURATION).fadein(0, 0.4).fadeout(self.DURATION - 0.6, 0.6).volume(0.22)
            hum2 = aud.Sound.sine(142).limit(0, self.DURATION).fadein(0, 0.4).fadeout(self.DURATION - 0.6, 0.6).volume(0.12)
            dev.play(click); dev.play(hum); dev.play(hum2)
        except Exception:
            pass
    def status(self):
        if self.t0 is None: return None
        return "VIEWPORT SHUTTERS: OPENING" if self.open else "VIEWPORT SHUTTERS: CLOSING"
    def update(self):
        if self.t0 is None:
            return
        t = time.time() - self.t0
        u = max(0.0, min(1.0, (t - 0.4) / (self.DURATION - 0.4)))
        u = u * u * (3 - 2 * u)
        self.k = u if self.open else 1.0 - u
        for o, (c, op) in self.blinds:
            o.location.z = c + (op - c) * self.k
        for o, (lo, hi) in self.lights:
            o.data.energy = lo + (hi - lo) * self.k
        press = max(0.0, 1.0 - abs(t - 0.18) / 0.18)
        for o in self.buttons:
            o.location.z = self.btn_rest[o.name] - 0.035 * press
        if self.emit is not None:
            self.emit.default_value = 2.0 + 12.0 * press + (4.0 if t < self.DURATION and int(t * 6) % 2 == 0 else 0.0)
        if t > self.DURATION:
            self.t0 = None
            if self.emit is not None: self.emit.default_value = 2.0


def draw_overlay(op):
    region = bpy.context.region
    if region is None: return
    W, H = region.width, region.height
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')
    def rect(x0, y0, x1, y1, col):
        batch = batch_for_shader(shader, 'TRI_FAN', {"pos": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]})
        shader.bind(); shader.uniform_float("color", col); batch.draw(shader)
    inter = op.inter
    sub = inter.subtitle()
    font = 0
    if sub:
        name, line = sub
        blf.size(font, 26)
        words = line.split(); lines = []; cur = ""
        for w_ in words:
            if blf.dimensions(font, cur + " " + w_)[0] > W * 0.7 and cur:
                lines.append(cur); cur = w_
            else:
                cur = (cur + " " + w_).strip()
        lines.append(cur)
        lh = 34; box_h = lh * (len(lines) + 1) + 30
        rect(W * 0.12, 60, W * 0.88, 60 + box_h, (0.02, 0.03, 0.06, 0.78))
        rect(W * 0.12, 60 + box_h - 3, W * 0.88, 60 + box_h, (1.0, 0.45, 0.1, 0.9))
        blf.color(font, 1.0, 0.55, 0.15, 1.0); blf.size(font, 24)
        blf.position(font, W * 0.12 + 24, 60 + box_h - lh - 8, 0); blf.draw(font, name.upper())
        blf.color(font, 0.95, 0.97, 1.0, 1.0); blf.size(font, 26)
        for i, ln in enumerate(lines):
            blf.position(font, W * 0.12 + 24, 60 + box_h - lh * (i + 2) - 12, 0); blf.draw(font, ln)
    elif op.blinds.status():
        txt = op.blinds.status()
        blf.size(font, 24); tw = blf.dimensions(font, txt)[0]
        rect(W / 2 - tw / 2 - 18, 90, W / 2 + tw / 2 + 18, 136, (0.02, 0.03, 0.06, 0.7))
        blf.color(font, 1.0, 0.45, 0.1, 1.0); blf.position(font, W / 2 - tw / 2, 104, 0); blf.draw(font, txt)
    elif inter.prompt:
        txt = f"[E]  Talk to {inter.prompt}" if not inter.prompt.startswith("[") else inter.prompt[1:]
        blf.size(font, 24)
        tw = blf.dimensions(font, txt)[0]
        rect(W / 2 - tw / 2 - 18, 90, W / 2 + tw / 2 + 18, 136, (0.02, 0.03, 0.06, 0.7))
        blf.color(font, 0.3, 0.8, 1.0, 1.0)
        blf.position(font, W / 2 - tw / 2, 104, 0); blf.draw(font, txt)
    gpu.state.blend_set('NONE')


class ME_OT_walk(bpy.types.Operator):
    """First-person walk with reliable key handling and wall collision"""
    bl_idname = "view3d.me_walk"
    bl_label = "ME Walk"
    bl_options = {'BLOCKING', 'GRAB_CURSOR'}

    MOVE_KEYS = {'W', 'A', 'S', 'D', 'UP_ARROW', 'DOWN_ARROW', 'LEFT_ARROW', 'RIGHT_ARROW'}
    EYE_H = 1.70
    SPEED = 2.6
    RUN = 2.6
    CREEP = 0.35
    JUMP = 3.4
    GRAV = 9.8
    SENS = 0.0022
    RADIUS = 0.4          # collision radius
    WATCHDOG = 1.2        # seconds without a repeat event -> key considered released

    def build_bvh(self, context):
        """One BVH of all static architecture (walls, floors, props) built once; characters and
        holograms are skipped so nothing is rebuilt per frame."""
        skip = {"Characters", "Holograms", "Lights", "Space", "Camera"}
        dg = context.evaluated_depsgraph_get()
        verts, tris, base = [], [], 0
        for ob in bpy.data.objects:
            if ob.type != 'MESH' or ob.instance_type != 'NONE':
                continue
            if any(c.name in skip or c.name.startswith(("Vessa", "Liora")) for c in ob.users_collection):
                continue
            if ob.animation_data and ob.animation_data.action:
                continue
            par = ob.parent; animated = False
            while par:
                if par.animation_data and par.animation_data.action: animated = True; break
                par = par.parent
            if animated or ob.hide_viewport:
                continue
            ev = ob.evaluated_get(dg)
            try:
                me = ev.to_mesh()
            except Exception:
                continue
            if me is None or len(me.polygons) == 0:
                ev.to_mesh_clear(); continue
            me.calc_loop_triangles()
            n = len(me.vertices)
            co = np.empty(n * 3, dtype=np.float32); me.vertices.foreach_get("co", co)
            M = np.array(ev.matrix_world, dtype=np.float32)
            co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
            t = np.empty(len(me.loop_triangles) * 3, dtype=np.int32); me.loop_triangles.foreach_get("vertices", t)
            verts.extend(map(tuple, co.tolist()))
            tris.extend(map(tuple, (t.reshape(-1, 3) + base).tolist()))
            base += n
            ev.to_mesh_clear()
        self.bvh = BVHTree.FromPolygons(verts, tris, all_triangles=True)
        print(f"walk: collision BVH with {len(tris)} triangles", flush=True)

    def invoke(self, context, event):
        self.build_bvh(context)
        sp = context.space_data
        self.r3d = sp.region_3d
        self.region = context.region
        self.r3d.view_perspective = 'PERSP'
        if self.r3d.view_distance > 0.001:
            # convert orbit-style view into an eye position
            fwd = self.r3d.view_rotation @ Vector((0, 0, -1))
            self.eye = self.r3d.view_location - fwd * self.r3d.view_distance
            self.r3d.view_distance = 0.0
        else:
            self.eye = self.r3d.view_location.copy()
        fwd = self.r3d.view_rotation @ Vector((0, 0, -1))
        self.yaw = math.atan2(-fwd.x, fwd.y)
        self.pitch = math.acos(max(-1.0, min(1.0, -fwd.z)))
        self.keys = {}
        self.inter = Interaction()
        self.blinds = Blinds()
        self._draw = bpy.types.SpaceView3D.draw_handler_add(draw_overlay, (self,), 'WINDOW', 'POST_PIXEL')
        self.vz = 0.0
        self.grounded = False
        self.last = time.time()
        self.cx = self.region.x + self.region.width // 2
        self.cy = self.region.y + self.region.height // 2
        context.window.cursor_warp(self.cx, self.cy)
        context.window.cursor_modal_set('NONE')
        self._timer = context.window_manager.event_timer_add(1.0 / 60.0, window=context.window)
        context.window_manager.modal_handler_add(self)
        context.area.header_text_set("WALK: WASD move  mouse look  Shift run  Alt creep  Space jump  E talk  Esc/RMB exit")
        return {'RUNNING_MODAL'}

    def finish(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._draw, 'WINDOW')
        context.window_manager.event_timer_remove(self._timer)
        context.window.cursor_modal_restore()
        context.area.header_text_set(None)
        return {'FINISHED'}

    def floor_z(self, context):
        loc, nrm, idx, dist = self.bvh.ray_cast(self.eye, Vector((0, 0, -1)), self.EYE_H + 3.0)
        return loc.z if loc is not None else None

    def collide(self, context, step):
        """Slide the horizontal step along walls (two iterations)."""
        for _ in range(2):
            if step.length < 1e-6:
                break
            d = step.normalized()
            for hz in (0.5, 1.3):
                origin = Vector((self.eye.x, self.eye.y, self.eye.z - self.EYE_H + hz))
                loc, nrm, idx, dist = self.bvh.ray_cast(origin, d, step.length + self.RADIUS)
                if loc is not None and abs(nrm.z) < 0.6:
                    n = Vector((nrm.x, nrm.y, 0.0)).normalized()
                    allowed = max(0.0, (loc - origin).length - self.RADIUS)
                    if step.length > allowed:
                        step = d * allowed + (step - d * allowed) - n * (step - d * allowed).dot(n)
                    break
        return step

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self.finish(context)
        if event.type == 'MOUSEMOVE':
            dx = event.mouse_x - self.cx
            dy = event.mouse_y - self.cy
            if dx or dy:
                self.yaw -= dx * self.SENS
                self.pitch = max(math.radians(8), min(math.radians(172), self.pitch + dy * self.SENS))
                context.window.cursor_warp(self.cx, self.cy)
            return {'RUNNING_MODAL'}
        if event.type in self.MOVE_KEYS:
            if event.value == 'PRESS':
                self.keys[event.type] = time.time()
            elif event.value == 'RELEASE':
                self.keys.pop(event.type, None)
            return {'RUNNING_MODAL'}
        if event.type == 'E' and event.value == 'PRESS' and not event.is_repeat:
            fwd = Vector((-math.sin(self.yaw), math.cos(self.yaw), 0.0))
            if self.blinds.near(self.eye, fwd):
                self.blinds.toggle()
                return {'RUNNING_MODAL'}
            cn = self.inter.nearest(self.eye, fwd)
            if cn:
                self.inter.start(cn, self.eye)
            return {'RUNNING_MODAL'}
        if event.type == 'SPACE' and event.value == 'PRESS' and self.grounded:
            self.vz = self.JUMP
            self.grounded = False
            return {'RUNNING_MODAL'}
        if event.type.startswith('TIMER'):
            now = time.time()
            dt = min(now - self.last, 0.1)
            self.last = now
            for k, t in list(self.keys.items()):
                if now - t > self.WATCHDOG:
                    del self.keys[k]
            fwd = Vector((-math.sin(self.yaw), math.cos(self.yaw), 0.0))
            right = Vector((math.cos(self.yaw), math.sin(self.yaw), 0.0))
            v = Vector((0.0, 0.0, 0.0))
            ks = self.keys
            if 'W' in ks or 'UP_ARROW' in ks: v += fwd
            if 'S' in ks or 'DOWN_ARROW' in ks: v -= fwd
            if 'D' in ks or 'RIGHT_ARROW' in ks: v += right
            if 'A' in ks or 'LEFT_ARROW' in ks: v -= right
            speed = self.SPEED * (self.RUN if event.shift else 1.0) * (self.CREEP if event.alt else 1.0)
            moved = False
            if v.length > 0:
                step = v.normalized() * speed * dt
                step = self.collide(context, step)
                self.eye += step
                moved = True
            # gravity / floor following
            fz = self.floor_z(context)
            self.vz -= self.GRAV * dt
            self.eye.z += self.vz * dt
            if fz is not None:
                target = fz + self.EYE_H
                if self.eye.z <= target:
                    self.eye.z = target
                    self.vz = 0.0
                    self.grounded = True
                else:
                    self.grounded = False
            else:
                self.vz = 0.0
            self.r3d.view_location = self.eye
            self.r3d.view_rotation = Euler((self.pitch, 0.0, self.yaw), 'XYZ').to_quaternion()
            self.inter.update()
            self.blinds.update()
            if self.inter.active:
                self.inter.prompt = None
            elif self.blinds.near(self.eye, fwd) and self.blinds.t0 is None:
                self.inter.prompt = "[[E]  Close viewport shutters" if self.blinds.open else "[[E]  Open viewport shutters"
            else:
                self.inter.prompt = self.inter.nearest(self.eye, fwd)
            self.region.tag_redraw()
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}


bpy.utils.register_class(ME_OT_walk)


_tries = [0]
def _enter_walk():
    _tries[0] += 1
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            space = area.spaces.active
            if region is None or space is None:
                continue
            space.shading.type = 'RENDERED'
            space.overlay.show_overlays = SHOW_FPS
            if SHOW_FPS:
                space.overlay.show_stats = True
                bpy.context.scene.sync_mode = 'NONE'
            space.show_gizmo = False
            space.lens = 70
            r3d = space.region_3d
            r3d.view_perspective = 'PERSP'
            r3d.view_rotation = START_ROT.to_quaternion()
            r3d.view_distance = 0.0
            r3d.view_location = START_EYE
            try:
                with bpy.context.temp_override(window=window, area=area, region=region):
                    bpy.ops.screen.animation_play()
                    if NATIVE:
                        bpy.ops.view3d.walk('INVOKE_DEFAULT')
                    else:
                        bpy.ops.view3d.me_walk('INVOKE_DEFAULT')
                print("Walk mode started. WASD move, mouse look, Shift run, Alt creep, Space jump, Esc/RMB to exit.", flush=True)
            except Exception as ex:
                print("Could not auto-start walk mode:", ex, "- press Shift+` in the 3D viewport.", flush=True)
            return None
    return 0.5 if _tries[0] < 20 else None

bpy.app.timers.register(_enter_walk, first_interval=1.5)
