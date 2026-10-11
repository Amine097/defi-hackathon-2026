// FAULTLINE landing: "The Seam x Seismic Ledger". Source for public/assets/js/landing/landing.bundle.js (esbuild).
// The official logo (public/assets/brand/logo.svg) is extruded into a monolith: two bone slabs and the red zigzag
// fault between them. Story: STABLE -> SIGNAL -> PROPAGATION -> COUNTERMOVE -> PROOF. One orchestrated sequence.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const lowPower = (navigator.connection && navigator.connection.saveData) || (navigator.deviceMemory && navigator.deviceMemory <= 4) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4);
const $ = (s, r = document) => r.querySelector(s);
// Stacked hero (stage above the text) on phones and on any portrait or square viewport. Keep in sync with landing.css + index.html.
const STACKED = '(max-width: 760px), (max-aspect-ratio: 1/1)';

// ------------------------------------------------------------------ logo geometry (64-unit viewBox)
const LEFT = [[6, 6], [34, 6], [26, 23], [34, 29], [28, 41], [32, 58], [6, 58]];
const RIGHT = [[40, 6], [58, 6], [58, 58], [42, 58], [38, 41], [44, 29], [36, 23]];
const FAULT = [[34, 6], [26, 23], [34, 29], [28, 41], [32, 58], [38, 58], [34, 41], [40, 29], [32, 23], [40, 6]];
const S = 1.55; // world units per half logo
const P = ([x, y]) => new THREE.Vector2(((x - 32) / 32) * S, ((32 - y) / 32) * S);
function shape(pts) {
  const s = new THREE.Shape();
  pts.map(P).forEach((v, i) => (i ? s.lineTo(v.x, v.y) : s.moveTo(v.x, v.y)));
  s.closePath();
  return s;
}

// ------------------------------------------------------------------ chapters (HTML)
const CHAPTERS = ['stable', 'signal', 'propagation', 'countermove', 'proof'];
function setChapter(i) {
  document.querySelectorAll('[data-chapter]').forEach((el, j) => {
    el.classList.toggle('is-on', j === i);
    el.classList.toggle('is-done', j < i);
    if (j === i) el.setAttribute('aria-current', 'step'); else el.removeAttribute('aria-current');
  });
  const live = $('#heroLive');
  if (live) live.textContent = ['Stable: the position and what it stands on.', 'Signal: a dependency starts to fail.', 'Propagation: the fault travels toward the position.', 'Countermove: a pre-authorised action locks the seam.', 'Proof: the damage is contained and the evidence remains.'][i];
}

// ------------------------------------------------------------------ WebGL scene
function webglOK() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}

function buildScene(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, lowPower ? 1 : 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.82;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = !lowPower;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.setClearColor(0x0c0d0e, 1);

  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x0c0d0e, 9, 20);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.16;

  const camera = new THREE.PerspectiveCamera(28, 1, 0.1, 60);

  // monolith
  const rig = new THREE.Group();
  scene.add(rig);
  const depth = 0.95;
  const ex = { depth, bevelEnabled: true, bevelThickness: 0.025, bevelSize: 0.022, bevelSegments: 3, curveSegments: 1 };
  const bone = new THREE.MeshPhysicalMaterial({ color: 0xdcd6cb, roughness: 0.7, metalness: 0, clearcoat: 0.25, clearcoatRoughness: 0.55, sheen: 0.25, sheenRoughness: 0.8, sheenColor: new THREE.Color(0xfff4e6) });
  // limestone: mottled albedo + micro-pitting roughness + a monumental falloff toward the base (object space, so it does
  // not swim when the camera moves)
  bone.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vObj;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvObj = position;');
    sh.fragmentShader = sh.fragmentShader.replace('#include <common>', `#include <common>
      varying vec3 vObj;
      float h3(vec3 p){ return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
      float n3(vec3 p){ vec3 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
        return mix(mix(mix(h3(i), h3(i+vec3(1,0,0)), f.x), mix(h3(i+vec3(0,1,0)), h3(i+vec3(1,1,0)), f.x), f.y),
                   mix(mix(h3(i+vec3(0,0,1)), h3(i+vec3(1,0,1)), f.x), mix(h3(i+vec3(0,1,1)), h3(i+vec3(1,1,1)), f.x), f.y), f.z); }`)
      .replace('#include <color_fragment>', `#include <color_fragment>
      float m = n3(vObj * 3.1) * 0.55 + n3(vObj * 9.0) * 0.3 + n3(vObj * 27.0) * 0.15;
      diffuseColor.rgb *= 0.86 + 0.16 * m;
      diffuseColor.rgb *= mix(0.74, 1.04, smoothstep(-1.7, 1.5, vObj.y));`)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
      roughnessFactor = clamp(roughnessFactor + (n3(vObj * 40.0) - 0.5) * 0.22, 0.0, 1.0);`);
  };
  const left = new THREE.Mesh(new THREE.ExtrudeGeometry(shape(LEFT), ex), bone);
  const right = new THREE.Mesh(new THREE.ExtrudeGeometry(shape(RIGHT), ex), bone);
  [left, right].forEach((m) => { m.castShadow = true; m.receiveShadow = true; m.position.z = -depth / 2; rig.add(m); });

  const faultMat = new THREE.MeshStandardMaterial({ color: 0x1a0603, emissive: new THREE.Color(0xff3a17), emissiveIntensity: 0.0, roughness: 0.95, metalness: 0 });
  const fault = new THREE.Mesh(new THREE.ExtrudeGeometry(shape(FAULT), { depth: depth * 0.82, bevelEnabled: false }), faultMat);
  fault.position.z = -depth / 2 + 0.02;
  rig.add(fault);
  const glow = new THREE.PointLight(0xff5b3a, 0, 1.6, 2);
  glow.position.set(0.02, 0, -0.05);
  rig.add(glow);

  // titanium staples at the three inner joints of the zigzag (logo y = 23, 29, 41) + top and bottom
  const steel = new THREE.MeshStandardMaterial({ color: 0xc4c9cf, metalness: 0.35, roughness: 0.32, envMapIntensity: 2.2 });
  const staples = [17, 26, 35, 49].map((y) => {
    const g = new THREE.Group();
    const bar = new THREE.Mesh(new THREE.BoxGeometry(0.98, 0.07, 0.07), steel);
    bar.castShadow = true;
    const legGeo = new THREE.BoxGeometry(0.07, 0.07, 0.22);
    const l1 = new THREE.Mesh(legGeo, steel), l2 = new THREE.Mesh(legGeo, steel);
    l1.position.set(-0.455, 0, -0.08); l2.position.set(0.455, 0, -0.08);
    g.add(bar, l1, l2);
    const v = P([33, y]);
    g.position.set(v.x + 0.03, v.y, depth / 2 + 0.07);
    g.userData.home = g.position.clone();
    g.position.z += 4.5;
    g.visible = false;
    rig.add(g);
    return g;
  });

  // seismic ledger: hairlines behind the monolith, displaced in the vertex shader by a wave from the fault
  const lines = new THREE.Group();
  const lineMat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    uniforms: { uT: { value: 0 }, uAmp: { value: 0 }, uFront: { value: 0 }, uBreath: { value: 1 }, uX: { value: 1.15 }, uFault: { value: new THREE.Color(0xff5b3a) }, uInk: { value: new THREE.Color(0xece9e2) } },
    vertexShader: `uniform float uT; uniform float uAmp; uniform float uFront; uniform float uBreath; uniform float uX; attribute float aRow; varying float vHeat; varying float vEdge;
      void main(){ vec3 p = position; float d = abs(p.x - uX);
        float packet = exp(-pow((d - uFront) / 1.1, 2.0));
        float wave = sin(d * 5.2 - uT * 9.0 + aRow * 0.7) * packet * uAmp;
        float idle = sin(p.x * 0.9 + uT * 0.6 + aRow * 1.7) * 0.012 * uBreath;
        p.y += wave * (0.35 + 0.65 * exp(-d * 0.25)) + idle;
        vHeat = clamp(abs(wave) * 4.0, 0.0, 1.0); vEdge = smoothstep(9.0, 6.0, abs(p.x));
        gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }`,
    fragmentShader: `uniform vec3 uFault; uniform vec3 uInk; varying float vHeat; varying float vEdge;
      void main(){ vec3 c = mix(uInk, uFault, vHeat); gl_FragColor = vec4(c, (0.075 + vHeat * 0.55) * vEdge); }`,
  });
  const ROWS = 46, SEG = 220, X0 = -9, X1 = 9;
  for (let r = 0; r < ROWS; r++) {
    const pos = new Float32Array((SEG + 1) * 3), row = new Float32Array(SEG + 1);
    const y = -3.6 + (r / (ROWS - 1)) * 7.2;
    for (let i = 0; i <= SEG; i++) { pos[i * 3] = X0 + (X1 - X0) * (i / SEG); pos[i * 3 + 1] = y; pos[i * 3 + 2] = 0; row[i] = r; }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('aRow', new THREE.BufferAttribute(row, 1));
    lines.add(new THREE.Line(g, lineMat));
  }
  lines.position.z = -2.4;
  scene.add(lines);

  // light: a low raking key so the zigzag edges carve the stone
  const key = new THREE.DirectionalLight(0xfff1e2, 1.9);
  key.position.set(-7, 3.6, 2.2);
  key.castShadow = !lowPower;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.left = -3; key.shadow.camera.right = 3; key.shadow.camera.top = 3; key.shadow.camera.bottom = -3;
  key.shadow.bias = -0.0004; key.shadow.normalBias = 0.02;
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x9fc7d8, 0.7);
  rim.position.set(5, 1.5, -4);
  scene.add(rim);
  scene.add(new THREE.HemisphereLight(0x2a2c30, 0x080809, 0.35));

  let composer = null, bloom = null;
  if (!lowPower) {
    composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.62, 0.32, 0.9);
    composer.addPass(bloom);
    composer.addPass(new OutputPass());
  }

  const state = { open: 0, heat: 0, wave: 0, front: 0, yaw: -0.34, pitch: 0.04, dolly: 0, px: 0, py: 0 };
  let mobile = false;
  const stackedMQ = matchMedia(STACKED);
  // Desktop: the slab lives in the space right of the headline, measured from its real text line boxes
  // (the block box is wider than the text when a line wraps).
  function textRight(el) {
    let r = 0;
    const range = document.createRange();
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      if (!n.textContent.trim() || n.parentElement.closest('.vh')) continue;
      range.selectNodeContents(n);
      for (const b of range.getClientRects()) r = Math.max(r, b.right);
    }
    return r;
  }
  function placeDesktop(w, h) {
    const halfH = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 9.2;
    const halfW = halfH * camera.aspect;
    const pxPerWorld = h / (2 * halfH);
    const hl = document.querySelector('.hl');
    const tr = hl ? textRight(hl) - canvas.getBoundingClientRect().left : 0;
    const start = (tr > 0 ? tr : w * 0.5) + w * 0.035;
    const avail = Math.max(0, w * 0.96 - start);
    const SLAB = 3.0; // projected slab width in world units per unit of rig scale (final frame)
    const s = Math.max(0.5, Math.min(0.8, avail / (SLAB * pxPerWorld)));
    const cx = Math.min(w * 0.96 - (SLAB * s * pxPerWorld) / 2, start + avail / 2);
    return { x: 0.35 + ((cx / w) * 2 - 1) * halfW, s };
  }
  function layout() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    if (composer) { composer.setSize(w, h); }
    camera.aspect = w / h;
    mobile = stackedMQ.matches;
    camera.fov = mobile ? 36 : 28;
    camera.updateProjectionMatrix();
    const d = mobile ? { x: 0, s: 1.08 } : placeDesktop(w, h);
    rig.position.set(d.x, mobile ? 0.08 : 0.12, 0);
    rig.scale.setScalar(d.s);
    lineMat.uniforms.uX.value = rig.position.x;
  }
  function apply(t) {
    left.position.x = -state.open * 0.42;
    right.position.x = state.open * 0.42;
    left.rotation.z = state.open * 0.025;
    right.rotation.z = -state.open * 0.02;
    left.position.y = state.open * 0.03;
    right.position.y = -state.open * 0.035;
    faultMat.emissiveIntensity = state.heat * 1.55;
    glow.intensity = 0;
    lineMat.uniforms.uT.value = t;
    lineMat.uniforms.uAmp.value = state.wave * 0.34;
    lineMat.uniforms.uFront.value = state.front;
    rig.rotation.y = state.yaw + state.px * 0.07;
    rig.rotation.x = state.pitch + state.py * 0.04;
    camera.position.set(mobile ? 0.2 : 0.4, mobile ? 0.15 : 0.12, (mobile ? 9.6 : 9.2) - state.dolly);
    camera.lookAt(mobile ? 0.12 : 0.35, mobile ? 0.02 : 0.02, 0);
  }
  function render(t) {
    apply(t);
    if (composer) composer.render(); else renderer.render(scene, camera);
  }
  return { renderer, scene, camera, state, staples, layout, render, lineMat, setBreath: (v) => (lineMat.uniforms.uBreath.value = v) };
}

// ------------------------------------------------------------------ headline seam (HTML)
function seamTimeline(tl, at) {
  const fa = $('.hl-fault'), li = $('.hl-line'), seam = $('.hl-seam');
  if (!fa || !li || !seam) return;
  tl.to(seam, { opacity: 1, duration: 0.25 }, at.signal)
    .to(fa, { x: '-0.07em', duration: 0.9, ease: 'power3.out' }, at.propagation)
    .to(li, { x: '0.07em', y: '0.03em', duration: 0.9, ease: 'power3.out' }, at.propagation)
    .to(seam, { scaleX: 2.4, duration: 0.9, ease: 'power3.out' }, at.propagation)
    .to([fa, li], { x: 0, y: 0, duration: 0.55, ease: 'power4.inOut' }, at.countermove + 0.35)
    .to(seam, { scaleX: 1, opacity: 0.55, duration: 0.55, ease: 'power4.inOut' }, at.countermove + 0.35);
}

// ------------------------------------------------------------------ boot
function solidHeader() {
  const bar = document.querySelector('.topbar');
  if (!bar) return;
  const f = () => bar.classList.toggle('is-solid', scrollY > 40);
  addEventListener('scroll', f, { passive: true }); f();
}

function boot() {
  solidHeader();
  const hero = $('#hero');
  const canvas = $('#heroCanvas');
  const pauseBtn = $('#heroPause');
  const at = { stable: 0.4, signal: 1.9, propagation: 2.9, countermove: 4.9, proof: 6.4 };
  const gl = webglOK() && canvas ? buildScene(canvas) : null;
  document.documentElement.classList.toggle('no-webgl', !gl);

  // intro of the typography: one orchestrated reveal
  const lines = document.querySelectorAll('.hl > span');
  if (!reduce) gsap.from(lines, { yPercent: 110, opacity: 0, duration: 1.0, ease: 'power4.out', stagger: 0.09, delay: 0.15 });
  if (!reduce) gsap.from('.hero__lede, .hero__cta, .hero__rail', { opacity: 0, y: 14, duration: 0.8, ease: 'power3.out', stagger: 0.08, delay: 0.55 });

  if (!gl) { setChapter(4); hero.classList.add('is-static'); return; }
  gl.layout();
  addEventListener('resize', () => gl.layout());
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => gl.layout());

  const st = gl.state;
  const tl = gsap.timeline({ paused: true, defaults: { ease: 'power2.inOut' } });
  tl.call(() => setChapter(0), null, 0)
    .fromTo(st, { dolly: -2.2 }, { dolly: 0, duration: 2.6, ease: 'power3.out' }, 0)
    .call(() => setChapter(1), null, at.signal)
    .to(st, { heat: 0.35, duration: 0.12, ease: 'none' }, at.signal)
    .to(st, { heat: 0.12, duration: 0.18, ease: 'none' }, at.signal + 0.12)
    .to(st, { heat: 0.55, duration: 0.5 }, at.signal + 0.3)
    .call(() => setChapter(2), null, at.propagation)
    .to(st, { open: 1, heat: 1, duration: 1.4, ease: 'power3.out' }, at.propagation)
    .fromTo(st, { wave: 0, front: 0 }, { wave: 1, front: 7.5, duration: 2.4, ease: 'power1.out' }, at.propagation)
    .call(() => setChapter(3), null, at.countermove);
  gl.staples.forEach((s, i) => {
    tl.set(s, { visible: true }, at.countermove + i * 0.12)
      .to(s.position, { z: s.userData.home.z, duration: 0.42, ease: 'power4.out' }, at.countermove + i * 0.12);
  });
  tl.to(st, { open: 0.08, duration: 0.6, ease: 'power4.inOut' }, at.countermove + 0.35)
    .to(st, { wave: 0, duration: 1.2, ease: 'power2.out' }, at.countermove + 0.4)
    .to(st, { heat: 0.24, duration: 1.0 }, at.countermove + 0.5)
    .call(() => { setChapter(4); hero.classList.add('is-proved'); }, null, at.proof)
    .to(st, { yaw: -0.5, duration: 3, ease: 'sine.inOut' }, at.proof);
  seamTimeline(tl, at);

  let paused = false, visible = true, raf = 0;
  const t0 = performance.now();
  function loop() {
    raf = 0;
    if (paused || !visible || document.hidden) return;
    gl.render((performance.now() - t0) / 1000);
    raf = requestAnimationFrame(loop);
  }
  const kick = () => { if (!raf && !paused && visible) raf = requestAnimationFrame(loop); };

  if (reduce) {
    // final, contained state as a still frame; no sequence, no idle motion
    tl.progress(1);
    gl.staples.forEach((s) => { s.visible = true; s.position.copy(s.userData.home); });
    st.wave = 0; gl.setBreath(0);
    setChapter(4); hero.classList.add('is-proved');
    requestAnimationFrame(() => { gl.layout(); gl.render(0); canvas.classList.add('is-ready'); });
    if (pauseBtn) pauseBtn.hidden = true;
    return;
  }

  requestAnimationFrame(() => { gl.render(0); canvas.classList.add('is-ready'); tl.play(); kick(); });
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; kick(); }, { threshold: 0.01 }).observe(hero);
  document.addEventListener('visibilitychange', kick);
  addEventListener('pointermove', (e) => {
    if (e.pointerType !== 'mouse') return;
    gsap.to(st, { px: (e.clientX / innerWidth - 0.5) * 2, py: (e.clientY / innerHeight - 0.5) * 2, duration: 1.2, ease: 'power3.out', overwrite: 'auto' });
  }, { passive: true });

  // scroll: the monolith turns to show its depth as the hero leaves
  ScrollTrigger.create({ trigger: hero, start: 'top top', end: 'bottom top', scrub: 0.6,
    onUpdate: (self) => { st.yaw = -0.5 - self.progress * 0.55; st.dolly = -self.progress * 1.6; } });

  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      paused = !paused;
      pauseBtn.setAttribute('aria-pressed', String(paused));
      pauseBtn.querySelector('span').textContent = paused ? 'Play' : 'Pause';
      if (paused) { tl.pause(); gsap.globalTimeline.pause(); } else { gsap.globalTimeline.resume(); if (tl.progress() < 1) tl.resume(); kick(); }
    });
  }
  const replay = $('#heroReplay');
  if (replay) replay.addEventListener('click', () => {
    hero.classList.remove('is-proved');
    gl.staples.forEach((s) => { s.visible = false; s.position.z = s.userData.home.z + 4.5; });
    Object.assign(st, { open: 0, heat: 0, wave: 0, front: 0 });
    tl.restart(); if (paused) pauseBtn.click(); kick();
  });
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
