import bpy
import bmesh
from mathutils import Vector, Quaternion
from ... utils.math import get_center_between_verts, average_locations, create_rotation_matrix_from_vertex, create_rotation_matrix_from_edge, create_rotation_matrix_from_face
from ... utils.scene import set_cursor
from ... utils.ui import popup_message
from ... utils.registration import get_prefs, get_addon
from ... utils.draw import add_object_axes_drawing_handler, remove_object_axes_drawing_handler
from ... utils.tools import get_active_tool


cursor = None


class CursorToOrigin(bpy.types.Operator):
    bl_idname = "machin3.cursor_to_origin"
    bl_label = "MACHIN3: Cursor to Origin"
    bl_description = "Reset Cursor Location and/or Rotation to World Origin\nALT: Only reset Cursor Location\nCTRL: Only reset Cursor Rotation"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if event.alt and event.ctrl:
            popup_message("Hold down ATL, CTRL or neither, not both!", title="Invalid Modifier Keys")
            return {'CANCELLED'}

        # ensure cursor is actuall shown
        if not context.space_data.overlay.show_cursor:
            context.space_data.overlay.show_cursor = True

        cmx = context.scene.cursor.matrix

        set_cursor(location=cmx.to_translation() if event.ctrl else Vector(), rotation=cmx.to_quaternion() if event.alt else Quaternion())

        if get_prefs().cursor_set_transform_preset:
            global cursor

            if cursor is not None:
                bpy.ops.machin3.set_transform_preset(pivot=cursor[0], orientation=cursor[1])
                cursor = None

        if get_prefs().cursor_toggle_axes_drawing:
            dns = bpy.app.driver_namespace
            handler = dns.get('draw_object_axes')

            if handler:
                remove_object_axes_drawing_handler(handler)

        return {'FINISHED'}


class CursorToSelected(bpy.types.Operator):
    bl_idname = "machin3.cursor_to_selected"
    bl_label = "MACHIN3: Cursor to Selected"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def description(cls, context, properties):
        if context.mode == 'OBJECT':
            return "Align Cursor with Selected Object(s)\nALT: Only set Cursor Location\nCTRL: Only set Cursor Rotation"

        elif context.mode == 'EDIT_MESH':
            return "Align Cursor with Vert/Edge/Face\nALT: Only set Cursor Location\nCTRL: Only set Cursor Rotation"

    @classmethod
    def poll(cls, context):
        if context.mode == 'EDIT_MESH' and tuple(context.scene.tool_settings.mesh_select_mode) in [(True, False, False), (False, True, False), (False, False, True)]:
            bm = bmesh.from_edit_mesh(context.active_object.data)
            return [v for v in bm.verts if v.select]
        return context.active_object or context.selected_objects

    def invoke(self, context, event):

        # ensure cursor is actuall shown
        if not context.space_data.overlay.show_cursor:
            context.space_data.overlay.show_cursor = True

        # only actually set the presets and draw the axes if hyper cursor tools are not active
        set_transform_preset_and_draw_cursor_axes = 'machin3.tool_hyper_cursor' not in get_active_tool(context)

        active = context.active_object
        sel = [obj for obj in context.selected_objects if obj != active]
        cmx = context.scene.cursor.matrix

        # make sure there is an active
        if sel and not active:
            context.view_layer.objects.active = sel[0]
            sel.remove(active)


        if event.alt and event.ctrl:
            popup_message("Hold down ATL, CTRL or neither, not both!", title="Invalid Modifier Keys")
            return {'CANCELLED'}

        # if in object mode with multiple selected ojects, pass it on to Blender's op
        if context.mode == 'OBJECT' and active and not sel:
            self.cursor_to_active_object(active, cmx, only_location=event.alt, only_rotation=event.ctrl)

            if set_transform_preset_and_draw_cursor_axes:
                if get_prefs().activate_transform_pie and get_prefs().cursor_set_transform_preset:
                    self.set_cursor_transform_preset(context)

                if get_prefs().activate_shading_pie and get_prefs().cursor_toggle_axes_drawing:
                    self.enable_cursor_axes_drawing(context)

            return {'FINISHED'}

        elif context.mode == 'EDIT_MESH':
            self.cursor_to_editmesh(context, active, cmx, only_location=event.alt, only_rotation=event.ctrl)

            if set_transform_preset_and_draw_cursor_axes:
                if get_prefs().activate_transform_pie and get_prefs().cursor_set_transform_preset:
                    self.set_cursor_transform_preset(context)

                if get_prefs().activate_shading_pie and get_prefs().cursor_toggle_axes_drawing:
                    self.enable_cursor_axes_drawing(context)

            return {'FINISHED'}

        # fall back for cases not covered above
        bpy.ops.view3d.snap_cursor_to_selected()


        return {'FINISHED'}

    def enable_cursor_axes_drawing(self, context):
        dns = bpy.app.driver_namespace
        handler = dns.get('draw_object_axes')

        if handler:
            remove_object_axes_drawing_handler(handler)

        add_object_axes_drawing_handler(dns, context, [], True)

        context.area.tag_redraw()

    def set_cursor_transform_preset(self, context):
        global cursor

        pivot = context.scene.tool_settings.transform_pivot_point
        orientation = context.scene.transform_orientation_slots[0].type

        # only store a new cursor pivot and orientation if the previous one isn't already CURSOR, CURSOR
        if pivot != 'CURSOR' and orientation != 'CURSOR':
            cursor = (context.scene.tool_settings.transform_pivot_point, context.scene.transform_orientation_slots[0].type)

        bpy.ops.machin3.set_transform_preset(pivot='CURSOR', orientation='CURSOR')

    def cursor_to_editmesh(self, context, active, cmx, only_location, only_rotation):
        bm = bmesh.from_edit_mesh(active.data)
        mx = active.matrix_world

        if tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (True, False, False):
            verts = [v for v in bm.verts if v.select]

            co = average_locations([v.co for v in verts])

            # create vertex world matrix components
            loc = mx @ co

            v = bm.select_history[-1] if bm.select_history else verts[0]
            rot = create_rotation_matrix_from_vertex(active, v)

        elif tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, True, False):
            edges = [e for e in bm.edges if e.select]
            center = average_locations([get_center_between_verts(*e.verts) for e in edges])

            # create edge world matrix components
            loc = mx @ center

            e = bm.select_history[-1] if bm.select_history else edges[0]
            rot = create_rotation_matrix_from_edge(active, e)

        elif tuple(bpy.context.scene.tool_settings.mesh_select_mode) == (False, False, True):
            faces = [f for f in bm.faces if f.select]

            center = average_locations([f.calc_center_median_weighted() for f in faces])

            # create face world matrix components
            loc = mx @ center

            f = bm.faces.active if bm.faces.active and bm.faces.active in faces else faces[0]
            rot = create_rotation_matrix_from_face(mx, f)

        # set the cursor location/rotation
        set_cursor(location=cmx.to_translation() if only_rotation else loc, rotation=cmx.to_quaternion() if only_location else rot.to_quaternion())

    def cursor_to_active_object(self, active, cmx, only_location, only_rotation):
        mx = active.matrix_world
        loc, rot, _ = mx.decompose()

        set_cursor(location=cmx.to_translation() if only_rotation else loc, rotation=cmx.to_quaternion() if only_location else rot)
