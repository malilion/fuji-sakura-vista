// Real-time reconstruction of arakurayama_sunrise.blend.
// Geometry comes from web/assets/arakurayama.glb (scripts/export_web.py); lighting,
// sky, wind and drifting petals are rebuilt here so they can stay interactive.
//
// Blender (x, y, z) -> glTF/Three (x, z, -y). Every constant below that quotes a
// Blender position has been converted that way.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

const B2T = (x, y, z) => new THREE.Vector3(x, z, -y);

// Low morning sun: Blender rotation_euler (1.52, 0, -2.72) on a sun lamp pointing -Z.
const SUN_DIR = B2T(-0.409, 0.911, 0.051).normalize();
const CAM_START = { pos: B2T(-0.55, -14.8, 9.8), tilt: 1.487, yaw: -0.023 };
const CAM_END = { pos: B2T(0.0, -12.6, 10.2), tilt: 1.478, yaw: -0.015 };
const REVEAL_SECONDS = 12;
const LANTERNS = [
  [-3.85, -6.67, 9.24, 22], [3.85, -6.67, 9.24, 22],
  [-3.65, 2.63, 6.87, 12], [3.65, 2.63, 6.87, 12],
  [-3.65, 12.13, 4.46, 12], [3.65, 12.13, 4.46, 12],
  [-3.65, 21.63, 2.04, 12], [3.65, 21.63, 2.04, 12],
];

// Direction a Blender camera looks after Euler (tilt, 0, yaw); camera local -Z.
function lookDir(tilt, yaw) {
  const d = new THREE.Vector3(0, Math.sin(tilt), -Math.cos(tilt));      // after Rx
  const c = Math.cos(yaw), s = Math.sin(yaw);
  const b = new THREE.Vector3(d.x * c - d.y * s, d.x * s + d.y * c, d.z);  // after Rz (Blender)
  return B2T(b.x, b.y, b.z).normalize();
}

// build_scene.ground_z, used to keep drifting petals above the hillside.
function groundY(x, z) {
  const yb = -z;
  let g = Math.max(-13, 8.2 - 0.255 * (yb + 10));
  if (yb > 130) g = -13 - Math.min((yb - 130) / 160, 1) * 12.5;
  return g + 0.38 * Math.sin(x * 0.19) * Math.sin(yb * 0.13);
}

const easeInOut = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

// ---------------------------------------------------------------- sky dome
const SKY_VERT = /* glsl */`
  varying vec3 vWorld;
  void main() {
    vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
    vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    gl_Position = p.xyww;   // pin to far plane
  }`;
const SKY_FRAG = /* glsl */`
  precision highp float;
  varying vec3 vWorld;
  uniform vec3 uSun;
  uniform vec3 uZenith, uHorizon, uGlow, uGround;
  void main() {
    vec3 d = normalize(vWorld - cameraPosition);
    float h = d.y;
    float s = max(dot(d, uSun), 0.0);
    vec3 col = mix(uHorizon, uZenith, smoothstep(-0.02, 0.55, h));
    col += uGlow * (pow(s, 6.0) * 0.28 + pow(s, 48.0) * 0.55) * smoothstep(-0.05, 0.12, h + 0.05);
    col = mix(uGround, col, smoothstep(-0.12, 0.0, h));
    float disc = smoothstep(0.99955, 0.99985, dot(d, uSun));
    col += vec3(1.6, 1.35, 1.05) * disc;
    gl_FragColor = vec4(col, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`;

// Vertex-shader wind for the instanced sakura; replaces the Geometry Nodes sway.
function windify(material, uniforms) {
  material.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = 'uniform float uTime; uniform float uWind;\n' + shader.vertexShader.replace(
      '#include <begin_vertex>',
      /* glsl */`
      #include <begin_vertex>
      #ifdef USE_INSTANCING
        vec3 iPos = instanceMatrix[3].xyz;
      #else
        vec3 iPos = vec3(0.0);
      #endif
      float hgt = clamp(position.y / 3.2, 0.0, 1.0);
      float ph = uTime * 1.25 + iPos.x * 0.31 + iPos.z * 0.23 + position.x * 0.55 + position.z * 0.5;
      float gust = 0.6 + 0.4 * sin(uTime * 0.37 + iPos.x * 0.05);
      transformed += uWind * gust * hgt * hgt * vec3(sin(ph) * 0.075, sin(ph * 1.7 + 1.0) * 0.028, cos(ph * 0.83) * 0.06);
      `);
  };
  material.customProgramCacheKey = () => 'wind';
}

export class FirstLightScene {
  constructor(canvas, { onProgress, onReady, onError } = {}) {
    this.canvas = canvas;
    this.onProgress = onProgress || (() => {});
    this.onReady = onReady || (() => {});
    this.onError = onError || (() => {});
    this.clock = new THREE.Clock();
    this.uniforms = { uTime: { value: 0 }, uWind: { value: 1 } };
    this.state = { wind: true, petals: true, orbit: false, shadows: true, reveal: null };
    this.fps = { frames: 0, t: 0, value: 0 };
    this.disposed = false;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.toneMapping = THREE.AgXToneMapping;
    this.renderer.toneMappingExposure = 1.3;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0xcbbfb3, 0.00052);

    this.camera = new THREE.PerspectiveCamera(37.3, 1, 0.3, 6000);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 4;
    this.controls.maxDistance = 140;
    this.controls.maxPolarAngle = Math.PI * 0.53;
    this.controls.autoRotateSpeed = 0.35;
    this.controls.enabled = false;

    this.buildSky();
    this.buildLights();
    this.buildPetals();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.load();
  }

  // ------------------------------------------------------------ environment
  buildSky() {
    this.sky = new THREE.Mesh(
      new THREE.SphereGeometry(4500, 48, 24),
      new THREE.ShaderMaterial({
        vertexShader: SKY_VERT, fragmentShader: SKY_FRAG, side: THREE.BackSide, depthWrite: false,
        uniforms: {
          uSun: { value: SUN_DIR },
          uZenith: { value: new THREE.Color(0x8fa6c0).multiplyScalar(0.95) },
          uHorizon: { value: new THREE.Color(0xe7c39b).multiplyScalar(1.25) },
          uGlow: { value: new THREE.Color(0xffa860) },
          uGround: { value: new THREE.Color(0xb3ab9d) },
        },
      }));
    this.sky.frustumCulled = false;
    this.scene.add(this.sky);
  }

  buildLights() {
    this.sun = new THREE.DirectionalLight(0xffd7ad, 4.4);
    this.sun.position.copy(SUN_DIR).multiplyScalar(260);
    this.sun.target.position.set(4, 4, -20);
    this.sun.castShadow = true;
    const sc = this.sun.shadow.camera;
    sc.left = -46; sc.right = 46; sc.top = 34; sc.bottom = -34; sc.near = 60; sc.far = 520;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.06;
    this.sun.shadow.radius = 3;
    this.scene.add(this.sun, this.sun.target);

    this.hemi = new THREE.HemisphereLight(0xa9bdd6, 0x4a463d, 1.9);
    this.scene.add(this.hemi);

    this.lanterns = new THREE.Group();
    for (const [x, y, z, w] of LANTERNS) {
      const l = new THREE.PointLight(0xffa04a, w * 1.6, 14, 2);
      l.position.copy(B2T(x, y, z));
      this.lanterns.add(l);
    }
    this.scene.add(this.lanterns);
  }

  // Drifting petals: 360 instanced petal quads on deterministic paths above the stairs.
  buildPetals() {
    const N = 360;
    const outline = [[0, 0, 0], [.5, -.5, .01], [1.25, -.22, .13], [1.05, 0, .08], [1.25, .22, .13], [.5, .5, .01]];
    const geo = new THREE.BufferGeometry();
    const verts = new Float32Array(outline.flatMap(([x, y, z]) => [x * .06, z * .06, y * .06]));
    geo.setAttribute('position', new THREE.BufferAttribute(verts, 3));
    geo.setIndex([0, 1, 2, 0, 2, 3, 0, 3, 4, 0, 4, 5]);
    geo.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: 0xf5bfb9, emissive: 0xf5bfb9, emissiveIntensity: .35, roughness: .6, side: THREE.DoubleSide });
    this.petals = new THREE.InstancedMesh(geo, mat, N);
    this.petals.frustumCulled = false;
    const seeds = new Float32Array(N * 4);
    for (let i = 0; i < N; i++) {
      seeds[i * 4] = -13 + Math.random() * 27;       // x
      seeds[i * 4 + 1] = -48 + Math.random() * 60;   // z (three) => Blender y from -12 to 48
      seeds[i * 4 + 2] = Math.random() * 14;         // fall phase (m)
      seeds[i * 4 + 3] = Math.random() * Math.PI * 2;
    }
    this.petalSeeds = seeds;
    this.scene.add(this.petals);
  }

  updatePetals(t) {
    const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), p = new THREE.Vector3(), s = new THREE.Vector3(1, 1, 1);
    const seeds = this.petalSeeds, N = this.petals.count;
    for (let i = 0; i < N; i++) {
      const sx = seeds[i * 4], sz = seeds[i * 4 + 1], ph = seeds[i * 4 + 2], ang = seeds[i * 4 + 3];
      const fall = (ph + t * 0.55) % 14;             // metres fallen since spawn
      const x = sx + Math.sin(t * 0.8 + ang) * 0.45 + t * 0.12;
      const z = sz + Math.cos(t * 0.6 + ang * 1.3) * 0.35;
      const y = groundY(x, z) + 13.5 - fall;
      p.set(x, y, z);
      e.set(t * 1.7 + ang, t * 1.1 + ang * 2.0, ang);
      q.setFromEuler(e);
      m.compose(p, q, s);
      this.petals.setMatrixAt(i, m);
    }
    this.petals.instanceMatrix.needsUpdate = true;
  }

  // ------------------------------------------------------------------- glTF
  load() {
    const draco = new DRACOLoader();
    draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
    const loader = new GLTFLoader();
    loader.setDRACOLoader(draco);
    loader.load('assets/arakurayama.glb',
      gltf => { try { this.assemble(gltf.scene); } catch (e) { console.error(e); this.onError(e); } },
      ev => this.onProgress(ev.lengthComputable ? ev.loaded / ev.total : -1),
      err => { console.error(err); this.onError(err); });
  }

  assemble(root) {
    const sakura = new Map();   // "meshName|prim" -> { geometry, material, matrices[], near }
    const statics = [];
    for (const node of root.children) {
      const lod = node.userData.lod;
      if (!lod) { statics.push(node); continue; }
      const prims = node.isMesh ? [node] : node.children;
      node.updateMatrix();
      for (let i = 0; i < prims.length; i++) {
        const key = prims[i].geometry.uuid;
        let entry = sakura.get(key);
        if (!entry) {
          entry = { geometry: prims[i].geometry, material: prims[i].material, matrices: [], near: lod === 'near' };
          sakura.set(key, entry);
        }
        entry.matrices.push(node.matrix.clone());
      }
    }

    this.world = new THREE.Group();
    for (const node of statics) {
      node.traverse(o => {
        if (!o.isMesh) return;
        const far = node.name.startsWith('Fuji') || node.name.startsWith('Fujiyoshida');
        o.castShadow = !far;
        o.receiveShadow = true;
        o.material.side = THREE.DoubleSide;
        if (o.material.name === 'Washi glow') { o.material.emissive.set(0xff6b16); o.material.emissiveIntensity = 3.2; o.material.toneMapped = true; }
        if (far) o.material.roughness = 1;
        if (o.geometry.attributes.color) o.material.vertexColors = true;
      });
      this.world.add(node);
    }

    const windMats = new Map();
    for (const { geometry, material, matrices, near } of sakura.values()) {
      let mat = windMats.get(material.uuid);
      if (!mat) {
        mat = material.clone();
        mat.side = THREE.DoubleSide;
        if (mat.name.startsWith('Petal')) { mat.roughness = 0.62; mat.emissive.copy(mat.color).multiplyScalar(0.06); }
        windify(mat, this.uniforms);
        windMats.set(material.uuid, mat);
      }
      const im = new THREE.InstancedMesh(geometry, mat, matrices.length);
      matrices.forEach((m, i) => im.setMatrixAt(i, m));
      im.instanceMatrix.needsUpdate = true;
      im.castShadow = near;
      im.receiveShadow = near;
      im.frustumCulled = false;   // one bounding volume for 49 trees would be wrong anyway
      this.world.add(im);
    }
    this.scene.add(this.world);

    this.setShadows(this.state.shadows);
    this.startReveal();
    this.renderer.setAnimationLoop(() => this.frame());
    this.onReady();
  }

  // ---------------------------------------------------------------- camera
  applyBlenderCamera(cam) {
    this.camera.position.copy(cam.pos);
    const dir = lookDir(cam.tilt, cam.yaw);
    this.controls.target.copy(cam.pos).addScaledVector(dir, 26);
    this.camera.lookAt(this.controls.target);
  }

  startReveal() {
    this.controls.enabled = false;
    this.state.reveal = { t0: this.clock.elapsedTime };
    this.applyBlenderCamera(CAM_START);
  }

  resetView() {
    this.state.reveal = null;
    this.applyBlenderCamera(CAM_END);
    this.controls.enabled = true;
    this.controls.update();
  }

  updateReveal() {
    const r = this.state.reveal;
    if (!r) return;
    const k = Math.min((this.clock.elapsedTime - r.t0) / REVEAL_SECONDS, 1);
    const e = easeInOut(k);
    const pos = CAM_START.pos.clone().lerp(CAM_END.pos, e);
    const cam = { pos, tilt: THREE.MathUtils.lerp(CAM_START.tilt, CAM_END.tilt, e), yaw: THREE.MathUtils.lerp(CAM_START.yaw, CAM_END.yaw, e) };
    this.applyBlenderCamera(cam);
    if (k >= 1) { this.state.reveal = null; this.controls.enabled = true; }
  }

  // Blender's 30 mm lens on a 36 mm sensor, fit to the longer side like sensor_fit AUTO.
  resize() {
    const w = this.canvas.clientWidth || 1, h = this.canvas.clientHeight || 1;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    const hfov = 2 * Math.atan(18 / 30);
    this.camera.fov = THREE.MathUtils.radToDeg(w >= h ? 2 * Math.atan(Math.tan(hfov / 2) / this.camera.aspect) : hfov);
    this.camera.updateProjectionMatrix();
  }

  // --------------------------------------------------------------- toggles
  setWind(on) { this.state.wind = on; this.uniforms.uWind.value = on ? 1 : 0; }
  setPetals(on) { this.state.petals = on; this.petals.visible = on; }
  setOrbit(on) { this.state.orbit = on; this.controls.autoRotate = on; if (on && this.state.reveal) this.resetView(); }
  setShadows(on) {
    this.state.shadows = on;
    this.renderer.shadowMap.enabled = on;
    this.sun.castShadow = on;
    this.scene.traverse(o => { if (o.material && o.material.needsUpdate !== undefined) o.material.needsUpdate = true; });
  }

  // ----------------------------------------------------------------- frame
  frame() {
    if (this.disposed) return;
    const dt = this.clock.getDelta();
    const t = this.clock.elapsedTime;
    this.uniforms.uTime.value = t;
    this.updateReveal();
    if (this.controls.enabled) this.controls.update();
    if (this.state.petals) this.updatePetals(t);
    this.sky.position.copy(this.camera.position);
    this.renderer.render(this.scene, this.camera);

    this.fps.frames++; this.fps.t += dt;
    if (this.fps.t >= 0.5) { this.fps.value = this.fps.frames / this.fps.t; this.fps.frames = 0; this.fps.t = 0; }
  }

  get stats() {
    const r = this.renderer.info.render;
    return { fps: this.fps.value, triangles: r.triangles, calls: r.calls };
  }
}
