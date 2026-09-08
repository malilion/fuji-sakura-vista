"""Render an existing scene without opening Blender's UI.

Examples:
  .venv/bin/python scripts/render_scene.py --preset preview --frames 1,144,288
  .venv/bin/python scripts/render_scene.py --preset still --frames 288
  .venv/bin/python scripts/render_scene.py --preset animation --start 1 --end 288
  blender -b arakurayama_sunrise.blend -P scripts/render_scene.py -- --preset still
"""
import argparse
import json
import sys
import time
from pathlib import Path

import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from render_utils import render_log

ROOT = Path(__file__).resolve().parents[1]


def main():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    p=argparse.ArgumentParser()
    p.add_argument('--preset',choices=['preview','still','animation','animatic'],default='preview')
    p.add_argument('--frames',default=None,help='Comma-separated frame numbers')
    p.add_argument('--start',type=int,default=1)
    p.add_argument('--end',type=int,default=288)
    p.add_argument('--step',type=int,default=1)
    p.add_argument('--samples',type=int)
    p.add_argument('--width',type=int)
    p.add_argument('--device',choices=['CPU','GPU'],default=None)
    p.add_argument('--exr',action='store_true')
    a=p.parse_args(argv)
    if a.start>a.end or a.step<1:
        p.error('start must be <= end, and step must be >= 1')
    path=ROOT/'arakurayama_sunrise.blend'
    if not path.exists():
        p.error('Build the scene first: .venv/bin/python scripts/build_scene.py --render none')
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene=bpy.context.scene
    config={
        'preview':(960,32,.035,False),
        'still':(2560,192,.012,True),
        'animation':(1920,96,.02,True),
        'animatic':(640,12,.09,False),
    }
    width,samples,threshold,blur=config[a.preset]
    scene.render.resolution_x=a.width or width
    scene.render.resolution_y=round(scene.render.resolution_x*9/16)
    scene.render.resolution_percentage=100
    scene.cycles.samples=a.samples or samples
    scene.cycles.adaptive_threshold=threshold
    scene.render.use_motion_blur=blur
    scene.render.use_persistent_data=True
    if a.device:
        scene.cycles.device=a.device
    else:
        # Device preferences are external to .blend; probe in each new process.
        pref=bpy.context.preferences.addons['cycles'].preferences
        try:
            pref.compute_device_type='METAL'; pref.get_devices()
            gpu=[d for d in pref.devices if d.type=='METAL']
            for d in pref.devices: d.use=d.type=='METAL'
            scene.cycles.device='GPU' if gpu else 'CPU'
        except (TypeError,RuntimeError):
            scene.cycles.device='CPU'
    frames=([int(f) for f in a.frames.split(',')] if a.frames else
            list(range(a.start,a.end+1,a.step)) if a.preset in ['animation','animatic'] else [288])
    out=ROOT/'renders'/('frames' if a.preset=='animation' else a.preset)
    out.mkdir(parents=True,exist_ok=True)
    if a.exr:
        scene.render.image_settings.file_format='OPEN_EXR_MULTILAYER'
        scene.render.image_settings.color_depth='32'
        scene.render.image_settings.exr_codec='ZIP'
    else:
        scene.render.image_settings.file_format='PNG'
        scene.render.image_settings.color_mode='RGB'
        scene.render.image_settings.color_depth='8'
    durations=[]
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath=str(out/(f'frame_{frame:04d}'+('.exr' if a.exr else '.png')))
        started=time.time()
        with render_log(ROOT/'logs'/f'{a.preset}_{frame:04d}.log'):
            bpy.ops.render.render(write_still=True)
        duration=time.time()-started
        durations.append({'frame':frame,'seconds':round(duration,2),'path':scene.render.filepath})
        print('FRAME COMPLETE',json.dumps(durations[-1]),flush=True)
        (out/'render_log.json').write_text(json.dumps(durations,indent=2)+'\n')


if __name__=='__main__':
    main()
