import bpy
import os

class SmartTimelapsePreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    default_output_dir: bpy.props.StringProperty(
        name="Default Output Directory",
        description="Default directory to save timelapses if not set per scene (absolute path)",
        subtype='DIR_PATH',
        default=os.path.join(os.path.expanduser("~"), "Videos", "BlenderTimelapse")
    )

    default_interval: bpy.props.FloatProperty(
        name="Default Interval (s)",
        description="Default interval between captures in seconds",
        default=5.0,
        min=0.5,
        max=3600.0
    )

    default_idle_timeout: bpy.props.FloatProperty(
        name="Default Idle Timeout (s)",
        description="Pause capture if no user activity for this duration",
        default=30.0,
        min=5.0,
        max=600.0
    )

    default_fps: bpy.props.IntProperty(
        name="Default Video FPS",
        description="Frame rate for exported MP4 videos",
        default=30,
        min=1,
        max=120
    )

    video_quality: bpy.props.EnumProperty(
        name="Video Quality",
        description="Encoding quality for generated MP4 video",
        items=[
            ('HIGH', "High", "High quality / larger file size"),
            ('MEDIUM', "Medium", "Balanced quality and file size"),
            ('LOW', "Low", "Smaller file size")
        ],
        default='HIGH'
    )

    ignore_anim_playback: bpy.props.BoolProperty(
        name="Ignore Animation Playback for Idle",
        description="Do not treat animation playback as user activity to avoid false recordings while previewing",
        default=True
    )

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Global Default Settings", icon='PREFERENCES')
        box.prop(self, "default_output_dir")
        box.prop(self, "default_interval")
        box.prop(self, "default_idle_timeout")
        box.prop(self, "default_fps")
        box.prop(self, "video_quality")
        box.prop(self, "ignore_anim_playback")


def get_preferences(context=None):
    if context is None:
        context = bpy.context
    prefs = context.preferences.addons.get(__package__)
    if prefs:
        return prefs.preferences
    return None


def register():
    bpy.utils.register_class(SmartTimelapsePreferences)


def unregister():
    bpy.utils.unregister_class(SmartTimelapsePreferences)
