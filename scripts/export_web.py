"""Export a browser-sized glTF of arakurayama_sunrise.blend for the Three.js showcase.

The Cycles scene carries ~34M instanced polygons, almost all of them blossoms.
This script derives a web asset from the same .blend without touching it:

* blossom meshes are subsampled per flower (whole flowers kept or dropped, never
  half petals) into a near and a far LOD, assigned by distance from the stairs;
* evergreen needle sprays are thinned by half;
* procedural node materials are flattened to Principled base colour / roughness /
  metallic so the exporter writes real PBR values instead of white;
* modifiers are applied and static collections are joined per collection so the
  file has dozens of draw calls instead of three thousand;
* sakura trees stay as shared meshes so the exporter can write
  EXT_mesh_gpu_instancing;
* drifting petals, lights, sun, sky and cameras are left out - the website
  rebuilds them in Three.js where they can be interactive.

Run:  .venv/bin/python scripts/export_web.py  [--out web/assets/arakurayama.glb]
"""
import argparse, json, os, sys, time
import bpy, bmesh

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument('--blend', default=os.path.join(ROOT, 'arakurayama_sunrise.blend'))
ap.add_argument('--out', default=os.path.join(ROOT, 'web', 'assets', 'arakurayama.glb'))
ap.add_argument('--near-keep', type=float, default=.34, help='fraction of flowers kept on near trees')
ap.add_argument('--far-keep', type=float, default=.11, help='fraction of flowers kept on distant trees')
ap.add_argument('--far-y', type=float, default=112, help='trees beyond this Y use the far LOD')
ap.add_argument('--needle-keep', type=float, default=.5)
args = ap.parse_args(argv)

FACES_PER_FLOWER = 5 * 8 + 1   # five notched petals (8 tris) + hexagonal centre, see build_scene.flower_geometry
STATIC = ['01 • Hillside and stone approach', '02 • Vermilion railings',
          '03 • Chureito / five roof tiers', '04 • Dawn lanterns',
          '06 • Evergreen hillside', '07 • Fallen petals and undergrowth',
          '08 • Fujiyoshida valley', '09 • Fuji / radial gullies and spring snow']
SAKURA = '05 • Sakura grove / linked botanical meshes'
DROP = ['10 • Drifting petals / deterministic animation', '11 • Sunrise and atmosphere',
        '12 • Cameras / twelve second reveal']

t0 = time.time()
bpy.ops.wm.open_mainfile(filepath=args.blend)
scene = bpy.context.scene
scene.frame_set(1)


def log(*a):
    print(f'[export_web {time.time()-t0:6.1f}s]', *a, flush=True)


def hash01(i):
    """Deterministic 0..1 per flower id; independent of Python's hash seed."""
    x = (i * 2654435761) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 0x5bd1e995) & 0xFFFFFFFF
    return (x & 0xFFFF) / 65535.0


# ---------------------------------------------------------------- materials
def flatten_materials():
    """Replace procedural colour graphs with the authored colour so glTF gets real values."""
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        nt = m.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        out = next((n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if not bsdf or not out:
            continue
        base = bsdf.inputs['Base Color']
        if base.is_linked:
            for l in list(base.links):
                nt.links.remove(l)
        base.default_value = m.diffuse_color   # build_scene stores the authored colour here
        if m.name.startswith('Fuji'):
            base.default_value = (1, 1, 1, 1)  # rock/snow mix is baked to vertex colour, see bake_fuji_snow
        normal = bsdf.inputs['Normal']
        for l in list(normal.links):
            nt.links.remove(l)
        # Petal materials go through a translucent mix; give the exporter the Principled node directly.
        surf = out.inputs['Surface']
        for l in list(surf.links):
            nt.links.remove(l)
        nt.links.new(bsdf.outputs['BSDF'], surf)
        if m.name.startswith('Petal'):
            bsdf.inputs['Roughness'].default_value = .6
        m.use_backface_culling = False


# ------------------------------------------------------------ blossom LODs
def subsample_faces(src, keep, name, per=1, salt=0):
    """Copy mesh `src`, keeping whole groups of `per` consecutive faces with probability `keep`."""
    me = src.copy(); me.name = name
    bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
    doomed = [f for f in bm.faces if hash01(f.index // per + salt) > keep]
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    bm.to_mesh(me); bm.free()
    return me


def build_sakura_lods():
    col = bpy.data.collections[SAKURA]
    libs = {}
    for o in list(col.objects):
        if 'blossoms' not in o.name:
            continue
        src = o.data
        if src.name not in libs:
            libs[src.name] = (subsample_faces(src, args.near_keep, src.name + ' • web near', FACES_PER_FLOWER, 11),
                              subsample_faces(src, args.far_keep, src.name + ' • web far', FACES_PER_FLOWER, 23))
        near, far = libs[src.name]
        o.data = far if o.location.y > args.far_y else near
    for o in col.objects:   # geometry-nodes sway is rebuilt in the browser shader
        for md in list(o.modifiers):
            o.modifiers.remove(md)
    for o in col.objects:
        o['lod'] = 'far' if o.location.y > args.far_y else 'near'
    for name, (near, far) in libs.items():
        log(f'{name}: {len(bpy.data.meshes[name].polygons)} → near {len(near.polygons)} / far {len(far.polygons)} faces')


def bake_fuji_snow():
    """The Cycles shader mixes rock and snow by the `snow_coverage` point attribute;
    glTF has no attribute nodes, so bake the same mix into COLOR_0."""
    import numpy as np
    me = bpy.data.objects['Mount Fuji sculpted massif'].data
    n = len(me.vertices)
    cov = np.zeros(n, dtype=np.float32)
    me.attributes['snow_coverage'].data.foreach_get('value', cov)   # read before adding a layer: it invalidates handles
    rock, snow = np.array([.13, .185, .235]), np.array([.79, .84, .87])
    rgba = np.ones((n, 4), dtype=np.float32)
    rgba[:, :3] = rock + (snow - rock) * cov[:, None]
    col = me.color_attributes.new('snow_mix', 'FLOAT_COLOR', 'POINT')
    col.data.foreach_set('color', rgba.ravel())
    me.color_attributes.active_color = me.color_attributes['snow_mix']
    log(f'baked Fuji snow coverage into vertex colour ({(cov > 0).mean():.0%} of vertices carry snow)')


def thin_evergreens():
    for o in bpy.data.collections['06 • Evergreen hillside'].objects:
        if o.name.startswith('Fine evergreen branch sprays'):
            o.data = subsample_faces(o.data, args.needle_keep, o.data.name + ' • web', 4, 5)


# ------------------------------------------------------ apply + join statics
def apply_and_join(col_name):
    col = bpy.data.collections[col_name]
    objs = [o for o in col.objects if o.type in ('MESH', 'CURVE')]
    if not objs:
        return None
    bpy.ops.object.select_all(action='DESELECT')
    dg = bpy.context.evaluated_depsgraph_get()
    converted = []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
        new = bpy.data.objects.new(o.name + ' • baked', me)
        new.matrix_world = o.matrix_world.copy()
        col.objects.link(new)
        converted.append(new)
    for o in objs:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in converted:
        o.select_set(True)
    bpy.context.view_layer.objects.active = converted[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = col_name.split('• ', 1)[-1].strip()
    bpy.ops.object.select_all(action='DESELECT')
    return joined


def main():
    for name in DROP:
        for o in list(bpy.data.collections[name].objects):
            bpy.data.objects.remove(o, do_unlink=True)
    for o in list(bpy.data.objects):
        if o.type in ('LIGHT', 'CAMERA', 'EMPTY'):
            bpy.data.objects.remove(o, do_unlink=True)
    flatten_materials()
    build_sakura_lods()
    bake_fuji_snow()
    thin_evergreens()
    summary = {}
    for name in STATIC:
        j = apply_and_join(name)
        if j:
            summary[j.name] = len(j.data.polygons)
            log(f'joined {name}: {summary[j.name]} faces')
    tris = 0
    for o in bpy.data.objects:
        if o.type == 'MESH':
            tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
    log(f'total triangles drawn per frame ≈ {tris:,}')

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=args.out, export_format='GLB', export_apply=True,
        export_animations=False, export_cameras=False, export_lights=False,
        export_materials='EXPORT', export_image_format='NONE',
        export_gpu_instances=True, export_extras=True,
        export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
        export_draco_position_quantization=14, export_draco_normal_quantization=10,
        export_yup=True, export_skins=False, export_morph=False, export_texcoords=False,
        export_vertex_color='ACTIVE', export_active_vertex_color_when_no_material=False,
    )
    size = os.path.getsize(args.out)
    log(f'wrote {args.out} ({size/1e6:.1f} MB)')
    manifest = {
        'source': os.path.basename(args.blend), 'output': os.path.relpath(args.out, ROOT),
        'bytes': size, 'triangles_per_frame': tris,
        'near_flower_keep': args.near_keep, 'far_flower_keep': args.far_keep, 'far_y': args.far_y,
        'needle_keep': args.needle_keep, 'joined_meshes': summary, 'draco': True,
        'blender': bpy.app.version_string,
    }
    with open(os.path.join(os.path.dirname(args.out), 'export_manifest.json'), 'w') as f:
        json.dump(manifest, f, indent=2)


main()
