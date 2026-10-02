"""
Standalone headless render worker for Smart Timelapse.
Executed as: blender -b --factory-startup -P render_worker.py -- <args>
"""
import sys
import os
import re

def run_worker():
    # Parse arguments after '--'
    args = sys.argv
    if "--" not in args:
        print("[SmartTimelapse Worker] Error: Missing argument delimiter '--'")
        sys.exit(1)

    worker_args = args[args.index("--") + 1:]
    import argparse
    parser = argparse.ArgumentParser(description="Smart Timelapse MP4 Render Worker")
    parser.add_argument("--dir", required=True, help="Input directory containing PNG sequence")
    parser.add_argument("--base", required=True, help="Base filename prefix")
    parser.add_argument("--out", required=True, help="Output MP4 file path")
    parser.add_argument("--fps", type=int, default=30, help="Output FPS")
    parser.add_argument("--quality", default="HIGH", help="Video quality (HIGH, MEDIUM, LOW, VERYLOW)")
    parser.add_argument("--codec", default="H264", help="Video codec (H264, H265)")

    parsed = parser.parse_args(worker_args)
    output_dir = parsed.dir
    base_name = parsed.base
    mp4_out = parsed.out
    fps = parsed.fps
    quality = parsed.quality
    codec = parsed.codec

    print(f"[SmartTimelapse Worker] Scanning for '{base_name}' sequence in {output_dir}...")
    pattern = re.compile(rf"^{re.escape(base_name)}_(\d+)\.(jpg|jpeg|png)$", re.IGNORECASE)
    files = []

    if os.path.exists(output_dir):
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if entry.is_file():
                    match = pattern.match(entry.name)
                    if match:
                        files.append((int(match.group(1)), entry.name))

    files.sort(key=lambda x: x[0])
    image_names = [f[1] for f in files]

    if not image_names:
        print(f"[SmartTimelapse Worker] No image sequence found for {base_name}")
        sys.exit(1)

    print(f"[SmartTimelapse Worker] Found {len(image_names)} frames. Setting up VSE...")

    import bpy
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = len(image_names)
    scene.render.fps = fps

    # Sequence Editor setup (Blender 5.x strips API)
    se = scene.sequence_editor_create()
    first_filepath = os.path.join(output_dir, image_names[0])
    strip = se.strips.new_image(
        name="Timelapse_Strip",
        filepath=first_filepath,
        channel=1,
        frame_start=1
    )

    for img_name in image_names[1:]:
        strip.elements.append(img_name)

    # Resolution (round to even numbers for H.264)
    width = int(strip.elements[0].orig_width) if hasattr(strip.elements[0], "orig_width") else 1920
    height = int(strip.elements[0].orig_height) if hasattr(strip.elements[0], "orig_height") else 1080
    if width <= 0: width = 1920
    if height <= 0: height = 1080

    scene.render.resolution_x = width & ~1
    scene.render.resolution_y = height & ~1
    scene.render.resolution_percentage = 100

    # Encoding configuration (Blender 5.x media_type)
    scene.render.filepath = mp4_out
    if hasattr(scene.render.image_settings, "media_type"):
        scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H265' if str(codec).upper() == 'H265' else 'H264'

    # Color management
    if hasattr(scene, "view_settings") and hasattr(scene.view_settings, "view_transform"):
        try:
            scene.view_settings.view_transform = 'Standard'
        except Exception:
            pass

    # Video compression & quality (HandBrake-style CRF control)
    quality_upper = str(quality).upper()
    if quality_upper == 'VERYLOW':
        scene.render.ffmpeg.constant_rate_factor = 'VERYLOW'
    elif quality_upper == 'LOW':
        scene.render.ffmpeg.constant_rate_factor = 'LOW'
    elif quality_upper == 'MEDIUM':
        scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    else:
        scene.render.ffmpeg.constant_rate_factor = 'HIGH'

    # Optimize GOP size (keyframe interval) for timelapses to maximize compression
    scene.render.ffmpeg.gopsize = max(30, int(fps * 2))
    if hasattr(scene.render.ffmpeg, "ffmpeg_preset"):
        scene.render.ffmpeg.ffmpeg_preset = 'GOOD'

    print(f"[SmartTimelapse Worker] Rendering animation to {mp4_out}...")
    bpy.ops.render.render(animation=True)
    print("[SmartTimelapse Worker] Render completed successfully!")

if __name__ == "__main__":
    run_worker()
