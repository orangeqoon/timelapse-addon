import bpy
import os
import re
import time
from . import prefs

def find_active_view3d_region(window=None):
    if window is None:
        window = bpy.context.window
    if not window or not window.screen:
        return None, None, None

    # First look for active area if it is VIEW_3D
    active_area = getattr(window.screen, "areas", [])
    view3d_areas = [area for area in active_area if area.type == 'VIEW_3D']

    if not view3d_areas:
        return None, None, None

    # Pick the first or largest VIEW_3D area
    target_area = max(view3d_areas, key=lambda a: a.width * a.height)
    for region in target_area.regions:
        if region.type == 'WINDOW':
            return target_area, region, window

    return None, None, None


def get_resolved_output_dir(scene):
    settings = scene.smart_timelapse
    output_dir = settings.output_dir.strip()

    if output_dir.startswith("//"):
        if bpy.data.is_saved:
            output_dir = bpy.path.abspath(output_dir)
        else:
            # Blend is unsaved, fallback to AddonPreferences default
            p = prefs.get_preferences()
            if p and p.default_output_dir:
                output_dir = os.path.abspath(p.default_output_dir)
            else:
                output_dir = os.path.join(os.path.expanduser("~"), "Videos", "BlenderTimelapse")
    elif not output_dir:
        p = prefs.get_preferences()
        if p and p.default_output_dir:
            output_dir = os.path.abspath(p.default_output_dir)
        else:
            output_dir = os.path.join(os.path.expanduser("~"), "Videos", "BlenderTimelapse")
    else:
        output_dir = os.path.abspath(output_dir)

    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def get_next_filepath(output_dir, base_filename, ext="jpg"):
    pattern = re.compile(rf"^{re.escape(base_filename)}_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)
    highest_num = 0

    if os.path.exists(output_dir):
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    match = pattern.match(entry.name)
                    if match:
                        try:
                            num = int(match.group(1))
                            if num > highest_num:
                                highest_num = num
                        except ValueError:
                            pass

    next_num = highest_num + 1
    clean_ext = ext.lower().replace("jpeg", "jpg")
    filename = f"{base_filename}_{next_num:04d}.{clean_ext}"
    return os.path.join(output_dir, filename), next_num


# Global cache for lightweight frame comparison (diff skip)
_last_sample_signature = None

def reset_diff_cache():
    global _last_sample_signature
    _last_sample_signature = None


def _compute_sample_signature(pixels, w, h):
    try:
        import numpy as np
        import zlib
        # Multidimensional memoryview can be directly converted via frombuffer
        arr = np.frombuffer(pixels, dtype=np.uint8).reshape((h, w, 4))
        # Downsample to check global pixel changes across viewport (stride of 16 in X and Y)
        # Using RGB channels only (:3)
        sub = arr[::16, ::16, :3]
        return zlib.crc32(sub.tobytes())
    except Exception as e:
        # If numpy is unavailable or unexpected error, return None to safely fall back to saving
        return None


import io
import queue
import threading

_disk_write_queue = queue.Queue(maxsize=8)
_disk_worker_thread = None
_disk_worker_stop_event = threading.Event()

def _disk_writer_loop():
    while not _disk_worker_stop_event.is_set():
        try:
            item = _disk_write_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if item is None:
            break
        filepath, data_bytes = item
        try:
            with open(filepath, "wb") as f:
                f.write(data_bytes)
        except Exception as e:
            print(f"[SmartTimelapse DiskWorker] Error writing {filepath}: {e}")
        finally:
            _disk_write_queue.task_done()

def start_disk_worker():
    global _disk_worker_thread, _disk_worker_stop_event
    if _disk_worker_thread is not None and _disk_worker_thread.is_alive():
        return
    _disk_worker_stop_event.clear()
    _disk_worker_thread = threading.Thread(target=_disk_writer_loop, daemon=False)
    _disk_worker_thread.start()

def stop_disk_worker(timeout=2.0):
    global _disk_worker_thread, _disk_worker_stop_event
    if _disk_worker_thread is None:
        return
    _disk_worker_stop_event.set()
    try:
        _disk_write_queue.put_nowait(None)
    except Exception:
        pass
    if _disk_worker_thread.is_alive():
        _disk_worker_thread.join(timeout=timeout)
    _disk_worker_thread = None


def capture_wysiwyg(window, region, out_path, file_format='JPEG'):
    global _last_sample_signature
    import imbuf

    # Region coordinates: ((x0, y0), (x1, y1)) - end coordinates are non-inclusive
    region_rect = ((region.x, region.y), (region.x + region.width, region.y + region.height))
    pixels = window.screenshot(region=region_rect)

    if pixels is None:
        return False, "Failed to capture window screenshot"

    h, w = pixels.shape[0], pixels.shape[1]
    if w <= 0 or h <= 0:
        return False, "Invalid region dimensions"

    # 4th layer: diff-zero check (skip identical consecutive frames via fast downsampled CRC)
    sig = _compute_sample_signature(pixels, w, h)
    if sig is not None and _last_sample_signature is not None and sig == _last_sample_signature:
        return False, "DIFF_SKIP"
    if sig is not None:
        _last_sample_signature = sig

    # Configure imbuf
    ibuf = imbuf.new((w, h))
    fmt = 'PNG' if file_format == 'PNG' else 'JPEG'
    ibuf.file_type = fmt

    with ibuf.with_buffer(write=True) as buf:
        buf.cast('B')[:] = pixels.cast('B')

    if fmt == 'PNG':
        # Encode in memory and offload disk write to worker thread
        bio = io.BytesIO()
        imbuf.write_to_buffer(ibuf, bio)
        data = bio.getvalue()
        try:
            _disk_write_queue.put_nowait((out_path, data))
        except queue.Full:
            with open(out_path, "wb") as f:
                f.write(data)
    else:
        # Fast JPEG direct write (~15ms)
        imbuf.write(ibuf, filepath=out_path)

    return True, None


def capture_clean_opengl(area, out_path, scene):
    # Find WINDOW region within area
    target_region = None
    for r in area.regions:
        if r.type == 'WINDOW':
            target_region = r
            break
    if not target_region:
        target_region = area.regions[-1]

    # Backup render settings
    render = scene.render
    og_filepath = render.filepath
    og_res_x = render.resolution_x
    og_res_y = render.resolution_y
    og_format = render.image_settings.file_format
    og_display = render.display_mode

    try:
        render.filepath = out_path
        render.image_settings.file_format = 'PNG'
        render.resolution_x = target_region.width
        render.resolution_y = target_region.height
        render.display_mode = 'NONE'

        # Context override for the 3D View area
        with bpy.context.temp_override(area=area, region=target_region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
        return True, None
    except Exception as e:
        return False, str(e)
    finally:
        # Restore settings
        render.filepath = og_filepath
        render.resolution_x = og_res_x
        render.resolution_y = og_res_y
        render.image_settings.file_format = og_format
        render.display_mode = og_display


def execute_capture(scene):
    from . import activity_tracker
    activity_tracker.set_capturing(True)
    try:
        settings = scene.smart_timelapse
        output_dir = get_resolved_output_dir(scene)
        base_name = settings.base_filename.strip() or "Timelapse"
        fmt = getattr(settings, "file_format", 'JPEG')
        ext = "jpg" if fmt == 'JPEG' else "png"
        out_path, seq_num = get_next_filepath(output_dir, base_name, ext)

        area, region, window = find_active_view3d_region()
        if not area or not region or not window:
            return False, "NO_VIEW3D", 0

        if settings.capture_mode == 'CLEAN_OPENGL':
            success, err = capture_clean_opengl(area, out_path, scene)
        else:
            success, err = capture_wysiwyg(window, region, out_path, file_format=fmt)

        if success:
            return True, out_path, seq_num
        elif err == "DIFF_SKIP":
            return False, "DIFF_SKIP", seq_num - 1
        else:
            return False, err or "Capture failed", seq_num - 1
    finally:
        activity_tracker.set_capturing(False)
