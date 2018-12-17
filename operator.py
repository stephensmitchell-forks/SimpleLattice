import bpy
from mathutils import *

from . import util

# https://bitbucket.org/kursad/blender_addons_easylattice/src/170d20e1a6c751c5e7216fbc530ddb944bc2f9f3/src/kk_QuickLatticeCreate.py?at=master&fileviewer=file-view-default


allowed_object_types = set(['MESH', 'CURVE', 'SURFACE',
                            'FONT', 'GPENCIL', 'LATTICE'])


class Op_LatticeCreateOperator(bpy.types.Operator):
    bl_idname = "object.op_latticecreate"
    bl_label = "SimpleLattice"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_options = {"REGISTER", "UNDO"}

    orientation_types = (('GLOBAL', 'Global', '0'),
                         ('LOCAL', 'Local', '1'),
                         ('CURSOR', 'Cursor', '2'))

    orientation: bpy.props.EnumProperty(name="Orientation", items=orientation_types, default='LOCAL')

    resolution_u: bpy.props.IntProperty(name="u", default=2, min=2)
    resolution_v: bpy.props.IntProperty(name="v", default=2, min=2)
    resolution_w: bpy.props.IntProperty(name="w", default=2, min=2)

    interpolation_types = (('KEY_LINEAR', 'Linear', '0'),
                           ('KEY_CARDINAL', 'Cardinal', '1'),
                           ('KEY_CATMULL_ROM', 'Catmull-Rom', '2'),
                           ('KEY_BSPLINE', 'BSpline', '3'))

    interpolation: bpy.props.EnumProperty(name="Interpolation", items=interpolation_types, default='KEY_LINEAR')

    @classmethod
    def poll(self, context):
        has_selection = len(context.selected_objects) != 0
        if has_selection:
            for obj in context.selected_objects:
                if obj.type in allowed_object_types:
                    return True

        return False

    def invoke(self, context, event):
        print ("INVOKE")

        objects = []
        all_objecst_are_meshes = True

        for obj in context.selected_objects:
            if obj.type in allowed_object_types:
                objects.append(obj)

                if all_objecst_are_meshes and obj.type != 'MESH':
                    all_objecst_are_meshes = False

        self.vertex_mode = all_objecst_are_meshes and objects[0].mode == 'EDIT'

        if len(objects) > 0:
            lattice = self.createLattice(context)
            self.lattice = lattice
            self.lattice_name = lattice.name

            self.mapping = None
            self.group_mapping = None
            self.vert_mapping = None
            self.objects = list(map(lambda x: x.name, objects))

            self.cleanup(objects)

            if self.vertex_mode:
                bpy.ops.object.editmode_toggle()

                self.coords, self.vert_mapping = self.get_coords_from_verts(
                    objects)
                self.group_mapping = self.set_vertex_group(
                    objects, self.vert_mapping)

            else:
                self.coords = self.get_coords_from_objects(objects)

            self.matrix = context.active_object.matrix_world
            self.update_lattice_from_bbox(
                context, lattice, self.coords, self.matrix)

            self.add_ffd_modifier(objects, lattice, self.group_mapping)

            lattice.select_set(True)
            context.view_layer.objects.active = lattice
            return {'FINISHED'}
        else:
            return {'CANCELLED'}

    def execute(self, context):
        # print("execute")
        # print(self.matrix)

        #objects = list(map(lambda x: context.scene.objects[x], self.objects))
        #map(lambda obj: obj.select_set(False), objects)

        #lattice = self.createLattice(context)
        lattice = context.scene.objects[self.lattice_name]

        self.update_lattice_from_bbox(context,
                                      lattice,
                                      self.coords.copy(),
                                      self.matrix.copy())

        # self.cleanup(objects)
        # if self.vertex_mode:
        #    self.group_mapping = self.set_vertex_group(
        #        objects, self.vert_mapping)

        #self.add_ffd_modifier(objects, lattice, self.group_mapping)

        lattice.select_set(True)
        context.view_layer.objects.active = lattice

        if lattice.mode == "EDIT":
            bpy.ops.object.editmode_toggle()

        return {'FINISHED'}

    def get_coords_from_verts(self, objects):
        worldspace_verts = []
        vert_mapping = {}

        for obj in objects:
            obj.select_set(False)

            vert_indices = []
            vertices = obj.data.vertices
            for vert in vertices:
                if vert.select == True:
                    index = vert.index
                    vert_indices.append(index)
                    worldspace_verts.append(obj.matrix_world @ vert.co)

            vert_mapping[obj.name] = vert_indices

        return worldspace_verts, vert_mapping

    def get_coords_from_objects(self, objects):
        bbox_world_coords = []
        for obj in objects:
            obj.select_set(False)

            coords = obj.bound_box[:]
            coords = [(obj.matrix_world @ Vector(p[:])).to_tuple() for p in coords]
            bbox_world_coords.extend(coords)

        return bbox_world_coords

    def update_lattice_from_bbox(self, context, lattice, bbox_world_coords, matrix_world):

        if self.orientation == 'GLOBAL':
            rot = Matrix.Identity(4)
            bbox = util.bounds(bbox_world_coords)

        elif self.orientation == 'LOCAL':
            rot = matrix_world.to_quaternion().to_matrix().to_4x4()
            bbox = util.bounds(bbox_world_coords, rot.inverted())

        elif self.orientation == 'CURSOR':
            rot = context.scene.cursor_rotation.to_matrix().to_4x4()
            bbox = util.bounds(bbox_world_coords, rot.inverted())

        bound_min = Vector((bbox.x.min, bbox.y.min, bbox.z.min))
        bound_max = Vector((bbox.x.max, bbox.y.max, bbox.z.max))
        offset = (bound_min + bound_max) * 0.5

        # finally gather position/rotation/scaling for the lattice
        location = rot @ offset
        rotation = rot
        scale = Vector((abs(bound_max.x - bound_min.x),
                        abs(bound_max.y - bound_min.y),
                        abs(bound_max.z - bound_min.z)))

        self.updateLattice(lattice, location, rotation, scale)

    def createLattice(self, context):
        lattice_data = bpy.data.lattices.new('SimpleLattice')
        lattice_obj = bpy.data.objects.new('SimpleLattice', lattice_data)

        context.scene.collection.objects.link(lattice_obj)

        return lattice_obj

    def updateLattice(self, lattice, location, rotation, scale):
        lattice.data.points_u = self.resolution_u
        lattice.data.points_v = self.resolution_v
        lattice.data.points_w = self.resolution_w

        lattice.data.interpolation_type_u = self.interpolation
        lattice.data.interpolation_type_v = self.interpolation
        lattice.data.interpolation_type_w = self.interpolation

        lattice.location = location
        lattice.rotation_euler = rotation.to_euler()
        lattice.scale = scale.to_tuple()

    def add_ffd_modifier(self, objects, lattice, group_mapping):
        for obj in objects:
            ffd = obj.modifiers.new("SimpleLattice", "LATTICE")
            ffd.object = lattice
            if group_mapping != None:
                vertex_group_name = group_mapping[obj.name]
                ffd.name = vertex_group_name
                ffd.vertex_group = vertex_group_name

    def cleanup(self, objects):
        for obj in objects:
            used_vertex_groups = set()
            obsolete_modifiers = []
            for modifier in obj.modifiers:
                if modifier.type == 'LATTICE' and "SimpleLattice" in modifier.name:
                    if modifier.object == None:
                        obsolete_modifiers.append(modifier)
                    elif modifier.vertex_group == "":
                        used_vertex_groups.add(modifier.vertex_group)

            obsolete_groups = []
            for grp in obj.vertex_groups:
                if "SimpleLattice" in grp.name:
                    if grp.name not in used_vertex_groups:
                        obsolete_groups.append(grp)

            for group in obsolete_groups:
                print(f"removed vertex_group: {group.name}")
                obj.vertex_groups.remove(group)
            for modifier in obsolete_modifiers:
                print(f"removed modifier: {modifier.name}")
                obj.modifiers.remove(modifier)

    def set_vertex_group(self, objects, vert_mapping):
        group_mapping = {}
        for obj in objects:
            if obj.mode == "EDIT":
                bpy.ops.object.editmode_toggle()

            group_index = 0
            for grp in obj.vertex_groups:
                if "SimpleLattice." in grp.name:
                    index = int(grp.name.split(".")[-1])
                    group_index = max(group_index, index)

            group = obj.vertex_groups.new(name=f"SimpleLattice.{group_index}")

            group.add(vert_mapping[obj.name], 1.0, "REPLACE")
            group_mapping[obj.name] = group.name

        return group_mapping
