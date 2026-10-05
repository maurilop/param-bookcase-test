"""
web_api.py
----------
Puente entre el navegador (Pyodide) y la lógica del diseño. Recibe y devuelve JSON (texto), así que lo
puede llamar cualquier interfaz. No tiene reglas propias: usa biblioteca_param, herrajes y nesting,
las mismas que el componente de Grasshopper, de modo que hay una sola fuente de verdad.

  calcular(json)    -> medidas, validación y geometría para dibujar el mueble
  plan_corte(json)  -> plan de corte (nesting) con su SVG, cantidad de placas y costo de material
  valores_iniciales() -> valores por defecto y rangos para armar los controles
"""
import json

import biblioteca_param as bp
import herrajes as hj
import nesting as ns

DENSIDAD_KG_M3 = 680.0          # densidad aproximada de la multiplaca de abedul (para estimar el peso)

_CONV = {
    "t": float, "h": float, "luz": float, "n_postes": int, "n_ranuras": int, "profundidad": float,
    "separacion": float, "fresa": float, "anclaje": str, "zocalo": bool, "zocalo_alto": float,
    "zocalo_prof": float, "n_tablas": int, "semilla": int, "sep_min": int, "ranuras_unicas": bool,
    "anclaje_alto": float, "anclaje_ancho": float, "anclaje_espesor": float, "agujero_radio": float,
    "holgura_u": float, "fresa_manual": float, "buje": float,
}


def _numero(v):
    return None if v in (None, "") else float(v)


def _construir(datos: dict):
    kw = {}
    for k, conv in _CONV.items():
        v = datos.get(k)
        if v is not None and v != "":
            kw[k] = conv(v)
    return bp.desde_dimensiones(ancho_total=_numero(datos.get("ancho_total")),
                                alto_total=_numero(datos.get("alto_total")), **kw)


def _limites(datos: dict) -> dict:
    t = _numero(datos.get("t"))
    h = _numero(datos.get("h")) or 0.0
    t = t if t is not None else bp.PLACA_ABEDUL_15.espesor_real
    lim = bp.limites_dimensiones(t, h, bp.PLACA_ABEDUL_15)
    lim["profundidad_min"], lim["profundidad_max"] = bp.LIMITES["profundidad"]
    lim["n_tablas_max"] = bp.LIMITES["n_tablas"][1]
    lim["luz_max"] = bp.luz_max(t)
    lim["luz_min"] = bp.LUZ_MIN
    return lim


def _pts(contorno, pasos=10):
    return [[round(x, 2), round(y, 2)] for x, y in bp.muestrear(contorno, pasos)]


def _pieza_web(pz):
    return {"nombre": pz.nombre, "tipo": pz.tipo, "cantidad": pz.cantidad, "ancho": round(pz.ancho, 2),
            "largo": round(pz.largo, 2), "espesor": pz.espesor,
            "contorno": _pts(pz.contorno, 10),
            "huecos": [_pts(h["contorno"], 14) for h in pz.huecos]}


def calcular(json_str: str) -> str:
    datos = json.loads(json_str)
    p, notas, errores = _construir(datos)
    salida = {"ok": False, "errores": [], "notas": notas, "limites": _limites(datos)}
    if errores:
        salida["errores"] = errores
        return json.dumps(salida)
    errores = bp.validar(p)
    if errores:
        salida["errores"] = errores
        return json.dumps(salida)

    piezas = bp.generar_piezas(p)
    tablas, avisos = bp.tablas_efectivas(p)
    r = bp.resumen(p)
    area = sum(bp.area(pz.contorno) * pz.cantidad for pz in piezas)           # mm2 de placa en piezas
    est = bp.estimar_placas(p)
    anclajes = bp.anclajes(p)
    salida.update({
        "ok": True, "avisos": avisos,
        "medidas": {
            "ancho_total": r["ancho_total_mueble"], "alto_total": r["alto_total"], "profundidad": r["profundidad_total"],
            "ancho_entre_postes": r["ancho_entre_postes"], "n_postes": p.n_postes, "n_tablas": len(tablas),
            "n_ranuras": p.n_ranuras, "luz": p.luz, "luz_max": r["luz_max"], "flecha": r["flecha_estimada"],
            "separacion": p.separacion, "espacio_libre": r["espacio_libre_entre_tablas"], "espesor": p.t,
            "n_escuadras": len(anclajes) * p.n_postes, "anclaje": p.anclaje, "n_tablas_min": bp.min_tablas(p),
            "peso_kg": round(area * p.t * 1e-9 * DENSIDAD_KG_M3, 1), "placas_minimas": est["placas_minimas"],
            "costo_minimo_usd": round(est["costo_minimo_usd"], 2), "precio_placa_usd": p.placa.precio_usd,
        },
        "piezas": [_pieza_web(pz) for pz in piezas],
        "instancias": [{"nombre": i.nombre, "tipo": i.tipo, "pieza": i.pieza, "origen": list(i.origen)}
                       for i in bp.instancias(p)],
        "tablas": [{"poste_ini": t.poste_ini, "poste_fin": t.poste_fin, "ranura": t.ranura,
                    "z": bp.z_ranura(p, t.ranura)} for t in tablas],
    })
    if anclajes:
        salida["herrajes"] = {"escuadra": hj.dimensiones_u(p), "replanteo": hj.tabla_replanteo(p),
                              "regla": [round(x.largo) for x in hj.regla_replanteo(p)]}
    return json.dumps(salida)


def plan_corte(json_str: str) -> str:
    datos = json.loads(json_str)
    p, notas, errores = _construir(datos)
    if errores or bp.validar(p):
        return json.dumps({"ok": False})
    z = ns.piezas_para_nesting(p)
    plan = ns.planificar(z, ns.Inventario(), p, ns.ConfigNesting(fresa=p.fresa))
    return json.dumps({
        "ok": True, "hojas": len(plan.hojas), "placas_nuevas": plan.placas_nuevas,
        "aprovechamiento": round(plan.aprovechamiento * 100, 1),
        "costo_usd": round(plan.placas_nuevas * p.placa.precio_usd, 2),
        "columnas": ns.columnas_por_placa(p, ns.ConfigNesting(fresa=p.fresa)),
        "sobrantes": [[round(r[2]), round(r[3])] for _, r in plan.sobrantes_nuevos],
        "svg": ns.plan_a_svg_texto(plan, 0.3),
    })


def valores_iniciales() -> str:
    p = bp.Params()
    return json.dumps({"t": p.t, "h": p.h, "fresa": p.fresa, "sep_min": p.sep_min, "profundidad": p.profundidad,
                       "zocalo_alto": p.zocalo_alto, "zocalo_prof": p.zocalo_prof, "anclaje": p.anclaje,
                       "limites": _limites({})})
