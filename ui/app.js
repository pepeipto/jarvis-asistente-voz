import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const params = new URLSearchParams(location.search);
const TOKEN = params.get('t') || '';
const DEMO = params.get('demo');                       // ?demo=hablando | ciclo | ...  (sin servidor)
const $ = (id) => document.getElementById(id);

/* ============================================================ estados */
const ESTADOS = {
  inactivo:   { c1: '#22c7ff', c2: '#6b5bff', vel: 1.0, swirl: 0, pull: 0.00, label: 'En línea' },
  escuchando: { c1: '#2dffb0', c2: '#22c7ff', vel: 1.5, swirl: 0, pull: 0.10, label: 'Escuchando' },
  pensando:   { c1: '#ffb02e', c2: '#ff5a3c', vel: 3.2, swirl: 1, pull: 0.06, label: 'Procesando' },
  hablando:   { c1: '#6fe8ff', c2: '#b48cff', vel: 1.9, swirl: 0, pull: 0.00, label: 'Hablando' },
  error:      { c1: '#ff4d5e', c2: '#ff9a4d', vel: 0.4, swirl: 0, pull: 0.00, label: 'Sin audio' },
};
const cur = { c1: new THREE.Color('#22c7ff'), c2: new THREE.Color('#6b5bff'), vel: 1, swirl: 0, pull: 0 };
let estado = 'inactivo';
let nivelObjetivo = 0;                                  // 0..1 recibido del servidor
let lvl = 0;                                            // suavizado

/* uniformes compartidos por todos los materiales */
const U = {
  uTime: { value: 0 }, uLevel: { value: 0 }, uC1: { value: cur.c1 }, uC2: { value: cur.c2 },
  uSwirl: { value: 0 }, uPull: { value: 0 }, uPx: { value: 1 },
};

/* ============================================================ renderer */
const canvas = $('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
// Resolucion interna limitada (~4 megapixeles): nitida en 4K sin robar grafica a la IA
const MAX_PIX = 4.2e6;
function ratioPixeles() { return Math.max(0.5, Math.min(window.devicePixelRatio || 1, 1.25, Math.sqrt(MAX_PIX / (innerWidth * innerHeight)))); }
renderer.setPixelRatio(ratioPixeles());
renderer.setClearColor(0x02050a, 1);
U.uPx.value = renderer.getPixelRatio();

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 220);
const world = new THREE.Group();
world.position.y = 1.7; world.scale.setScalar(0.92);
scene.add(world);

const NOISE = /* glsl */`
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+10.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z); vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.5-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 105.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

const aditivo = { transparent: true, depthWrite: false, blending: THREE.AdditiveBlending };

/* ============================================================ 1. esfera de plasma (partículas) */
const N_PART = 18000;
const posP = new Float32Array(N_PART * 3), semP = new Float32Array(N_PART);
for (let i = 0; i < N_PART; i++) {
  const y = 1 - (i / (N_PART - 1)) * 2, r = Math.sqrt(1 - y * y), th = Math.PI * (3 - Math.sqrt(5)) * i;
  const s = (i % 4 === 0) ? 0.45 + 0.5 * Math.random() : 0.96 + 0.08 * Math.random();   // volumen + cáscara
  posP.set([Math.cos(th) * r * s, y * s, Math.sin(th) * r * s], i * 3);
  semP[i] = Math.random();
}
const geoP = new THREE.BufferGeometry();
geoP.setAttribute('position', new THREE.BufferAttribute(posP, 3));
geoP.setAttribute('aSeed', new THREE.BufferAttribute(semP, 1));
const plasma = new THREE.Points(geoP, new THREE.ShaderMaterial({
  ...aditivo, uniforms: { ...U, uSize: { value: 3.1 } },
  vertexShader: /* glsl */`
    ${NOISE}
    uniform float uTime, uLevel, uSwirl, uPull, uSize, uPx;
    attribute float aSeed;
    varying float vN, vFres, vSeed;
    void main(){
      vec3 p = position;
      float t = uTime * 0.32;
      float n  = snoise(p * 1.5 + vec3(0.0, t, t * 0.6));
      float n2 = snoise(p * 4.2 - vec3(t * 1.6));
      float amp = 0.55 + uLevel * 2.2;
      float r = 1.0 + (0.11 * n + 0.045 * n2) * amp + uLevel * 0.20 - uPull;
      float ang = uSwirl * (p.y * 2.4 + uTime * 1.9);
      float ca = cos(ang), sa = sin(ang);
      vec3 q = p * r; q.xz = mat2(ca, -sa, sa, ca) * q.xz;
      vec4 mv = modelViewMatrix * vec4(q, 1.0);
      gl_Position = projectionMatrix * mv;
      vec3 nrm = normalize(normalMatrix * normalize(p));
      vFres = pow(1.0 - abs(dot(nrm, normalize(-mv.xyz))), 1.5);
      vN = n * 0.5 + 0.5; vSeed = aSeed;
      gl_PointSize = uSize * uPx * (0.55 + aSeed) * (1.0 + uLevel * 0.6) * (7.5 / -mv.z);
    }`,
  fragmentShader: /* glsl */`
    uniform vec3 uC1, uC2; uniform float uLevel;
    varying float vN, vFres, vSeed;
    void main(){
      float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard;
      float a = smoothstep(0.5, 0.0, d); a *= a;
      vec3 col = mix(uC1, uC2, smoothstep(0.25, 0.85, vN)) * (0.16 + 1.5 * vFres + 0.26 * vSeed);
      gl_FragColor = vec4(col * (0.40 + uLevel * 0.22), a * 0.70);
    }`,
}));
plasma.frustumCulled = false;
world.add(plasma);

/* ============================================================ 2. núcleo luminoso */
const nucleo = new THREE.Mesh(new THREE.SphereGeometry(0.22, 64, 48), new THREE.ShaderMaterial({
  ...aditivo, uniforms: U,
  vertexShader: `varying vec3 vN, vV; void main(){ vec4 mv = modelViewMatrix * vec4(position,1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
  fragmentShader: `uniform vec3 uC1, uC2; uniform float uLevel; varying vec3 vN, vV;
    void main(){ float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.2);
      vec3 col = mix(uC2, uC1, f) * (0.2 + f * 1.1 + uLevel * 0.7) + vec3(0.06) * (1.0 - f) * (0.3 + uLevel);
      gl_FragColor = vec4(col, 0.8); }`,
}));
world.add(nucleo);

function texturaBrillo() {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d'), gr = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.18, 'rgba(255,255,255,.55)');
  gr.addColorStop(0.5, 'rgba(255,255,255,.12)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}
const texBrillo = texturaBrillo();
const brillo = new THREE.Sprite(new THREE.SpriteMaterial({ map: texBrillo, color: cur.c1, ...aditivo, opacity: 0.9 }));
world.add(brillo);

/* ============================================================ 3. cáscaras geodésicas */
function malla(radio, detalle, opacidad) {
  const g = new THREE.IcosahedronGeometry(radio, detalle);
  const lineas = new THREE.LineSegments(new THREE.WireframeGeometry(g),
    new THREE.LineBasicMaterial({ color: cur.c1, ...aditivo, opacity: opacidad }));
  const nodos = new THREE.Points(g, new THREE.PointsMaterial({ color: cur.c1, size: 0.05, map: texBrillo, ...aditivo, opacity: Math.min(1, opacidad * 4.5) }));
  const grupo = new THREE.Group(); grupo.add(lineas, nodos); grupo.userData = { lineas, nodos };
  return grupo;
}
const mallaA = malla(1.42, 2, 0.14), mallaB = malla(2.0, 1, 0.09);
world.add(mallaA, mallaB);

/* ============================================================ 4. anillos giroscópicos */
const giros = [];
[[1.78, 0.0085, 0.55, 0.0], [2.12, 0.0065, -0.4, 0.9], [2.46, 0.0050, 0.25, -0.6]].forEach(([r, tubo, vel, fase], i) => {
  const pivote = new THREE.Object3D();
  const aro = new THREE.Mesh(new THREE.TorusGeometry(r, tubo, 8, 220), new THREE.MeshBasicMaterial({ color: cur.c1, ...aditivo, opacity: 0.85 }));
  const orb = new THREE.Object3D();
  const perla = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), new THREE.MeshBasicMaterial({ color: 0xffffff, ...aditivo }));
  perla.position.x = r; orb.add(perla);
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: texBrillo, color: cur.c1, ...aditivo, opacity: 0.9 }));
  halo.scale.setScalar(0.5); halo.position.x = r; orb.add(halo);
  pivote.add(aro, orb);
  pivote.rotation.set(1.1 + i * 0.55, i * 0.9, i * 0.4);
  world.add(pivote);
  giros.push({ pivote, aro, orb, halo, vel, fase });
});

/* ============================================================ 5. disco holográfico */
const disco = new THREE.Group();
disco.rotation.x = 0.22; disco.position.y = -0.9;
world.add(disco);

function anilloPlano(r0, r1, th0, len, op) {
  const m = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 120, 1, th0, len), new THREE.MeshBasicMaterial({ color: cur.c1, side: THREE.DoubleSide, ...aditivo, opacity: op }));
  m.rotation.x = -Math.PI / 2; return m;
}
const arcos = [];
for (let k = 0; k < 3; k++) { const a = anilloPlano(3.05, 3.12, 0, 1.25, 0.9); a.userData = { v: 0.35, off: k * 2.09 }; disco.add(a); arcos.push(a); }
for (let k = 0; k < 2; k++) { const a = anilloPlano(3.45, 3.48, 0, 1.9, 0.75); a.userData = { v: -0.22, off: k * 3.14 }; disco.add(a); arcos.push(a); }
for (let k = 0; k < 6; k++) { const a = anilloPlano(2.72, 2.745, 0, 0.42, 0.7); a.userData = { v: 0.6, off: k * 1.047 }; disco.add(a); arcos.push(a); }
const finos = [anilloPlano(3.78, 3.795, 0, 6.283, 0.35), anilloPlano(2.2, 2.212, 0, 6.283, 0.30), anilloPlano(1.15, 1.162, 0, 6.283, 0.25)];
finos.forEach((f) => disco.add(f));

/* marcas (reglas) */
const posT = [], N_T = 240;
for (let i = 0; i < N_T; i++) {
  const a = (i / N_T) * Math.PI * 2, largo = i % 10 === 0, r0 = 3.62, r1 = largo ? 3.78 : 3.69;
  posT.push(Math.cos(a) * r0, 0, Math.sin(a) * r0, Math.cos(a) * r1, 0, Math.sin(a) * r1);
}
const geoT = new THREE.BufferGeometry(); geoT.setAttribute('position', new THREE.Float32BufferAttribute(posT, 3));
const marcas = new THREE.LineSegments(geoT, new THREE.LineBasicMaterial({ color: cur.c1, ...aditivo, opacity: 0.55 }));
disco.add(marcas);

/* ecualizador cilíndrico */
const N_B = 112, R_B = 2.32;
const eq = new THREE.InstancedMesh(new THREE.BoxGeometry(0.028, 1, 0.028).translate(0, 0.5, 0),
  new THREE.MeshBasicMaterial({ ...aditivo, opacity: 0.6 }), N_B);
const sembrado = Array.from({ length: N_B }, () => Math.random() * 6.283);
const alturas = new Float32Array(N_B);
const dummy = new THREE.Object3D(), colTmp = new THREE.Color(), BLANCO = new THREE.Color(0xffffff);
disco.add(eq);

/* ondas de choque (se emiten al hablar) */
const ondas = [];
for (let i = 0; i < 6; i++) {
  const o = new THREE.Mesh(new THREE.RingGeometry(0.985, 1, 180), new THREE.MeshBasicMaterial({ color: cur.c1, side: THREE.DoubleSide, ...aditivo, opacity: 0 }));
  o.rotation.x = -Math.PI / 2; o.visible = false; o.userData = { vida: 0 }; disco.add(o); ondas.push(o);
}
let ultimaOnda = 0;
function emitirOnda(fuerza) {
  const o = ondas.find((x) => !x.visible); if (!o) return;
  o.visible = true; o.userData.vida = 1; o.userData.fuerza = fuerza;
}

/* ============================================================ 6. satélites con estela */
const satelites = [];
const N_E = 56;
for (let k = 0; k < 6; k++) {
  const grupo = new THREE.Group();
  grupo.rotation.set((Math.random() - 0.5) * 1.6, Math.random() * 6.28, (Math.random() - 0.5) * 1.2);
  const a = 2.7 + k * 0.28, b = 2.35 + k * 0.26;
  const orbita = [];
  for (let i = 0; i <= 160; i++) { const t = (i / 160) * Math.PI * 2; orbita.push(Math.cos(t) * a, 0, Math.sin(t) * b); }
  const gO = new THREE.BufferGeometry(); gO.setAttribute('position', new THREE.Float32BufferAttribute(orbita, 3));
  grupo.add(new THREE.Line(gO, new THREE.LineBasicMaterial({ color: cur.c1, ...aditivo, opacity: 0.07 })));
  const estela = new Float32Array(N_E * 3), colE = new Float32Array(N_E * 3);
  for (let i = 0; i < N_E; i++) { const f = Math.pow(1 - i / N_E, 2); colE.set([f, f, f], i * 3); }
  const gE = new THREE.BufferGeometry();
  gE.setAttribute('position', new THREE.BufferAttribute(estela, 3)); gE.setAttribute('color', new THREE.BufferAttribute(colE, 3));
  const linea = new THREE.Line(gE, new THREE.LineBasicMaterial({ color: cur.c1, vertexColors: true, ...aditivo, opacity: 0.9 }));
  linea.frustumCulled = false;
  const punto = new THREE.Sprite(new THREE.SpriteMaterial({ map: texBrillo, color: 0xffffff, ...aditivo, opacity: 0.95 }));
  punto.scale.setScalar(0.22);
  grupo.add(linea, punto); world.add(grupo);
  satelites.push({ grupo, linea, punto, a, b, w: (0.28 + 0.07 * k) * (k % 2 ? -1 : 1), t: Math.random() * 6.28, hist: [] });
}

/* ============================================================ 7. polvo y profundidad */
function nube(n, r0, r1, tam, op) {
  const p = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = r0 + (r1 - r0) * Math.pow(Math.random(), 0.7), th = Math.random() * 6.283, ph = Math.acos(2 * Math.random() - 1);
    p.set([r * Math.sin(ph) * Math.cos(th), (r * Math.cos(ph)) * 0.6, r * Math.sin(ph) * Math.sin(th)], i * 3);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({ color: 0x9fe6ff, size: tam, map: texBrillo, ...aditivo, opacity: op, sizeAttenuation: true }));
}
const polvo = nube(2600, 4.5, 20, 0.07, 0.55), bokeh = nube(36, 3.0, 9, 0.55, 0.14);
scene.add(polvo, bokeh);

/* suelo reticulado */
const suelo = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShaderMaterial({
  ...aditivo, side: THREE.DoubleSide, uniforms: U,
  vertexShader: `varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `uniform vec3 uC1; uniform float uTime, uLevel; varying vec2 vP;
    void main(){
      float r = length(vP); float a = atan(vP.y, vP.x);
      float lr = smoothstep(0.47, 0.5, abs(fract(r) - 0.5));
      float ls = smoothstep(0.485, 0.5, abs(fract(a / (6.2831853 / 64.0)) - 0.5)) * smoothstep(1.2, 3.0, r);
      float fade = smoothstep(11.0, 2.0, r);
      float pulso = exp(-pow((r - fract(uTime * 0.12) * 11.0) * 1.1, 2.0));
      float al = (lr * 0.5 + ls * 0.22) * fade * (0.45 + uLevel * 0.9) + pulso * 0.45 * fade;
      gl_FragColor = vec4(uC1 * 1.2, al * 0.7); }`,
}));
suelo.rotation.x = -Math.PI / 2; suelo.position.y = -2.55; world.add(suelo);

/* fondo atmosférico */
const fondo = new THREE.Mesh(new THREE.PlaneGeometry(90, 52), new THREE.ShaderMaterial({
  ...aditivo, uniforms: U, depthTest: false,
  vertexShader: `varying vec2 vU; void main(){ vU = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `uniform vec3 uC1, uC2; uniform float uLevel, uTime; varying vec2 vU;
    void main(){ vec2 p = (vU - vec2(0.5, 0.52)) * vec2(1.7, 1.0); float d = length(p);
      float g = exp(-d * d * 7.0), h = exp(-d * d * 22.0);
      vec3 col = mix(uC2, uC1, 0.5 + 0.5 * p.x) * g * (0.09 + uLevel * 0.08) + uC1 * h * 0.05;
      gl_FragColor = vec4(col, 1.0); }`,
}));
fondo.position.z = -30; fondo.renderOrder = -10; scene.add(fondo);

/* ============================================================ post-proceso */
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(4, 4, { type: THREE.HalfFloatType, samples: 4 }));
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.55, 0.55, 0.32);
composer.addPass(bloom);
const lente = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, uTime: { value: 0 }, uAmt: { value: 0.0006 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: `uniform sampler2D tDiffuse; uniform float uTime, uAmt; varying vec2 vUv;
    float h(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
    void main(){ vec2 c = vUv - 0.5; float d = dot(c, c); vec2 o = c * d * uAmt * 60.0;
      vec3 col = vec3(texture2D(tDiffuse, vUv + o).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - o).b);
      col *= smoothstep(0.98, 0.22, length(c * vec2(1.0, 1.15)) * 1.25);
      col += (h(vUv * vec2(1920.0, 1080.0) + uTime) - 0.5) * 0.014;
      gl_FragColor = vec4(col, 1.0); }`,
});
composer.addPass(lente);
composer.addPass(new OutputPass());

function ajustar() {
  const w = window.innerWidth, h = window.innerHeight, asp = w / h;
  renderer.setPixelRatio(ratioPixeles()); U.uPx.value = renderer.getPixelRatio(); composer.setPixelRatio(renderer.getPixelRatio());
  renderer.setSize(w, h, false); composer.setSize(w, h); bloom.setSize(w, h);
  camera.aspect = asp; camera.fov = asp < 1 ? 58 : 42;
  const alejar = Math.max(1, 1.45 / asp);
  camera.userData.base = new THREE.Vector3(0, 2.2 * alejar, 8.6 * alejar);
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', ajustar); ajustar();

let ratonX = 0, ratonY = 0, camX = 0, camY = 0;
window.addEventListener('pointermove', (e) => { ratonX = e.clientX / innerWidth - 0.5; ratonY = e.clientY / innerHeight - 0.5; });

/* ============================================================ bucle de animación */
const reloj = new THREE.Clock();
let t = 0, barrido = 0;
const rojoTmp = new THREE.Color();

let cuadros = 0, tFps = performance.now(), fps = 0;
let ultimoCuadro = 0;
function animar(ahoraRaf) {
  requestAnimationFrame(animar);
  if (document.hidden) return;                       // ventana minimizada: no gastar grafica
  // Limite de fotogramas: 60 normalmente y 30 mientras la IA piensa, para dejarle la grafica a ella
  const minMs = (estado === 'pensando' ? 1000 / 30 : 1000 / 60) - 1;
  if (ahoraRaf - ultimoCuadro < minMs) return;
  ultimoCuadro = ahoraRaf;
  cuadros++;
  const ahoraMs = performance.now();
  if (ahoraMs - tFps > 1000) { fps = cuadros * 1000 / (ahoraMs - tFps); cuadros = 0; tFps = ahoraMs; }
  const crudo = reloj.getDelta(), dt = Math.min(0.05, crudo), ds = 1 - Math.exp(-Math.min(0.5, crudo) * 4.5); t += dt;
  const E = ESTADOS[estado] || ESTADOS.inactivo;

  // transición suave de color y parámetros
  cur.c1.lerp(rojoTmp.set(E.c1), ds); cur.c2.lerp(rojoTmp.set(E.c2), ds);
  cur.vel += (E.vel - cur.vel) * ds; cur.swirl += (E.swirl - cur.swirl) * ds; cur.pull += (E.pull - cur.pull) * ds;
  const previo = lvl;
  lvl += (nivelObjetivo - lvl) * (nivelObjetivo > lvl ? 0.45 : 0.12);
  if (lvl - previo > 0.05 && lvl > 0.22 && t - ultimaOnda > 0.2) { emitirOnda(lvl); ultimaOnda = t; }

  U.uTime.value = t; U.uLevel.value = lvl; U.uSwirl.value = cur.swirl; U.uPull.value = cur.pull;
  const v = cur.vel;

  // objetos que cambian de color con el estado
  [mallaA, mallaB].forEach((m) => { m.userData.lineas.material.color.copy(cur.c1); m.userData.nodos.material.color.copy(cur.c1); });
  brillo.material.color.copy(cur.c1);
  giros.forEach((g) => { g.aro.material.color.copy(cur.c1); g.halo.material.color.copy(cur.c1); });
  arcos.forEach((a) => a.material.color.copy(cur.c1));
  finos.forEach((a) => a.material.color.copy(cur.c1));
  marcas.material.color.copy(cur.c1);
  satelites.forEach((s) => s.linea.material.color.copy(cur.c1));

  // núcleo y brillo
  nucleo.scale.setScalar(1 + lvl * 0.55 + Math.sin(t * 1.6) * 0.03);
  brillo.scale.setScalar(1.9 + lvl * 1.3 + Math.sin(t * 1.6) * 0.1);
  brillo.material.opacity = 0.16 + lvl * 0.22;
  plasma.rotation.y += dt * 0.12 * v; plasma.rotation.x = Math.sin(t * 0.2) * 0.15;

  // cáscaras
  mallaA.rotation.y += dt * 0.10 * v; mallaA.rotation.x += dt * 0.04 * v;
  mallaB.rotation.y -= dt * 0.07 * v; mallaB.rotation.z += dt * 0.03 * v;
  mallaA.userData.lineas.material.opacity = 0.12 + lvl * 0.22;
  mallaA.scale.setScalar(1 + lvl * 0.10); mallaB.scale.setScalar(1 + lvl * 0.06);

  // giroscopio
  giros.forEach((g, i) => {
    g.pivote.rotation.x += dt * g.vel * 0.5 * v; g.pivote.rotation.y += dt * g.vel * 0.7 * v;
    g.orb.rotation.z += dt * (1.1 + i * 0.5) * v * (i % 2 ? -1 : 1);
    g.aro.material.opacity = 0.55 + lvl * 0.45;
  });

  // disco
  arcos.forEach((a) => { a.userData.ang = (a.userData.ang ?? a.userData.off) + dt * a.userData.v * v; a.rotation.z = a.userData.ang; });
  marcas.rotation.y += dt * 0.05 * v;
  barrido += dt * 2.2 * v;
  for (let i = 0; i < N_B; i++) {
    const ang = (i / N_B) * Math.PI * 2;
    let h;
    if (estado === 'pensando') {
      let d = Math.abs(((ang - barrido) % 6.2832 + 6.2832) % 6.2832); d = Math.min(d, 6.2832 - d);
      h = 0.06 + 0.75 * Math.pow(Math.max(0, 1 - d / 1.1), 2);
    } else {
      const ruido = 0.5 + 0.5 * Math.sin(t * (2.2 + (i % 9) * 0.55) + sembrado[i] + i * 0.31);
      h = 0.04 + 0.04 * (1 + Math.sin(t * 1.3 + i * 0.22)) + lvl * 0.95 * (0.3 + 0.7 * ruido);
    }
    alturas[i] += (h - alturas[i]) * 0.42;
    dummy.position.set(Math.cos(ang) * R_B, 0, Math.sin(ang) * R_B);
    dummy.rotation.set(0, -ang, 0); dummy.scale.set(1, Math.max(0.02, alturas[i]), 1); dummy.updateMatrix();
    eq.setMatrixAt(i, dummy.matrix);
    colTmp.copy(cur.c1).lerp(BLANCO, Math.min(1, alturas[i] * 0.35)); eq.setColorAt(i, colTmp);
  }
  eq.instanceMatrix.needsUpdate = true; if (eq.instanceColor) eq.instanceColor.needsUpdate = true;
  ondas.forEach((o) => {
    if (!o.visible) return;
    o.userData.vida -= dt * 0.7;
    if (o.userData.vida <= 0) { o.visible = false; return; }
    const p = 1 - o.userData.vida;
    o.scale.setScalar(1.0 + p * 3.1); o.material.color.copy(cur.c1);
    o.material.opacity = Math.pow(o.userData.vida, 1.6) * (0.35 + 0.4 * o.userData.fuerza);
  });

  // satélites
  satelites.forEach((s) => {
    s.t += dt * s.w * v;
    const x = Math.cos(s.t) * s.a, z = Math.sin(s.t) * s.b;
    s.punto.position.set(x, 0, z);
    s.hist.unshift(x, 0, z); if (s.hist.length > N_E * 3) s.hist.length = N_E * 3;
    const arr = s.linea.geometry.attributes.position.array;
    for (let i = 0; i < N_E; i++) { const j = Math.min(i * 3, s.hist.length - 3); arr[i * 3] = s.hist[j] ?? x; arr[i * 3 + 1] = s.hist[j + 1] ?? 0; arr[i * 3 + 2] = s.hist[j + 2] ?? z; }
    s.linea.geometry.attributes.position.needsUpdate = true;
  });
  polvo.rotation.y += dt * 0.012 * v; bokeh.rotation.y -= dt * 0.02;

  // cámara: sutil vaivén + paralaje con el ratón
  camX += (ratonX * 1.6 - camX) * 0.04; camY += (-ratonY * 0.9 - camY) * 0.04;
  const b = camera.userData.base;
  camera.position.set(b.x + camX + Math.sin(t * 0.16) * 0.35, b.y + camY + Math.sin(t * 0.21) * 0.12, b.z - lvl * 0.35);
  camera.lookAt(0, 0.1, 0);

  bloom.strength = 0.5 + lvl * 0.25;
  lente.uniforms.uTime.value = t;
  composer.render();
}
requestAnimationFrame(animar);

/* ============================================================ interfaz (HTML) */
function aRGB(c) { return `${Math.round(c.r * 255)}, ${Math.round(c.g * 255)}, ${Math.round(c.b * 255)}`; }
let ultimoEstado = '', desconectado = false;
setInterval(() => {
  document.documentElement.style.setProperty('--c', aRGB(new THREE.Color().copy(cur.c1).convertLinearToSRGB()));
  const et = desconectado ? 'Desconectado' : (ESTADOS[estado] || ESTADOS.inactivo).label;
  if ($('estado').textContent !== et) $('estado').textContent = et;
  const d = new Date();
  $('hora').textContent = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  $('fecha').textContent = d.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });
}, 120);

/* osciloscopio y traza de nivel */
const osc = $('osc'), trz = $('traza');
const histNivel = new Array(110).fill(0);
function pintaOsc() {
  const c = osc.getContext('2d'), w = osc.width, h = osc.height, col = `rgb(${aRGB(new THREE.Color().copy(cur.c1).convertLinearToSRGB())})`;
  c.clearRect(0, 0, w, h);
  const g = c.createLinearGradient(0, 0, w, 0); g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(0.5, col); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.strokeStyle = g; c.lineWidth = 2; c.shadowColor = col; c.shadowBlur = 10; c.beginPath();
  for (let x = 0; x <= w; x += 3) {
    const u = x / w, env = Math.sin(Math.PI * u);
    const y = h / 2 + Math.sin(u * 26 + t * 7) * (1.5 + lvl * 17) * env * (0.6 + 0.4 * Math.sin(u * 9 - t * 3)) + Math.sin(u * 61 - t * 11) * lvl * 5 * env;
    x === 0 ? c.moveTo(x, y) : c.lineTo(x, y);
  }
  c.stroke();
  // traza histórica
  histNivel.push(lvl); histNivel.shift();
  const c2 = trz.getContext('2d'), W = trz.width, H = trz.height; c2.clearRect(0, 0, W, H);
  c2.fillStyle = `rgba(${aRGB(new THREE.Color().copy(cur.c1).convertLinearToSRGB())}, .55)`;
  const bw = W / histNivel.length;
  histNivel.forEach((v, i) => { const hh = 2 + v * (H - 4); c2.fillRect(i * bw + 1, (H - hh) / 2, Math.max(1, bw - 2), hh); });
  requestAnimationFrame(pintaOsc);
}
pintaOsc();

/* chat */
const ROL = { tu: 'Tú', jarvis: 'Jarvis', sistema: 'Sistema' };
let mensajes = [];
function pintaChat(lista) {
  const chat = $('chat'), visibles = lista.slice(-3);
  const firma = JSON.stringify(visibles);
  if (chat.dataset.firma === firma) return; chat.dataset.firma = firma;
  chat.textContent = '';
  visibles.forEach(([rol, texto]) => {
    const d = document.createElement('div'); d.className = `msg ${rol}`;
    const b = document.createElement('b'); b.textContent = ROL[rol] || rol;
    d.append(b, document.createTextNode(texto)); chat.append(d);
  });
}
function nuevosMensajes(lista) { mensajes = lista; pintaChat(mensajes); }

/* panel de datos */
function formatoUp(s) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return h ? `${h} h ${m} min` : m ? `${m} min` : `${s} s`; }
function pintaDatos(d) {
  $('n-notas').textContent = d.notas ?? 0;
  $('ia-linea').textContent = d.ia || 'Sin IA';
  $('s-ia').textContent = d.ia || '—';
  const voz = $('s-voz'); voz.textContent = d.voz ? 'ElevenLabs' : 'Solo texto'; voz.className = d.voz ? 'ok' : 'mal';
  const mic = $('s-mic'); mic.textContent = d.audio ? 'Activo' : 'Sin audio'; mic.className = d.audio ? 'ok' : 'mal';
  const gg = $('s-google'), gEst = d.google || 'sin credenciales';
  gg.textContent = gEst === 'conectado' ? 'Calendario, Gmail y Drive' : 'No conectado'; gg.className = gEst === 'conectado' ? 'ok' : 'mal';
  $('s-wake').textContent = `«${d.wake || 'jarvis'}»`;
  $('s-up').textContent = formatoUp(d.activo_seg || 0);
  const ul = $('recientes'); ul.textContent = '';
  const r = d.recientes || [];
  if (!r.length) { const li = document.createElement('li'); li.className = 'vacio'; li.textContent = 'Aún no hay notas. Dile a Jarvis que apunte algo.'; ul.append(li); }
  r.forEach((n) => { const li = document.createElement('li'); const a = document.createElement('span'), b = document.createElement('span'); a.textContent = n.titulo; b.textContent = n.hace; li.append(a, b); ul.append(li); });
}
async function cargaDatos() {
  try { const r = await fetch(`/datos?t=${encodeURIComponent(TOKEN)}`); if (r.ok) pintaDatos(await r.json()); } catch (e) { /* sin servidor */ }
}

/* envío de texto */
$('form').addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const inp = $('texto'), txt = inp.value.trim(); if (!txt) return;
  inp.value = '';
  if (DEMO) { nuevosMensajes([...mensajes, ['tu', txt]]); return; }
  try { await fetch(`/enviar?t=${encodeURIComponent(TOKEN)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ texto: txt }) }); }
  catch (e) { nuevosMensajes([...mensajes, ['sistema', 'No he podido enviar el mensaje: Jarvis no responde.']]); }
});

/* ============================================================ conexión con Jarvis */
if (DEMO) {
  const demoMsgs = [['tu', 'Jarvis, ¿qué decidimos con Pedro sobre el proyecto Atlas?'], ['jarvis', 'Lo lanzaréis en noviembre, con Python y un presupuesto de tres mil euros.']];
  nuevosMensajes(demoMsgs);
  pintaDatos({ notas: 128, ia: 'Ollama · qwen3.8:27b', voz: true, audio: true, google: 'conectado', wake: 'jarvis', activo_seg: 4260,
    recientes: [{ titulo: 'Reunión con Pedro', hace: '12 min' }, { titulo: 'Idea: canal de IA', hace: '2 h' }, { titulo: 'Contrato del local', hace: '1 d' }, { titulo: 'Receta de lentejas', hace: '3 d' }, { titulo: 'Diario 2026-10-12', hace: '3 d' }] });
  const ciclo = ['inactivo', 'escuchando', 'pensando', 'hablando'];
  let t0 = performance.now();
  setInterval(() => {
    const s = (performance.now() - t0) / 1000;
    estado = DEMO === 'ciclo' ? ciclo[Math.floor(s / 5) % 4] : DEMO;
    const base = estado === 'hablando' ? 0.62 : estado === 'escuchando' ? 0.5 : estado === 'inactivo' ? 0.06 : 0.0;
    nivelObjetivo = base ? Math.min(1, base * (0.55 + 0.45 * Math.abs(Math.sin(s * 9.1)) + 0.25 * Math.sin(s * 3.3))) : 0;
  }, 33);
} else {
  let errores = 0;
  const conectar = () => {
    const es = new EventSource(`/eventos?t=${encodeURIComponent(TOKEN)}`);
    es.onmessage = (ev) => {
      errores = 0; desconectado = false; const d = JSON.parse(ev.data);
      if (d.e) estado = d.e; nivelObjetivo = d.n || 0;
      if (d.m) nuevosMensajes(d.m);
    };
    es.onerror = () => {
      if (++errores >= 4) { estado = 'error'; nivelObjetivo = 0; desconectado = true; }
      if (errores >= 40) { es.close(); window.close(); }
    };
  };
  conectar(); cargaDatos(); setInterval(cargaDatos, 6000);
  setInterval(() => {                                  // informa a Jarvis de la fluidez de la ventana
    fetch(`/telemetria?t=${encodeURIComponent(TOKEN)}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fps: Math.round(fps) }) }).catch(() => {});
  }, 5000);
}
