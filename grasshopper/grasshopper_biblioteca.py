#! python 3
"""
Componente "Python 3 Script" de Grasshopper (Rhino 8)
=====================================================
Usa biblioteca_param.py como única fuente de reglas: este componente solo
traduce sus resultados a geometría de Rhino.

ENTRADAS  (agregalas con el "+" del componente; Type hint entre paréntesis)
  t            (float)  espesor de trabajo, mm. OPCIONAL: si no lo conectás usa el espesor
                        real de la placa (hoy 15)          -> Number Slider  5 a 30
  h            (float)  holgura, mm                        -> Number Slider  0 a 0.5
  n_postes     (int)    cantidad de postes                 -> Number Slider  2 a 20 (entero)
  luz          (float)  luz libre entre postes, mm. Máximo estructural = 36 x espesor (540 con 15 mm);
                        mínimo 250. Si no la conectás usa el máximo.   -> Number Slider  250 a 540
  n_ranuras    (int)    cantidad de ranuras por poste      -> Number Slider  4 a 40 (entero)
  anclaje      (str)    anclaje de cada poste a la pared: "ambos" (por defecto), "superior" o "ninguno".
                        Agrega a TODOS los postes una muesca trasera para una escuadra empotrada, a 1 cm
                        de la ranura más alta y/o de la más baja  -> Panel con una de esas palabras
  anclaje_alto   (float) alto de la escuadra de anclaje, mm (inicial 20)    -> Number Slider  8 a 60
  anclaje_ancho  (float) largo del brazo de la escuadra que apoya en la cara lateral del poste, mm
                         (inicial 40). La profundidad de la escuadra (brazo contra la pared) es
                         siempre el espesor de la placa.                  -> Number Slider  15 a 80
  anclaje_espesor (float) espesor de la chapa de la escuadra, mm (inicial 2). Define la profundidad
                         del rebaje y de la muesca trasera.                -> Number Slider  1 a 5
  agujero_radio  (float) radio del agujero PASANTE del pasador, mm (inicial 2.25 = Ø4,5, para tornillo M4;
                         4 para M8...). Atraviesa brazo, poste y brazo y ubica la plantilla del rebaje manual.
                                                                          -> Number Slider  1 a 5
  holgura_u      (float) holgura del ancho interior de la U, mm (inicial 0.5). El ancho interior sale del
                         espesor REAL de la placa: t - 2 x chapa + holgura.   -> Number Slider  0 a 2
  fresa_manual   (float) diámetro de la fresa del router manual, mm (inicial 6) -> Number Slider  3 a 12
  buje           (float) diámetro exterior del buje guía del router manual, mm (inicial 10)
                                                                          -> Number Slider  6 a 30
  zocalo       (bool)   con / sin recorte de zócalo        -> Boolean Toggle
  zocalo_alto  (float)  alto del recorte, mm               -> Number Slider  0 a 140
  zocalo_prof  (float)  profundidad del recorte, mm        -> Number Slider  0 a 50
  profundidad  (float)  profundidad TOTAL del mueble = ancho de postes y tablas, mm (inicial 193)
                                                              -> Number Slider  100 a 300
                        193 permite 6 columnas de piezas por placa; con 200 solo caben 5
  ancho_total  (float)  ancho de punta a punta, mm (incluye el voladizo de las tablas).
                        Fija n_postes y luz, y el ancho queda EXACTO. Usa la MENOR cantidad de postes cuya
                        luz no supere el máximo estructural. Si conectás 'luz', funciona como luz máxima
                        deseada (más baja que el máximo, nunca más alta). -> Number Slider  480 a 10760
  alto_total   (float)  alto del mueble, mm. El alto queda EXACTO: las 'n_ranuras' se reparten entre la
                        base (200 mm bajo la primera ranura) y el remate (100 mm sobre la última), con
                        una separación uniforme que nunca baja de 110 mm entre ranuras.
                        Si no conectás 'n_ranuras', usa la mayor cantidad que respeta ese mínimo.
                                                              -> Number Slider  690 a 2420
  n_tablas     (int)    cantidad total de tablas              -> Number Slider  2 a 60 (entero)
                        (el mínimo depende de los postes: el Panel 'info' lo avisa)
  semilla      (int)    cambia la distribución al azar        -> Number Slider  0 a 999 (entero)
  sep_min      (int)    separación mínima entre tablas de un mismo tramo, en ranuras
                                                              -> Number Slider  1 a 5 (entero), inicial 2
  ranuras_unicas (bool) True: ninguna altura se repite en todo el mueble (solo sirve con
                        pocos postes). Por defecto False: solo se evita repetirla en un mismo poste.
                                                              -> Boolean Toggle
  tablas       (str, OPCIONAL) modo manual: una tabla por línea "poste_ini,poste_fin,ranura"
               ej.:  0,3,15   Si la conectás, anula n_tablas y semilla.

  fresa        (float)  diámetro de la fresa, mm (inicial 6). Define el tamaño de los alivios (círculos)
                        en los rincones de las ranuras y la separación entre piezas en la placa.
                        Máximo útil: ancho de ranura / 1,41 (10,6 con 15 mm)  -> Number Slider  3 a 10.5
  pedido_id    (str)    nombre del pedido, p. ej. PED-001      -> Panel
  confirmar    (bool)   True = descuenta las placas del inventario y agrega los sobrantes
                        (solo con 'pedido_id'; ver aviso abajo) -> Boolean Toggle, inicial False
  exportar_svg (bool)   True = guarda plan_de_corte.svg en la carpeta del proyecto

Todas las entradas son opcionales: las que no conectes usan su valor por defecto.

SALIDAS
  ensamblado   mueble armado en 3D (sólidos)
  despiece     contornos 2D de cada pieza, en fila, listos para ver o exportar
  mecanizados  rebajes laterales de la cara de corte (los hace la CNC, con alivios), dibujados en el
               despiece y en el plan de corte.
  manual       rebajes laterales de la cara opuesta (los hace a mano un router con la plantilla).
  escuadras    las escuadras en U ya colocadas en cada poste (base contra la pared + dos brazos embutidos),
               para ver cómo encajan en los rebajes del modelo armado.
  plantilla3d  modelo 3D de la plantilla del router (placa con ventana + 2 topes con llave), armada sobre un
               trozo de poste. Está a la izquierda del mueble (x = -4200).
  plantilla_ref  lo que rodea a la plantilla: el trozo de poste con la muesca trasera, el rebaje y el agujero,
               el volumen del rebaje (donde entra el brazo de la escuadra), y el buje con la fresa del router.
  plantilla3d_despiece  las piezas de la plantilla separadas (placa y los dos topes), debajo del modelo armado.
  cortadores   solo si la resta booleana falla: los volúmenes de los rebajes y del agujero, para ver dónde irían.
  plantilla    plantilla del router (placa con ventana + 2 topes) y regla(s) de replanteo para la pared,
               a cortar en MDF (NO van en la multiplaca). Se dibujan debajo del plan de corte.
  corte        plan de corte: placas con las piezas acomodadas y los sobrantes (a la izquierda del mueble)
  info         medidas calculadas, plan de corte, inventario y errores de validación

CONFIRMAR UN PEDIDO: activá 'confirmar' solo cuando el diseño esté definitivo y APAGALO enseguida.
Mientras esté en True, el primer cálculo con un 'pedido_id' nuevo se confirma. Un mismo pedido_id
nunca se descuenta dos veces.

ANTES DE USAR: editá CARPETA con la ruta donde guardaste biblioteca_param.py
"""
import os
import sys
import importlib

import Rhino.Geometry as rg

CARPETA = r"/Users/mauricio.lopez/Documents/Proyecto Biblioteca"

if CARPETA not in sys.path:
    sys.path.append(CARPETA)
import biblioteca_param as bp
importlib.reload(bp)        # toma los cambios si editás el módulo
import herrajes as hj
importlib.reload(hj)
import nesting as ns
importlib.reload(ns)

RUTA_INV = os.path.join(CARPETA, "inventario.json")


def _in(nombre, defecto=None):
    """Lee una entrada del componente. Si la entrada no existe o no está
    conectada, devuelve el valor por defecto (así podés ir agregando
    entradas de a una)."""
    v = globals().get(nombre)
    return defecto if v is None else v


def _parsear_tablas(lineas):
    """Acepta una lista de textos o un solo texto con varias líneas."""
    if not lineas:
        return None
    if isinstance(lineas, str):
        lineas = [lineas]
    res = []
    for item in lineas:
        for ln in str(item).splitlines():
            ln = ln.strip()
            if not ln:
                continue
            a, b, c = [int(float(v)) for v in ln.replace(";", ",").split(",")]
            res.append(bp.Tabla(a, b, c))
    return res or None


def _contorno_a_curva(contorno, dx=0.0, dy=0.0):
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
            poli.Append(rg.ArcCurve(rg.Arc(a, rg.Point3d(mx + dx, my + dy, 0), c)))
    return poli


def _rect(x, y, w, h):
    return rg.Rectangle3d(rg.Plane.WorldXY, rg.Interval(x, x + w), rg.Interval(y, y + h)).ToNurbsCurve()


def _solido(curva_plana, vector):
    """Sólido por extrusión de una curva plana cerrada. Se usa Extrusion.Create, que genera una cara por
    tramo de la curva (una sola superficie con quiebres hace fallar las booleanas); si no se puede, se
    recurre a la extrusión simple."""
    try:
        ok, pl = curva_plana.TryGetPlane(0.01)
        if ok:
            h = rg.Vector3d.Multiply(pl.Normal, vector)          # altura con signo respecto de la normal
            c = curva_plana
            if h < 0:                                             # extruir "hacia atrás": se corre la curva
                c = curva_plana.DuplicateCurve()
                c.Translate(rg.Vector3d.Multiply(pl.Normal, h))
            ext = rg.Extrusion.Create(c, abs(h), True)
            if ext:
                b = ext.ToBrep()
                if b is not None and b.IsValid:
                    return b
    except Exception:
        pass
    srf = rg.Surface.CreateExtrusion(curva_plana, vector)
    brep = srf.ToBrep()
    cerrado = brep.CapPlanarHoles(0.01)
    return cerrado if cerrado else brep


def _prisma(item, origen):
    """Prisma de un elemento de plantilla_3d: contorno (x, z) extruido en y de y0 a y1, colocado en 'origen'.
    Los huecos se restan con la misma booleana que usan los postes (probada en tu Rhino). Devuelve
    (sólido, huecos_ok); si no se pueden restar, devuelve el sólido sin huecos y huecos_ok = False."""
    plano = rg.Plane(rg.Point3d(origen[0], origen[1] + item["y0"], origen[2]),
                     rg.Vector3d(1, 0, 0), rg.Vector3d(0, 0, 1))
    mover = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plano)
    c = _contorno_a_curva(item["contorno"])
    c.Transform(mover)
    h = item["y1"] - item["y0"]
    sol = _solido(c, rg.Vector3d(0, h, 0))
    if not item["huecos"]:
        return sol, True
    original = sol
    try:
        for hh in item["huecos"]:
            ci = _contorno_a_curva(hh)
            ci.Transform(mover)
            ci.Translate(rg.Vector3d(0, -1.0, 0))                 # el cortador sobresale 1 mm de cada cara
            cortador = _solido(ci, rg.Vector3d(0, h + 2.0, 0))
            r_ = None
            for tol_ in (0.01, 0.05, 0.1):
                r_ = rg.Brep.CreateBooleanDifference(sol, cortador, tol_)
                if r_ and len(r_) > 0:
                    break
            if not (r_ and len(r_) > 0):
                return original, False
            sol = r_[0]
        return sol, True
    except Exception:
        return original, False


# --- Parámetros -------------------------------------------------------------
tablas_manual = _parsear_tablas(_in("tablas"))
_CONV = (("t", float), ("h", float), ("n_postes", int), ("luz", float), ("n_ranuras", int), ("separacion", float),
         ("profundidad", float), ("fresa", float), ("anclaje", lambda v: str(v).strip().lower()), ("anclaje_alto", float), ("anclaje_ancho", float), ("anclaje_espesor", float), ("agujero_radio", float), ("holgura_u", float), ("fresa_manual", float), ("buje", float), ("zocalo", bool), ("zocalo_alto", float), ("zocalo_prof", float),
         ("n_tablas", int), ("semilla", int), ("sep_min", int), ("ranuras_unicas", bool))
_kw = {nombre: conv(_in(nombre)) for nombre, conv in _CONV if _in(nombre) is not None}
_alias_nota = ""
if _in("inserto_radio") is not None or _in("inserto_prof") is not None:
    if _in("inserto_radio") is not None and "agujero_radio" not in _kw:
        _kw["agujero_radio"] = float(_in("inserto_radio"))
    _alias_nota = ("Las entradas 'inserto_radio' e 'inserto_prof' ya no existen: el agujero ahora es PASANTE. "
                   "'inserto_radio' se usó como 'agujero_radio' (renombrala) e 'inserto_prof' se ignora.")
_ancho = _in("ancho_total")
_alto = _in("alto_total")
p, notas_dim, errores_dim = bp.desde_dimensiones(
    ancho_total=None if _ancho is None else float(_ancho),
    alto_total=None if _alto is None else float(_alto),
    **_kw)
if tablas_manual is not None:
    p.tablas = tablas_manual

ensamblado = []
despiece = []
corte = []
mecanizados = []
manual = []
plantilla = []
escuadras = []
cortadores = []
plantilla3d = []
plantilla_ref = []
plantilla3d_despiece = []
errores = errores_dim or bp.validar(p)

if errores:
    info = "PARÁMETROS INVÁLIDOS:\n- " + "\n- ".join(errores)
    if notas_dim:
        info += "\n\nAjuste por medidas totales:\n  " + "\n  ".join(notas_dim)
else:
    piezas = {pz.nombre: pz for pz in bp.generar_piezas(p)}
    curvas = {nombre: _contorno_a_curva(pz.contorno) for nombre, pz in piezas.items()}

    # Ensamblado 3D: los postes llevan restados los rebajes de las dos caras y el agujero pasante
    cortes_poste = bp.cortes_3d(p)
    fallos_bool = 0
    diag_bool = []
    cortadores_fallidos = []
    for inst in bp.instancias(p):
        crv = curvas[inst.pieza].DuplicateCurve()
        plano = rg.Plane(rg.Point3d(*inst.origen),
                         rg.Vector3d(*inst.eje_x), rg.Vector3d(*inst.eje_y))
        mover = rg.Transform.PlaneToPlane(rg.Plane.WorldXY, plano)
        crv.Transform(mover)
        solido = _solido(crv, rg.Vector3d(*inst.extrusion))
        if inst.tipo == "poste" and cortes_poste:
            cortadores = []
            try:
                for c_ in cortes_poste:
                    cc = _contorno_a_curva(c_["contorno"])
                    cc.Transform(mover)
                    cc.Translate(rg.Vector3d(0, c_["y_desde"], 0))
                    cortadores.append((c_["tipo"], _solido(cc, rg.Vector3d(0, c_["largo"], 0))))
                resultado = solido
                for tipo_c, cort in cortadores:                  # de a uno: más robusto que restar todos juntos
                    r_ = None
                    for tol_ in (0.01, 0.05, 0.1):
                        r_ = rg.Brep.CreateBooleanDifference(resultado, cort, tol_)
                        if r_ and len(r_) > 0:
                            break
                    if not (r_ and len(r_) > 0):
                        raise RuntimeError("falló la resta del cortador '%s' (poste sólido: %s, cortador sólido: %s)"
                                           % (tipo_c, resultado.IsSolid, cort.IsSolid))
                    resultado = r_[0]
                solido = resultado
            except Exception as ex_:
                fallos_bool += 1
                if len(diag_bool) < 3:
                    diag_bool.append("poste %s: %s" % (inst.nombre, ex_))
                cortadores_fallidos += [c_ for _t, c_ in cortadores]
        ensamblado.append(solido)
    cortadores = cortadores_fallidos           # si alguna resta falla, se ve dónde irían los rebajes y el agujero
    for e_ in hj.escuadras_3d(p):
        x0_, y0_, z0_, x1_, y1_, z1_ = e_["caja"]
        escuadras.append(rg.Brep.CreateFromBox(rg.BoundingBox(rg.Point3d(x0_, y0_, z0_), rg.Point3d(x1_, y1_, z1_))))

    # Despiece 2D (una copia por unidad, en filas)
    # El despiece arranca 500 mm a la derecha del mueble para no superponerse con él
    X0, ANCHO_FILA, SEP = 500.0, 6000.0, 100.0
    x, y, alto_fila = X0, 0.0, 0.0
    for nombre, pz in piezas.items():
        for _ in range(pz.cantidad):
            if x + pz.ancho > X0 + ANCHO_FILA and x > X0:
                x, y, alto_fila = X0, y - alto_fila - SEP, 0.0
            c = curvas[nombre].DuplicateCurve()
            c.Translate(rg.Vector3d(x, y, 0))
            despiece.append(c)
            for m_ in pz.mecanizados:
                (manual if m_.get("manual") else mecanizados).append(_contorno_a_curva(m_["contorno"], x, y))
            for hu_ in pz.huecos:
                despiece.append(_contorno_a_curva(hu_["contorno"], x, y))
            x += pz.ancho + SEP
            alto_fila = max(alto_fila, pz.largo)

    r = bp.resumen(p)
    pl = p.placa
    lineas = [
        "Placa: %s (%.0f x %.0f mm, útil %.0f x %.0f) - %s %s - U$S %.2f c/u"
        % (pl.nombre, pl.largo, pl.ancho, bp.largo_util(pl), bp.ancho_util(pl),
           pl.proveedor, pl.codigo, pl.precio_usd),
        "",
        "Medidas totales: ancho %.1f x alto %.1f x profundidad %.1f mm (ancho entre postes: %.1f)"
        % (r["ancho_total_mueble"], r["alto_total"], r["profundidad_total"], r["ancho_entre_postes"]),
        "Ancho de ranura (t + h): %.2f mm | profundidad de piezas: %.1f mm (ranuras de %.1f mm)"
        % (r["ancho_ranura"], p.profundidad, bp.prof_ranura(p)),
        "Anclajes a la pared: %s | %d escuadras en total | muesca trasera de %.0f x %.1f mm | %s"
        % (r["anclaje"], len(r["anclajes"]) * r["n_postes"], r["muesca_anclaje"][0], r["muesca_anclaje"][1],
           " ; ".join("%s: z %.0f-%.0f mm" % (a["nombre"], a["z_ini"], a["z_fin"]) for a in r["anclajes"]) or "sin anclajes"),
    ]
    if r["anclajes"]:
        u_, ag_ = hj.dimensiones_u(p), r["agujero"]
        pl_ = hj.plantilla_router(p)
        placa_ = [q for q in pl_ if q.nombre == "plantilla_router"][0]
        ven_ = [h for h in placa_.huecos if h["tipo"] == "ventana"][0]
        vx = [x_ for x_, z_, b_ in ven_["contorno"]]
        vz = [z_ for x_, z_, b_ in ven_["contorno"]]
        rg_ = hj.regla_replanteo(p)
        lineas += [
            "",
            "--- ESCUADRA EN U (datos para el taller de chapa) ---",
            "Chapa %.1f mm | alto %.0f mm | brazos de %.0f mm | ancho exterior %.1f mm (= espesor de la placa)"
            % (u_["chapa"], u_["alto"], u_["largo_brazos"], u_["ancho_exterior"]),
            "Ancho interior %.1f mm (núcleo de madera %.1f mm + holgura %.1f mm) | puntas de los brazos redondeadas, radio >= %.1f mm"
            % (u_["ancho_interior"], u_["nucleo"], p.holgura_u, u_["radio_puntas_min"]),
            "Agujero de los brazos Ø%.1f mm, a %.0f mm de la pared, centrado en el alto | pasador: tornillo avellanado + tuerca autoprensada en el brazo opuesto"
            % (u_["diametro_agujero_brazos"], u_["centro_agujero_desde_pared"]),
            "Agujero PASANTE en el poste: Ø%.1f mm, 1 por escuadra, centrado%s"
            % (ag_["diametro"], " | OJO: es menor que la fresa, hay que taladrarlo con broca" if ag_["con_broca"] else ""),
            "Rebajes de %.1f mm en las dos caras: cara de corte (CNC, con alivios) y cara opuesta (a mano, con la plantilla)"
            % u_["chapa"],
            ("Modelo 3D: rebajes de las dos caras y agujero pasante restados en los postes; %d piezas de escuadra en la salida 'escuadras'"
             % len(escuadras)) if not fallos_bool else
            ("AVISO modelo 3D: no se pudo restar los rebajes en %d poste(s) (se muestran sin rebajes; los volúmenes que faltan "
             "salen en 'cortadores'). Detalle: %s" % (fallos_bool, " | ".join(diag_bool))),
            "Plantilla del router (MDF %.0f mm): placa de %.0f x %.0f mm con ventana de %.1f x %.1f mm (rebaje + %.1f mm por el buje de %.0f mm con fresa de %.0f mm) y 2 topes con llave que entra en la muesca trasera. Modelo 3D en las salidas 'plantilla3d', 'plantilla_ref' y 'plantilla3d_despiece' (a la izquierda del mueble, x = -4200)"
            % (hj.PLANTILLA_ESPESOR, placa_.ancho, placa_.largo, max(vx) - min(vx), max(vz) - min(vz),
               ven_["offset"], p.buje, p.fresa_manual),
            "Regla de replanteo (MDF %.0f mm): %d tramo(s) de %s mm (marcas de Ø%.0f mm en el centro de cada poste)"
            % (hj.REGLA_ESPESOR, len(rg_), " + ".join("%.0f" % q.largo for q in rg_), 2 * hj.MARCA_RADIO),
            "Replanteo en la pared (y desde la cara izquierda del primer poste, z desde el piso):",
        ] + ["  poste %d: y = %.1f mm | %s" % (f_["poste"], f_["y_centro"],
             " | ".join("z %s = %.0f mm" % (k_[2:], v_) for k_, v_ in f_.items() if k_.startswith("z_")))
             for f_ in hj.tabla_replanteo(p)]
    lineas += [
        "Luz entre postes: %.1f mm (máx. estructural %.0f mm) | flecha estimada con libros: %.1f mm (luz/%.0f)"
        % (r["luz"], r["luz_max"], r["flecha_estimada"], r["luz"] / max(r["flecha_estimada"], 1e-9)),
        "Separación entre ranuras: %.1f mm (paso %.1f mm) | espacio libre entre tablas a %d ranuras: %.0f mm"
        % (r["separacion"], r["paso"], p.sep_min, r["espacio_libre_entre_tablas"]),
        "Postes: %d | Tablas: %d" % (r["n_postes"], r["n_tablas"]),
        "",
    ]
    for pz in piezas.values():
        lineas.append("%-18s x%d   %.0f x %.1f x %.1f mm"
                      % (pz.nombre, pz.cantidad, pz.ancho, pz.largo, pz.espesor))
    # --- Plantilla del router y regla de replanteo (MDF), debajo del plan de corte ------------
    XT, y_t = -2800.0, -400.0
    for pz_ in hj.plantilla_router(p) + hj.regla_replanteo(p):
        pts_ = bp.muestrear(pz_.contorno, 4)
        minx, miny = min(a_ for a_, b_ in pts_), min(b_ for a_, b_ in pts_)
        maxy = max(b_ for a_, b_ in pts_)
        for _k in range(pz_.cantidad):
            dx_, dy_ = XT - minx, y_t - maxy
            plantilla.append(_contorno_a_curva(pz_.contorno, dx_, dy_))
            for hu_ in pz_.huecos:
                plantilla.append(_contorno_a_curva(hu_["contorno"], dx_, dy_))
            y_t -= (maxy - miny) + 100.0

    # --- Modelo 3D de la plantilla del router (a la izquierda del mueble) --------------------------
    huecos_perdidos = 0
    try:
        for origen_, explotada_, destino_ in (((-4200.0, 0.0, 0.0), False, None), ((-4200.0, -300.0, 0.0), True, None)):
            modelo_ = hj.plantilla_3d(p, explotada=explotada_)
            for it_ in modelo_["plantilla"]:
                b_, ok_ = _prisma(it_, origen_)
                huecos_perdidos += 0 if ok_ else 1
                (plantilla3d_despiece if explotada_ else plantilla3d).append(b_)
            if not explotada_:
                for it_ in modelo_["referencia"]:
                    b_, ok_ = _prisma(it_, origen_)
                    huecos_perdidos += 0 if ok_ else 1
                    plantilla_ref.append(b_)
    except Exception as ex_:
        lineas.append("AVISO modelo 3D de la plantilla: no se pudo armar (%s)" % ex_)
    if huecos_perdidos:
        lineas.append("AVISO modelo 3D de la plantilla: %d pieza(s) se muestran sin sus huecos (no se pudo restar el hueco)" % huecos_perdidos)

    # --- Plan de corte (nesting) ---------------------------------------------
    if notas_dim:
        lineas += ["Ajuste por medidas totales:"] + ["  " + n_ for n_ in notas_dim] + [""]
    if _alias_nota:
        lineas += ["AVISO: " + _alias_nota, ""]
    lineas += ["", "--- PLAN DE CORTE ---"]
    try:
        cfg = ns.ConfigNesting(fresa=p.fresa)
        inv = ns.Inventario.cargar(RUTA_INV)
        piezas_n = ns.piezas_para_nesting(p)
        plan = ns.planificar(piezas_n, inv, p, cfg)
        if os.path.exists(RUTA_INV):
            lineas.append(inv.resumen().split("\n")[0])
        else:
            lineas.append("(No hay inventario.json: se asume que todas las placas se compran.)")
        lineas.append("Columnas de piezas por placa: %d (profundidad máx. para %d columnas: %.1f mm)"
                      % (ns.columnas_por_placa(p, cfg), ns.columnas_por_placa(p, cfg) + 1,
                         ns.profundidad_max_para_columnas(p.placa, cfg, ns.columnas_por_placa(p, cfg) + 1)))
        lineas += ns.texto_plan(plan)
        for e in ns.verificar_plan(plan, piezas_n):
            lineas.append("ERROR DE NESTING: " + e)

        # Geometría: las placas se dibujan a la izquierda del mueble
        XN, SEP_N, y_cursor = -2800.0, 200.0, 0.0
        for h_ in plan.hojas:
            corte.append(_rect(XN, y_cursor, h_.largo, h_.ancho))
            for c_ in h_.colocaciones:
                cont = ns.contorno_colocado(plan.contornos[c_.nombre], c_.u, c_.v, c_.dv)
                corte.append(_contorno_a_curva(cont, XN, y_cursor))
                for m_ in plan.mecanizados.get(c_.nombre, []):
                    (manual if m_.get("manual") else mecanizados).append(_contorno_a_curva(
                        ns.contorno_colocado(m_["contorno"], c_.u, c_.v, c_.dv), XN, y_cursor))
                for hu_ in plan.huecos.get(c_.nombre, []):
                    corte.append(_contorno_a_curva(
                        ns.contorno_colocado(hu_["contorno"], c_.u, c_.v, c_.dv), XN, y_cursor))
            for (u_, v_, w_, hh_) in h_.sobrantes:
                corte.append(_rect(XN + u_, y_cursor + v_, w_, hh_))
            y_cursor += h_.ancho + SEP_N

        if bool(_in("exportar_svg", False)):
            ruta_svg = os.path.join(CARPETA, "plan_de_corte.svg")
            ns.plan_a_svg(plan, ruta_svg)
            lineas.append("SVG guardado en: " + ruta_svg)

        # Confirmación del pedido (idempotente: un mismo pedido_id no se descuenta dos veces)
        pedido = str(_in("pedido_id", "")).strip()
        if bool(_in("confirmar", False)):
            if not pedido:
                lineas.append("PARA CONFIRMAR escribí un nombre en 'pedido_id'.")
            else:
                try:
                    ns.confirmar(inv, plan, pedido, p.placa)
                    inv.guardar(RUTA_INV)
                    lineas.append("PEDIDO '%s' CONFIRMADO: inventario actualizado. Apagá 'confirmar'." % pedido)
                except ValueError as ex:
                    lineas.append("NO SE CONFIRMÓ: %s" % ex)
    except Exception as ex:
        lineas.append("No se pudo armar el plan de corte: %s" % ex)

    tablas_ef, avisos = bp.tablas_efectivas(p)
    if abs(p.t - pl.espesor_real) > 1e-6:
        avisos = avisos + ["El espesor de trabajo t=%.2f mm no coincide con el espesor real de la placa "
                           "(%.2f mm): sirve para probar, pero no para fabricar con esta placa."
                           % (p.t, pl.espesor_real)]
    modo = "manual" if p.tablas is not None else "automático (semilla %d)" % p.semilla
    lineas += ["", "Tablas - modo %s:" % modo]
    for i, tb in enumerate(tablas_ef, 1):
        z = bp.z_ranura(p, tb.ranura)
        lineas.append("  %2d) postes %d a %d | ranura %2d (z = %.0f mm)"
                      % (i, tb.poste_ini, tb.poste_fin, tb.ranura, z))
    lineas += ["", "Para congelar esta distribución, copiá estas líneas en el Panel 'tablas':"]
    lineas += ["%d,%d,%d" % (tb.poste_ini, tb.poste_fin, tb.ranura) for tb in tablas_ef]
    for av in avisos:
        lineas += ["", "AVISO: " + av]
    info = "\n".join(lineas)
