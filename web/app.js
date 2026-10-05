import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
// @@GEOMETRIA@@

const CFG = window.__CFG;
const $ = (s, r = document) => r.querySelector(s);
function h(tag, attrs = {}, ...hijos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') e.className = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v);
  }
  for (const c of hijos.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const fmt = (n, d = 0) => Number(n).toLocaleString('es-UY', { maximumFractionDigits: d, minimumFractionDigits: d });

/* ---------------------------------------------------------------- estado */
const POR_DEFECTO = { ancho_total: 1880, alto_total: 2000, profundidad: 193, n_tablas: null, semilla: 0, zocalo: true,
  zocalo_alto: 55, zocalo_prof: 15, anclaje: 'ambos', t: 15, h: 0, fresa: 6, sep_min: 2, n_ranuras: null };
function leerHash() {
  try { const m = location.hash.match(/c=([^&]+)/); return m ? JSON.parse(decodeURIComponent(escape(atob(decodeURIComponent(m[1]))))) : {}; }
  catch (e) { return {}; }
}
function guardarHash() {
  const cambios = {};
  for (const k of Object.keys(POR_DEFECTO)) if (estado[k] !== POR_DEFECTO[k]) cambios[k] = estado[k];
  history.replaceState(null, '', Object.keys(cambios).length ? '#c=' + encodeURIComponent(btoa(unescape(encodeURIComponent(JSON.stringify(cambios))))) : location.pathname + location.search);
}
let estado = { ...POR_DEFECTO, ...leerHash() };
let ultimo = null;           // último resultado de calcular()
const controles = {};        // id -> {rango, num, it}

/* ---------------------------------------------------------------- worker */
const worker = new Worker(URL.createObjectURL(new Blob([$('#worker-src').textContent], { type: 'text/javascript' })));
const pendientes = new Map(); let sigId = 1;
worker.onmessage = (e) => {
  const m = e.data;
  if (m.progreso) { $('#cargando-texto').textContent = m.progreso; return; }
  const p = pendientes.get(m.id); if (!p) return; pendientes.delete(m.id);
  m.error ? p.rej(new Error(m.error)) : p.res(m);
};
worker.onerror = (e) => { $('#cargando-texto').textContent = 'No se pudo iniciar: ' + (e.message || 'error del worker'); };
const pedir = (tipo, datos) => new Promise((res, rej) => { const id = sigId++; pendientes.set(id, { res, rej }); worker.postMessage({ id, tipo, datos }); });

/* ---------------------------------------------------------------- controles */
const CONTROLES = [
  { grupo: 'Medidas', items: [
    { id: 'ancho_total', et: 'Ancho total', u: 'mm', paso: 10, lim: ['ancho_min', 'ancho_max'], ayuda: 'De punta a punta, contando lo que sobresalen las tablas (100 mm a cada lado). El sistema elige la menor cantidad de postes posible.' },
    { id: 'alto_total', et: 'Alto total', u: 'mm', paso: 10, lim: ['alto_min', 'alto_max'], ayuda: 'Queda exacto: las ranuras se reparten con una separación uniforme que nunca baja de 110 mm.' },
    { id: 'profundidad', et: 'Profundidad', u: 'mm', paso: 1, lim: ['profundidad_min', 'profundidad_max'], ayuda: 'Con 193 mm o menos entran más piezas por placa y se usa menos material.' } ] },
  { grupo: 'Estantes', items: [
    { id: 'n_tablas', et: 'Cantidad de tablas', u: '', paso: 1, auto: 'n_tablas', lim: ['n_tablas_min', 'n_tablas_max_ui'], ayuda: 'Siempre hay una tabla abajo y una arriba que atan todos los postes; el resto se reparte al azar.' } ],
    extra: () => h('button', { class: 'prim', onclick: () => { estado.semilla = Math.floor(Math.random() * 1000); programar(0); } }, 'Redistribuir tablas al azar') },
  { grupo: 'Zócalo', custom: 'zocalo' },
  { grupo: 'Anclaje a la pared', custom: 'anclaje' },
  { grupo: 'Avanzado (taller)', abierto: false, items: [
    { id: 't', et: 'Espesor real de la placa', u: 'mm', paso: 0.1, lim: [5, 30], ayuda: 'Medilo con calibre: define el ancho de las ranuras.' },
    { id: 'h', et: 'Holgura de los encastres', u: 'mm', paso: 0.05, lim: [0, 0.5] },
    { id: 'fresa', et: 'Fresa de la CNC', u: 'mm', paso: 0.5, lim: [3, 10.5], ayuda: 'Define los alivios de las esquinas y la separación entre piezas.' },
    { id: 'sep_min', et: 'Separación mínima entre tablas', u: 'ranuras', paso: 1, lim: [1, 5], ayuda: 'Con 2 ranuras quedan al menos 235 mm libres para libros.' },
    { id: 'n_ranuras', et: 'Cantidad de ranuras', u: '', paso: 1, auto: 'n_ranuras', lim: [4, 40], ayuda: 'Automático: la mayor cantidad que respeta los 110 mm entre ranuras.' } ] },
];

function crearControl(it) {
  const rango = h('input', { type: 'range', step: it.paso }), num = h('input', { type: 'number', step: it.paso });
  const etiqueta = h('label', { title: it.ayuda || '' }, it.et);
  if (it.auto) {
    const a = h('button', { class: 'auto', title: 'Dejar que el sistema lo elija', onclick: () => { estado[it.id] = null; programar(0); } }, 'automático');
    etiqueta.append(a);
  }
  const fila = h('div', { class: 'ctl' }, etiqueta, h('div', { class: 'fila' }, rango, num, h('span', { class: 'u' }, it.u)));
  if (typeof it.lim[0] === 'number') { rango.min = num.min = it.lim[0]; rango.max = num.max = it.lim[1]; }
  const poner = (v) => { rango.value = num.value = v; };
  rango.oninput = () => { poner(rango.value); estado[it.id] = +rango.value; programar(120); };
  num.onchange = () => { if (num.value === '') return; poner(num.value); estado[it.id] = +num.value; programar(0); };
  controles[it.id] = { rango, num, it, fila, poner };
  return fila;
}
function construirPanel() {
  const cont = $('#controles');
  for (const g of CONTROLES) {
    const caja = g.abierto === false ? h('details', { class: 'grupo' }, h('summary', {}, g.grupo)) : h('section', { class: 'grupo' }, h('h2', {}, g.grupo));
    if (g.custom === 'zocalo') {
      const chk = h('input', { type: 'checkbox', id: 'zocalo' }); chk.checked = estado.zocalo;
      chk.onchange = () => { estado.zocalo = chk.checked; $('#zocalo-medidas').style.display = chk.checked ? '' : 'none'; programar(0); };
      caja.append(h('label', { class: 'check', title: 'Recorte en la base trasera de cada poste para apoyar la biblioteca por delante de un zócalo.' }, chk, 'Tengo zócalo en la pared'));
      const med = h('div', { id: 'zocalo-medidas' },
        crearControl({ id: 'zocalo_alto', et: 'Alto del zócalo', u: 'mm', paso: 1, lim: [0, 150] }),
        crearControl({ id: 'zocalo_prof', et: 'Espesor del zócalo', u: 'mm', paso: 1, lim: [0, 50] }));
      med.style.display = estado.zocalo ? '' : 'none'; caja.append(med);
    } else if (g.custom === 'anclaje') {
      const sel = h('select', {}, h('option', { value: 'ambos' }, 'Arriba y abajo (recomendado)'), h('option', { value: 'superior' }, 'Solo arriba'), h('option', { value: 'ninguno' }, 'Sin anclaje'));
      sel.value = estado.anclaje; sel.onchange = () => { estado.anclaje = sel.value; programar(0); };
      caja.append(h('div', { class: 'ctl' }, h('label', { title: 'Escuadras en U atornilladas a la pared: evitan que la biblioteca vuelque.' }, 'Fijación'), h('div', { class: 'fila' }, sel)));
      caja.append(h('p', { class: 'nota-chica' }, 'Una biblioteca cargada vuelca con muy poca fuerza: fijarla a la pared es parte del producto.'));
    } else {
      for (const it of g.items) caja.append(crearControl(it));
      if (g.extra) caja.append(g.extra());
    }
    cont.append(caja);
  }
}
function sincronizarControles(r) {
  const m = r.ok ? r.medidas : null, l = r.limites || {};
  for (const [id, c] of Object.entries(controles)) {
    const it = c.it;
    if (Array.isArray(it.lim) && typeof it.lim[0] === 'string') {
      const mn = it.lim[0] === 'n_tablas_min' ? (m ? m.n_tablas_min : 2) : l[it.lim[0]];
      const mx = it.lim[1] === 'n_tablas_max_ui' ? 60 : l[it.lim[1]];
      if (mn != null) c.rango.min = c.num.min = mn; if (mx != null) c.rango.max = c.num.max = mx;
    }
    let v = estado[id];
    if (v == null && m) v = id === 'n_tablas' ? m.n_tablas : id === 'n_ranuras' ? m.n_ranuras : v;
    if (v != null && document.activeElement !== c.num) c.poner(v);
    if (it.auto) c.fila.querySelector('.auto').style.visibility = estado[id] == null ? 'hidden' : 'visible';
  }
}

/* ---------------------------------------------------------------- cálculo */
let enCurso = null, hayPendiente = false, temporizador = null, tokenPlan = 0;
function programar(ms) { clearTimeout(temporizador); temporizador = setTimeout(recalcular, ms); guardarHash(); }
function recalcular() {
  if (enCurso) { hayPendiente = true; return enCurso; }
  enCurso = (async () => { do { hayPendiente = false; await ciclo(); } while (hayPendiente); enCurso = null; })();
  return enCurso;
}
async function ciclo() {
  $('#estado-calculo').textContent = 'Calculando…';
  const datos = JSON.stringify(estado);
  let r, ms;
  try { const x = await pedir('calcular', datos); r = JSON.parse(x.resultado); ms = x.ms; }
  catch (err) { $('#estado-calculo').textContent = 'Error: ' + err.message; return; }
  ultimo = r; aplicarResultado(r, ms);
  if (r.ok) programarPlan(datos);
}
function programarPlan(datos) {
  const token = ++tokenPlan; $('#plan-contenido').style.opacity = .5;
  setTimeout(async () => {
    if (token !== tokenPlan) return;
    try { const x = await pedir('plan_corte', datos); if (token === tokenPlan) mostrarPlan(JSON.parse(x.resultado)); } catch (e) { /* se ignora */ }
  }, 350);
}

/* ---------------------------------------------------------------- resultado */
function aplicarResultado(r, ms) {
  sincronizarControles(r);
  const msg = $('#mensajes'); msg.replaceChildren();
  for (const e of r.errores || []) msg.append(h('div', { class: 'msg err' }, e));
  for (const a of r.avisos || []) msg.append(h('div', { class: 'msg av' }, a));
  for (const n of r.notas || []) msg.append(h('div', { class: 'msg nota' }, n));
  $('#estado-calculo').textContent = r.ok ? `Calculado en ${ms} ms` : 'Hay medidas que corregir';
  if (!r.ok) return;
  dibujar(r); mostrarResumen(r); mostrarDatos(r);
}
function mostrarResumen(r) {
  const m = r.medidas, cont = $('#resumen'); cont.replaceChildren();
  const pill = (g, c) => h('div', { class: 'pill' }, h('b', {}, g), h('span', {}, c));
  cont.append(pill(`${fmt(m.ancho_total)} × ${fmt(m.alto_total)} × ${fmt(m.profundidad)} mm`, 'ancho × alto × profundidad'),
    pill(`${m.n_postes} postes · ${m.n_tablas} tablas`, `luz de ${fmt(m.luz)} mm entre postes`),
    pill(`≈ ${fmt(m.peso_kg)} kg`, 'peso aproximado'),
    pill(`${m.placas_minimas} placas (mín.)`, `≈ U$S ${fmt(m.costo_minimo_usd)} de material`));
}
function mostrarPlan(p) {
  const c = $('#plan-contenido'); c.style.opacity = 1; c.replaceChildren();
  if (!p.ok) return;
  c.append(h('div', { class: 'tarjetas' },
    h('div', { class: 'tarjeta' }, h('b', {}, p.placas_nuevas), h('span', {}, 'placas de 2440 × 1220 mm')),
    h('div', { class: 'tarjeta' }, h('b', {}, `U$S ${fmt(p.costo_usd, 2)}`), h('span', {}, 'costo de material (referencia)')),
    h('div', { class: 'tarjeta' }, h('b', {}, `${p.aprovechamiento} %`), h('span', {}, 'aprovechamiento de las placas')),
    h('div', { class: 'tarjeta' }, h('b', {}, p.columnas), h('span', {}, 'columnas de piezas por placa'))));
  const caja = h('div', { class: 'svgbox' }); caja.innerHTML = p.svg;
  c.append(h('h3', {}, 'Cómo se cortan las piezas (las piezas no se giran: respetan la veta)'), caja);
  if (p.sobrantes.length) c.append(h('p', { class: 'nota-chica' }, 'Sobrantes reutilizables que quedan: ' + p.sobrantes.map(s => `${s[0]} × ${s[1]} mm`).join(', ') + '.'));
  const m = ultimo && ultimo.ok ? ultimo.medidas : null;
  const resumen = $('#resumen').lastChild;
  if (resumen && m) { resumen.firstChild.textContent = `${p.placas_nuevas} placas`; resumen.lastChild.textContent = `U$S ${fmt(p.costo_usd)} de material`; }
}
function mostrarDatos(r) {
  const m = r.medidas, c = $('#datos-contenido'); c.replaceChildren();
  const tabla = (cab, filas) => h('table', {}, h('tr', {}, cab.map(x => h('th', {}, x))), filas.map(f => h('tr', {}, f.map(x => h('td', {}, x)))));
  c.append(h('h3', {}, 'Piezas'), tabla(['Pieza', 'Cantidad', 'Medidas (mm)'], r.piezas.map(p => [p.nombre.replaceAll('_', ' '), p.cantidad, `${fmt(p.ancho)} × ${fmt(p.largo, 1)} × ${p.espesor}`])));
  c.append(h('h3', {}, 'Estructura'), tabla(['Dato', 'Valor'], [
    ['Luz entre postes', `${fmt(m.luz, 1)} mm (máx. ${fmt(m.luz_max)} mm)`],
    ['Flecha estimada de una tabla con libros', `${fmt(m.flecha, 1)} mm (luz/${fmt(m.luz / m.flecha)})`],
    ['Separación entre ranuras', `${fmt(m.separacion, 1)} mm`],
    ['Espacio libre entre tablas (para libros)', `${fmt(m.espacio_libre)} mm`],
    ['Ranuras por poste', m.n_ranuras], ['Tablas (mínimo estructural)', `${m.n_tablas} (${m.n_tablas_min})`]]));
  c.append(h('p', { class: 'nota-chica' }, 'Valores estimados por cálculo, a confirmar con el prototipo físico.'));
  if (r.herrajes) {
    const u = r.herrajes.escuadra;
    c.append(h('h3', {}, `Escuadra en U (${m.n_escuadras} unidades)`), tabla(['Dato', 'Valor'], [
      ['Chapa', `${u.chapa} mm`], ['Alto', `${u.alto} mm`], ['Largo de los brazos', `${u.largo_brazos} mm`],
      ['Ancho exterior (= espesor de la placa)', `${fmt(u.ancho_exterior, 1)} mm`], ['Ancho interior', `${fmt(u.ancho_interior, 1)} mm`],
      ['Agujero de los brazos', `Ø${fmt(u.diametro_agujero_brazos, 1)} mm`], ['Radio mínimo de las puntas', `${u.radio_puntas_min} mm`]]));
    c.append(h('h3', {}, 'Replanteo en la pared'), h('p', { class: 'nota-chica' }, 'Posición del tornillo de cada escuadra (y desde la cara izquierda del primer poste; z desde el piso).'),
      tabla(['Poste', 'y (mm)', 'z superior (mm)', 'z inferior (mm)'], r.herrajes.replanteo.map(f => [f.poste + 1, fmt(f.y_centro, 1), f.z_superior != null ? fmt(f.z_superior) : '—', f.z_inferior != null ? fmt(f.z_inferior) : '—'])));
  }
}

/* ---------------------------------------------------------------- escena 3D */
const lienzo = $('#lienzo'), canvas = $('#c');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
const escena = new THREE.Scene();
const camara = new THREE.PerspectiveCamera(35, 1, 10, 60000);
const orbita = new OrbitControls(camara, canvas);
orbita.addEventListener('change', () => pedirRender());
escena.add(new THREE.HemisphereLight(0xffffff, 0xcdbfa8, 1.45));
const sol = new THREE.DirectionalLight(0xffffff, 0.95); sol.castShadow = true; sol.shadow.mapSize.set(2048, 2048); sol.shadow.bias = -0.0004;
escena.add(sol); escena.add(sol.target);
const grupo = new THREE.Group(); escena.add(grupo);
const grupoCotas = new THREE.Group(); escena.add(grupoCotas);
const pared = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshStandardMaterial({ color: 0xf8f6f2, roughness: 1 }));
pared.receiveShadow = true; pared.position.z = -1; escena.add(pared);
const piso = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshStandardMaterial({ color: 0xe9e3d8, roughness: 1 }));
piso.rotation.x = -Math.PI / 2; piso.receiveShadow = true; escena.add(piso);
const matPoste = new THREE.MeshStandardMaterial({ color: 0xd2b180, roughness: .75, metalness: 0 });
const matTabla = new THREE.MeshStandardMaterial({ color: 0xe3c795, roughness: .75, metalness: 0 });
const matLinea = new THREE.LineBasicMaterial({ color: 0x7a5a2e, transparent: true, opacity: .45 });
let caja = new THREE.Box3(new THREE.Vector3(-900, 0, 0), new THREE.Vector3(900, 2000, 193)), tamPrevio = null;
let etiquetas = [];

let renderPedido = false;
function pedirRender() { if (!renderPedido) { renderPedido = true; requestAnimationFrame(() => { renderPedido = false; renderizar(); }); } }
function renderizar() { renderer.render(escena, camara); posicionarEtiquetas(); }
function ajustarTamano() {
  const w = lienzo.clientWidth, hh = lienzo.clientHeight; if (!w || !hh) return;
  renderer.setSize(w, hh, false); camara.aspect = w / hh; camara.updateProjectionMatrix(); pedirRender();
}
new ResizeObserver(ajustarTamano).observe(lienzo);

function liberar(obj) { obj.traverse(o => { if (o.geometry) o.geometry.dispose(); }); obj.clear(); }
function dibujar(r) {
  liberar(grupo);
  const geos = {};
  for (const pz of r.piezas) { const g = geometriaPieza(pz); geos[pz.nombre] = { g, e: new THREE.EdgesGeometry(g, 30) }; }
  for (const inst of r.instancias) {
    const { g, e } = geos[inst.pieza], pos = posicionInstancia(inst);
    const malla = new THREE.Mesh(g, inst.tipo === 'poste' ? matPoste : matTabla);
    malla.position.set(...pos); malla.castShadow = malla.receiveShadow = true; malla.userData.inst = inst;
    const lin = new THREE.LineSegments(e, matLinea); lin.position.set(...pos);
    grupo.add(malla, lin);
  }
  grupo.position.x = 0; grupo.updateMatrixWorld(true);
  const c0 = new THREE.Box3().setFromObject(grupo);
  grupo.position.x = -(c0.min.x + c0.max.x) / 2; grupo.updateMatrixWorld(true);
  caja = new THREE.Box3().setFromObject(grupo);
  const tam = caja.getSize(new THREE.Vector3()), ctr = caja.getCenter(new THREE.Vector3());
  const ap = Math.max(tam.x, tam.y) * .9;
  pared.scale.set(Math.max(tam.x + 2400, 4200), Math.max(tam.y + 700, 3000), 1); pared.position.set(ctr.x, pared.scale.y / 2, -1);
  piso.scale.set(pared.scale.x, tam.z + 2600, 1); piso.position.set(ctr.x, -0.5, (tam.z + 2600) / 2 - 1300);
  sol.position.set(ctr.x + tam.x * .18, tam.y * 1.25 + 500, tam.z + Math.max(tam.x, tam.y) * 1.3);
  sol.target.position.set(ctr.x, tam.y * .4, 0);
  Object.assign(sol.shadow.camera, { left: -ap, right: ap, top: ap, bottom: -ap, near: 10, far: Math.max(tam.x, tam.y) * 4 + 2000 }); sol.shadow.camera.updateProjectionMatrix();
  dibujarCotas(tam);
  const cambioGrande = !tamPrevio || Math.abs(tam.x - tamPrevio.x) / tamPrevio.x > .25 || Math.abs(tam.y - tamPrevio.y) / tamPrevio.y > .25;
  tamPrevio = tam.clone();
  if (cambioGrande) vista('persp'); else pedirRender();
}
function cota(a, b, tick, texto, mid) {
  const geo = new THREE.BufferGeometry().setFromPoints([a, b, a.clone().add(tick), a.clone().sub(tick), b.clone().add(tick), b.clone().sub(tick)]);
  const l = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0x3b3b3b })); grupoCotas.add(l);
  const div = h('div', { class: 'cota' }, texto); $('#etiquetas').append(div); etiquetas.push({ div, pos: mid });
}
function dibujarCotas(tam) {
  liberar(grupoCotas); etiquetas.forEach(e => e.div.remove()); etiquetas = [];
  const m = ultimo.medidas, x0 = caja.min.x, x1 = caja.max.x, zf = caja.max.z, v = (x, y, z) => new THREE.Vector3(x, y, z);
  cota(v(x0, tam.y + 170, zf), v(x1, tam.y + 170, zf), v(0, 40, 0), `${fmt(m.ancho_total)} mm`, v((x0 + x1) / 2, tam.y + 170, zf));
  cota(v(x0 - 160, 0, 0), v(x0 - 160, tam.y, 0), v(40, 0, 0), `${fmt(m.alto_total)} mm`, v(x0 - 160, tam.y / 2, 0));
  cota(v(x1 + 160, 0, 0), v(x1 + 160, 0, zf), v(40, 0, 0), `${fmt(m.profundidad)} mm`, v(x1 + 160, 0, zf / 2));
  alternarCotas();
}
function alternarCotas() { const on = $('#chk-cotas').checked; grupoCotas.visible = on; etiquetas.forEach(e => e.div.style.display = on ? '' : 'none'); pedirRender(); }
function posicionarEtiquetas() {
  if (!$('#chk-cotas').checked) return;
  const w = lienzo.clientWidth, hh = lienzo.clientHeight;
  for (const e of etiquetas) {
    const p = e.pos.clone().project(camara);
    const visible = p.z > -1 && p.z < 1;
    e.div.style.display = visible ? '' : 'none';
    e.div.style.left = ((p.x + 1) / 2 * w) + 'px'; e.div.style.top = ((1 - p.y) / 2 * hh) + 'px';
  }
}
function vista(nombre) {
  const tam = caja.getSize(new THREE.Vector3()), ctr = caja.getCenter(new THREE.Vector3());
  const fov = camara.fov * Math.PI / 180, asp = camara.aspect;
  const lateral = nombre === 'lateral';
  const dAlto = (tam.y * 1.32) / (2 * Math.tan(fov / 2)), dAncho = ((lateral ? tam.z * 2.5 : tam.x * 1.15)) / (2 * Math.tan(fov / 2) * asp);
  const dist = Math.max(dAlto, dAncho) + tam.z;
  const dir = nombre === 'frontal' ? new THREE.Vector3(0, 0.02, 1) : lateral ? new THREE.Vector3(1, 0.04, 0.0001) : new THREE.Vector3(0.62, 0.24, 1);
  camara.position.copy(ctr).add(dir.normalize().multiplyScalar(dist));
  orbita.target.copy(ctr).add(new THREE.Vector3(0, tam.y * 0.04, 0)); camara.near = Math.max(10, dist / 200); camara.far = dist * 20; camara.updateProjectionMatrix(); orbita.update(); pedirRender();
}
// ayuda al pasar el mouse
const rayo = new THREE.Raycaster(), puntero = new THREE.Vector2(); let tipPend = null;
canvas.addEventListener('pointermove', (ev) => { tipPend = ev; requestAnimationFrame(actualizarTip); });
canvas.addEventListener('pointerleave', () => { $('#tip').style.display = 'none'; });
function actualizarTip() {
  const ev = tipPend; if (!ev || !ultimo || !ultimo.ok) return; tipPend = null;
  const r = canvas.getBoundingClientRect(); puntero.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  rayo.setFromCamera(puntero, camara);
  const hit = rayo.intersectObjects(grupo.children.filter(o => o.isMesh), false)[0], tip = $('#tip');
  if (!hit) { tip.style.display = 'none'; return; }
  const inst = hit.object.userData.inst, pz = ultimo.piezas.find(p => p.nombre === inst.pieza);
  let txt;
  if (inst.tipo === 'poste') txt = `Poste ${inst.nombre.split('_')[1]} · alto ${fmt(pz.largo)} mm`;
  else { const t = ultimo.tablas[+inst.nombre.split('_')[1] - 1]; txt = `Tabla ${inst.nombre.split('_')[1]} · cruza los postes ${t.poste_ini + 1} a ${t.poste_fin + 1} · altura ${fmt(t.z)} mm · largo ${fmt(pz.largo)} mm`; }
  tip.textContent = txt; tip.style.display = 'block'; tip.style.left = Math.min(ev.clientX - r.left + 14, r.width - 290) + 'px'; tip.style.top = (ev.clientY - r.top + 14) + 'px';
}

/* ---------------------------------------------------------------- interfaz */
for (const b of document.querySelectorAll('#tabs button')) b.onclick = () => {
  document.querySelectorAll('#tabs button').forEach(x => x.classList.toggle('act', x === b));
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('act', t.id === b.dataset.tab)); ajustarTamano();
};
for (const b of document.querySelectorAll('#barra button')) b.onclick = () => vista(b.dataset.vista === 'encuadrar' ? 'persp' : b.dataset.vista);
$('#chk-cotas').onchange = alternarCotas;
$('#chk-pared').onchange = () => { pared.visible = $('#chk-pared').checked; pedirRender(); };
$('#btn-reiniciar').onclick = () => { estado = { ...POR_DEFECTO }; $('#zocalo').checked = true; $('#zocalo-medidas').style.display = ''; document.querySelector('#controles select').value = 'ambos'; programar(0); };
$('#btn-enlace').onclick = async () => { guardarHash(); try { await navigator.clipboard.writeText(location.href); $('#btn-enlace').textContent = '¡Copiado!'; } catch (e) { $('#btn-enlace').textContent = 'Copialo de la barra'; } setTimeout(() => $('#btn-enlace').textContent = 'Copiar enlace', 1800); };

/* ---------------------------------------------------------------- arranque */
(async function iniciar() {
  construirPanel(); ajustarTamano();
  try {
    const archivos = {}; for (const nombre of CFG.archivos) archivos[nombre] = $('#py_' + nombre.replace('.py', '')).textContent;
    const ini = await pedir('init', { pyodideUrl: new URL(CFG.pyodideUrl, location.href).href, archivos });
    const v = JSON.parse(ini.resultado);
    for (const [k, val] of Object.entries({ t: v.t, h: v.h, fresa: v.fresa })) if (!(k in leerHash())) estado[k] = val;
    $('#cargando-texto').textContent = 'Calculando el primer diseño…';
    await recalcular();
    $('#cargando').classList.add('oculto');
    window.__listo = true;
  } catch (err) {
    $('#cargando-texto').textContent = 'No se pudo cargar el motor de cálculo: ' + err.message + '. Revisá tu conexión a internet.';
  }
})();

// ganchos para pruebas
window.__app = {
  estado: () => estado, ultimo: () => ultimo, vista, renderizar,
  aplicar: async (cambios) => { Object.assign(estado, cambios); await recalcular(); renderizar(); return ultimo; },
  caja: () => { const s = caja.getSize(new THREE.Vector3()); return { x: s.x, y: s.y, z: s.z }; },
  mallas: () => grupo.children.filter(o => o.isMesh).length,
};
