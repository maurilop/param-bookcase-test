import * as THREE from 'three';

/* Geometría de las piezas. Ejes del mundo (Y hacia arriba): X = largo del mueble, Y = altura, Z = profundidad
   (la pared está en Z = 0 y el frente mira hacia +Z). Se corresponde con los ejes del diseño así:
   x_diseño (profundidad) -> Z, y_diseño (largo) -> X, z_diseño (altura) -> Y. */

export function limpiarPuntos(pts) {
  const out = [];
  for (const p of pts) {
    const q = out[out.length - 1];
    if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-6) out.push(p);
  }
  if (out.length > 1) {
    const a = out[0], b = out[out.length - 1];
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) <= 1e-6) out.pop();
  }
  return out;
}

/* pz = {tipo: 'poste' | 'tabla', contorno: [[x, y]...], huecos: [[[x, y]...]...], espesor}
   El contorno viene en el plano de la pieza: (x = profundidad, y = altura) en los postes y
   (x = profundidad, y = largo) en las tablas. Se extruye el espesor. */
export function geometriaPieza(pz) {
  const v2 = pts => limpiarPuntos(pts).map(p => new THREE.Vector2(p[0], p[1]));
  const forma = new THREE.Shape(v2(pz.contorno));
  for (const h of pz.huecos || []) forma.holes.push(new THREE.Path(v2(h)));
  const g = new THREE.ExtrudeGeometry(forma, { depth: pz.espesor, bevelEnabled: false, curveSegments: 1, steps: 1 });
  const pos = g.attributes.position;
  const esPoste = pz.tipo === 'poste';
  // (u, v, w) = (x_diseño, y_contorno, espesor)
  //   poste: v = altura (Y), w = largo del mueble (X)  -> (X, Y, Z) = (w, v, u)   (permutación impar)
  //   tabla: v = largo (X),  w = altura (Y)            -> (X, Y, Z) = (v, w, u)   (permutación par)
  for (let i = 0; i < pos.count; i++) {
    const u = pos.getX(i), v = pos.getY(i), w = pos.getZ(i);
    if (esPoste) pos.setXYZ(i, w, v, u); else pos.setXYZ(i, v, w, u);
  }
  if (esPoste) {                                   // permutación impar: se invierte el orden de cada triángulo
    for (let i = 0; i + 2 < pos.count; i += 3) {
      const x = pos.getX(i + 1), y = pos.getY(i + 1), z = pos.getZ(i + 1);
      pos.setXYZ(i + 1, pos.getX(i + 2), pos.getY(i + 2), pos.getZ(i + 2));
      pos.setXYZ(i + 2, x, y, z);
    }
  }
  pos.needsUpdate = true;
  g.computeVertexNormals();
  g.computeBoundingBox();
  return g;
}

/* Posición de una instancia en el mundo (el origen del diseño es [x, y, z] = [profundidad, largo, altura]). */
export function posicionInstancia(inst) {
  const o = inst.origen;
  return inst.tipo === 'poste' ? [o[1], 0, 0] : [o[1], o[2], 0];
}
