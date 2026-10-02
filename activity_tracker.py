import bpy
import time
from bpy.app.handlers import persistent
from . import prefs

_last_activity_time = time.monotonic()
_last_mouse_pos = (0, 0)
_last_view_matrices = {}
_is_capturing_active = False

def set_capturing(active: bool):
    global _is_capturing_active
    _is_capturing_active = active

def get_last_activity_time():
    global _last_activity_time
    return _last_activity_time

def record_activity():
    global _last_activity_time
    _last_activity_time = time.monotonic()


@persistent
def on_depsgraph_update(scene, depsgraph):
    global _last_activity_time, _is_capturing_active
    # If the capture engine itself is currently rendering, ignore depsgraph event
    if _is_capturing_active:
        return

    try:
        # Check if animation is playing and if user prefers to ignore it
        p = prefs.get_preferences()
        if p and p.ignore_anim_playback:
            screen = bpy.context.screen
            if screen and getattr(screen, "is_animation_playing", False):
                return
        _last_activity_time = time.monotonic()
    except Exception:
        pass


def check_view_matrix_changes():
    global _last_activity_time, _last_view_matrices
    changed = False

    try:
        wm = getattr(bpy.context, "window_manager", None)
        windows = getattr(wm, "windows", []) if wm else []
        if not windows:
            windows = [bpy.context.window] if getattr(bpy.context, "window", None) else []

        for window in windows:
            if not window or not window.screen:
                continue
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    if space and hasattr(space, "region_3d") and space.region_3d:
                        mat = space.region_3d.view_matrix
                        flat_mat = tuple(round(float(v), 4) for row in mat for v in row)
                        area_key = area.as_pointer()
                        last_mat = _last_view_matrices.get(area_key)
                        if last_mat is not None and flat_mat != last_mat:
                            changed = True
                        _last_view_matrices[area_key] = flat_mat

        if changed:
            _last_activity_time = time.monotonic()
    except Exception:
        pass

    return changed


def is_idle(scene, current_time=None):
    global _last_activity_time
    if current_time is None:
        current_time = time.monotonic()

    # Also check camera navigation changes
    check_view_matrix_changes()

    settings = scene.smart_timelapse
    timeout = settings.idle_timeout
    return (current_time - _last_activity_time) > timeout


_is_stroke_active = False
_stroke_press_time = 0.0
_action_stroke_count = 0

def is_stroke_active(max_hold_sec=3.0):
    global _is_stroke_active, _stroke_press_time
    if not _is_stroke_active:
        return False
    # If held for too long (e.g. over max_hold_sec), release hold to avoid infinite lock
    if (time.monotonic() - _stroke_press_time) > max_hold_sec:
        return False
    return True

def get_action_stroke_count():
    global _action_stroke_count
    return _action_stroke_count

def reset_action_stroke_count():
    global _action_stroke_count
    _action_stroke_count = 0


class SMART_TIMELAPSE_OT_modal_monitor(bpy.types.Operator):
    bl_idname = "smart_timelapse.modal_monitor"
    bl_label = "Smart Timelapse Activity Monitor"
    bl_options = {'INTERNAL'}

    _is_running = False

    @classmethod
    def is_running(cls):
        return cls._is_running

    def modal(self, context, event):
        global _last_activity_time, _last_mouse_pos
        global _is_stroke_active, _stroke_press_time, _action_stroke_count

        # Check if recording is still active
        wm = context.window_manager
        if not getattr(wm, "smart_timelapse_recording", False):
            self.cancel(context)
            return {'CANCELLED'}

        # Track stylus / left mouse button for stroke drawing state & action count
        if event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                _is_stroke_active = True
                _stroke_press_time = time.monotonic()
                _last_activity_time = time.monotonic()
            elif event.value == 'RELEASE':
                _is_stroke_active = False
                _action_stroke_count += 1
                _last_activity_time = time.monotonic()

        # Handle mouse movement with 3px threshold
        elif event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            dx = abs(event.mouse_x - _last_mouse_pos[0])
            dy = abs(event.mouse_y - _last_mouse_pos[1])
            if dx > 3 or dy > 3:
                _last_activity_time = time.monotonic()
                _last_mouse_pos = (event.mouse_x, event.mouse_y)
        elif event.type in {
            'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE',
            'TRACKPADPAN', 'TRACKPADZOOM', 'RIGHTMOUSE'
        }:
            _last_activity_time = time.monotonic()

        return {'PASS_THROUGH'}

    def execute(self, context):
        global _is_stroke_active, _action_stroke_count
        if SMART_TIMELAPSE_OT_modal_monitor._is_running:
            return {'CANCELLED'}

        _is_stroke_active = False
        _action_stroke_count = 0
        SMART_TIMELAPSE_OT_modal_monitor._is_running = True
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        global _is_stroke_active
        _is_stroke_active = False
        SMART_TIMELAPSE_OT_modal_monitor._is_running = False


def start_monitoring(context):
    global _last_activity_time, _last_view_matrices
    _last_activity_time = time.monotonic()
    _last_view_matrices.clear()

    # Register depsgraph handler if not already present
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

    # Launch modal operator for navigation/interaction
    if not SMART_TIMELAPSE_OT_modal_monitor.is_running():
        bpy.ops.smart_timelapse.modal_monitor('INVOKE_DEFAULT')


def stop_monitoring(context=None):
    SMART_TIMELAPSE_OT_modal_monitor._is_running = False
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)


def register():
    bpy.utils.register_class(SMART_TIMELAPSE_OT_modal_monitor)


def unregister():
    stop_monitoring()
    bpy.utils.unregister_class(SMART_TIMELAPSE_OT_modal_monitor)
