"""
Compara los contornos que genera biblioteca_param.py (con t=15, h=0 y ranura de
poste en 20, como el modelo original) contra las piezas reales del .3dm.
Uso:  python3 validar_contra_3dm.py biblioteca.3dm
Requiere:  pip install rhino3dm
"""
import sys
import math
import rhino3dm
import biblioteca_param as bp


def muestrear_curva(c, por_segmento=60):
    """Muestrea cada segmento de la curva por separado (los arcos y las rectas
    tienen dominios distintos, así que muestrear todo junto deja los arcos ralos)."""
    pts = []
    for i in range(c.SegmentCount):
        s = c.SegmentCurve(i)
        t0, t1 = s.Domain.T0, s.Domain.T1
        pts += [s.PointAt(t0 + (t1 - t0) * k / por_segmento) for k in range(por_segmento)]
    return pts


def dist_punto_polilinea(px, py, poly):
    mejor = 1e18
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        dx, dy = x1 - x0, y1 - y0
        l2 = dx * dx + dy * dy
        u = 0 if l2 == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / l2))
        mejor = min(mejor, math.hypot(px - (x0 + u * dx), py - (y0 + u * dy)))
    return mejor


def area_pts(pts):
    s = 0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def comparar(nombre, pts_archivo, contorno_gen):
    gen = bp.muestrear(contorno_gen, 40)
    # distancia máxima en ambos sentidos (≈ Hausdorff)
    d1 = max(dist_punto_polilinea(x, y, gen) for x, y in pts_archivo)
    d2 = max(dist_punto_polilinea(x, y, pts_archivo) for x, y in gen)
    a_arch, a_gen = area_pts(pts_archivo), area_pts(gen)
    ok = max(d1, d2) < 0.25 and abs(a_arch - a_gen) / a_arch < 0.001
    print(f"{nombre:18s} dist.máx = {max(d1, d2):.3f} mm | área archivo {a_arch:,.0f} "
          f"vs generada {a_gen:,.0f} | {'OK' if ok else 'REVISAR'}")
    return ok


def main(ruta):
    m = rhino3dm.File3dm.Read(ruta)
    # El diseño actual cambió (base de 200, separación variable). Para seguir comparando contra
    # el modelo original se usan sus valores: base 160, paso 120, ranura del poste de 20, profundidad 200.
    p = bp.Params(t=15, h=0, fresa=0.0, anclaje="ninguno", luz=600.0, profundidad=200.0, tablas=bp.TABLAS_DEMO, ranuras_unicas=False,
                  _ancho_ranura_poste=20.0, _base_inferior=160.0, _paso=120.0)
    from types import SimpleNamespace as _NS
    piezas = {"poste": _NS(contorno=bp.contorno_poste(p))}
    for _n in (2, 3, 4):
        piezas[f"tabla_{_n}_postes"] = _NS(contorno=bp.contorno_tabla(p, _n))
    todo_ok = True
    vistos = set()
    for o in m.Objects:
        g = o.Geometry
        capa = m.Layers[o.Attributes.LayerIndex].Name
        if type(g).__name__ != "Extrusion":
            continue
        c = g.Profile3d(0, 0)
        pts3 = muestrear_curva(c)
        if capa == "Piezas verticales":
            if "poste" in vistos:
                continue
            vistos.add("poste")
            pts = [(q.X, q.Z) for q in pts3]            # (profundidad, altura)
            todo_ok &= comparar("poste", pts, piezas["poste"].contorno)
        elif capa == "Piezas horizontales":
            ymin = min(q.Y for q in pts3)
            largo = max(q.Y for q in pts3) - ymin
            n = round((largo - 2 * bp.VOLADIZO + p.luz) / (p.t + p.luz))
            clave = f"tabla_{n}_postes"
            if clave in vistos:
                continue
            vistos.add(clave)
            pts = [(q.X, q.Y - ymin) for q in pts3]
            todo_ok &= comparar(clave, pts, piezas[clave].contorno)
    print("\nRESULTADO:", "todo coincide con el modelo original" if todo_ok else "hay diferencias")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "biblioteca.3dm")
