"""Arakurayama / First Light — deterministic, entirely headless Blender scene.

Run with .venv/bin/python scripts/build_scene.py --render preview
or blender --background --python scripts/build_scene.py -- --render preview.
All geometry and shaders are authored here; no network assets are required.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector, Matrix, Euler
from mathutils import noise
sys.path.insert(0,str(Path(__file__).resolve().parent))
from render_utils import render_log

ROOT = Path(__file__).resolve().parents[1]
RNG = random.Random(829)
TAU = math.tau
COL = None
M = {}


def collection(name):
    global COL
    COL = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(COL)
    return COL


def mesh(name, verts, faces, mat, smooth=False):
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    COL.objects.link(obj)
    if mat:
        data.materials.append(mat)
    if smooth:
        for p in data.polygons:
            p.use_smooth = True
    return obj


def box(name, loc, size, mat, bevel=0):
    x, y, z = [v / 2 for v in size]
    obj = mesh(name, [(-x,-y,-z),(x,-y,-z),(x,y,-z),(-x,y,-z),
                      (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)],
               [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], mat)
    obj.location = loc
    if bevel:
        mod = obj.modifiers.new('Light-catching edges', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
    return obj


def rod(name, a, b, radius, mat, sides=8, radius2=None):
    a, b = Vector(a), Vector(b)
    q = (b-a).to_track_quat('Z','Y')
    r2 = radius if radius2 is None else radius2
    verts = [a + q @ Vector((math.cos(t*TAU/sides)*r,math.sin(t*TAU/sides)*r,z))
             for z,r in [(0,radius),((b-a).length,r2)] for t in range(sides)]
    faces = [(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
    faces += [tuple(reversed(range(sides))),tuple(range(sides,sides*2))]
    return mesh(name, verts, faces, mat, True)


def curve(name, points, radius, mat):
    data = bpy.data.curves.new(name, 'CURVE')
    data.dimensions = '3D'
    data.resolution_u = 8
    data.bevel_depth = radius
    data.bevel_resolution = 2
    spline = data.splines.new('POLY')
    spline.points.add(len(points)-1)
    for p,co in zip(spline.points,points):
        p.co = (*co[:3],1)
        if len(co)>3:
            p.radius=co[3]
    obj=bpy.data.objects.new(name,data)
    COL.objects.link(obj)
    data.materials.append(mat)
    return obj


def material(name, color, rough=.6, metallic=0, noise_scale=0, bump=.0):
    m=bpy.data.materials.new(name)
    m.diffuse_color=(*color,1)
    m.use_nodes=True
    n=m.node_tree.nodes
    l=m.node_tree.links
    bs=n.get('Principled BSDF')
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough
    bs.inputs['Metallic'].default_value=metallic
    if noise_scale:
        tex=n.new('ShaderNodeTexNoise')
        tex.inputs['Scale'].default_value=noise_scale
        tex.inputs['Detail'].default_value=3
        ramp=n.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position=.18
        ramp.color_ramp.elements[0].color=(*(c*.57 for c in color),1)
        ramp.color_ramp.elements[1].position=.82
        ramp.color_ramp.elements[1].color=(*(min(c*1.24,1) for c in color),1)
        l.new(tex.outputs['Fac'],ramp.inputs[0])
        l.new(ramp.outputs['Color'],bs.inputs['Base Color'])
        if bump:
            b=n.new('ShaderNodeBump')
            b.inputs['Strength'].default_value=.35
            b.inputs['Distance'].default_value=bump
            l.new(tex.outputs['Fac'],b.inputs['Height'])
            l.new(b.outputs['Normal'],bs.inputs['Normal'])
    M[name]=m
    return m


def materials():
    material('Vermilion lacquer',(.48,.037,.019),.38,noise_scale=18,bump=.008)
    material('Aged vermilion',(.29,.029,.013),.5,noise_scale=9,bump=.013)
    material('Warm plaster',(.69,.61,.45),.76,noise_scale=45,bump=.008)
    material('Oxidized roof',(.067,.099,.091),.42,.45,noise_scale=25,bump=.012)
    material('Roof seam',(.10,.135,.121),.45,.5)
    material('Bronze',(.12,.115,.067),.4,.72)
    material('Stone',(.24,.255,.255),.86,noise_scale=30,bump=.065)
    material('Stone light',(.37,.35,.31),.83,noise_scale=32,bump=.045)
    material('Dark stone',(.13,.155,.147),.88,noise_scale=24,bump=.06)
    # Foot-polished centre treads and lichen-stained wall stones break up the uniform grey.
    material('Stone worn',(.20,.205,.195),.80,noise_scale=26,bump=.04)
    material('Lichen stone',(.20,.235,.185),.90,noise_scale=19,bump=.07)
    # Large-scale verdigris blooms over the copper roofs.
    m=M['Oxidized roof']; n=m.node_tree.nodes; l=m.node_tree.links
    bs=n.get('Principled BSDF')
    patch=n.new('ShaderNodeTexNoise'); patch.inputs['Scale'].default_value=1.6; patch.inputs['Detail'].default_value=5; patch.inputs['Roughness'].default_value=.62
    vramp=n.new('ShaderNodeValToRGB')
    vramp.color_ramp.elements[0].position=.47; vramp.color_ramp.elements[0].color=(0,0,0,1)
    vramp.color_ramp.elements[1].position=.60; vramp.color_ramp.elements[1].color=(1,1,1,1)
    l.new(patch.outputs['Fac'],vramp.inputs[0])
    base_link=[lk for lk in l if lk.to_socket==bs.inputs['Base Color']][0]
    base_out=base_link.from_socket
    mix=n.new('ShaderNodeMixRGB'); mix.inputs[2].default_value=(.15,.33,.29,1)
    l.new(vramp.outputs['Color'],mix.inputs[0]); l.new(base_out,mix.inputs[1]); l.new(mix.outputs[0],bs.inputs['Base Color'])
    material('Soil',(.084,.095,.051),.97,noise_scale=9,bump=.09)
    material('Moss',(.12,.16,.036),.96,noise_scale=15,bump=.05)
    material('Bark',(.09,.047,.026),.88,noise_scale=17,bump=.08)
    bark=M['Bark']; n=bark.node_tree.nodes; l=bark.node_tree.links
    geo=n.new('ShaderNodeNewGeometry')
    tex=n.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value=7
    tex.inputs['Detail'].default_value=4
    l.new(geo.outputs['Position'],tex.inputs['Vector'])
    wave=n.new('ShaderNodeTexWave'); wave.bands_direction='Z'
    wave.inputs['Scale'].default_value=9
    wave.inputs['Distortion'].default_value=5
    wave.inputs['Detail'].default_value=4
    l.new(geo.outputs['Position'],wave.inputs['Vector'])
    mix=n.new('ShaderNodeMixRGB'); mix.blend_type='MULTIPLY'; mix.inputs[0].default_value=.65
    l.new(tex.outputs['Fac'],mix.inputs[1]); l.new(wave.outputs['Color'],mix.inputs[2])
    ramp=n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color=(.028,.02,.015,1)
    ramp.color_ramp.elements[1].color=(.21,.13,.073,1)
    l.new(mix.outputs[0],ramp.inputs[0]); l.new(ramp.outputs[0],n.get('Principled BSDF').inputs['Base Color'])
    bump=n.new('ShaderNodeBump'); bump.inputs['Distance'].default_value=.07; bump.inputs['Strength'].default_value=.6
    l.new(mix.outputs[0],bump.inputs['Height']); l.new(bump.outputs[0],n.get('Principled BSDF').inputs['Normal'])
    material('Twigs',(.07,.038,.025),.89)
    material('Lantern timber',(.105,.073,.038),.62,noise_scale=16,bump=.022)
    material('Needles',(.035,.07,.043),.9,noise_scale=6,bump=.06)
    for i,c in enumerate([(.83,.52,.51),(.96,.73,.68),(.95,.83,.75),(.68,.32,.37)]):
        m=material(f'Petal {i}',c,.53)
        bs=m.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Subsurface Weight'].default_value=.06
        bs.inputs['Subsurface Radius'].default_value=(1,.35,.22)
        n=m.node_tree.nodes
        tr=n.new('ShaderNodeBsdfTranslucent')
        tr.inputs[0].default_value=(*c,1)
        mix=n.new('ShaderNodeMixShader')
        mix.inputs[0].default_value=.22
        m.node_tree.links.new(bs.outputs[0],mix.inputs[1])
        m.node_tree.links.new(tr.outputs[0],mix.inputs[2])
        m.node_tree.links.new(mix.outputs[0],n.get('Material Output').inputs['Surface'])
    material('Stamen',(.69,.32,.065),.65)
    m=material('Washi glow',(1,.64,.28),.65)
    bs=m.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Emission Color'].default_value=(1,.42,.085,1)
    bs.inputs['Emission Strength'].default_value=2.5
    for i,c in enumerate([(.35,.32,.28),(.55,.48,.38),(.45,.47,.43),(.26,.31,.34),(.61,.58,.50)]):
        material(f'City wall {i}',c,.8)
    for i,c in enumerate([(.14,.18,.20),(.23,.23,.22),(.29,.19,.14),(.20,.25,.24)]):
        material(f'City roof {i}',c,.72)
    material('Valley',(.17,.21,.19),.95,noise_scale=2,bump=.06)
    material('Road',(.25,.27,.26),.93)
    material('Mountain rock',(.13,.185,.235),.92,noise_scale=7,bump=.07)
    material('Snow',(.79,.84,.87),.85,noise_scale=80,bump=.035)


def ground_z(x,y):
    z=max(-13,8.2-.255*(y+10))
    if y>130:
        z=-13-min((y-130)/160,1)*12.5
    return z+.38*math.sin(x*.19)*math.sin(y*.13)


def terrain():
    collection('01 • Hillside and stone approach')
    verts=[]
    faces=[]
    nx,ny=145,190
    for j in range(ny):
        y=-20+j*1.7
        for i in range(nx):
            x=(i-(nx-1)/2)*2.2
            z=ground_z(x,y)
            if abs(x)<3.3 and y<30:
                z-=.5
            verts.append((x,y,z))
    for j in range(ny-1):
        for i in range(nx-1):
            a=j*nx+i
            faces.append((a,a+1,a+nx+1,a+nx))
    mesh('Sculpted hillside',verts,faces,M['Soil'],True)
    # Comfortable steps, each assembled from offset blocks rather than a solid ramp.
    for step in range(66):
        y=-11+step*.61
        z=8.45-step*.155
        for slab in range(5):
            x=(slab-2)*1.15+RNG.uniform(-.018,.018)
            # Centre slabs are polished by feet; edge slabs settle and chip unevenly.
            r=RNG.random()
            if slab==2 and r<.45: mat=M['Stone worn']
            elif r<.30: mat=M['Stone light']
            elif r>.93: mat=M['Lichen stone']
            else: mat=M['Stone']
            settle=RNG.uniform(-.014,.008)*(1+abs(slab-2)*.6)
            tread=box(f'Tread {step:02d} slab {slab}',(x,y,z-.15+settle),(1.14+RNG.uniform(-.02,.01),.606,.30),
                mat,RNG.uniform(.012,.048))
            tread.rotation_euler=(RNG.uniform(-.010,.010),RNG.uniform(-.014,.014),RNG.uniform(-.006,.006))
            if RNG.random()<(.20 if abs(slab-2)==2 else .06):
                box('Joint moss',(x+RNG.choice([-1,1])*.57,y+RNG.uniform(-.2,.2),z+.003),(.06,RNG.uniform(.12,.34),.014),M['Moss'],.004)
    # Landings connect the downhill approach to the tower terrace.
    box('Lower landing',(0,31,-1.8),(6,5,.5),M['Stone'],.05)
    box('Pagoda terrace',(12,35,-1.7),(15,16,1.0),M['Stone'],.09)
    box('Connecting path',(5,32,-1.48),(10,3,.35),M['Stone light'],.045)
    for side in [-1,1]:
        for j in range(52):
            y=-11+j*.81
            z=8.45-(y+11)*.155/.61
            r=RNG.random()
            rockmat=M['Lichen stone'] if r<.22 else M['Stone'] if r<.34 else M['Dark stone']
            rock=box('Retaining wall stone',(side*(3.22+RNG.uniform(-.07,.09)),y,z-.20+RNG.uniform(-.05,.05)),
                     (RNG.uniform(.42,.95),RNG.uniform(.55,1.0),RNG.uniform(.45,.95)),rockmat,RNG.uniform(.06,.16))
            rock.rotation_euler=(RNG.uniform(-.10,.10),RNG.uniform(-.13,.13),RNG.uniform(-.14,.14))
            if RNG.random()<.62:
                box('Moss ledge',(side*(3.24+RNG.uniform(-.06,.06)),y+RNG.uniform(-.15,.15),z+.22+RNG.uniform(-.04,.04)),
                    (RNG.uniform(.28,.52),RNG.uniform(.30,.60),.025),M['Moss'],.015)


def railings():
    collection('02 • Vermilion railings')
    for side in [-1,1]:
        pts=[]
        for i in range(19):
            y=-10+i*2.13
            z=8.45-(y+11)*.155/.61
            x=side*3.15
            pts.append((x,y,z))
            box('Railing post',(x,y,z+.57),(.16,.16,1.18),M['Vermilion lacquer'],.017)
            box('Post dark cap',(x,y,z+1.19),(.235,.235,.10),M['Bronze'],.027)
            box('Stone post shoe',(x,y,z+.07),(.25,.25,.17),M['Stone'],.025)
        for a,b in zip(pts,pts[1:]):
            for h,r in [(1.01,.085),(.49,.052)]:
                rod('Continuous slope rail',(a[0],a[1],a[2]+h),(b[0],b[1],b[2]+h),r,M['Vermilion lacquer'],4)


def roof(name, center, half, z, rise, mat, seams=True):
    cx,cy=center
    # Four trapezoidal hip surfaces; broad sweep and uplift only at the corners.
    verts=[]
    faces=[]
    steps_u,steps_v=28,14
    def point(side,u,t,offset=0):
        extent=half*(.20+.80*t)
        x=u*extent
        y=extent
        sweep=min(1,half/4.5)
        height=z+rise*(1-t)**1.7 + .16*sweep*t**5 + .24*sweep*abs(u)**7*t**5
        angle=side*math.pi/2
        return (cx+x*math.cos(angle)-y*math.sin(angle),cy+x*math.sin(angle)+y*math.cos(angle),height+offset)
    for side in range(4):
        base=len(verts)
        for j in range(steps_v+1):
            for i in range(steps_u+1):
                verts.append(point(side,-1+2*i/steps_u,j/steps_v))
        for j in range(steps_v):
            for i in range(steps_u):
                a=base+j*(steps_u+1)+i
                faces.append((a,a+1,a+steps_u+2,a+steps_u+1))
        curve(name+' red eave',[point(side,-1+2*i/32,1,-.09) for i in range(33)],.10,M['Aged vermilion'])
        curve(name+' edge lip',[point(side,-1+2*i/32,1,.025) for i in range(33)],.038,M['Roof seam'])
        # Rolled copper hip ridge down each corner, ending in a small upturned ridge cap.
        if seams:
            hip=[point(side,1,i/16,.055) for i in range(17)]
            curve(name+' hip ridge',hip,.065,M['Roof seam'])
            cap=box('Hip ridge cap',hip[-1],(.30,.30,.16),M['Bronze'],.03)
            cap.rotation_euler[2]=side*math.pi/2+math.pi/4
        if seams:
            for row in range(1,14):
                t=row/14
                curve(name+' horizontal standing seam',[point(side,-1+2*i/28,t,.018) for i in range(29)],.009,M['Roof seam'])
            for column in range(19):
                u=-.97+1.94*column/18
                curve(name+' radial seam',[point(side,u,i/14,.020) for i in range(15)],.007,M['Roof seam'])
    o=mesh(name,verts,faces,mat,True)
    solid=o.modifiers.new('Copper roof thickness','SOLIDIFY')
    solid.thickness=.045
    return o


def pagoda():
    collection('03 • Chureito / five roof tiers')
    cx,cy=12,35
    red=M['Vermilion lacquer']
    white=M['Warm plaster']
    base=-1.1
    box('Pagoda plinth',(cx,cy,base),(10.2,10.2,.5),M['Stone light'],.06)
    for tier in range(5):
        level=base+.25+tier*3.35
        width=6.1-tier*.50
        h=2.4-tier*.06
        box(f'Tier {tier+1} plaster core',(cx,cy,level+h/2),(width,width,h),white,.025)
        for side in [-1,1]:
            for axis in [0,1]:
                for p in [-.5,0,.5]:
                    loc=(cx+p*width,cy+side*(width/2+.035),level+h/2) if axis==0 else (cx+side*(width/2+.035),cy+p*width,level+h/2)
                    box('Red structural upright',loc,(.18,.18,h+.16),red,.018)
                for elev,thick in [(.10,.14),(.85,.11),(h-.12,.20)]:
                    loc=(cx,cy+side*(width/2+.08),level+elev) if axis==0 else (cx+side*(width/2+.08),cy,level+elev)
                    size=(width+.3,.18,thick) if axis==0 else (.18,width+.3,thick)
                    box('Horizontal vermilion band',loc,size,red,.015)
        # Dark lattice windows in each bay between the uprights, above the balcony rail.
        for side in [-1,1]:
            for axis in [0,1]:
                for p in [-.25,.25]:
                    w=width*.30
                    loc=(cx+p*width,cy+side*(width/2+.02),level+1.45) if axis==0 else (cx+side*(width/2+.02),cy+p*width,level+1.45)
                    size=(w,.05,.72) if axis==0 else (.05,w,.72)
                    box('Lattice window recess',loc,size,M['Lantern timber'],.006)
                    for k in range(5):
                        q=-w/2+w*(k+.5)/5
                        bl=(cx+p*width+q,cy+side*(width/2+.055),level+1.45) if axis==0 else (cx+side*(width/2+.055),cy+p*width+q,level+1.45)
                        bs=(.035,.04,.70) if axis==0 else (.04,.035,.70)
                        box('Lattice bar',bl,bs,M['Bronze'],.003)
        deck=width+1.1
        box('Balcony deck',(cx,cy,level+.22),(deck,deck,.16),M['Aged vermilion'],.035)
        for side in [-1,1]:
            for axis in [0,1]:
                for t in range(9):
                    p=-deck/2+t*deck/8
                    x,y=(cx+p,cy+side*deck/2) if axis==0 else (cx+side*deck/2,cy+p)
                    box('Balcony baluster',(x,y,level+.63),(.085,.085,.72),red,.009)
                for elev in [.45,.88]:
                    loc=(cx,cy+side*deck/2,level+elev) if axis==0 else (cx+side*deck/2,cy,level+elev)
                    size=(deck+.18,.105,.105) if axis==0 else (.105,deck+.18,.105)
                    box('Balcony rail',loc,size,red,.01)
        half=5.3-tier*.42
        rz=level+h+.04
        roof(f'Roof {tier+1} / swept copper',(cx,cy),half,rz,.94,M['Oxidized roof'])
        # Shadowed bracket rhythm underneath all four eaves.
        for side in range(4):
            angle=side*math.pi/2
            for j in range(17):
                u=-half+.32+j*(2*half-.64)/16
                x=cx+u*math.cos(angle)-(half-.55)*math.sin(angle)
                y=cy+u*math.sin(angle)+(half-.55)*math.cos(angle)
                beam=box('Eave rafter',(x,y,rz-.12),(.09,1.18,.12),red,.007)
                beam.rotation_euler[2]=angle
                x2=cx+u*.78*math.cos(angle)-(width/2+.28)*math.sin(angle)
                y2=cy+u*.78*math.sin(angle)+(width/2+.28)*math.cos(angle)
                b=box('Ivory bracket end',(x2,y2,rz-.30),(.13,.32,.17),white,.012)
                b.rotation_euler[2]=angle
            # Stepped bracket clusters above each upright carry the eave visually.
            for p in [-.5,0,.5]:
                for k,(dz,w) in enumerate([(-.62,.30),(-.46,.46),(-.30,.64)]):
                    x3=cx+p*width*math.cos(angle)-(width/2+.16+k*.10)*math.sin(angle)
                    y3=cy+p*width*math.sin(angle)+(width/2+.16+k*.10)*math.cos(angle)
                    c=box('Bracket cluster',(x3,y3,rz+dz),(w,.22+k*.18,.13),red if k%2 else white,.008)
                    c.rotation_euler[2]=angle
    # Small entrance gives the lower floor a human scale.
    box('Shadow within entry',(cx,cy-3.13,base+1.25),(1.45,.055,1.95),M['Lantern timber'],.012)
    for x in [cx-.57,cx,cx+.57]:
        box('Entry door divisions',(x,cy-3.18,base+1.27),(.045,.04,1.86),M['Bronze'],.004)
    top=base+.25+4*3.35+2.4+.98
    box('Finial pedestal',(cx,cy,top+.12),(1.05,1.05,.28),M['Bronze'],.045)
    rod('Sorin mast',(cx,cy,top+.2),(cx,cy,top+4.3),.063,M['Bronze'],12,radius2=.028)
    for i in range(9):
        z=top+.60+i*.31
        r=.47-i*.022
        pts=[(cx+r*math.cos(t*TAU/48),cy+r*math.sin(t*TAU/48),z) for t in range(49)]
        curve('Sorin ring',pts,.052,M['Bronze'])
    rod('Finial spear',(cx,cy,top+3.3),(cx,cy,top+4.4),.16,M['Bronze'],12,radius2=.0)


def lanterns():
    collection('04 • Dawn lanterns')
    for side in [-1,1]:
        for i,y in enumerate([-6.3,3,12.5,22]):
            x=side*(3.85 if i==0 else 3.65)
            z=8.45-(y+11)*.155/.61
            box('Lantern stone foot',(x,y,z+.08),(.65,.65,.26),M['Stone'],.06)
            box('Lantern timber post',(x,y,z+.85),(.21,.21,1.45),M['Lantern timber'],.025)
            box('Lantern sill',(x,y,z+1.57),(.68,.68,.16),M['Lantern timber'],.025)
            box('Washi diffuser',(x,y,z+1.95),(.49,.49,.66),M['Washi glow'],.014)
            for a in [-1,1]:
                for b in [-1,1]:
                    box('Lantern corner frame',(x+a*.29,y+b*.29,z+1.96),(.065,.065,.83),M['Lantern timber'],.008)
            for a in [-1,1]:
                box('Lantern transom',(x+a*.30,y,z+1.98),(.045,.6,.05),M['Lantern timber'],.005)
                box('Lantern transom',(x,y+a*.30,z+1.98),(.6,.045,.05),M['Lantern timber'],.005)
            roof('Lantern hipped cap',(x,y),.48,z+2.37,.20,M['Oxidized roof'],False)
            data=bpy.data.lights.new('Amber lantern practical','POINT')
            data.energy=22 if i==0 else 12
            data.color=(1,.47,.17)
            data.shadow_soft_size=.20
            o=bpy.data.objects.new('Amber lantern practical',data)
            COL.objects.link(o)
            o.location=(x,y-.37,z+1.98)


class Batch:
    """Many small primitives in a single mesh, with material indices."""
    def __init__(self):
        self.v=[]; self.f=[]; self.mi=[]

    def add(self,vs,fs,index=0):
        start=len(self.v)
        self.v.extend(vs)
        self.f.extend(tuple(start+i for i in f) for f in fs)
        self.mi.extend([index]*len(fs))

    def tube(self,a,b,r1,r2,index=0,sides=6):
        a,b=Vector(a),Vector(b)
        q=(b-a).to_track_quat('Z','Y')
        v=[a+q@Vector((math.cos(i*TAU/sides)*r,math.sin(i*TAU/sides)*r,z))
           for z,r in [(0,r1),((b-a).length,r2)] for i in range(sides)]
        f=[(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
        self.add(v,f,index)

    def finish(self,name,mats,smooth=True):
        obj=mesh(name,self.v,self.f,mats[0],smooth)
        for m in mats[1:]: obj.data.materials.append(m)
        for p,i in zip(obj.data.polygons,self.mi): p.material_index=i
        return obj


def flower_geometry(batch, center, scale, rot, shade):
    center=Vector(center)
    for i in range(5):
        a=i*TAU/5
        # Notched petal tip, slightly cupped profile; no opacity cards.
        outline=[(0,0,0),(.30,-.21,.03),(.70,-.30,.08),
                 (1.0,-.10,.17),(.87,0,.15),(1.0,.10,.17),(.70,.30,.08),(.30,.21,.03),(.48,0,.065)]
        r=Matrix.Rotation(a,3,'Z')
        vs=[center+rot@(r@Vector(p)*scale) for p in outline]
        fs=[(8,j,(j+1)%8) for j in range(8)]
        batch.add(vs,fs,shade)
    # A warm center, visible on foreground blossoms.
    vs=[center+rot@Vector((math.cos(i*TAU/6)*scale*.15,math.sin(i*TAU/6)*scale*.15,scale*.10)) for i in range(6)]
    batch.add(vs,[tuple(range(6))],4)


# Six sakura silhouettes.  Somei-yoshino spreads into a broad umbrella, yamazakura
# grows taller and more upright with rustier young leaves, the low old tree leans and
# sprawls, and a drooping form lets the outer branches fall like a light shidare.
SPECIES=[
    dict(name='yoshino hero',   lean=.10, trunk=2.40, spread=.70, droop=.00, kids=(3,3), length=(1.9,2.7), flowers=46, shades=[2,4,6,1]),
    dict(name='yamazakura',     lean=.05, trunk=2.15, spread=.58, droop=-.04, kids=(3,3), length=(1.6,2.3), flowers=36, shades=[3,3,4,3]),
    dict(name='old spreading',  lean=.22, trunk=1.35, spread=.88, droop=.08, kids=(2,4), length=(1.5,2.1), flowers=36, shades=[2,5,5,1]),
    dict(name='yoshino',        lean=.08, trunk=1.75, spread=.68, droop=.02, kids=(3,3), length=(1.5,2.2), flowers=38, shades=[2,4,5,1]),
    dict(name='drooping',       lean=.06, trunk=2.05, spread=.60, droop=.22, kids=(2,3), length=(1.6,2.3), flowers=40, shades=[1,5,6,1]),
    dict(name='young slender',  lean=.03, trunk=2.20, spread=.48, droop=-.03, kids=(2,2), length=(1.3,1.9), flowers=28, shades=[3,4,4,2]),
]


def sakura_tree(seed, species):
    r=random.Random(seed)
    sp=SPECIES[species]
    wood=Batch(); petals=Batch()
    terminals=[]
    def branch(a, direction, length, radius, depth):
        a=Vector(a); direction=Vector(direction).normalized()
        # Deeper branches sag or lift depending on the species.
        direction=(direction+Vector((0,0,-sp['droop']*(3-depth)))).normalized()
        b=a+direction*length
        points=[]
        bend=Vector((r.uniform(-.14,.14),r.uniform(-.14,.14),r.uniform(-.02,.12)))
        for k in range(7):
            t=k/6
            points.append(a.lerp(b,t)+bend*math.sin(t*math.pi))
        for k in range(6):
            wood.tube(points[k],points[k+1],radius*(1-.5*k/6),radius*(1-.5*(k+1)/6),sides=10 if radius>.12 else 6)
        if depth==0:
            terminals.append((a,b,direction,1.0))
            return
        if depth==1:
            terminals.append((a,b,direction,.45))
        lo,hi=sp['kids']
        for k in range(r.randint(lo,hi) if depth>1 else 2):
            angle=r.uniform(0,TAU)
            spread=sp['spread'] if depth>1 else sp['spread']+.14
            d=direction*.70+Vector((math.cos(angle)*spread,math.sin(angle)*spread,r.uniform(.1,.5)))
            branch(b,d,length*r.uniform(.56,.73),radius*.48,depth-1)
    # Trunk as three leaning segments so the bole reads as grown, not extruded.
    lean=Vector((r.uniform(-1,1),r.uniform(-1,1),0)).normalized()*sp['lean']
    trunk=[Vector((0,0,0))]
    for k in range(1,4):
        t=k/3
        trunk.append(Vector((lean.x*t*sp['trunk']*1.6,lean.y*t*sp['trunk']*1.6,t*sp['trunk']))+Vector((r.uniform(-.05,.05),r.uniform(-.05,.05),0)))
    for k in range(3):
        wood.tube(trunk[k],trunk[k+1],.34*(1-.12*k),.34*(1-.12*(k+1)),sides=12)
    top=trunk[-1]
    for i in range(6 if species!=5 else 5):
        a=i*TAU/6+r.uniform(-.3,.3)
        lo,hi=sp['length']
        branch(top+Vector((0,0,r.uniform(-.35,.15))),(math.cos(a),math.sin(a),r.uniform(.55,1.05)),r.uniform(lo,hi),.18,3)
    # Blossoms hang in umbels of three to six on short twigs, not as a uniform mist.
    for a,b,d,density in terminals:
        clusters=max(2,round(sp['flowers']*density/4.5))
        for i in range(clusters):
            t=r.uniform(.15,1.0)
            base_pt=a.lerp(b,t)
            twig=Vector((r.uniform(-.28,.28),r.uniform(-.28,.28),r.uniform(-.22,.18)))
            centre=base_pt+twig
            wood.tube(base_pt,centre,.014,.008,sides=4)
            for k in range(r.randint(3,6)):
                p=centre+Vector((r.uniform(-.09,.09),r.uniform(-.09,.09),r.uniform(-.07,.06)))
                rot=Euler((r.uniform(-1.6,1.6),r.uniform(-1.6,1.6),r.uniform(0,TAU))).to_matrix()
                flower_geometry(petals,p,r.uniform(.050,.082),rot,r.choices([0,1,2,3],sp['shades'])[0])
    return wood,petals


def vegetation():
    col=collection('05 • Sakura grove / linked botanical meshes')
    prototypes=[]
    for i in range(len(SPECIES)):
        wood,p=sakura_tree(321+i,i)
        w=wood.finish('Sakura branch library',[M['Bark']])
        f=p.finish('Sakura flower library',[M[f'Petal {j}'] for j in range(4)]+[M['Stamen']])
        prototypes.append((w.data,f.data))
        bpy.data.objects.remove(w,do_unlink=True)
        bpy.data.objects.remove(f,do_unlink=True)
    positions=[(-10,-3,1.65),(11,-.5,1.50),(-9,8,1.20),(11,13,1.05),
               (-8,19,1.1),(-15,28,1.25),(3,27,.94),(21,28,1.12),
               (24,42,1.15),(-4,39,1.1),(-15,43,1.3),(3,48,1.15),(16,53,1.15),
               (10,27,1.1),(18,27,1.0),(-10,28,1.25),(-20,32,1.2)]
    for i in range(85):
        x=RNG.uniform(-58,63); y=RNG.uniform(20,112)
        if (abs(x)<6 and y<35) or (4<x<23 and 25<y<47): continue
        positions.append((x,y,RNG.uniform(.85,1.4)))
    for i in range(95):
        positions.append((RNG.uniform(-140,140),RNG.uniform(112,285),RNG.uniform(.9,1.6)))
    for i,(x,y,s) in enumerate(positions):
        pair=prototypes[i%len(SPECIES)]
        angle=RNG.uniform(0,TAU)
        for j,data in enumerate(pair):
            obj=bpy.data.objects.new(f'Sakura {i:02d} '+('branches' if j==0 else 'blossoms'),data)
            col.objects.link(obj)
            obj.location=(x,y,ground_z(x,y))
            obj.rotation_euler[2]=angle
            obj.scale=(s,s,s)
    # Evergreen silhouettes among sakura keep the landscape from becoming a pink mass.
    collection('06 • Evergreen hillside')
    for i in range(70):
        x=RNG.uniform(-125,130); y=RNG.uniform(40,275)
        if 2<x<24 and y<57: continue
        z=ground_z(x,y); height=RNG.uniform(5,11)
        rod('Evergreen trunk',(x,y,z),(x,y,z+height),.13,M['Bark'],6,radius2=.015)
        b=Batch()
        for tier in range(13):
            zz=z+height*(.20+tier*.057)
            rad=height*.25*(1-tier*.069)
            for arm in range(7):
                angle=arm*TAU/7+RNG.uniform(-.2,.2)+tier*.31
                dx,dy=math.cos(angle),math.sin(angle)
                for k in range(7):
                    t=(k+1)/7
                    px=x+dx*rad*t; py=y+dy*rad*t; pz=zz+.2*math.sin(t*math.pi)
                    size=rad*.3*(1-t*.55)
                    for sprig in range(4):
                        a=RNG.uniform(0,TAU); rr=size*RNG.uniform(.5,1)
                        q=(px+math.cos(a)*rr,py+math.sin(a)*rr,pz+RNG.uniform(-.13,.24))
                        v=[(q[0]-rr*.7,q[1],q[2]),(q[0]+rr*.7,q[1],q[2]),
                           (q[0],q[1]-rr*.7,q[2]-.04),(q[0],q[1]+rr*.7,q[2]-.04),
                           (q[0],q[1],q[2]+size*.65)]
                        b.add(v,[(0,2,4),(2,1,4),(1,3,4),(3,0,4)])
        b.finish('Fine evergreen branch sprays',[M['Needles']])


def ground_dressing():
    collection('07 • Fallen petals and undergrowth')
    b=Batch()
    for i in range(2500):
        y=RNG.uniform(-11,29)
        # Accumulation along edges with a walkable clear center.
        x=RNG.choice([-1,1])*RNG.uniform(1.8,3) if RNG.random()<.8 else RNG.uniform(-2.8,2.8)
        step=max(0,min(65,int((y+11+.305)/.61)))
        z=8.45-step*.155+.012
        a=RNG.uniform(0,TAU); s=RNG.uniform(.018,.047)
        rot=Matrix.Rotation(a,3,'Z')
        vs=[Vector((x,y,z))+rot@Vector((px*s,py*s,pz*s)) for px,py,pz in [(0,0,0),(.5,-.5,.01),(1.25,-.22,.13),(1.05,0,.08),(1.25,.22,.13),(.5,.5,.01)]]
        b.add(vs,[(0,1,2,3),(0,3,4,5)],RNG.randrange(3))
    b.finish('Petals settled on treads',[M[f'Petal {i}'] for i in range(3)])
    b=Batch()
    for i in range(3200):
        side=RNG.choice([-1,1]); x=side*RNG.uniform(3.7,13)
        y=RNG.uniform(-10,50); z=ground_z(x,y)
        h=RNG.uniform(.13,.5); w=RNG.uniform(.018,.05)
        a=RNG.uniform(0,TAU)
        v=[(x-w,y,z),(x+w,y,z),(x+math.cos(a)*h*.4,y+math.sin(a)*h*.4,z+h)]
        b.add(v,[(0,1,2)])
    b.finish('Hillside grasses',[M['Moss']])


def city():
    collection('08 • Fujiyoshida valley')
    box('Valley floor',(0,530,-28),(2100,1200,5),M['Valley'])
    walls=[Batch() for _ in range(5)]; roofs=[Batch() for _ in range(4)]
    def cuboid(b,x,y,z,w,d,h):
        b.add([(x-w/2,y-d/2,z),(x+w/2,y-d/2,z),(x+w/2,y+d/2,z),(x-w/2,y+d/2,z),
               (x-w/2,y-d/2,z+h),(x+w/2,y-d/2,z+h),(x+w/2,y+d/2,z+h),(x-w/2,y+d/2,z+h)],
              [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])
    for j in range(80):
        for i in range(140):
            if i%10==0 or j%9==0 or RNG.random()<.16: continue
            x=(i-70)*8+RNG.uniform(-1,1)
            y=290+j*8+RNG.uniform(-1,1)
            z=-25.5
            w=RNG.uniform(3,6); d=RNG.uniform(4,6.5); h=RNG.uniform(2.8,5.5)
            if RNG.random()<.035: h*=2.5
            cuboid(walls[RNG.randrange(5)],x,y,z,w,d,h)
            roofb=roofs[RNG.randrange(4)]
            roofb.add([(x-w*.56,y-d*.56,z+h),(x+w*.56,y-d*.56,z+h),
                       (x+w*.56,y+d*.56,z+h),(x-w*.56,y+d*.56,z+h),
                       (x,y-d*.56,z+h+1.4),(x,y+d*.56,z+h+1.4)],
                      [(0,4,5,3),(4,1,2,5),(0,1,4),(3,5,2)])
    for i,b in enumerate(walls): b.finish(f'City plaster district {i}',[M[f'City wall {i}']],False)
    for i,b in enumerate(roofs): b.finish(f'City roof district {i}',[M[f'City roof {i}']],False)
    for j in range(0,80,9):
        box('East west street',(0,290+j*8,-25.44),(1150,3,.04),M['Road'])
    for i in range(-7,8):
        box('North south street',(i*80,610,-25.43),(3,650,.04),M['Road'])


def fuji():
    collection('09 • Fuji / radial gullies and spring snow')
    cx,cy=-180,1550
    radius,height,base=800,320,-29
    angular,rings=400,170
    verts=[]; faces=[]; snow_faces=[]
    def relief(a,t):
        """Radial erosion: several gully bands with noise-wandering phase, V-shaped
        bottoms, deepening down the slope.  Returns (height offset, valley 0..1)."""
        valley=0.0; total=0.0
        for k,amp in ((23,.30),(41,.55),(77,.28),(131,.12)):
            phase=noise.noise(Vector((math.cos(a)*2.6,math.sin(a)*2.6,k*.037)))*3.4
            v=abs(math.sin(a*k*.5+phase))**.62          # sharp valley floors, rounded ridges
            valley+=amp*(1-v); total+=amp
        valley/=total
        depth=(1.5+8.5*t**1.35)*math.sin(t*math.pi)**.7
        erosion=noise.noise(Vector((math.cos(a)*t*14,math.sin(a)*t*14,2.7)))*2.6*t
        return -valley*depth+erosion, valley
    for j in range(rings+1):
        t=.014+(1-.014)*j/rings
        for i in range(angular):
            a=i*TAU/angular
            radial=radius*t*(1+.025*math.sin(3*a)+.018*math.cos(7*a))
            h=height*(1-t)**1.62
            g,_=relief(a,t)
            h+=g + noise.noise_vector(Vector((math.cos(a)*t*9,math.sin(a)*t*9,t*3)))[0]*2*math.sin(t*math.pi)
            # Rounded, slightly asymmetric summit ridge, not a needle cone.
            h+=1.7*math.sin(4*a)*(1-t)**12
            verts.append((cx+radial*math.cos(a),cy+radial*math.sin(a),base+h))
    for j in range(rings):
        t=j/rings
        for i in range(angular):
            a=i*TAU/angular
            face=(j*angular+i,(j+1)*angular+i,(j+1)*angular+(i+1)%angular,j*angular+(i+1)%angular)
            faces.append(face)
            edge=.34+.11*math.sin(a*41+math.sin(a*9)*2)+.045*math.sin(a*77)+.02*math.sin(a*13)
            snow_faces.append(t<edge)
    # Interpolated snow coverage removes the stair-stepped material boundary.
    snowmat=M['Mountain rock'].copy(); snowmat.name='Fuji • wind-carved snow coverage'
    n=snowmat.node_tree.nodes; l=snowmat.node_tree.links
    bs=n.get('Principled BSDF')
    attr=n.new('ShaderNodeAttribute'); attr.attribute_name='snow_coverage'
    mix=n.new('ShaderNodeMixRGB'); mix.blend_type='MIX'
    mix.inputs[1].default_value=(.13,.185,.235,1)
    mix.inputs[2].default_value=(.79,.84,.87,1)
    l.new(attr.outputs['Fac'],mix.inputs[0]); l.new(mix.outputs[0],bs.inputs['Base Color'])
    obj=mesh('Mount Fuji sculpted massif',verts,faces,snowmat,True)
    attrdata=obj.data.attributes.new('snow_coverage','FLOAT','POINT')
    for j in range(rings+1):
        t=j/rings
        for i in range(angular):
            a=i*TAU/angular
            _,valley=relief(a,t)
            # Snow lingers as tongues down the gully floors, is scoured on the windward
            # (south-west) face, and breaks into an irregular fringe along the snowline.
            aspect=math.cos(a-math.radians(225))
            edge=.29+.075*valley-.045*max(0,aspect)+.015*math.sin(a*13)
            irregular=noise.noise(Vector((math.cos(a)*t*50,math.sin(a)*t*50,t*30)))*.018
            attrdata.data[j*angular+i].value=max(0,min(1,(edge-t+irregular)*70))
    # Close the tiny summit opening.
    cap=mesh('Fuji summit snow rim',verts[:angular],[tuple(reversed(range(angular)))],M['Snow'])
    # Lower foothills soften the join to the city without a lake or a hard horizon.
    for index,(y,z,height2) in enumerate([(740,-27,26),(855,-26,38)]):
        v=[]; f=[]
        for j in range(5):
            for i in range(151):
                x=-1050+i*14
                h=height2*(.6+.22*math.sin(i*.24)+.14*math.sin(i*.63))
                v.append((x,y+j*28,z+h*math.sin(j*math.pi/4)))
        for j in range(4):
            for i in range(150):
                a=j*151+i; f.append((a,a+1,a+152,a+151))
        mesh(f'Foothill ridge {index}',v,f,M['Valley'],True)


def airborne():
    collection('10 • Drifting petals / deterministic animation')
    # Shared petal mesh, independently keyed, with no simulation cache dependency.
    template=mesh('Petal template',[(0,0,0),(.022,-.016,.001),(.049,-.01,.008),(.043,0,.006),(.049,.01,.008),(.022,.016,.001)],[(0,1,2,3),(0,3,4,5)],M['Petal 1'],True)
    data=template.data
    bpy.data.objects.remove(template,do_unlink=True)
    for i in range(90):
        o=bpy.data.objects.new(f'Drifting petal {i:03d}',data)
        COL.objects.link(o)
        x,y,z=RNG.uniform(-9,10),RNG.uniform(-6,42),RNG.uniform(5,17)
        phase=RNG.uniform(0,TAU)
        s=RNG.uniform(.8,1.8); o.scale=(s,s,s)
        speed=RNG.uniform(.08,.22)
        for frame in range(1,290,12):
            t=(frame-1)/24
            o.location=(x+.26*t+.35*math.sin(t*.8+phase),y+.14*t+.3*math.cos(t*.5+phase),z-speed*t+.12*math.sin(t*1.4+phase))
            o.rotation_euler=(t*1.2+phase,t*.7+phase,t*.5)
            o.keyframe_insert(data_path='location',frame=frame)
            o.keyframe_insert(data_path='rotation_euler',frame=frame)


def geometry_nodes_wind():
    """Apply matching world-space, height-weighted sway to branch and blossom meshes."""
    group=bpy.data.node_groups.new('Sakura • gentle coherent branch sway','GeometryNodeTree')
    group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
    group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    n=group.nodes; l=group.links
    inp=n.new('NodeGroupInput'); out=n.new('NodeGroupOutput')
    pos=n.new('GeometryNodeInputPosition')
    time_node=n.new('GeometryNodeInputSceneTime')
    separate=n.new('ShaderNodeSeparateXYZ'); l.new(pos.outputs['Position'],separate.inputs[0])
    scale=n.new('ShaderNodeMath'); scale.operation='MULTIPLY'; scale.inputs[1].default_value=.65
    l.new(time_node.outputs['Seconds'],scale.inputs[0])
    coord=n.new('ShaderNodeVectorMath'); coord.operation='ADD'
    l.new(pos.outputs['Position'],coord.inputs[0])
    comb=n.new('ShaderNodeCombineXYZ'); l.new(scale.outputs[0],comb.inputs['Z'])
    l.new(comb.outputs[0],coord.inputs[1])
    tex=n.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value=.45; tex.inputs['Detail'].default_value=1
    l.new(coord.outputs[0],tex.inputs['Vector'])
    subtract=n.new('ShaderNodeMath'); subtract.operation='SUBTRACT'; subtract.inputs[1].default_value=.5
    l.new(tex.outputs['Fac'],subtract.inputs[0])
    height=n.new('ShaderNodeMapRange'); height.clamp=True
    height.inputs['From Min'].default_value=1.5; height.inputs['From Max'].default_value=6
    height.inputs['To Max'].default_value=.10
    l.new(separate.outputs['Z'],height.inputs['Value'])
    mul=n.new('ShaderNodeMath'); mul.operation='MULTIPLY'
    l.new(subtract.outputs[0],mul.inputs[0]); l.new(height.outputs['Result'],mul.inputs[1])
    offset=n.new('ShaderNodeCombineXYZ'); l.new(mul.outputs[0],offset.inputs['X'])
    setpos=n.new('GeometryNodeSetPosition')
    l.new(inp.outputs['Geometry'],setpos.inputs['Geometry']); l.new(offset.outputs[0],setpos.inputs['Offset'])
    l.new(setpos.outputs[0],out.inputs['Geometry'])
    for i,node in enumerate(n): node.location=((i%5)*200,-(i//5)*200)
    for o in bpy.data.collections['05 • Sakura grove / linked botanical meshes'].objects:
        if o.location.y<25:
            mod=o.modifiers.new('Gentle breeze / shared branch and blossom field','NODES')
            mod.node_group=group


def lighting():
    collection('11 • Sunrise and atmosphere')
    world=bpy.data.worlds.new('Spring sunrise')
    bpy.context.scene.world=world
    world.use_nodes=True
    n=world.node_tree.nodes; l=world.node_tree.links
    sky=n.new('ShaderNodeTexSky'); sky.sky_type='NISHITA'
    sky.sun_elevation=math.radians(3)
    sky.sun_rotation=math.radians(114)
    sky.sun_disc=False
    sky.altitude=.6
    sky.air_density=1.0
    sky.dust_density=.25
    n.get('Background').inputs['Strength'].default_value=.30
    l.new(sky.outputs['Color'],n.get('Background').inputs['Color'])
    data=bpy.data.lights.new('Low morning sun','SUN')
    data.energy=3.0; data.angle=math.radians(.65); data.color=(1,.72,.44)
    sun=bpy.data.objects.new('Low morning sun',data); COL.objects.link(sun)
    # Light travels down and toward the camera-right side of the landscape.
    direction=Vector((.4067,-.9135,-.0523)).normalized()
    sun.rotation_euler=direction.to_track_quat('-Z','Y').to_euler()
    # Camera-visible solar disc. Illumination comes only from the aligned Sun lamp.
    sunmat=bpy.data.materials.new('Visible solar disc / camera rays only'); sunmat.use_nodes=True
    nodes=sunmat.node_tree.nodes; links=sunmat.node_tree.links; nodes.clear()
    out=nodes.new('ShaderNodeOutputMaterial'); mix=nodes.new('ShaderNodeMixShader')
    lightpath=nodes.new('ShaderNodeLightPath'); transparent=nodes.new('ShaderNodeBsdfTransparent')
    emission=nodes.new('ShaderNodeEmission'); emission.inputs['Color'].default_value=(1,.60,.23,1); emission.inputs['Strength'].default_value=12
    links.new(lightpath.outputs['Is Camera Ray'],mix.inputs[0]); links.new(transparent.outputs[0],mix.inputs[1]); links.new(emission.outputs[0],mix.inputs[2]); links.new(mix.outputs[0],out.inputs['Surface'])
    center=-direction*2400
    orient=direction.to_track_quat('Z','Y')
    discverts=[center+orient@Vector((math.cos(i*TAU/64)*12,math.sin(i*TAU/64)*12,0)) for i in range(64)]
    mesh('Sun just above the eastern horizon',discverts,[tuple(range(64))],sunmat)
    data=bpy.data.lights.new('Soft cool sky bounce','AREA')
    data.energy=1400; data.shape='DISK'; data.size=35; data.color=(.63,.77,1)
    o=bpy.data.objects.new('Soft cool sky bounce',data); COL.objects.link(o)
    o.location=(0,-5,28); o.rotation_euler=(Vector((8,28,5))-o.location).to_track_quat('-Z','Y').to_euler()
    # Thin local volume across city, with a smooth vertical density falloff.
    vol=bpy.data.materials.new('Valley atmospheric perspective'); vol.use_nodes=True
    n=vol.node_tree.nodes; n.clear(); l=vol.node_tree.links
    out=n.new('ShaderNodeOutputMaterial'); p=n.new('ShaderNodeVolumePrincipled')
    p.inputs['Color'].default_value=(.66,.75,.86,1)
    p.inputs['Anisotropy'].default_value=.15
    tex=n.new('ShaderNodeTexCoord'); sep=n.new('ShaderNodeSeparateXYZ')
    l.new(tex.outputs['Generated'],sep.inputs[0])
    ramp=n.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.05; ramp.color_ramp.elements[0].color=(.0015,.0015,.0015,1)
    ramp.color_ramp.elements[1].position=.95; ramp.color_ramp.elements[1].color=(0,0,0,1)
    l.new(sep.outputs['Z'],ramp.inputs[0]); l.new(ramp.outputs[0],p.inputs['Density'])
    l.new(p.outputs[0],out.inputs['Volume'])
    box('Thin valley atmosphere',(0,575,12),(2200,1100,130),vol)


def cameras():
    collection('12 • Cameras / twelve second reveal')
    scene=bpy.context.scene
    data=bpy.data.cameras.new('Cinematic 30mm')
    data.lens=30; data.sensor_width=36; data.clip_end=4000
    camera=bpy.data.objects.new('CAM • First Light',data); COL.objects.link(camera)
    scene.camera=camera
    target=Vector((1,54,4.0))
    for frame,loc in [(1,(-.55,-14.8,9.8)),(144,(-.25,-13.7,10.0)),(288,(0,-12.6,10.2))]:
        camera.location=loc
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.keyframe_insert(data_path='location',frame=frame)
        camera.keyframe_insert(data_path='rotation_euler',frame=frame)
    focus=bpy.data.objects.new('Focus • pagoda facade',None); COL.objects.link(focus)
    focus.location=(12,33,8)
    data.dof.use_dof=True; data.dof.focus_object=focus; data.dof.aperture_fstop=8
    scene.frame_start=1; scene.frame_end=288; scene.render.fps=24
    scene.timeline_markers.new('Opening / lantern foreground',frame=1)
    scene.timeline_markers.new('Mid reveal',frame=144)
    scene.timeline_markers.new('Hero still',frame=288)
    scene.frame_set(288)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.region_3d.view_perspective='CAMERA'
                area.spaces.active.overlay.show_overlays=False


def render_settings():
    scene=bpy.context.scene
    scene.render.engine='CYCLES'
    scene.cycles.samples=96
    scene.cycles.use_denoising=True
    scene.cycles.adaptive_threshold=.025
    scene.cycles.max_bounces=7
    scene.cycles.diffuse_bounces=3
    scene.cycles.glossy_bounces=3
    scene.cycles.transmission_bounces=3
    scene.cycles.volume_bounces=1
    scene.render.resolution_x=1920; scene.render.resolution_y=1080
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.image_settings.color_mode='RGB'
    scene.render.image_settings.color_depth='8'
    scene.render.film_transparent=False
    scene.render.use_motion_blur=True
    scene.render.motion_blur_shutter=.5
    scene.view_settings.view_transform='AgX'
    scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=.5
    scene.unit_settings.system='METRIC'
    scene.unit_settings.scale_length=1
    scene.use_nodes=True
    n=scene.node_tree.nodes; n.clear(); l=scene.node_tree.links
    layers=n.new('CompositorNodeRLayers'); layers.location=(0,0)
    glare=n.new('CompositorNodeGlare'); glare.glare_type='FOG_GLOW'; glare.quality='HIGH'; glare.threshold=2; glare.mix=-.93
    glare.location=(220,0)
    out=n.new('CompositorNodeComposite'); out.location=(440,0)
    l.new(layers.outputs['Image'],glare.inputs['Image']); l.new(glare.outputs['Image'],out.inputs['Image'])
    layer=scene.view_layers[0]
    layer.use_pass_cryptomatte_object=True
    layer.use_pass_z=True
    layer.use_pass_emit=True
    # CPU is the portable default for the PyPI headless module; try Metal if exposed.
    prefs=bpy.context.preferences.addons['cycles'].preferences
    try:
        prefs.compute_device_type='METAL'
        prefs.get_devices()
        gpu=[d for d in prefs.devices if d.type=='METAL']
        if gpu:
            for d in prefs.devices: d.use=d.type=='METAL'
            scene.cycles.device='GPU'
    except (TypeError, RuntimeError):
        scene.cycles.device='CPU'


def manifest():
    scene=bpy.context.scene
    record={
        'title':'Arakurayama — First Light',
        'blender':bpy.app.version_string,
        'seed':829,
        'layout':'Art-directed interpretation; not a surveyed reconstruction.',
        'geometry':'All scene geometry and procedural shaders authored by build_scene.py.',
        'external_assets':[],
        'objects':len(scene.objects),
        'unique_meshes':len(bpy.data.meshes),
        'unique_mesh_polygons':sum(len(m.polygons) for m in bpy.data.meshes),
        'frames':[1,288], 'fps':24,
        'render_device':scene.cycles.device,
        'roof_tiers':5,
        'output_blend':'arakurayama_sunrise.blend',
    }
    (ROOT/'scene_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
    text=bpy.data.texts.new('READ ME • First Light')
    text.write('ARAKURAYAMA / FIRST LIGHT\n\n'+json.dumps(record,indent=2)+'\n\nCamera frame 288 is the hero still.\nAll materials are procedural and packed with the blend.\nAnimation is deterministic; no external simulation bake needed.\nUse scripts/render_scene.py for quality presets and frame ranges.\n')


def main():
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else sys.argv[1:]
    parser=argparse.ArgumentParser()
    parser.add_argument('--render',choices=['none','preview','still'],default='preview')
    a=parser.parse_args(args)
    started=time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for fn in [materials,terrain,railings,pagoda,lanterns,vegetation,ground_dressing,city,fuji,airborne,geometry_nodes_wind,lighting,cameras,render_settings,manifest]:
        print('BUILD',fn.__name__,flush=True)
        fn()
    bpy.context.scene.render.filepath=str(ROOT/'renders'/'hero.png')
    (ROOT/'renders').mkdir(exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'arakurayama_sunrise.blend'))
    print(f'SAVED scene in {time.time()-started:.1f}s',flush=True)
    if a.render!='none':
        scene=bpy.context.scene
        if a.render=='preview':
            scene.render.resolution_percentage=50
            scene.cycles.samples=32
            scene.render.use_motion_blur=False
            scene.render.filepath=str(ROOT/'renders'/'preview.png')
        else:
            scene.cycles.samples=192
        with render_log(ROOT/'logs'/'build_render.log'):
            bpy.ops.render.render(write_still=True)
        print('RENDERED',scene.render.filepath,flush=True)


if __name__=='__main__':
    main()
