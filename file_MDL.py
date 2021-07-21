import bpy
import os
import mathutils
from . import fileHelper, enums, common, format_BASIC, format_CHUNK, format_GC
from .common import ModelData
from typing import Dict, List

DO = False  # Debug out


def hex8(number: int):
    return '{:08x}'.format(number)


def read(context: bpy.types.Context,
         filepath: str, noDoubleVerts: bool, console_debug_output: bool):

    global DO
    DO = console_debug_output
    common.DO = DO
    format_BASIC.DO = DO
    format_CHUNK.DO = DO
    format_GC.DO = DO
    if DO:
        os.system("cls")

    fileR = fileHelper.FileReader(filepath)

    if fileR.filepath is None:
        print("no valid filepath")
        return {'CANCELLED'}

    indicator = enums.MDLFormatIndicator(fileR.rULong(0) & ~0xFF00000000000000)
    fileVersion = fileR.rByte(7)

    if indicator == enums.MDLFormatIndicator.SA1MDL:
        file_format = 'SA1'
    elif indicator == enums.MDLFormatIndicator.SA2MDL:
        file_format = 'SA2'
    elif indicator == enums.MDLFormatIndicator.SA2BMDL:
        file_format = 'SA2B'
    else:
        print("no Valid file")
        return {'CANCELLED'}

    if DO:
        print(" == Starting MDL file reading ==")
        print("  File:", filepath)
        print("  Format:", file_format, "version", fileVersion)
        print("  - - - - - -\n")

    # reading meta data

    labels: Dict[int, str] = dict()
    animFiles = list()
    morphFiles = list()

    if fileVersion < 2:
        if fileVersion == 1:
            # getting labels
            tmpAddr = fileR.rUInt(0x14)
            if tmpAddr > 0:
                addr = fileR.rInt(tmpAddr)
                while addr != -1:
                    labels[fileR.rUInt(tmpAddr)] = fileR.rString(tmpAddr + 4)
                    tmpAddr += 8
                    addr = fileR.rInt(tmpAddr)

            # getting morph paths
            tmpAddr = fileR.rUInt(0x10)
            if tmpAddr > 0:
                addr = fileR.rInt(tmpAddr)
                while addr != -1:
                    addr = fileR.rUInt(tmpAddr)
                    morphFiles.append(fileR.rString(addr))
                    tmpAddr += 4
                    addr = fileR.rInt(tmpAddr)

        # getting animation paths
        tmpAddr = fileR.rUInt(0xC)
        if tmpAddr > 0:
            addr = fileR.rInt(tmpAddr)
            while addr != -1:
                addr = fileR.rUInt(tmpAddr)
                animFiles.append(fileR.rString(addr))
                tmpAddr += 4
                addr = fileR.rInt(tmpAddr)
    else:
        tmpAddr = fileR.rUInt(0xC)
        if tmpAddr > 0:
            finished = False
            while not finished:
                cnkType = enums.Chunktypes(fileR.rUInt(tmpAddr))
                cnkSize = fileR.rUInt(tmpAddr + 4)
                cnkNext = tmpAddr + 8 + cnkSize

                if fileVersion == 2:
                    cnkBase = 0
                else:
                    cnkBase = tmpAddr + 8

                tmpAddr += 8

                if cnkType == enums.Chunktypes.Label:
                    while fileR.rLong(tmpAddr) != -1:
                        labels[fileR.rUInt(tmpAddr)] \
                            = fileR.rString(cnkBase + fileR.rUInt(tmpAddr + 4))
                        tmpAddr += 8
                elif cnkType == enums.Chunktypes.Animation:
                    while fileR.rInt(tmpAddr) != -1:
                        animFiles.append(
                            fileR.rString(cnkBase + fileR.rUInt(tmpAddr)))
                        tmpAddr += 4
                elif cnkType == enums.Chunktypes.Morph:
                    while fileR.rInt(tmpAddr) != -1:
                        morphFiles.append(
                            fileR.rString(cnkBase + fileR.rUInt(tmpAddr)))
                        tmpAddr += 4
                elif cnkType == enums.Chunktypes.Author:
                    context.scene.saSettings.author = fileR.rString(tmpAddr)
                elif cnkType == enums.Chunktypes.Description:
                    context.scene.saSettings.description \
                        = fileR.rString(tmpAddr)
                elif cnkType == enums.Chunktypes.Tool and DO:
                    print("Tool metadata found")
                elif cnkType == enums.Chunktypes.Texture and DO:
                    print("Texture metadata found")
                elif cnkType == enums.Chunktypes.End:
                    finished = True
                else:
                    if DO:
                        print("invalid Chunk type:", cnkType.value)

                tmpAddr = cnkNext

    if DO:
        if len(labels) > 0:
            print("Labels:", len(labels))
            for l in labels.keys():
                print(hex8(l), labels[l])
        if context.scene.saSettings.author != "":
            print("Author:", context.scene.saSettings.author)
        if context.scene.saSettings.description != "":
            print("Description:", context.scene.saSettings.description)
        print("\n")

        if len(animFiles) > 0:
            print(" == Animation Files ==")
            for s in animFiles:
                print(" -", s)
            print(" - - - - \n")

        if len(morphFiles) > 0:
            print(" == Morph Files ==")
            for s in morphFiles:
                print(" -", s)
            print(" - - - - \n")

        print(" == Reading Models ==")

    objects: List[common.Model] = list()
    common.readObjects(fileR, fileR.rUInt(8), 0, None, labels, objects)

    attaches = dict()
    objID = 0
    numberCount = max(3, len(str(len(objects))))
    for o in objects:
        o.name = str(objID).zfill(numberCount) + "_" + o.name
        objID += 1
        if o.meshPtr > 0 and o.meshPtr not in attaches:
            if file_format == 'SA2':
                attaches[o.meshPtr] = format_CHUNK.Attach.read(fileR,
                                                               o.meshPtr,
                                                               len(attaches),
                                                               labels)
            elif file_format == 'SA1':
                attaches[o.meshPtr] = format_BASIC.Attach.read(fileR,
                                                               o.meshPtr,
                                                               len(attaches),
                                                               labels)
            elif file_format == 'SA2B':
                attaches[o.meshPtr] = format_GC.Attach.read(fileR,
                                                            o.meshPtr,
                                                            len(attaches),
                                                            labels)

    isArmature = False
    if file_format == 'SA2':
        # checking whether the file is an armature (weighted model)

        processedAttaches = format_CHUNK.OrderChunks(objects, attaches)

        for a in processedAttaches.values():
            if len(a.affectedBy) > 1:
                isArmature = True
                break
        root = None
        if isArmature:
            root = objects[0]
        format_CHUNK.ProcessChunkData(objects,
                                      processedAttaches,
                                      noDoubleVerts,
                                      root)
    elif file_format == 'SA1':
        format_BASIC.process_BASIC(objects, attaches)
    elif file_format == 'SA2B':
        format_GC.process_GC(objects, attaches)

    collection = bpy.data.collections.new(
        "Import_" + os.path.splitext(os.path.basename(filepath))[0])
    context.scene.collection.children.link(collection)

    if isArmature:
        from bpy_extras.io_utils import axis_conversion
        corrective = axis_conversion(to_forward='X', to_up='Z',).to_4x4()

        root = objects[0]
        armature = bpy.data.armatures.new(root.name)
        armatureObj = bpy.data.objects.new(root.name, armature)
        armatureObj.matrix_local = root.matrix_local

        collection.objects.link(armatureObj)
        for c in root.meshes:
            collection.objects.link(c)
            c.parent = armatureObj
            modif = c.modifiers.new("deform", 'ARMATURE')
            modif.object = armatureObj

        armatureMatrix = root.matrix_world
        root.bone = None

        # gotta be in edit mode to add bones
        context.view_layer.objects.active = armatureObj
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        bones = objects[1:]
        edit_bones = armatureObj.data.edit_bones
        for b in bones:
            bone = edit_bones.new(b.name)
            bone.layers[0] = True
            bone.head = (0, 0, 0)
            bone.tail = (1, 0, 0)

            bone.matrix = armatureMatrix.inverted() @ (b.matrix_world)
            # @ corrective)

            if b.parent.bone is not None:
                bone.parent = b.parent.bone
            b.bone = bone

            bone.use_deform = False
            for o in root.meshes:
                if o.vertex_groups.find(bone.name) >= 0:
                    bone.use_deform = True
                    break

        # correcting the lengths
        for b in edit_bones:
            childCount = len(b.children)
            distance = 1
            if childCount > 0:
                distance = (b.head - b.children[0].head).magnitude
                if childCount > 1:
                    for c in b.children:
                        newDist = (b.head - c.head).magnitude
                        if newDist < distance:
                            distance = newDist
            if distance < 0.5:
                distance = 0.5
            b.length = distance

        bpy.ops.object.mode_set(mode='OBJECT')

    else:
        for o in objects:
            data = None
            if len(o.meshes) == 1:
                data = o.meshes[0]

            bpyObj = bpy.data.objects.new(o.name, data)
            o.origObject = bpyObj
            if o.parent is not None:
                bpyObj.parent = o.parent.origObject
            bpyObj.matrix_local = o.matrix_local
            collection.objects.link(bpyObj)

    context.view_layer.update()

    if DO:
        for o in objects:
            o.debug()

    return {'FINISHED'}

def readWithValues(context: bpy.types.Context, filepath: str, noDoubleVerts: bool, console_debug_output: bool, position: List, rotation: List, scale: List):

    global DO
    DO = console_debug_output
    common.DO = DO
    format_BASIC.DO = DO
    format_CHUNK.DO = DO
    format_GC.DO = DO
    if DO:
        os.system("cls")

    fileR = fileHelper.FileReader(filepath)

    if fileR.filepath is None:
        print("no valid filepath")
        return {'CANCELLED'}

    indicator = enums.MDLFormatIndicator(fileR.rULong(0) & ~0xFF00000000000000)
    fileVersion = fileR.rByte(7)

    if indicator == enums.MDLFormatIndicator.SA1MDL:
        file_format = 'SA1'
    elif indicator == enums.MDLFormatIndicator.SA2MDL:
        file_format = 'SA2'
    elif indicator == enums.MDLFormatIndicator.SA2BMDL:
        file_format = 'SA2B'
    else:
        print("no Valid file")
        return {'CANCELLED'}

    if DO:
        print(" == Starting MDL file reading ==")
        print("  File:", filepath)
        print("  Format:", file_format, "version", fileVersion)
        print("  - - - - - -\n")

    # reading meta data

    labels: Dict[int, str] = dict()
    animFiles = list()
    morphFiles = list()

    if fileVersion < 2:
        if fileVersion == 1:
            # getting labels
            tmpAddr = fileR.rUInt(0x14)
            if tmpAddr > 0:
                addr = fileR.rInt(tmpAddr)
                while addr != -1:
                    labels[fileR.rUInt(tmpAddr)] = fileR.rString(tmpAddr + 4)
                    tmpAddr += 8
                    addr = fileR.rInt(tmpAddr)

            # getting morph paths
            tmpAddr = fileR.rUInt(0x10)
            if tmpAddr > 0:
                addr = fileR.rInt(tmpAddr)
                while addr != -1:
                    addr = fileR.rUInt(tmpAddr)
                    morphFiles.append(fileR.rString(addr))
                    tmpAddr += 4
                    addr = fileR.rInt(tmpAddr)

        # getting animation paths
        tmpAddr = fileR.rUInt(0xC)
        if tmpAddr > 0:
            addr = fileR.rInt(tmpAddr)
            while addr != -1:
                addr = fileR.rUInt(tmpAddr)
                animFiles.append(fileR.rString(addr))
                tmpAddr += 4
                addr = fileR.rInt(tmpAddr)
    else:
        tmpAddr = fileR.rUInt(0xC)
        if tmpAddr > 0:
            finished = False
            while not finished:
                cnkType = enums.Chunktypes(fileR.rUInt(tmpAddr))
                cnkSize = fileR.rUInt(tmpAddr + 4)
                cnkNext = tmpAddr + 8 + cnkSize

                if fileVersion == 2:
                    cnkBase = 0
                else:
                    cnkBase = tmpAddr + 8

                tmpAddr += 8

                if cnkType == enums.Chunktypes.Label:
                    while fileR.rLong(tmpAddr) != -1:
                        labels[fileR.rUInt(tmpAddr)] \
                            = fileR.rString(cnkBase + fileR.rUInt(tmpAddr + 4))
                        tmpAddr += 8
                elif cnkType == enums.Chunktypes.Animation:
                    while fileR.rInt(tmpAddr) != -1:
                        animFiles.append(
                            fileR.rString(cnkBase + fileR.rUInt(tmpAddr)))
                        tmpAddr += 4
                elif cnkType == enums.Chunktypes.Morph:
                    while fileR.rInt(tmpAddr) != -1:
                        morphFiles.append(
                            fileR.rString(cnkBase + fileR.rUInt(tmpAddr)))
                        tmpAddr += 4
                elif cnkType == enums.Chunktypes.Author:
                    context.scene.saSettings.author = fileR.rString(tmpAddr)
                elif cnkType == enums.Chunktypes.Description:
                    context.scene.saSettings.description \
                        = fileR.rString(tmpAddr)
                elif cnkType == enums.Chunktypes.Tool and DO:
                    print("Tool metadata found")
                elif cnkType == enums.Chunktypes.Texture and DO:
                    print("Texture metadata found")
                elif cnkType == enums.Chunktypes.End:
                    finished = True
                else:
                    if DO:
                        print("invalid Chunk type:", cnkType.value)

                tmpAddr = cnkNext

    if DO:
        if len(labels) > 0:
            print("Labels:", len(labels))
            for l in labels.keys():
                print(hex8(l), labels[l])
        if context.scene.saSettings.author != "":
            print("Author:", context.scene.saSettings.author)
        if context.scene.saSettings.description != "":
            print("Description:", context.scene.saSettings.description)
        print("\n")

        if len(animFiles) > 0:
            print(" == Animation Files ==")
            for s in animFiles:
                print(" -", s)
            print(" - - - - \n")

        if len(morphFiles) > 0:
            print(" == Morph Files ==")
            for s in morphFiles:
                print(" -", s)
            print(" - - - - \n")

        print(" == Reading Models ==")

    objects: List[common.Model] = list()
    common.readObjects(fileR, fileR.rUInt(8), 0, None, labels, objects)

    attaches = dict()
    objID = 0
    numberCount = max(3, len(str(len(objects))))
    for o in objects:
        o.name = str(objID).zfill(numberCount) + "_" + o.name
        objID += 1
        if o.meshPtr > 0 and o.meshPtr not in attaches:
            if file_format == 'SA2':
                attaches[o.meshPtr] = format_CHUNK.Attach.read(fileR,
                                                               o.meshPtr,
                                                               len(attaches),
                                                               labels)
            elif file_format == 'SA1':
                attaches[o.meshPtr] = format_BASIC.Attach.read(fileR,
                                                               o.meshPtr,
                                                               len(attaches),
                                                               labels)
            elif file_format == 'SA2B':
                attaches[o.meshPtr] = format_GC.Attach.read(fileR,
                                                            o.meshPtr,
                                                            len(attaches),
                                                            labels)

    isArmature = False
    if file_format == 'SA2':
        # checking whether the file is an armature (weighted model)

        processedAttaches = format_CHUNK.OrderChunks(objects, attaches)

        for a in processedAttaches.values():
            if len(a.affectedBy) > 1:
                isArmature = True
                break
        root = None
        if isArmature:
            root = objects[0]
        format_CHUNK.ProcessChunkData(objects,
                                      processedAttaches,
                                      noDoubleVerts,
                                      root)
    elif file_format == 'SA1':
        format_BASIC.process_BASIC(objects, attaches)
    elif file_format == 'SA2B':
        format_GC.process_GC(objects, attaches)

    collection = bpy.data.collections.new(
        "Import_" + os.path.splitext(os.path.basename(filepath))[0])
    context.scene.collection.children.link(collection)

    if isArmature:
        from bpy_extras.io_utils import axis_conversion
        corrective = axis_conversion(to_forward='X', to_up='Z',).to_4x4()

        root = objects[0]
        armature = bpy.data.armatures.new(root.name)
        armatureObj = bpy.data.objects.new(root.name, armature)
        armatureObj.matrix_local = root.matrix_local

        collection.objects.link(armatureObj)
        for c in root.meshes:
            collection.objects.link(c)
            c.parent = armatureObj
            modif = c.modifiers.new("deform", 'ARMATURE')
            modif.object = armatureObj

        armatureMatrix = root.matrix_world
        root.bone = None

        # gotta be in edit mode to add bones
        context.view_layer.objects.active = armatureObj
        bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        bones = objects[1:]
        edit_bones = armatureObj.data.edit_bones
        for b in bones:
            bone = edit_bones.new(b.name)
            bone.layers[0] = True
            bone.head = (0, 0, 0)
            bone.tail = (1, 0, 0)

            bone.matrix = armatureMatrix.inverted() @ (b.matrix_world)
            # @ corrective)

            if b.parent.bone is not None:
                bone.parent = b.parent.bone
            b.bone = bone

            bone.use_deform = False
            for o in root.meshes:
                if o.vertex_groups.find(bone.name) >= 0:
                    bone.use_deform = True
                    break

        # correcting the lengths
        for b in edit_bones:
            childCount = len(b.children)
            distance = 1
            if childCount > 0:
                distance = (b.head - b.children[0].head).magnitude
                if childCount > 1:
                    for c in b.children:
                        newDist = (b.head - c.head).magnitude
                        if newDist < distance:
                            distance = newDist
            if distance < 0.5:
                distance = 0.5
            b.length = distance

        bpy.ops.object.mode_set(mode='OBJECT')

    else:
        for o in objects:
            data = None
            if len(o.meshes) == 1:
                data = o.meshes[0]

            bpyObj = bpy.data.objects.new(o.name, data)
            o.origObject = bpyObj
            if o.parent is not None:
                bpyObj.parent = o.parent.origObject
            bpyObj.matrix_local = o.matrix_local
            collection.objects.link(bpyObj)

    context.view_layer.update()

    if DO:
        for o in objects:
            o.debug()

    bpy.context.active_object.location = (position[0], position[1], position[2])
    bpy.context.active_object.rotation_euler = (rotation[0], rotation[1], rotation[2])
    bpy.context.active_object.scale = (scale[0], scale[1], scale[2])

    return {'FINISHED'}

def write(context,
          filepath, *,
          export_format,
          write_Specular,
          use_selection,
          apply_modifs,
          console_debug_output):
    from .common import ModelData

    global DO
    DO = console_debug_output
    common.DO = DO
    format_BASIC.DO = DO
    format_CHUNK.DO = DO
    format_GC.DO = DO

    format_CHUNK.writeSpecular = write_Specular

    if DO:
        # clear console and enable debug outputs
        os.system("cls")

    # create the file
    fileW = fileHelper.FileWriter()  # filepath=filepath)
    common.exportedFile = fileW

    # write the header
    fileVersion = 3

    if export_format == 'SA1':
        indicator = enums.MDLFormatIndicator.SA1MDL
    elif export_format == 'SA2':
        indicator = enums.MDLFormatIndicator.SA2MDL
    else:  # SA2BLVL
        indicator = enums.MDLFormatIndicator.SA2BMDL

    fileW.wULong(indicator.value | (fileVersion << 56))

    if DO:
        print(" == Starting MDL file exporting ==")
        print("  File:", filepath)
        print("  Format:", export_format, "version", fileVersion)
        print("  - - - - - -\n")

    fileW.wUInt(0)  # placeholder for the model properties address
    fileW.wUInt(0)  # placeholder for the labels address
    labels: Dict[int, str] = dict()  # for labels methadata

    from bpy_extras.io_utils import axis_conversion

    global_matrix = axis_conversion(to_forward='-Z', to_up='Y',).to_4x4()

    # creating and getting variables to use in the export process
    objects, meshes, materials, mObjects \
        = common.convertObjectData(context,
                                   use_selection,
                                   apply_modifs,
                                   global_matrix,
                                   export_format,
                                   False)

    meshDict: Dict[bpy.types.Mesh, int] = dict()

    # writing mesh data
    isArmature = False
    if export_format == 'SA1':
        # writing material data first
        # bscMaterials \
        # = format_BASIC.Material.writeMaterials(fileW, materials, labels)
        # then writing mesh data
        for m in meshes:
            matPtr, bscMaterials \
                = format_BASIC.Material.writeMaterials(fileW,
                                                       m.materials,
                                                       m.name,
                                                       labels)
            mesh = format_BASIC.Attach.fromMesh(m,
                                                global_matrix,
                                                matPtr,
                                                bscMaterials)
            if mesh is not None:
                mesh.write(fileW, labels, meshDict)

    elif export_format == 'SA2':
        # armature meshes get written differently
        isArmature = (len(objects) == 1
                      and isinstance(objects[0], common.Armature))
        if not isArmature:
            for m in meshes:
                mesh = format_CHUNK.Attach.fromMesh(m,
                                                    global_matrix,
                                                    materials)
                if mesh is not None:
                    mesh.write(fileW, labels, meshDict)

    else:
        for m in meshes:
            mesh = format_GC.Attach.fromMesh(m, global_matrix, materials)
            if mesh is not None:
                mesh.write(fileW, labels, meshDict)

    # writing model data
    if export_format == 'SA2' and isArmature:  # writing an armature
        modelPtr = objects[0].writeArmature(fileW,
                                            global_matrix,
                                            materials,
                                            labels)
    else:
        ModelData.updateMeshPointer(objects, meshDict)
        modelPtr = ModelData.writeObjectList(objects, fileW, labels)

    labelsAddress = fileW.tell()
    fileW.seek(8, 0)  # go to the location of the model properties addrees
    fileW.wUInt(modelPtr)  # and write the address
    fileW.wUInt(labelsAddress)
    fileW.seek(0, 2)  # then return back to the end

    if DO:
        print(" == Model file info ==")
        print("  model pointer: ", hex8(modelPtr))
        print("  labels pointer:", hex8(labelsAddress))
        print(" - - - -\n")
        print(" == Model hierarchy == \n")
        for o in objects:
            marker = " "
            for r in range(o.hierarchyDepth):
                marker += "--"
            if len(marker) > 1:
                print(marker, o.name)
            else:
                print("", o.name)
        print(" - - - -\n")

    # writing chunk data
    common.writeMethaData(fileW, labels, context.scene)

    fileW.close()
