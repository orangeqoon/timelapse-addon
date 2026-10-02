bl_info = {
    "name": "TIMELAPSE Addon",
    "author": "orangeqoon",
    "version": (1, 0, 0),
    "blender": (5, 2, 0),
    "location": "View3D > Header / Sidebar > Timelapse",
    "description": "Smart timelapse recording with viewport capture, idle pause, and MP4 export",
    "category": "System",
}

import bpy
import os
import time
from bpy.app.handlers import persistent
from . import prefs
from . import capture
from . import activity_tracker
from . import video_export
from . import ui

# Runtime state
_timer_registered = False
_last_capture_time = 0.0

def _tag_redraw_view3d():
    wm = getattr(bpy.context, "window_manager", None)
    if not wm:
        return
    for window in wm.windows:
        screen = window.screen
        if screen:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

class SmartTimelapseSettings(bpy.types.PropertyGroup):
    output_dir: bpy.props.StringProperty(
        name="Output Directory",
        description="Directory to save captures and MP4 video (supports relative // path)",
        subtype='DIR_PATH',
        default="//timelapse"
    )

    base_filename: bpy.props.StringProperty(
        name="Base Filename",
        description="Filename prefix for screenshots and video",
        default="Timelapse"
    )

    interval: bpy.props.FloatProperty(
        name="Interval (seconds)",
        description="Seconds between captures",
        default=5.0,
        min=0.5,
        max=3600.0
    )

    trigger_mode: bpy.props.EnumProperty(
        name="Trigger Mode",
        description="Choose how captures are triggered",
        items=[
            ('TIME', "Time Interval", "Capture automatically every N seconds"),
            ('ACTION', "Action / Stroke", "Capture every N pen strokes / actions (best for drawing)")
        ],
        default='TIME'
    )

    action_threshold: bpy.props.IntProperty(
        name="Strokes per shot",
        description="Number of completed pen strokes/actions before taking a shot",
        default=5,
        min=1,
        max=100
    )

    file_format: bpy.props.EnumProperty(
        name="File Format",
        description="Format for captured image sequence",
        items=[
            ('JPEG', "JPG (Fast)", "Faster encoding & smaller size (recommended for drawing)"),
            ('PNG', "PNG (Lossless)", "Lossless quality (larger files)")
        ],
        default='JPEG'
    )

    use_smart_delay: bpy.props.BoolProperty(
        name="Smart Delay",
        description="Wait until pen/mouse is released before capturing to eliminate stutter",
        default=True
    )

    capture_mode: bpy.props.EnumProperty(
        name="Capture Mode",
        description="Choose how 3D Viewport is recorded",
        items=[
            ('WYSIWYG_WINDOW_SHOT', "WYSIWYG Viewport", "Record visible 3D Viewport via official imbuf (fast, exact view)"),
            ('CLEAN_OPENGL', "Clean OpenGL", "Record clean viewport render without UI/gizmos")
        ],
        default='WYSIWYG_WINDOW_SHOT'
    )

    idle_timeout: bpy.props.FloatProperty(
        name="Idle Timeout (seconds)",
        description="Automatically pause recording if no user activity for this duration",
        default=30.0,
        min=5.0,
        max=600.0
    )

    auto_mp4: bpy.props.BoolProperty(
        name="Auto Generate MP4 on Stop",
        description="Automatically launch background MP4 export when recording stops",
        default=False
    )

    fps: bpy.props.IntProperty(
        name="Video FPS",
        description="Frame rate of the exported timelapse MP4",
        default=30,
        min=1,
        max=120
    )

    video_quality: bpy.props.EnumProperty(
        name="Compression / Quality",
        description="Encoding quality and compression level",
        items=[
            ('HIGH', "High Quality", "Standard high quality (larger file size)"),
            ('MEDIUM', "Balanced", "Balanced quality and compression"),
            ('LOW', "High Compression", "Compact file size (HandBrake style compression)"),
            ('VERYLOW', "Ultra Compact", "Maximum compression, smallest file size")
        ],
        default='HIGH'
    )

    video_codec: bpy.props.EnumProperty(
        name="Video Codec",
        description="Video encoding format",
        items=[
            ('H264', "H.264 (Universal)", "Standard compatibility for all browsers, devices and platforms"),
            ('H265', "H.265 / HEVC (High Efficiency)", "Next-gen codec, 40-50% smaller file size for modern players")
        ],
        default='H264'
    )


def _timelapse_timer_callback():
    global _timer_registered, _last_capture_time
    context = bpy.context
    wm = getattr(context, "window_manager", None)
    scene = getattr(context, "scene", None)

    if not wm or not scene or not getattr(wm, "smart_timelapse_recording", False):
        _timer_registered = False
        return None

    settings = scene.smart_timelapse

    # 1. Smart Delay: wait if user is currently drawing/dragging stroke
    if settings.use_smart_delay and activity_tracker.is_stroke_active():
        _tag_redraw_view3d()
        return 0.15

    # 2. Trigger mode evaluation
    if settings.trigger_mode == 'ACTION':
        current_actions = activity_tracker.get_action_stroke_count()
        if current_actions < settings.action_threshold:
            _tag_redraw_view3d()
            return 0.2

        success, res_info, count = capture.execute_capture(scene)
        if success:
            wm.smart_timelapse_no_view = False
            wm.smart_timelapse_frame_count = count
            activity_tracker.reset_action_stroke_count()
        elif res_info == "NO_VIEW3D":
            wm.smart_timelapse_no_view = True

        _tag_redraw_view3d()
        return 0.2
    else:
        now = time.monotonic()

        # Idle detection in time interval mode
        if activity_tracker.is_idle(scene):
            wm.smart_timelapse_idle = True
            _tag_redraw_view3d()
            return 0.5

        wm.smart_timelapse_idle = False

        # Check if requested interval has elapsed
        target_interval = max(0.5, float(settings.interval))
        if now - _last_capture_time >= target_interval:
            success, res_info, count = capture.execute_capture(scene)
            if success:
                _last_capture_time = now
                wm.smart_timelapse_no_view = False
                wm.smart_timelapse_frame_count = count
            elif res_info == "NO_VIEW3D":
                wm.smart_timelapse_no_view = True

        _tag_redraw_view3d()
        return 0.5


class SMART_TIMELAPSE_OT_start(bpy.types.Operator):
    bl_idname = "smart_timelapse.start"
    bl_label = "Start Recording"
    bl_description = "Start Timelapse recording"

    def execute(self, context):
        global _timer_registered, _last_capture_time
        wm = context.window_manager
        scene = context.scene

        if getattr(wm, "smart_timelapse_recording", False):
            self.report({'WARNING'}, "Timelapse is already recording")
            return {'CANCELLED'}

        # Verify output directory
        out_dir = capture.get_resolved_output_dir(scene)
        if not os.path.exists(out_dir):
            self.report({'ERROR'}, f"Failed to access output directory: {out_dir}")
            return {'CANCELLED'}

        wm.smart_timelapse_recording = True
        wm.smart_timelapse_idle = False
        wm.smart_timelapse_no_view = False
        wm.smart_timelapse_start_time = time.monotonic()
        wm.smart_timelapse_frame_count = 0
        _last_capture_time = 0.0

        # Reset differential comparison cache for new session
        capture.reset_diff_cache()

        # Start background disk worker
        capture.start_disk_worker()

        # Start input monitor & timers
        activity_tracker.start_monitoring(context)

        if not _timer_registered:
            _timer_registered = True
            bpy.app.timers.register(_timelapse_timer_callback, first_interval=0.1)

        self.report({'INFO'}, "Timelapse recording started")
        return {'FINISHED'}


class SMART_TIMELAPSE_OT_stop(bpy.types.Operator):
    bl_idname = "smart_timelapse.stop"
    bl_label = "Stop Recording"
    bl_description = "Stop Timelapse recording"

    def execute(self, context):
        global _timer_registered
        wm = context.window_manager
        scene = context.scene

        if not getattr(wm, "smart_timelapse_recording", False):
            return {'CANCELLED'}

        wm.smart_timelapse_recording = False
        wm.smart_timelapse_idle = False
        wm.smart_timelapse_no_view = False
        _timer_registered = False

        activity_tracker.stop_monitoring(context)
        capture.stop_disk_worker()

        count = getattr(wm, "smart_timelapse_frame_count", 0)
        self.report({'INFO'}, f"Timelapse stopped ({count} frames recorded)")

        _tag_redraw_view3d()

        # Auto generate MP4 if enabled
        if scene.smart_timelapse.auto_mp4 and count > 0:
            success, msg = video_export.start_async_mp4_render(scene)
            if success:
                self.report({'INFO'}, msg)

        return {'FINISHED'}


class SMART_TIMELAPSE_OT_toggle(bpy.types.Operator):
    bl_idname = "smart_timelapse.toggle"
    bl_label = "Toggle Timelapse Recording"
    bl_description = "Toggle Start/Stop for Timelapse recording"

    def execute(self, context):
        wm = context.window_manager
        if getattr(wm, "smart_timelapse_recording", False):
            return bpy.ops.smart_timelapse.stop()
        else:
            return bpy.ops.smart_timelapse.start()


@persistent
def on_blend_load_post(dummy1, dummy2):
    # Ensure recording state is reset on file load/open
    wm = bpy.context.window_manager
    if wm:
        wm.smart_timelapse_recording = False
        wm.smart_timelapse_idle = False
        wm.smart_timelapse_no_view = False
    activity_tracker.stop_monitoring()
    capture.stop_disk_worker()
    _tag_redraw_view3d()


# Keymap storage
_addon_keymaps = []

def register_keymaps():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return

    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    kmi = km.keymap_items.new(
        SMART_TIMELAPSE_OT_toggle.bl_idname,
        type='T',
        value='PRESS',
        ctrl=True,
        shift=True
    )
    _addon_keymaps.append((km, kmi))


def unregister_keymaps():
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()


classes = (
    SmartTimelapseSettings,
    SMART_TIMELAPSE_OT_start,
    SMART_TIMELAPSE_OT_stop,
    SMART_TIMELAPSE_OT_toggle,
)

def register():
    prefs.register()

    for cls in classes:
        bpy.utils.register_class(cls)

    activity_tracker.register()
    video_export.register()
    ui.register()

    # Register properties
    bpy.types.Scene.smart_timelapse = bpy.props.PointerProperty(type=SmartTimelapseSettings)

    wm = bpy.types.WindowManager
    wm.smart_timelapse_recording = bpy.props.BoolProperty(default=False)
    wm.smart_timelapse_idle = bpy.props.BoolProperty(default=False)
    wm.smart_timelapse_no_view = bpy.props.BoolProperty(default=False)
    wm.smart_timelapse_frame_count = bpy.props.IntProperty(default=0)
    wm.smart_timelapse_start_time = bpy.props.FloatProperty(default=0.0)

    # Keymaps & Handlers
    register_keymaps()
    if on_blend_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_blend_load_post)


def unregister():
    global _timer_registered
    _timer_registered = False

    capture.stop_disk_worker()

    if on_blend_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_blend_load_post)

    unregister_keymaps()

    # Clean up properties
    if hasattr(bpy.types.Scene, "smart_timelapse"):
        del bpy.types.Scene.smart_timelapse

    wm = bpy.types.WindowManager
    for prop in [
        "smart_timelapse_recording",
        "smart_timelapse_idle",
        "smart_timelapse_no_view",
        "smart_timelapse_frame_count",
        "smart_timelapse_start_time"
    ]:
        if hasattr(wm, prop):
            delattr(wm, prop)

    ui.unregister()
    video_export.unregister()
    activity_tracker.unregister()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    prefs.unregister()


if __name__ == "__main__":
    register()
