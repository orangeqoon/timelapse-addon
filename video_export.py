import bpy
import os
import re
import subprocess
import glob
from . import capture
from . import prefs

_active_render_process = None
_active_job_file = None

def get_image_sequence_files(output_dir, base_filename, ext=None):
    if ext:
        pattern = re.compile(rf"^{re.escape(base_filename)}_(\d+)\.{ext}$", re.IGNORECASE)
    else:
        pattern = re.compile(rf"^{re.escape(base_filename)}_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)
    files = []

    if os.path.exists(output_dir):
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    match = pattern.match(entry.name)
                    if match:
                        files.append((int(match.group(1)), entry.name))

    files.sort(key=lambda x: x[0])
    return [f[1] for f in files]


def build_temp_vse_scene(scene, image_files, output_dir, mp4_out_path):
    settings = scene.smart_timelapse
    temp_scene = bpy.data.scenes.new("SmartTimelapse_Export_Scene")

    # Frame settings
    total_frames = len(image_files)
    temp_scene.frame_start = 1
    temp_scene.frame_end = total_frames
    temp_scene.render.fps = settings.fps

    # Configure Sequence Editor (Blender 5.2 API)
    se = temp_scene.sequence_editor_create()
    first_filepath = os.path.join(output_dir, image_files[0])

    # StripsTopLevel.new_image in Blender 5.2
    strip = se.strips.new_image(
        name="Timelapse_Strip",
        filepath=first_filepath,
        channel=1,
        frame_start=1
    )

    # Append remaining frames
    for img_name in image_files[1:]:
        strip.elements.append(img_name)

    # Resolution (round to even numbers for H.264 / yuv420p)
    width = int(strip.elements[0].orig_width) if hasattr(strip.elements[0], "orig_width") else 1920
    height = int(strip.elements[0].orig_height) if hasattr(strip.elements[0], "orig_height") else 1080
    if width <= 0: width = 1920
    if height <= 0: height = 1080

    temp_scene.render.resolution_x = width & ~1
    temp_scene.render.resolution_y = height & ~1
    temp_scene.render.resolution_percentage = 100

    # Encoding settings (Blender 5.x requires media_type = 'VIDEO' before selecting FFMPEG)
    temp_scene.render.filepath = mp4_out_path
    if hasattr(temp_scene.render.image_settings, "media_type"):
        temp_scene.render.image_settings.media_type = 'VIDEO'
    temp_scene.render.image_settings.file_format = 'FFMPEG'
    temp_scene.render.ffmpeg.format = 'MPEG4'
    temp_scene.render.ffmpeg.codec = 'H264'

    # Color management: force Standard to avoid double transform
    if hasattr(temp_scene, "view_settings") and hasattr(temp_scene.view_settings, "view_transform"):
        try:
            temp_scene.view_settings.view_transform = 'Standard'
        except Exception:
            pass

    # Video quality
    p = prefs.get_preferences()
    quality = p.video_quality if p else 'HIGH'
    if quality == 'HIGH':
        temp_scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    elif quality == 'MEDIUM':
        temp_scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    else:
        temp_scene.render.ffmpeg.constant_rate_factor = 'LOW'

    return temp_scene


def get_unique_mp4_path(output_dir, base_name):
    # Avoid accidental overwriting by checking existing mp4 files
    mp4_filename = f"{base_name}.mp4"
    target = os.path.join(output_dir, mp4_filename)
    if not os.path.exists(target):
        return target

    idx = 1
    while True:
        target = os.path.join(output_dir, f"{base_name}_{idx:03d}.mp4")
        if not os.path.exists(target):
            return target
        idx += 1


def start_async_mp4_render(scene):
    global _active_render_process, _active_job_file

    if _active_render_process is not None and _active_render_process.poll() is None:
        return False, "Render job is already running in background"

    output_dir = capture.get_resolved_output_dir(scene)
    base_name = scene.smart_timelapse.base_filename.strip() or "Timelapse"
    images = get_image_sequence_files(output_dir, base_name, "png")

    if not images:
        return False, f"No image sequence found for '{base_name}' in {output_dir}"

    mp4_out_path = get_unique_mp4_path(output_dir, base_name)

    # Resolve render_worker.py script located in addon directory
    worker_script = os.path.join(os.path.dirname(__file__), "render_worker.py")
    if not os.path.exists(worker_script):
        return False, f"Render worker script missing at {worker_script}"

    p = prefs.get_preferences()
    quality = p.video_quality if p else 'HIGH'

    # Launch dedicated background worker with factory startup
    blender_bin = bpy.app.binary_path
    cmd = [
        blender_bin,
        "-b",
        "--factory-startup",
        "-P", worker_script,
        "--",
        "--dir", output_dir,
        "--base", base_name,
        "--out", mp4_out_path,
        "--fps", str(scene.smart_timelapse.fps),
        "--quality", quality
    ]

    try:
        _active_render_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _active_job_file = None

        # Register poll timer
        bpy.app.timers.register(_poll_render_process)
        return True, f"Started MP4 generation in background ({len(images)} frames -> {os.path.basename(mp4_out_path)})"
    except Exception as e:
        return False, str(e)


def _poll_render_process():
    global _active_render_process, _active_job_file

    if _active_render_process is None:
        return None

    ret = _active_render_process.poll()
    if ret is None:
        # Still running, check again in 1.0 second
        return 1.0

    # Finished
    job_file = _active_job_file
    _active_render_process = None
    _active_job_file = None

    if job_file and os.path.exists(job_file):
        try:
            os.remove(job_file)
        except Exception:
            pass

    if ret == 0:
        print("[Smart Timelapse] MP4 video generated successfully!")
        def show_msg(self, context):
            self.layout.label(text="Smart Timelapse: MP4 video generated successfully!", icon='CHECKMARK')
        try:
            wm = getattr(bpy.context, "window_manager", None)
            if wm and hasattr(wm, "popup_menu"):
                wm.popup_menu(show_msg, title="Smart Timelapse", icon='INFO')
        except Exception:
            pass
    else:
        print(f"[Smart Timelapse] Video export failed with code {ret}")
        def show_msg(self, context):
            self.layout.label(text=f"Smart Timelapse: Video export failed with code {ret}", icon='ERROR')
        try:
            wm = getattr(bpy.context, "window_manager", None)
            if wm and hasattr(wm, "popup_menu"):
                wm.popup_menu(show_msg, title="Smart Timelapse Error", icon='ERROR')
        except Exception:
            pass

    return None


def is_rendering():
    global _active_render_process
    return _active_render_process is not None and _active_render_process.poll() is None


class SMART_TIMELAPSE_OT_export_video(bpy.types.Operator):
    bl_idname = "smart_timelapse.export_video"
    bl_label = "Generate MP4 Video"
    bl_description = "Export recorded image sequence to MP4 using Blender built-in VSE (Non-blocking background process)"

    @classmethod
    def poll(cls, context):
        return not is_rendering()

    def execute(self, context):
        success, msg = start_async_mp4_render(context.scene)
        if success:
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}


def register():
    bpy.utils.register_class(SMART_TIMELAPSE_OT_export_video)


def unregister():
    global _active_render_process
    if _active_render_process and _active_render_process.poll() is None:
        try:
            _active_render_process.terminate()
        except Exception:
            pass
    _active_render_process = None
    bpy.utils.unregister_class(SMART_TIMELAPSE_OT_export_video)
