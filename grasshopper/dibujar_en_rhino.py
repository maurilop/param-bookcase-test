"""
dibujar_en_rhino.py  —  Rhino 8 (Python 3)
Dibuja en el plano XY los contornos 2D de todas las piezas que genera
biblioteca_param.py, para compararlos con tu modelo original.

CÓMO USARLO
1. Guardá este archivo y biblioteca_param.py en la MISMA carpeta.
2. En Rhino: comando ScriptEditor -> abrir este archivo -> botón "Run".
3. Cambiá los valores del bloque PARÁMETROS y volvé a correr.
   Cada corrida borra lo que dibujó la corrida anterior (capa "PARAM").

Si da error de "No module named biblioteca_param", completá CARPETA abajo.
"""
import os
import sys

import Rhino
import Rhino.Geometry as rg
import scriptcontext as sc
import System.Drawing as sd

# Si hace falta, poné acá la carpeta donde guardaste los dos archivos:
CARPETA = ""

try:
    _aqui = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _aqui = ""
for ruta in (CARPETA, _aqui):
    if ruta and ruta not in sys.path:
        sys.path.append(ruta)

import importlib
import biblioteca_param as bp
importlib.reload(bp)   # para tomar cambios si editás el módulo y volvés a correr

# ----------------------------------------------------------------------------
# PARÁMETROS (editá acá)
# ----------------------------------------------------------------------------
p = bp.Params(
    t=15.0,            # espesor del tablero
    h=0.0,             # holgura 0 a 0,5
    n_postes=4,
    luz=600.0,         # luz libre entre postes
    n_ranuras=16,
    zocalo=True,
    zocalo_alto=55.0,
    zocalo_prof=15.0,
    n_tablas=9,        # cantidad total de tablas (mín. 2)
    semilla=0,         # cambiá el número para otra distribución al azar
    # tablas=[bp.Tabla(poste_ini, poste_fin, ranura), ...]  (modo manual, opcional)
)
SEPARACION = 100.0      # espacio entre piezas dibujadas (mm)
# ----------------------------------------------------------------------------


def _capa(nombre, color):
    idx = sc.doc.Layers.FindByFullPath(nombre, -1)
    if idx >= 0:
        return idx
    capa = Rhino.DocObjects.Layer()
    capa.Name = nombre
    capa.Color = color
    return sc.doc.Layers.Add(capa)


def _borrar_corrida_anterior(idx_capa):
    objs = sc.doc.Objects.FindByLayer(sc.doc.Layers[idx_capa])
    for o in objs or []:
        sc.doc.Objects.Delete(o, True)


def _contorno_a_curva(contorno, dx, dy):
    """Convierte [(x, y, bulge)] en una PolyCurve cerrada, desplazada (dx, dy)."""
    poli = rg.PolyCurve()
    n = len(contorno)
    for i in range(n):
        x0, y0, b = contorno[i]
        x1, y1, _ = contorno[(i + 1) % n]
        a = rg.Point3d(x0 + dx, y0 + dy, 0)
        c = rg.Point3d(x1 + dx, y1 + dy, 0)
        if b == 0:
            poli.Append(rg.LineCurve(a, c))
        else:
            mx, my = bp.punto_medio_arco(x0, y0, x1, y1, b)
            m = rg.Point3d(mx + dx, my + dy, 0)
            poli.Append(rg.ArcCurve(rg.Arc(a, m, c)))
    return poli


def main():
    errores = bp.validar(p)
    if errores:
        print("PARÁMETROS INVÁLIDOS:")
        for e in errores:
            print(" -", e)
        return

    piezas = bp.generar_piezas(p)
    color = {"poste": sd.Color.FromArgb(120, 80, 200),
             "tabla": sd.Color.FromArgb(30, 30, 230)}
    idx_raiz = _capa("PARAM", sd.Color.Black)
    _borrar_corrida_anterior(idx_raiz)

    x = 0.0
    fila_y = 0.0
    alto_fila = 0.0
    ANCHO_MAX_FILA = 6000.0
    for pz in piezas:
        idx = _capa("PARAM::" + pz.tipo, color[pz.tipo])
        for k in range(pz.cantidad):
            if x + pz.ancho > ANCHO_MAX_FILA and x > 0:      # nueva fila
                x = 0.0
                fila_y -= alto_fila + SEPARACION
                alto_fila = 0.0
            curva = _contorno_a_curva(pz.contorno, x, fila_y)
            attr = Rhino.DocObjects.ObjectAttributes()
            attr.LayerIndex = idx
            attr.Name = "%s_%d" % (pz.nombre, k + 1)
            sc.doc.Objects.AddCurve(curva, attr)
            pt = rg.Point3d(x + pz.ancho / 2, fila_y + pz.largo / 2, 0)
            sc.doc.Objects.AddTextDot(attr.Name, pt)
            x += pz.ancho + SEPARACION
            alto_fila = max(alto_fila, pz.largo)
    sc.doc.Views.Redraw()

    r = bp.resumen(p)
    print("Listo. Alto total: %.1f mm | Ancho del mueble: %.1f mm | Ranura: %.2f mm"
          % (r["alto_total"], r["ancho_total_mueble"], r["ancho_ranura"]))
    for pz in piezas:
        print("  %-18s x%d   %.0f x %.1f x %.1f mm" % (pz.nombre, pz.cantidad, pz.ancho, pz.largo, pz.espesor))


main()
