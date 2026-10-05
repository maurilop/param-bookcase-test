"""
nesting.py
----------
Acomoda las piezas de la biblioteca dentro de placas, respetando la veta (las piezas
no se rotan), y lleva el inventario de placas y sobrantes reutilizables.

Python puro, sin dependencias externas. Usa biblioteca_param.py.

Coordenadas de la placa (en mm)
  u = a lo largo de la placa (dirección de la veta, 2440)
  v = a lo ancho de la placa (1220)
Una pieza (largo L, profundidad 200) se coloca con su largo sobre u y su
profundidad sobre v. Se la gira 90° (sin espejar) respecto de su contorno original.

Flujo
  1. inv = Inventario.cargar("inventario.json")   (vacío si no existe)
  2. plan = planificar(piezas_para_nesting(p), inv, p, cfg)   (NO modifica el inventario)
  3. confirmar(inv, plan, "PED-001")   (descuenta placas usadas, agrega sobrantes)
  4. inv.guardar("inventario.json")
"""
import json
import math
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Tuple

import biblioteca_param as bp

Rect = Tuple[float, float, float, float]  # (u, v, ancho_u, alto_v)
EPS = 1e-6


# ----------------------------------------------------------------------------
# Configuración (valores PROVISORIOS hasta definir la máquina)
# ----------------------------------------------------------------------------
@dataclass
class ConfigNesting:
    fresa: float = 6.0               # diámetro de la fresa (mm)
    sep_extra: float = 2.0           # luz adicional entre piezas, además del diámetro de la fresa
    margen_sobrante: float = 5.0     # margen de seguridad en los bordes de un sobrante
    sobrante_min_largo: float = 500.0  # un sobrante se guarda solo si mide al menos esto a lo largo de la veta...
    sobrante_min_ancho: float = 210.0  # ...y esto a lo ancho (una pieza de 200 + márgenes)
    intentos: int = 40               # órdenes aleatorios probados además de los básicos
    semilla: int = 1
    tol_espesor: float = 0.2         # diferencia de espesor tolerada para reutilizar un sobrante

    @property
    def sep(self) -> float:
        """Distancia mínima entre piezas: lo que ocupa la fresa más una luz."""
        return self.fresa + self.sep_extra


# ----------------------------------------------------------------------------
# Piezas para acomodar
# ----------------------------------------------------------------------------
@dataclass
class PiezaNesting:
    id: str
    nombre: str
    du: float          # largo (sobre la veta)
    dv: float          # profundidad (a lo ancho)
    contorno: list
    area: float
    mecanizados: list = field(default_factory=list)   # rebajes (profundidad parcial)
    huecos: list = field(default_factory=list)        # agujeros pasantes


def piezas_para_nesting(p: "bp.Params") -> List[PiezaNesting]:
    out = []
    for pz in bp.generar_piezas(p):
        a = bp.area(pz.contorno)
        for k in range(1, pz.cantidad + 1):
            out.append(PiezaNesting(f"{pz.nombre}#{k}", pz.nombre, pz.largo, pz.ancho, pz.contorno, a,
                                    pz.mecanizados, pz.huecos))
    return out


def contorno_colocado(contorno, u0: float, v0: float, dv: float):
    """Contorno de la pieza en coordenadas de la placa (rotación de 90°, sin espejo)."""
    return [(u0 + y, v0 + dv - x, b) for (x, y, b) in contorno]


# ----------------------------------------------------------------------------
# Empaquetado MaxRects (sin rotación)
# ----------------------------------------------------------------------------
def _intersecta(a: Rect, b: Rect) -> bool:
    return (a[0] < b[0] + b[2] - EPS and a[0] + a[2] > b[0] + EPS and
            a[1] < b[1] + b[3] - EPS and a[1] + a[3] > b[1] + EPS)


def _contiene(a: Rect, b: Rect) -> bool:
    """¿a contiene a b?"""
    return (a[0] <= b[0] + EPS and a[1] <= b[1] + EPS and
            a[0] + a[2] >= b[0] + b[2] - EPS and a[1] + a[3] >= b[1] + b[3] - EPS)


def _podar(rects: List[Rect]) -> List[Rect]:
    res = []
    for i, r in enumerate(rects):
        if r[2] <= EPS or r[3] <= EPS:
            continue
        if any(i != j and _contiene(o, r) and (not _contiene(r, o) or j < i)
               for j, o in enumerate(rects) if o[2] > EPS and o[3] > EPS):
            continue
        res.append(r)
    return res


class MaxRects:
    def __init__(self, ancho: float, alto: float):
        self.libres: List[Rect] = [(0.0, 0.0, ancho, alto)]

    @staticmethod
    def _puntaje(r: Rect, w: float, h: float, heur: str):
        sobra_u, sobra_v = r[2] - w, r[3] - h
        if heur == "bssf":
            return (min(sobra_u, sobra_v), max(sobra_u, sobra_v))
        if heur == "blsf":
            return (max(sobra_u, sobra_v), min(sobra_u, sobra_v))
        return (r[0] + w, r[1])          # "bl": el que termina antes a lo largo de la veta

    def insertar(self, w: float, h: float, heur: str):
        mejor = None
        for r in self.libres:
            if w <= r[2] + EPS and h <= r[3] + EPS:
                sc = self._puntaje(r, w, h, heur)
                if mejor is None or sc < mejor[0]:
                    mejor = (sc, r[0], r[1])
        if mejor is None:
            return None
        _, x, y = mejor
        self._colocar((x, y, w, h))
        return x, y

    def _colocar(self, a: Rect):
        nuevos = []
        for r in self.libres:
            if not _intersecta(r, a):
                nuevos.append(r)
                continue
            if a[0] > r[0]:
                nuevos.append((r[0], r[1], a[0] - r[0], r[3]))
            if a[0] + a[2] < r[0] + r[2]:
                nuevos.append((a[0] + a[2], r[1], r[0] + r[2] - (a[0] + a[2]), r[3]))
            if a[1] > r[1]:
                nuevos.append((r[0], r[1], r[2], a[1] - r[1]))
            if a[1] + a[3] < r[1] + r[3]:
                nuevos.append((r[0], a[1] + a[3], r[2], r[1] + r[3] - (a[1] + a[3])))
        self.libres = _podar(nuevos)


# ----------------------------------------------------------------------------
# Sobrantes: descomposición del espacio libre en rectángulos disjuntos
# ----------------------------------------------------------------------------
def _restar(r: Rect, a: Rect) -> List[Rect]:
    if not _intersecta(r, a):
        return [r]
    res = []
    if a[0] > r[0]:
        res.append((r[0], r[1], a[0] - r[0], r[3]))
    if a[0] + a[2] < r[0] + r[2]:
        res.append((a[0] + a[2], r[1], r[0] + r[2] - (a[0] + a[2]), r[3]))
    x0, x1 = max(r[0], a[0]), min(r[0] + r[2], a[0] + a[2])
    if a[1] > r[1]:
        res.append((x0, r[1], x1 - x0, a[1] - r[1]))
    if a[1] + a[3] < r[1] + r[3]:
        res.append((x0, a[1] + a[3], x1 - x0, r[1] + r[3] - (a[1] + a[3])))
    return [q for q in res if q[2] > EPS and q[3] > EPS]


def descomponer_libres(libres: List[Rect], U: float, V: float, min_u: float, min_v: float) -> List[Rect]:
    """Rectángulos disjuntos aprovechables dentro del área útil [0,U]x[0,V]."""
    cands = []
    for (x, y, w, h) in libres:
        w2, h2 = min(x + w, U) - x, min(y + h, V) - y   # recorta lo que sobresale del área útil
        if w2 > EPS and h2 > EPS:
            cands.append((x, y, w2, h2))
    elegidos = []
    while cands:
        cands.sort(key=lambda r: r[2] * r[3], reverse=True)
        r = cands.pop(0)
        if r[2] + EPS < min_u or r[3] + EPS < min_v:
            continue
        elegidos.append(r)
        nuevos = []
        for c in cands:
            nuevos += _restar(c, r)
        cands = nuevos
    return elegidos


# ----------------------------------------------------------------------------
# Inventario
# ----------------------------------------------------------------------------
@dataclass
class Item:
    id: str
    tipo: str            # "placa" | "sobrante"
    material: str        # código de la placa (p. ej. MAB15244)
    espesor: float
    largo: float         # a lo largo de la veta
    ancho: float
    estado: str = "disponible"   # "disponible" | "usado"
    origen: str = ""             # "compra" o "PEDIDO:fuente" si es un sobrante
    usado_en: str = ""


class Inventario:
    def __init__(self, items: Optional[List[Item]] = None, pedidos: Optional[list] = None,
                 contadores: Optional[dict] = None):
        self.items: List[Item] = items or []
        self.pedidos: list = pedidos or []
        self.contadores: dict = contadores or {"P": 0, "S": 0}

    # --- persistencia
    @classmethod
    def cargar(cls, ruta: str) -> "Inventario":
        if not ruta or not os.path.exists(ruta):
            return cls()
        with open(ruta, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls([Item(**i) for i in d.get("items", [])], d.get("pedidos", []),
                   d.get("contadores", {"P": 0, "S": 0}))

    def guardar(self, ruta: str):
        d = {"items": [asdict(i) for i in self.items], "pedidos": self.pedidos,
             "contadores": self.contadores}
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ruta)

    # --- operaciones
    def _nuevo_id(self, prefijo: str) -> str:
        self.contadores[prefijo] = self.contadores.get(prefijo, 0) + 1
        return f"{prefijo}-{self.contadores[prefijo]:04d}"

    def agregar_placas(self, placa: "bp.Placa", cantidad: int, origen: str = "compra") -> List[str]:
        ids = []
        for _ in range(cantidad):
            it = Item(self._nuevo_id("P"), "placa", placa.codigo, placa.espesor_real,
                      placa.largo, placa.ancho, origen=origen)
            self.items.append(it)
            ids.append(it.id)
        return ids

    def agregar_sobrante(self, material: str, espesor: float, largo: float, ancho: float, origen: str) -> Item:
        it = Item(self._nuevo_id("S"), "sobrante", material, espesor, largo, ancho, origen=origen)
        self.items.append(it)
        return it

    def disponibles(self, material: str, espesor: float, tol: float):
        """(sobrantes, placas) disponibles del material y espesor pedidos."""
        ok = [i for i in self.items if i.estado == "disponible" and i.material == material
              and abs(i.espesor - espesor) <= tol]
        return ([i for i in ok if i.tipo == "sobrante"], [i for i in ok if i.tipo == "placa"])

    def resumen(self) -> str:
        disp = [i for i in self.items if i.estado == "disponible"]
        placas = [i for i in disp if i.tipo == "placa"]
        sob = [i for i in disp if i.tipo == "sobrante"]
        lineas = [f"Inventario: {len(placas)} placa(s) enteras y {len(sob)} sobrante(s) disponibles"]
        for i in sorted(sob, key=lambda x: -x.largo * x.ancho):
            lineas.append(f"  {i.id}  sobrante {i.largo:.0f} x {i.ancho:.0f} mm  ({i.material}, "
                          f"{i.espesor:g} mm)  de {i.origen}")
        return "\n".join(lineas)


# ----------------------------------------------------------------------------
# Plan de corte
# ----------------------------------------------------------------------------
@dataclass
class Colocacion:
    id: str
    nombre: str
    u: float            # esquina inferior izquierda, coordenadas físicas de la placa
    v: float
    du: float
    dv: float


@dataclass
class HojaPlan:
    fuente: str                   # "sobrante" | "placa" | "nueva"
    item_id: Optional[str]
    largo: float
    ancho: float
    margen: float
    colocaciones: List[Colocacion] = field(default_factory=list)
    sobrantes: List[Rect] = field(default_factory=list)   # rectángulos nuevos aprovechables (coord. físicas)
    area_piezas: float = 0.0


@dataclass
class Plan:
    hojas: List[HojaPlan]
    material: str
    espesor: float
    cfg: ConfigNesting
    contornos: dict = field(default_factory=dict)   # nombre de pieza -> contorno
    mecanizados: dict = field(default_factory=dict) # nombre de pieza -> rebajes (profundidad parcial)
    huecos: dict = field(default_factory=dict)      # nombre de pieza -> agujeros pasantes

    @property
    def placas_nuevas(self) -> int:
        return sum(1 for h in self.hojas if h.fuente == "nueva")

    @property
    def placas_inventario(self) -> int:
        return sum(1 for h in self.hojas if h.fuente == "placa")

    @property
    def sobrantes_usados(self) -> int:
        return sum(1 for h in self.hojas if h.fuente == "sobrante")

    @property
    def sobrantes_nuevos(self) -> List[Tuple[int, Rect]]:
        return [(i, r) for i, h in enumerate(self.hojas) for r in h.sobrantes]

    @property
    def aprovechamiento(self) -> float:
        a = sum(h.largo * h.ancho for h in self.hojas)
        return sum(h.area_piezas for h in self.hojas) / a if a else 0.0


def _empacar(orden, fuentes, heur, cfg: ConfigNesting, placa: "bp.Placa"):
    """Devuelve una lista de (fuente, MaxRects, colocaciones[(pieza, x, y)]) o lanza ValueError."""
    sep = cfg.sep
    restantes = list(orden)
    usos = []

    def llenar(fuente):
        nonlocal restantes
        U, V = fuente.largo - 2 * fuente.margen, fuente.ancho - 2 * fuente.margen
        mr = MaxRects(U + sep, V + sep)
        cols, sig = [], []
        for pz in restantes:
            pos = mr.insertar(pz.du + sep, pz.dv + sep, heur)
            (cols if pos else sig).append((pz, pos) if pos else pz)
        if cols:
            usos.append((fuente, mr, cols))
            restantes = sig
        return bool(cols)

    for f in fuentes:
        if not restantes:
            break
        llenar(f)
    while restantes:
        f = HojaPlan("nueva", None, placa.largo, placa.ancho, placa.margen_borde)
        if not llenar(f):
            raise ValueError("Una pieza no entra en una placa entera: revisá las medidas.")
    return usos


def planificar(piezas: List[PiezaNesting], inv: Inventario, p: "bp.Params",
               cfg: Optional[ConfigNesting] = None) -> Plan:
    """Plan de corte que usa primero los sobrantes, luego las placas del inventario y,
    si no alcanza, placas nuevas. No modifica el inventario."""
    cfg = cfg or ConfigNesting(fresa=p.fresa)
    placa = p.placa
    min_ancho = max(cfg.sobrante_min_ancho, p.profundidad + 2 * cfg.margen_sobrante)
    sobrantes, placas = inv.disponibles(placa.codigo, p.t, cfg.tol_espesor)
    fuentes = ([HojaPlan("sobrante", i.id, i.largo, i.ancho, cfg.margen_sobrante)
                for i in sorted(sobrantes, key=lambda x: x.largo * x.ancho)] +
               [HojaPlan("placa", i.id, i.largo, i.ancho, placa.margen_borde) for i in placas])

    rnd = random.Random(cfg.semilla)
    ordenes = [sorted(piezas, key=lambda z: (-z.du, -z.dv)),
               sorted(piezas, key=lambda z: (-z.du * z.dv, -z.du)),
               sorted(piezas, key=lambda z: (-z.dv, -z.du))]
    for _ in range(cfg.intentos):
        ordenes.append(sorted(piezas, key=lambda z: -z.du * (0.7 + 0.6 * rnd.random())))

    # Se prueban dos estrategias: con los sobrantes disponibles y sin ellos. Gana la que
    # compra menos placas; a igualdad, la que gasta menos placas enteras y menos material.
    mejor, mejor_sc = None, None
    variantes = [fuentes]
    if sobrantes and placas:
        variantes.append([f for f in fuentes if f.fuente != "sobrante"])
    for fuentes_v in variantes:
        for orden in ordenes:
            for heur in ("bssf", "blsf", "bl"):
                try:
                    usos = _empacar(orden, [HojaPlan(f.fuente, f.item_id, f.largo, f.ancho, f.margen)
                                            for f in fuentes_v], heur, cfg, placa)
                except ValueError:
                    continue
                nuevas = sum(1 for f, _, _ in usos if f.fuente == "nueva")
                enteras = sum(1 for f, _, _ in usos if f.fuente == "placa")
                area = sum(f.largo * f.ancho for f, _, _ in usos)
                sc = (nuevas, enteras, area)
                if mejor_sc is None or sc < mejor_sc:
                    mejor, mejor_sc = usos, sc
    if mejor is None:
        raise ValueError("No se pudo armar el plan de corte.")

    hojas = []
    for f, mr, cols in mejor:
        m = f.margen
        U, V = f.largo - 2 * m, f.ancho - 2 * m
        for pz, (x, y) in cols:
            f.colocaciones.append(Colocacion(pz.id, pz.nombre, m + x, m + y, pz.du, pz.dv))
            f.area_piezas += pz.area
        # Espacio libre con la separación de la fresa en TODOS los lados de cada pieza
        # (para poder cortar el sobrante sin tocar las piezas).
        sep = cfg.sep
        mr2 = MaxRects(U, V)
        for pz, (x, y) in cols:
            mr2._colocar((x - sep, y - sep, pz.du + 2 * sep, pz.dv + 2 * sep))
        libres = descomponer_libres(mr2.libres, U, V, cfg.sobrante_min_largo, min_ancho)
        f.sobrantes = [(m + x, m + y, w, h) for (x, y, w, h) in libres]
        hojas.append(f)
    return Plan(hojas, placa.codigo, p.t, cfg, {pz.nombre: pz.contorno for pz in piezas},
                {pz.nombre: pz.mecanizados for pz in piezas}, {pz.nombre: pz.huecos for pz in piezas})


def columnas_por_placa(p: "bp.Params", cfg: Optional[ConfigNesting] = None) -> int:
    """Cuántas columnas de piezas (de ancho = profundidad) entran a lo ancho de la placa."""
    cfg = cfg or ConfigNesting(fresa=p.fresa)
    util = bp.ancho_util(p.placa)
    return max(0, int((util + cfg.sep) // (p.profundidad + cfg.sep)))


def profundidad_max_para_columnas(placa: "bp.Placa", cfg: ConfigNesting, columnas: int) -> float:
    """Mayor profundidad de pieza con la que entran 'columnas' columnas en la placa."""
    return (bp.ancho_util(placa) - (columnas - 1) * cfg.sep) / columnas


def verificar_plan(plan: Plan, piezas: List[PiezaNesting]) -> List[str]:
    """Comprobaciones independientes del algoritmo: nada se pisa, nada sale de la placa,
    respeta la separación y están todas las piezas exactamente una vez."""
    err = []
    ids = [c.id for h in plan.hojas for c in h.colocaciones]
    if sorted(ids) != sorted(p.id for p in piezas):
        err.append("Las piezas colocadas no coinciden con las pedidas.")
    sep = plan.cfg.sep
    for n, h in enumerate(plan.hojas, 1):
        for c in h.colocaciones:
            if (c.u < h.margen - EPS or c.v < h.margen - EPS or
                    c.u + c.du > h.largo - h.margen + EPS or c.v + c.dv > h.ancho - h.margen + EPS):
                err.append(f"Hoja {n}: {c.id} sale del área útil.")
        cs = h.colocaciones
        for i in range(len(cs)):
            for j in range(i + 1, len(cs)):
                a, b = cs[i], cs[j]
                sep_u = max(b.u - (a.u + a.du), a.u - (b.u + b.du))
                sep_v = max(b.v - (a.v + a.dv), a.v - (b.v + b.dv))
                if max(sep_u, sep_v) < sep - 1e-4:
                    err.append(f"Hoja {n}: {a.id} y {b.id} quedan a menos de {sep:.1f} mm.")
        for (u, v, w, hh) in h.sobrantes:      # un sobrante no puede pisar una pieza ni quedar cerca
            for c in cs:
                sep_u = max(c.u - (u + w), u - (c.u + c.du))
                sep_v = max(c.v - (v + hh), v - (c.v + c.dv))
                if max(sep_u, sep_v) < sep - 1e-4:
                    err.append(f"Hoja {n}: un sobrante queda a menos de {sep:.1f} mm de {c.id}.")
    return err


def texto_plan(plan: Plan, inv: Optional[Inventario] = None) -> List[str]:
    lin = []
    tot = len(plan.hojas)
    lin.append(f"Nesting: {tot} hoja(s) en total | {plan.sobrantes_usados} sobrante(s) y "
               f"{plan.placas_inventario} placa(s) del inventario | {plan.placas_nuevas} placa(s) a comprar")
    lin.append(f"Aprovechamiento del material usado: {plan.aprovechamiento * 100:.1f} %  "
               f"(fresa {plan.cfg.fresa:g} mm, separación entre piezas {plan.cfg.sep:g} mm)")
    for n, h in enumerate(plan.hojas, 1):
        etiqueta = {"nueva": "placa nueva", "placa": f"placa {h.item_id}",
                    "sobrante": f"sobrante {h.item_id}"}[h.fuente]
        lin.append(f"  Hoja {n}: {etiqueta} ({h.largo:.0f} x {h.ancho:.0f}) - {len(h.colocaciones)} piezas")
    nuevos = plan.sobrantes_nuevos
    lin.append(f"Sobrantes reutilizables que quedarían: {len(nuevos)}")
    for i, (n, (u, v, w, h)) in enumerate(sorted(nuevos, key=lambda t: -t[1][2] * t[1][3]), 1):
        lin.append(f"  {w:.0f} x {h:.0f} mm  (hoja {n + 1})")
    return lin


# ----------------------------------------------------------------------------
# Confirmar un pedido: descuenta placas usadas y agrega los sobrantes al inventario
# ----------------------------------------------------------------------------
def confirmar(inv: Inventario, plan: Plan, pedido_id: str, placa: "bp.Placa") -> dict:
    if any(ped["id"] == pedido_id for ped in inv.pedidos):
        raise ValueError(f"El pedido '{pedido_id}' ya fue confirmado; no se vuelve a descontar.")
    # validar que todo lo que se va a usar siga disponible
    por_id = {i.id: i for i in inv.items}
    for h in plan.hojas:
        if h.fuente != "nueva":
            it = por_id.get(h.item_id)
            if it is None or it.estado != "disponible":
                raise ValueError(f"{h.item_id} ya no está disponible: volvé a generar el plan.")
    usados, nuevos = [], []
    for h in plan.hojas:
        if h.fuente == "nueva":
            iid = inv.agregar_placas(placa, 1, origen="compra")[0]
            it = [i for i in inv.items if i.id == iid][0]
        else:
            it = por_id[h.item_id]
        it.estado, it.usado_en = "usado", pedido_id
        usados.append(it.id)
        for (u, v, w, hh) in h.sobrantes:
            s = inv.agregar_sobrante(plan.material, plan.espesor, w, hh, f"{pedido_id}:{it.id}")
            nuevos.append(s.id)
    inv.pedidos.append({"id": pedido_id, "fecha": datetime.now().isoformat(timespec="seconds"),
                        "piezas": sum(len(h.colocaciones) for h in plan.hojas),
                        "fuentes_usadas": usados, "sobrantes_generados": nuevos,
                        "placas_compradas": plan.placas_nuevas})
    return {"usados": usados, "sobrantes_nuevos": nuevos}


# ----------------------------------------------------------------------------
# Exportación a SVG (para ver el plan en el navegador)
# ----------------------------------------------------------------------------
def plan_a_svg_texto(plan: Plan, escala: float = 0.35) -> str:
    sep_h = 60
    ancho_max = max(h.largo for h in plan.hojas)
    total_h = sum(h.ancho + sep_h for h in plan.hojas) + 40
    W, H = ancho_max * escala + 40, total_h * escala + 30
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
           f'viewBox="0 0 {W:.0f} {H:.0f}" font-family="sans-serif">',
           '<rect width="100%" height="100%" fill="white"/>']
    y_base = 30.0                      # margen superior (px) para el título de la primera hoja
    for n, h in enumerate(plan.hojas, 1):
        def X(u): return 20 + u * escala
        def Y(v): return y_base + (h.ancho - v) * escala      # v hacia arriba
        etiqueta = {"nueva": "Placa nueva", "placa": f"Placa {h.item_id}",
                    "sobrante": f"Sobrante {h.item_id}"}[h.fuente]
        out.append(f'<text x="20" y="{y_base - 6:.0f}" font-size="13" fill="#333">'
                   f'Hoja {n}: {etiqueta} - {h.largo:.0f} x {h.ancho:.0f} mm</text>')
        out.append(f'<rect x="{X(0):.1f}" y="{Y(h.ancho):.1f}" width="{h.largo * escala:.1f}" '
                   f'height="{h.ancho * escala:.1f}" fill="#f3e3c3" stroke="#555"/>')
        out.append(f'<rect x="{X(h.margen):.1f}" y="{Y(h.ancho - h.margen):.1f}" '
                   f'width="{(h.largo - 2 * h.margen) * escala:.1f}" '
                   f'height="{(h.ancho - 2 * h.margen) * escala:.1f}" fill="none" stroke="#aaa" '
                   f'stroke-dasharray="4 3"/>')
        for (u, v, w, hh) in h.sobrantes:
            out.append(f'<rect x="{X(u):.1f}" y="{Y(v + hh):.1f}" width="{w * escala:.1f}" '
                       f'height="{hh * escala:.1f}" fill="#9bd39b" fill-opacity="0.45" stroke="#2e8b2e" '
                       f'stroke-dasharray="6 3"/>')
            out.append(f'<text x="{X(u) + 4:.1f}" y="{Y(v + hh) + 14:.1f}" font-size="11" fill="#1d5e1d">'
                       f'sobrante {w:.0f} x {hh:.0f}</text>')
        for c in h.colocaciones:
            cont = contorno_colocado(plan.contornos[c.nombre], c.u, c.v, c.dv)
            pts = bp.muestrear(cont, 10)
            d = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in pts)
            color = "#a98ae0" if c.nombre == "poste" else "#7d9bf0"
            out.append(f'<polygon points="{d}" fill="{color}" stroke="#222" stroke-width="0.8"/>')
            for m in plan.mecanizados.get(c.nombre, []):            # rebajes (naranja) y agujeros (rojo)
                mc = contorno_colocado(m["contorno"], c.u, c.v, c.dv)
                dm = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in bp.muestrear(mc, 16))
                if m.get("manual"):                                    # cara opuesta: va a mano, se dibuja punteado
                    out.append(f'<polygon points="{dm}" fill="none" stroke="#2a6fdb" stroke-width="0.9" stroke-dasharray="3 2"/>')
                else:
                    out.append(f'<polygon points="{dm}" fill="#e8a33d" fill-opacity="0.55" stroke="#e8a33d" stroke-width="0.8"/>')
            for hu in plan.huecos.get(c.nombre, []):                # agujeros pasantes
                dh = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in bp.muestrear(contorno_colocado(hu["contorno"], c.u, c.v, c.dv), 16))
                out.append(f'<polygon points="{dh}" fill="white" stroke="#222" stroke-width="0.8"/>')
            out.append(f'<text x="{X(c.u + c.du / 2):.1f}" y="{Y(c.v + c.dv / 2) + 4:.1f}" font-size="10" '
                       f'text-anchor="middle" fill="#111">{c.id}</text>')
        y_base += (h.ancho + sep_h) * escala
    out.append("</svg>")
    return "\n".join(out)


def plan_a_svg(plan: Plan, ruta: str, escala: float = 0.35):
    """Guarda el plan de corte como SVG."""
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(plan_a_svg_texto(plan, escala))
