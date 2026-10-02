import bpy
import os
import time
from . import capture
from . import video_export

class SMART_TIMELAPSE_OT_open_folder(bpy.types.Operator):
    bl_idname = "smart_timelapse.open_folder"
    bl_label = "Open Output Folder"
    bl_description = "Open the directory where timelapse images and videos are saved"

    def execute(self, context):
        folder = capture.get_resolved_output_dir(context.scene)
        if os.path.exists(folder):
            bpy.ops.wm.path_open(filepath=folder)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, "Folder does not exist yet")
            return {'CANCELLED'}


def draw_header_button(self, context):
    layout = self.layout
    wm = context.window_manager

    is_rec = getattr(wm, "smart_timelapse_recording", False)
    is_idle_status = getattr(wm, "smart_timelapse_idle", False)
    is_no_view = getattr(wm, "smart_timelapse_no_view", False)
    count = getattr(wm, "smart_timelapse_frame_count", 0)

    row = layout.row(align=True)

    if video_export.is_rendering():
        row.label(text="Exporting MP4...", icon='FILE_MOVIE')

    if is_rec:
        elapsed_sec = int(time.monotonic() - getattr(wm, "smart_timelapse_start_time", time.monotonic()))
        mins, secs = divmod(elapsed_sec, 60)
        time_str = f"{mins:02d}:{secs:02d}"

        if is_no_view:
            row.alert = True
            row.operator("smart_timelapse.stop", text="NO VIEW3D", icon='ERROR')
        elif is_idle_status:
            row.operator("smart_timelapse.stop", text=f"IDLE ({count})", icon='PAUSE')
        else:
            row.alert = True
            row.operator("smart_timelapse.stop", text=f"REC {time_str} ({count})", icon='RECORD_OFF')
    else:
        row.operator("smart_timelapse.start", text="Timelapse", icon='PLAY')

    # Quick Settings Popover (Gear icon)
    row.popover(panel="SMART_TIMELAPSE_PT_quick_settings", icon='PREFERENCES', text="")


class SMART_TIMELAPSE_PT_quick_settings(bpy.types.Panel):
    bl_label = "TIMELAPSE Settings"
    bl_idname = "SMART_TIMELAPSE_PT_quick_settings"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 13

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.smart_timelapse

        # Warning if unsaved and using relative path
        if not bpy.data.is_saved and settings.output_dir.startswith("//"):
            row = layout.row()
            row.alert = True
            row.label(text="Save file first for relative path!", icon='ERROR')

        # Trigger & Timing
        box_trigger = layout.box()
        box_trigger.label(text="Trigger & Timing", icon='TIME')
        box_trigger.prop(settings, "trigger_mode")
        if settings.trigger_mode == 'TIME':
            box_trigger.prop(settings, "interval")
            box_trigger.prop(settings, "idle_timeout")
        else:
            box_trigger.prop(settings, "action_threshold")

        box_trigger.prop(settings, "use_smart_delay")

        # Format & Viewport
        box_fmt = layout.box()
        box_fmt.label(text="Format & Viewport", icon='IMAGE_DATA')
        box_fmt.prop(settings, "file_format")
        box_fmt.prop(settings, "capture_mode")

        # Output & Export
        box_out = layout.box()
        box_out.label(text="Output & Video", icon='FILE_FOLDER')
        box_out.prop(settings, "output_dir")
        box_out.prop(settings, "base_filename")
        box_out.operator("smart_timelapse.open_folder", icon='FOLDER_REDIRECT')

        box_out.separator()
        box_out.prop(settings, "fps")
        box_out.prop(settings, "auto_mp4")

        row_exp = box_out.row()
        if video_export.is_rendering():
            row_exp.label(text="Rendering MP4 in background...", icon='TIME')
        else:
            row_exp.operator("smart_timelapse.export_video", text="Export MP4 Now", icon='RENDER_ANIMATION')

        # Prevention Tips
        box_tips = layout.box()
        box_tips.label(text="Drawing Stutter Prevention:", icon='LIGHT')
        box_tips.label(text="• Smart Delay + JPG is recommended.")
        box_tips.label(text="• Action mode captures on pen release.")


class SMART_TIMELAPSE_PT_main_panel(bpy.types.Panel):
    bl_label = "TIMELAPSE Addon"
    bl_idname = "SMART_TIMELAPSE_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Timelapse"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        wm = context.window_manager
        settings = scene.smart_timelapse

        is_rec = getattr(wm, "smart_timelapse_recording", False)
        is_idle_status = getattr(wm, "smart_timelapse_idle", False)
        count = getattr(wm, "smart_timelapse_frame_count", 0)

        # Warning if unsaved and using relative path
        if not bpy.data.is_saved and settings.output_dir.startswith("//"):
            row = layout.row()
            row.alert = True
            row.label(text="Save Blend file first to use relative path!", icon='ERROR')

        # Control Box
        box_ctrl = layout.box()
        box_ctrl.label(text="Recording Controls", icon='TIME')

        row_btn = box_ctrl.row(align=True)
        if is_rec:
            row_btn.alert = True
            row_btn.operator("smart_timelapse.stop", text="Stop Recording", icon='CANCEL')
            if is_idle_status:
                box_ctrl.label(text=f"Status: PAUSED (IDLE) - {count} shots", icon='PAUSE')
            else:
                box_ctrl.label(text=f"Status: RECORDING - {count} shots", icon='RECORD_ON')
        else:
            row_btn.operator("smart_timelapse.start", text="Start Recording", icon='PLAY')

        box_ctrl.separator()
        box_ctrl.prop(settings, "trigger_mode")
        if settings.trigger_mode == 'TIME':
            box_ctrl.prop(settings, "interval")
            box_ctrl.prop(settings, "idle_timeout")
        else:
            box_ctrl.prop(settings, "action_threshold")

        box_ctrl.prop(settings, "use_smart_delay")
        box_ctrl.prop(settings, "file_format")
        box_ctrl.prop(settings, "capture_mode")

        # Output Settings Box
        box_out = layout.box()
        box_out.label(text="Output Settings", icon='FILE_FOLDER')
        box_out.prop(settings, "output_dir")
        box_out.prop(settings, "base_filename")

        row_folder = box_out.row(align=True)
        row_folder.operator("smart_timelapse.open_folder", icon='FOLDER_REDIRECT')

        resolved = capture.get_resolved_output_dir(scene)
        box_out.label(text=f"Target: {resolved}", icon='INFO')

        # MP4 Video Export Box
        box_vse = layout.box()
        box_vse.label(text="MP4 Video Export", icon='FILE_MOVIE')
        box_vse.prop(settings, "fps")
        box_vse.prop(settings, "auto_mp4")

        # Estimated video length
        if count > 0 and settings.fps > 0:
            est_sec = count / settings.fps
            box_vse.label(text=f"Estimated Duration: {est_sec:.1f}s ({count} frames @ {settings.fps}fps)")

        row_export = box_vse.row()
        if video_export.is_rendering():
            row_export.label(text="Rendering MP4 in background...", icon='TIME')
        else:
            row_export.operator("smart_timelapse.export_video", icon='RENDER_ANIMATION')

        # Drawing Stutter Prevention Tips
        box_tips = layout.box()
        box_tips.label(text="Drawing Stutter Prevention:", icon='LIGHT')
        box_tips.label(text="• Smart Delay + JPG is recommended.")
        box_tips.label(text="• Action mode captures on pen release.")


classes = (
    SMART_TIMELAPSE_OT_open_folder,
    SMART_TIMELAPSE_PT_quick_settings,
    SMART_TIMELAPSE_PT_main_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(draw_header_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_header_button)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
