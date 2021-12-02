import bpy


class Install_P4Python(bpy.types.Operator):
    bl_idname = "machin3.install_p4python"
    bl_label = "MACHIN3: Install P4Python"
    bl_description = "Install official P4 Python module"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            from .. utils.pip import Pip
            #Pip.upgrade_pip()
            Pip.install('p4python')
            print('P4Python successfully installed!')
            self.report({'INFO'}, 'P4Python successfully installed!')
        except:
            print('P4Python not loaded correctly. Try restarting Blender')
        return {'FINISHED'}