"""Encode and verify the 96-frame, 8 fps headless motion preview."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'renders'/'animatic'
expected=[folder/f'frame_{frame:04d}.png' for frame in range(1,289,3)]
actual=sorted(folder.glob('frame_*.png'))
if actual!=expected:
    missing=[p.name for p in expected if not p.exists()]
    raise SystemExit(f'Expected all 96 preview frames. Missing: {missing}; actual count: {len(actual)}')
ffmpeg=shutil.which('ffmpeg')
ffprobe=shutil.which('ffprobe')
if not ffmpeg or not ffprobe:
    raise SystemExit('ffmpeg and ffprobe are required to encode and verify the preview.')
output=ROOT/'renders'/'first_light_preview.mp4'
subprocess.run([ffmpeg,'-y','-hide_banner','-loglevel','error','-framerate','8',
                '-pattern_type','glob','-i',str(folder/'frame_*.png'),
                '-c:v','libx264','-crf','18','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(output)],check=True)
probe=subprocess.run([ffprobe,'-v','error','-show_entries',
                      'stream=width,height,avg_frame_rate,nb_frames:format=duration',
                      '-of','json',str(output)],check=True,capture_output=True,text=True)
info=json.loads(probe.stdout)
stream=info['streams'][0]
assert (stream['width'],stream['height'])==(640,360)
assert stream['avg_frame_rate']=='8/1'
assert int(stream['nb_frames'])==96
assert abs(float(info['format']['duration'])-12)<.05
info['source_timeline_fps']=24
info['sampling']='Every third Blender frame; motion preview, not the 24 fps master.'
(ROOT/'renders'/'preview_video_manifest.json').write_text(json.dumps(info,indent=2)+'\n')
print(json.dumps(info,indent=2))
print(output)
