import bpy
import os
import mathutils
from . import fileHelper, file_MDL, enums, common, format_BASIC, format_CHUNK, format_GC
from .common import ModelData
from typing import Dict, List

DO = True  # Debug out

def read(context: bpy.types.Context, filepath: str, noDoubleVerts: bool, console_debug_output: bool):

    global DO
    DO = console_debug_output

    fileR = fileHelper.FileReader(filepath)

    if fileR.filepath is None:
        print("no valid filepath")
        return {'CANCELLED'}
    else: 
        fileR = open(filepath, "r")
        amld = (line.strip().split(',') for line in fileR)

    if DO:
        print(" == Starting AMLD file reading ==")
        print("  File:", filepath)
        print("  - - - - - -\n")
    
    for entry in amld:
        values = []
        for var in entry:
            var = var.replace('{', ' ')
            var = var.replace('}', ' ')
            var = var.strip()
            values.append(var)
        pos = [ float(values[1]), float(values[2]), float(values[3])]
        rot = [ float(values[4]), float(values[5]), float(values[6])]
        scl = [ float(values[7]), float(values[8]), float(values[9])]
        if DO:
            print(((((entry[0].split(" "))[2]).split("."))[0]) + ".sa2mdl")
        entry[0] = os.path.dirname(filepath) + "\\" + (((((entry[0].split(" "))[2]).split("."))[0]) + ".sa2mdl")
        file_MDL.readWithValues( context, entry[0], noDoubleVerts, console_debug_output, pos, rot, scl)
        