"""
herrajes.py
-----------
Herrajes de anclaje a la pared y herramientas para fabricarlos e instalarlos. Está separado de
biblioteca_param.py para mantener el orden: ahí queda solo el diseño del mueble (postes, tablas,
anclajes en el poste); acá todo lo que rodea a la escuadra en U.

Contiene
  - dimensiones_u():     medidas de la escuadra en U para encargarla a un taller de chapa
  - plantilla_router():  plantilla de MDF para hacer a mano, con router y buje guía, el rebaje de la
                         cara opuesta del poste (placa con ventana + 2 topes con llave)
  - plantilla_3d():      modelo 3D de esa plantilla (armada sobre un poste de ejemplo y despiezada)
  - regla_replanteo():   regla(s) de MDF para marcar en la pared el tornillo de cada escuadra
  - tabla_replanteo():   coordenadas de esas marcas
  - escuadras_3d():      escuadras en U ya colocadas en el mueble armado

Depende de biblioteca_param.py (no al revés). Python puro, sin dependencias.
"""
import math

from biblioteca_param import (Params, Pieza, anclajes, alto_muesca, mecanizados_poste,
                              largo_util, pos_poste, ANCLAJE_HOLGURA, _zona_escuadra, _rect, _circulo)

# ----------------------------------------------------------------------------
# Plantilla y regla de replanteo (se cortan en MDF aparte, no en la multiplaca)
# ----------------------------------------------------------------------------
PLANTILLA_ESPESOR = 12.0       # MDF de la plantilla del router
PLANTILLA_MARGEN = 25.0        # material de la plantilla alrededor de la ventana
TOPE_ANCHO = 10.0              # ancho del tope de la plantilla (apoya en el canto trasero del poste)
LLAVE_HOLGURA = 0.3            # holgura de la llave del tope dentro de la muesca trasera (en alto y en profundidad)
REGLA_ESPESOR = 6.0            # MDF de la regla de replanteo
REGLA_ALTO = 50.0              # alto de la regla de replanteo
REGLA_MARGEN = 40.0            # sobrante en cada extremo de la regla
MARCA_RADIO = 2.0              # radio de los agujeros de marcado de la regla (Ø4)


def dimensiones_u(p: Params) -> dict:
    """Medidas de la escuadra en U para encargarla a un taller de chapa. Los brazos van embutidos en los
    rebajes (quedan a ras de las caras) y la base contra la pared va en la muesca trasera.
    Todas las medidas dependen de los parámetros; el ancho interior sale del espesor REAL de la placa."""
    e = p.anclaje_espesor
    return {"chapa": e, "alto": p.anclaje_alto, "largo_brazos": p.anclaje_ancho,
            "ancho_exterior": p.t,                          # = espesor de la placa (profundidad de la escuadra)
            "ancho_interior": p.t - 2 * e + p.holgura_u,    # núcleo de madera entre los rebajes + holgura
            "nucleo": p.t - 2 * e,
            "diametro_agujero_brazos": 2 * p.agujero_radio,
            "centro_agujero_desde_pared": p.anclaje_ancho / 2,
            "radio_puntas_min": p.fresa_manual / 2.0}


def plantilla_router(p: Params) -> list:
    """Plantilla (MDF) para hacer a mano, con router y buje guía, el rebaje de la cara opuesta del poste.
    Se cortan: 1 placa con la ventana + 2 topes con llave (uno por cada cara, así la misma plantilla sirve
    dada vuelta). Coordenadas en el plano del poste (x = profundidad con el canto trasero en x = 0) y
    centradas en el alto de la escuadra (z = 0).
    Cómo se ubica en el poste, sin necesidad del agujero pasante:
      - en profundidad: el tope apoya contra el canto trasero del poste (x = 0);
      - en altura: la llave del tope, una lengüeta, entra en la muesca trasera que corta la CNC;
      - la placa apoya sobre la cara del poste.
    Ventana = rebaje agrandado en (buje - fresa manual) / 2 por cada lado."""
    if not anclajes(p):
        return []
    e = p.anclaje_espesor
    off = (p.buje - p.fresa_manual) / 2.0
    a = anclajes(p)[0]
    _, x0, x1, z0, z1 = _zona_escuadra(p, a)
    h2 = (z1 - z0) / 2
    ventana = _rect(x0 - off, -h2 - off, x1 + off, h2 + off)
    placa_x0, placa_x1 = -TOPE_ANCHO, x1 + off + PLANTILLA_MARGEN
    placa_z = h2 + off + PLANTILLA_MARGEN
    placa = Pieza("plantilla_router", "plantilla", _rect(placa_x0, -placa_z, placa_x1, placa_z), PLANTILLA_ESPESOR, 1,
                  placa_x1 - placa_x0, 2 * placa_z,
                  huecos=[{"tipo": "ventana", "contorno": ventana, "offset": off}], material="MDF")
    tz = alto_muesca(p) / 2 - LLAVE_HOLGURA / 2          # medio alto de la llave
    tl = e - LLAVE_HOLGURA                                 # cuánto entra la llave en la muesca
    contorno_tope = [(-TOPE_ANCHO, -placa_z, 0.0), (0.0, -placa_z, 0.0), (0.0, -tz, 0.0), (tl, -tz, 0.0),
                     (tl, tz, 0.0), (0.0, tz, 0.0), (0.0, placa_z, 0.0), (-TOPE_ANCHO, placa_z, 0.0)]
    tope = Pieza("tope_plantilla", "plantilla", contorno_tope, PLANTILLA_ESPESOR, 2,
                 TOPE_ANCHO + tl, 2 * placa_z, material="MDF")
    return [placa, tope]


def plantilla_3d(p: Params, explotada: bool = False) -> dict:
    """Modelo 3D de la plantilla, para poder visualizarla. Devuelve dos grupos de prismas
    {nombre, contorno, huecos, y0, y1}, en coordenadas del poste: x = profundidad (canto trasero en x = 0),
    z centrada en el alto de la escuadra, y = espesor (el poste ocupa y de 0 a t).
      - 'plantilla': placa de MDF con su ventana + los dos topes con llave. Se apoya en la cara -Y del poste
        (la que se rebaja a mano). El tope 'en uso' queda contra el canto trasero con su llave dentro de la
        muesca; el otro tope queda del lado de afuera y pasa a ser el de uso al dar vuelta la plantilla.
      - 'referencia': un trozo de poste (con la muesca trasera, el rebaje ya hecho y el agujero pasante), el
        volumen del rebaje (donde entra el brazo de la escuadra), y el buje con la fresa del router.
    Con explotada=True las piezas de la plantilla se separan en y para verlas por separado."""
    if not anclajes(p):
        return {"plantilla": [], "referencia": []}
    placa, tope = plantilla_router(p)
    t, e, E = p.t, p.anclaje_espesor, PLANTILLA_ESPESOR
    ventana = [h for h in placa.huecos if h["tipo"] == "ventana"][0]["contorno"]
    x_fin = max(x for x, z, b in placa.contorno)
    Zp = placa.largo / 2
    d = dict(placa=-45.0, tope_uso=-20.0, tope_otro=-75.0) if explotada else dict(placa=0.0, tope_uso=0.0, tope_otro=0.0)
    plantilla = [
        {"nombre": "placa", "contorno": placa.contorno, "huecos": [ventana], "y0": -E + d["placa"], "y1": d["placa"]},
        {"nombre": "tope_en_uso", "contorno": tope.contorno, "huecos": [], "y0": d["tope_uso"], "y1": E + d["tope_uso"]},
        {"nombre": "tope_otra_cara", "contorno": tope.contorno, "huecos": [], "y0": -2 * E + d["tope_otro"], "y1": -E + d["tope_otro"]},
    ]
    # --- poste de ejemplo, con el rebaje de la cara -Y ya hecho
    rm = p.fresa_manual / 2.0
    a = anclajes(p)[0]
    zc, x0, x1, z0, z1 = _zona_escuadra(p, a)
    ph2, hn2 = (z1 - z0) / 2, alto_muesca(p) / 2
    X, Z = x_fin + 15.0, Zp + 15.0
    k = -math.tan(math.pi / 8)                                       # cuarto de círculo horario
    con_rebaje = [(0, Z, 0), (0, hn2, 0), (e, hn2, 0), (e, ph2, 0), (x1 - rm, ph2, k), (x1, ph2 - rm, 0),
                  (x1, -ph2 + rm, k), (x1 - rm, -ph2, 0), (e, -ph2, 0), (e, -hn2, 0), (0, -hn2, 0),
                  (0, -Z, 0), (X, -Z, 0), (X, Z, 0)]
    solo_muesca = [(0, Z, 0), (0, hn2, 0), (e, hn2, 0), (e, -hn2, 0), (0, -hn2, 0), (0, -Z, 0), (X, -Z, 0), (X, Z, 0)]
    xc = p.anclaje_ancho / 2
    man = [m for m in mecanizados_poste(p) if m["manual"] and m["anclaje"] == a["nombre"]][0]
    rebaje = [(x, z - zc, b) for x, z, b in man["contorno"]]
    xb = x1 - rm                                                       # buje apoyado en el extremo de la ventana
    referencia = [
        {"nombre": "poste_capa_con_rebaje", "contorno": con_rebaje, "huecos": [], "y0": 0.0, "y1": e},
        {"nombre": "poste_capa_maciza", "contorno": solo_muesca, "huecos": [_circulo(xc, 0.0, p.agujero_radio)], "y0": e, "y1": t},
        {"nombre": "volumen_rebaje", "contorno": rebaje, "huecos": [], "y0": 0.0, "y1": e},
        {"nombre": "buje", "contorno": _circulo(xb, 0.0, p.buje / 2), "huecos": [], "y0": -E - 8.0, "y1": -2.0},
        {"nombre": "fresa", "contorno": _circulo(xb, 0.0, rm), "huecos": [], "y0": -E - 30.0, "y1": e},
    ]
    return {"plantilla": plantilla, "referencia": referencia}


def tabla_replanteo(p: Params) -> list:
    """Coordenadas para marcar en la pared el tornillo de la base de cada escuadra. Eje y desde la cara
    izquierda del primer poste (las tablas sobresalen 100 mm más a la izquierda); eje z desde el piso."""
    pas = p.t + p.luz
    return [{"poste": k, "y_centro": k * pas + p.t / 2, "y_cara_izq": k * pas,
             **{f"z_{a['nombre']}": (a["z_ini"] + a["z_fin"]) / 2 for a in anclajes(p)}}
            for k in range(p.n_postes)]


def regla_replanteo(p: Params) -> list:
    """Regla(s) de MDF para replantear en la pared las escuadras. Una tira con un agujero de marcado
    (Ø4) en el centro de cada poste, cuyo eje queda a la altura de la escuadra. Si el mueble es más
    largo que la placa se parte en tramos que comparten un poste (se hace coincidir el agujero)."""
    if not anclajes(p):
        return []
    pas = p.t + p.luz
    por_tramo = max(2, int((largo_util(p.placa) - 2 * REGLA_MARGEN) // pas) + 1)
    out, k0 = [], 0
    while k0 < p.n_postes - 1:
        k1 = min(k0 + por_tramo - 1, p.n_postes - 1)
        largo = (k1 - k0) * pas + 2 * REGLA_MARGEN
        hu = [{"tipo": "marca", "poste": k, "centro": (REGLA_ALTO / 2, REGLA_MARGEN + (k - k0) * pas),
               "radio": MARCA_RADIO, "contorno": _circulo(REGLA_ALTO / 2, REGLA_MARGEN + (k - k0) * pas, MARCA_RADIO),
               "pasante": True} for k in range(k0, k1 + 1)]
        out.append(Pieza(f"regla_replanteo_{len(out) + 1}", "regla", _rect(0, 0, REGLA_ALTO, largo), REGLA_ESPESOR, 1,
                         REGLA_ALTO, largo, huecos=hu, material="MDF"))
        k0 = k1
    return out


def escuadras_3d(p: Params) -> list:
    """Cajas (x0, y0, z0, x1, y1, z1) de las escuadras en U ya colocadas en el mueble armado: una base
    contra la pared (dentro de la muesca) y dos brazos embutidos en los rebajes, en cada poste y nivel."""
    e, t = p.anclaje_espesor, p.t
    out = []
    for k in range(p.n_postes):
        y0 = pos_poste(p, k)
        for a in anclajes(p):
            zc, h2 = (a["z_ini"] + a["z_fin"]) / 2, p.anclaje_alto / 2
            base = dict(poste=k, anclaje=a["nombre"])
            out.append({**base, "tipo": "base", "caja": (0.0, y0, zc - h2, e, y0 + t, zc + h2)})
            out.append({**base, "tipo": "brazo_opuesto", "caja": (e, y0, zc - h2, p.anclaje_ancho, y0 + e, zc + h2)})
            out.append({**base, "tipo": "brazo_corte", "caja": (e, y0 + t - e, zc - h2, p.anclaje_ancho, y0 + t, zc + h2)})
    return out
