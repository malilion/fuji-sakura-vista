"""Verify the saved deliverable in headless Blender, including camera framing."""
import json
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'arakurayama_sunrise.blend'))
s=bpy.context.scene
assert s.render.engine=='CYCLES'
assert s.camera is not None
assert (s.frame_start,s.frame_end,s.render.fps)==(1,288,24)
roofs=[o for o in s.objects if o.name.startswith('Roof ') and '/ swept copper' in o.name and o.type=='MESH']
assert len(roofs)==5, f'Expected five roof surfaces, got {len(roofs)}'
assert len([o for o in s.objects if o.name.startswith('Drifting petal')])==90
assert bpy.data.node_groups.get('Sakura • gentle coherent branch sway')
assert all(not image.filepath for image in bpy.data.images if image.source=='FILE'), 'Unexpected external image dependency'
frames={}
for frame in (1,144,288):
    s.frame_set(frame)
    bpy.context.view_layer.update()
    points={
        'pagoda_finial':Vector((12,35,20.33)),
        'pagoda_center':Vector((12,35,8)),
        'fuji_peak':Vector((-180,1550,286)),
    }
    projections={name:tuple(round(c,4) for c in world_to_camera_view(s,s.camera,pt)) for name,pt in points.items()}
    frames[frame]={'camera_position':list(s.camera.location),'projection':projections}
    for name,(x,y,z) in projections.items():
        assert 0<x<1 and 0<y<1 and z>0, f'{name} outside frame {frame}: {(x,y,z)}'
petal=bpy.data.objects['Drifting petal 000']
s.frame_set(1); first=petal.location.copy()
s.frame_set(288); last=petal.location.copy()
assert (last-first).length>1, 'Petal animation did not move'
report={'passed':True,'blender':bpy.app.version_string,'five_roof_tiers':len(roofs),
        'objects':len(s.objects),'external_images':0,'camera_checks':frames,
        'petal_travel_m':round((last-first).length,3)}
(ROOT/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
