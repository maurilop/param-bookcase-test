"""
biblioteca_param.py
-------------------
Fuente única de verdad del diseño de la biblioteca.

Recibe parámetros y devuelve los contornos 2D de cada pieza (postes y tablas).
Python puro, sin dependencias: sirve igual dentro de Rhino 8, en un backend web,
en el nesting y en la generación del archivo CNC.

Convenciones
- Unidades: milímetros.
- Cada contorno es una lista de vértices (x, y, bulge), recorrida en sentido
  antihorario. El "bulge" del vértice i describe el tramo i -> i+1:
  0 = recta; >0 = arco antihorario (mismo criterio que LWPOLYLINE de DXF;
  bulge = tan(ángulo_del_arco / 4)).
- Poste:  x = profundidad (0 = atrás, p.profundidad = frente), y = altura desde la base.
- Tabla:  x = profundidad (0 = atrás, p.profundidad = frente), y = largo.
"""
import math
import random
from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple

# ----------------------------------------------------------------------------
# Constantes de diseño FIJAS (acordadas por ahora)
# ----------------------------------------------------------------------------
BASE_A_PRIMERA_RANURA = 200.0 # base del poste -> inicio de la primera ranura
SEPARACION_MIN = 110.0        # mínimo de material macizo entre el borde de una ranura y el inicio de la
                              # siguiente. Con tablas separadas 2 ranuras deja >= 2*110 + 15 = 235 mm libres.
ULTIMA_RANURA_A_TOPE = 100.0  # fin de la última ranura -> extremo superior del poste
VOLADIZO = 100.0              # lo que la tabla sobresale de los postes extremos
PROFUNDIDAD_DEFECTO = 193.0   # profundidad (ancho) de postes y tablas; con la placa de 1220 mm y fresa de
                              # 6 mm es lo máximo que permite 6 columnas de piezas por placa
# La profundidad de las ranuras es siempre la mitad de la profundidad de la pieza: así las
# dos mitades de cada encastre se tocan exactamente (ver prof_ranura).
R_BOCA = 5.0                  # redondeo de la boca de las ranuras y esquinas traseras
R_FRENTE = 20.0               # redondeo de las esquinas frontales

# Anclaje de los postes a la pared: escuadra empotrada en el poste (invisible de frente).
# Medidas de la escuadra (decisión de diseño; se ajustan cuando se defina el herraje):
ANCLAJE_ESPESOR_DEFECTO = 2.0  # espesor de la chapa = profundidad de la muesca y del rebaje
ANCLAJE_ALTO_DEFECTO = 20.0    # alto de la escuadra (a lo largo del poste)
ANCLAJE_ANCHO_DEFECTO = 40.0   # largo del brazo que apoya sobre la cara lateral del poste
AGUJERO_RADIO_DEFECTO = 2.25   # radio del agujero pasante del pasador (2,25 mm = Ø4,5, para un tornillo M4)
FRESA_MANUAL_DEFECTO = 6.0     # diámetro de la fresa del router manual (rebaje de la cara opuesta)
BUJE_DEFECTO = 10.0            # diámetro exterior del buje guía del router manual
HOLGURA_U_DEFECTO = 0.5        # holgura en el ancho interior de la U de la escuadra
# La profundidad de la escuadra (base contra la pared) es siempre el espesor de la placa.
ANCLAJE_A_RANURA = 10.0       # distancia entre la escuadra y la ranura más cercana (1 cm)
ANCLAJE_HOLGURA = 1.0         # holgura total en el alto de la muesca y del rebaje
NUCLEO_MIN = 6.0              # espesor mínimo del núcleo de madera entre los dos rebajes del poste
ANCLAJES = ("ninguno", "superior", "ambos")

# ----------------------------------------------------------------------------
# Reglas estructurales (deducidas; a confirmar con el prototipo físico)
# ----------------------------------------------------------------------------
MIN_TABLAS_POR_TRAMO = 2      # cada tramo entre postes contiguos lo cruzan >= 2 tablas
ZONA_ATADO = 2                # cada poste debe estar atado en las 2 ranuras más bajas y en las 2 más altas

# Luz entre postes: el límite lo da la FLECHA de las tablas con libros (la resistencia sobra).
# Se calcula una tabla apoyada en dos postes (caso más desfavorable), con fluencia a largo plazo.
LUZ_MIN = 250.0               # > 2 x voladizo (si no, tablas contiguas a igual altura se tocan) y deja
                              # apoyar acostado un libro de ~230 mm
E_DISENO = 7000.0             # MPa, módulo de elasticidad de la multiplaca, veta paralela a la luz.
                              # Valor conservador (publicados: 7000-10000). A CONFIRMAR con un ensayo.
CARGA_LIBROS = 0.002          # N/mm2 = 2,0 kPa (~200 kg por m2 de estante, libros de tapa dura de ~23 cm)
FLUENCIA = 1.6                # la flecha crece ~60 % con el tiempo bajo carga (EN 1995, contrachapado)
LIM_FLECHA = 300.0            # flecha final admisible = luz / 300

# ----------------------------------------------------------------------------
# Límites PROVISORIOS (a confirmar con el prototipo físico)
# ----------------------------------------------------------------------------
LIMITES = {
    "t": (5.0, 30.0),             # espesor del tablero
    "h": (0.0, 0.5),              # holgura (definida por vos)
    "n_postes": (2, 20),
    "n_ranuras": (4, 40),
    "remanente_min": 20.0,        # material mínimo que debe quedar entre ranuras / sobre el zócalo
    "zocalo_alto": (0.0, 150.0),
    "zocalo_prof": (0.0, 50.0),
    "profundidad": (100.0, 300.0),  # profundidad de postes y tablas
    "fresa": (3.0, 12.0),          # diámetro de la fresa
    "anclaje_alto": (8.0, 60.0),
    "anclaje_ancho": (15.0, 80.0),
    "anclaje_espesor": (1.0, 5.0),
    "agujero_radio": (1.0, 5.0),
    "fresa_manual": (3.0, 12.0),
    "buje": (6.0, 30.0),
    "holgura_u": (0.0, 2.0),
    "n_tablas": (2, 120),         # el mínimo real depende de los postes (ver min_tablas)
    "sep_min": (1, 10),           # separación mínima (en ranuras) entre tablas de un mismo tramo
}


# ----------------------------------------------------------------------------
# Placa (tablero) de partida
# ----------------------------------------------------------------------------
@dataclass
class Placa:
    nombre: str
    largo: float                 # mm, dirección de la veta
    ancho: float                 # mm
    espesor_nominal: float       # mm, el que figura en el comercio
    espesor_real: float          # mm, medido con calibre (define las ranuras)
    margen_borde: float = 10.0   # mm sin usar en cada borde (PROVISORIO)
    precio_usd: float = 0.0      # precio de referencia por placa
    proveedor: str = ""
    codigo: str = ""
    no_rotar: bool = True        # la veta debe quedar a lo largo de la placa: las piezas no se rotan


# Multiplaca de abedul 15 mm, 2,44 x 1,22 m - Barraca Paraná, cód. MAB15244.
# Precio de referencia: U$S 115,71 (consultado el 2026-10-03). Etiquetada "no-rotar".
# El espesor real hay que medirlo con calibre; hasta entonces se asume el nominal.
PLACA_ABEDUL_15 = Placa(
    nombre="Multiplaca abedul 15 mm", largo=2440.0, ancho=1220.0,
    espesor_nominal=15.0, espesor_real=15.0, margen_borde=10.0,
    precio_usd=115.71, proveedor="Barraca Paraná", codigo="MAB15244", no_rotar=True,
)


def largo_util(placa: Placa) -> float:
    return placa.largo - 2 * placa.margen_borde


def ancho_util(placa: Placa) -> float:
    return placa.ancho - 2 * placa.margen_borde


@dataclass
class Tabla:
    """Una tabla horizontal: de qué poste a qué poste va y en qué ranura."""
    poste_ini: int   # índice del primer poste que cruza (0 = el primero)
    poste_fin: int   # índice del último poste que cruza (inclusive)
    ranura: int      # índice de ranura (0 = la más baja)


# Configuración del modelo original (biblioteca.3dm)
TABLAS_DEMO = [
    Tabla(0, 3, 15), Tabla(0, 3, 0),
    Tabla(1, 3, 13), Tabla(0, 2, 6), Tabla(1, 3, 4),
    Tabla(0, 1, 10), Tabla(2, 3, 10), Tabla(2, 3, 2), Tabla(1, 2, 8),
]


@dataclass
class Params:
    t: Optional[float] = None  # espesor de trabajo; si es None se usa el espesor real de la placa
    placa: Placa = field(default_factory=lambda: PLACA_ABEDUL_15)
    h: float = 0.0             # holgura (0 a 0,5)
    n_postes: int = 4
    luz: Optional[float] = None  # luz libre entre postes; si es None se usa la máxima estructural luz_max(t)
    n_ranuras: int = 16
    separacion: float = SEPARACION_MIN   # material entre ranuras consecutivas (mín. SEPARACION_MIN)
    anclaje: str = "ambos"      # anclaje a la pared en cada poste: "ninguno", "superior" o "ambos"
    anclaje_alto: float = ANCLAJE_ALTO_DEFECTO       # alto de la escuadra
    anclaje_ancho: float = ANCLAJE_ANCHO_DEFECTO     # largo del brazo lateral de la escuadra
    anclaje_espesor: float = ANCLAJE_ESPESOR_DEFECTO # espesor de la chapa de la escuadra
    agujero_radio: float = AGUJERO_RADIO_DEFECTO     # radio del agujero PASANTE del pasador
    holgura_u: float = HOLGURA_U_DEFECTO             # holgura del ancho interior de la U
    fresa_manual: float = FRESA_MANUAL_DEFECTO       # fresa del router manual (rebaje de la cara opuesta)
    buje: float = BUJE_DEFECTO                       # buje guía del router manual (diámetro exterior)
    fresa: float = 6.0         # diámetro de la fresa: define los alivios de los rincones y la separación entre piezas
    profundidad: float = PROFUNDIDAD_DEFECTO   # profundidad (ancho) de postes y tablas
    # Tablas horizontales. Dos modos:
    #  - automático (tablas=None): se generan n_tablas con posiciones al azar
    #    reproducibles según 'semilla'
    #  - manual: lista explícita de Tabla(...)
    tablas: Optional[List[Tabla]] = None
    n_tablas: int = 9           # total, incluidas las 2 estructurales (base y tope)
    semilla: int = 0            # cambiar la semilla = otra distribución al azar
    sep_min: int = 2            # separación mínima en ranuras entre tablas de un mismo tramo
    ranuras_unicas: bool = False # True: ninguna altura (ranura) se repite en todo el mueble
                                 # (False: solo se prohíbe repetirla en un mismo poste)
    zocalo: bool = True
    zocalo_alto: float = 55.0
    zocalo_prof: float = 15.0
    # Solo para validar contra el modelo original, que tiene la ranura del poste
    # en 20 por error. En uso normal dejar en None (ancho = t + h).
    _ancho_ranura_poste: float = None
    # Idem, solo para validar contra el modelo original (base 160 y paso 120):
    _base_inferior: float = None
    _paso: float = None

    def __post_init__(self):
        if self.t is None:
            self.t = self.placa.espesor_real
        if self.luz is None:
            self.luz = luz_max(self.t)


@dataclass
class Pieza:
    nombre: str
    tipo: str                       # "poste" | "tabla"
    contorno: List[Tuple[float, float, float]]
    espesor: float
    cantidad: int
    ancho: float                    # bbox en x
    largo: float                    # bbox en y
    # Mecanizados de profundidad parcial (rebajes y agujeros ciegos), todos desde la cara de corte
    # (la cara superior de la placa): [{tipo, contorno, prof, ...}]
    mecanizados: list = field(default_factory=list)
    # Agujeros pasantes (contornos interiores): [{tipo, contorno, centro, radio, con_broca, ...}]
    huecos: list = field(default_factory=list)
    material: str = "multiplaca"    # las plantillas y reglas son de MDF y no entran en el nesting de la placa


# ----------------------------------------------------------------------------
# Medidas derivadas
# ----------------------------------------------------------------------------
def ancho_ranura(p: Params) -> float:
    return p.t + p.h


def luz_max(t: float) -> float:
    """Luz máxima entre postes (mm) para que la flecha final de una tabla de espesor t, cargada con
    libros, no pase de luz/LIM_FLECHA. Resulta proporcional al espesor (~36 x t); se redondea
    hacia abajo a múltiplos de 5 mm. Para t = 15 mm da 540 mm."""
    c = FLUENCIA * 60.0 / 384.0
    return math.floor(t * (E_DISENO / (c * CARGA_LIBROS * LIM_FLECHA)) ** (1.0 / 3.0) / 5.0 + 1e-9) * 5.0


def flecha_final(luz: float, t: float) -> float:
    """Flecha final estimada (mm) de una tabla apoyada en dos postes, con libros y fluencia."""
    c = FLUENCIA * 60.0 / 384.0
    return c * CARGA_LIBROS * luz ** 4 / (E_DISENO * t ** 3)


def base_inferior(p: Params) -> float:
    """Espacio bajo la ranura más baja."""
    return p._base_inferior if p._base_inferior is not None else BASE_A_PRIMERA_RANURA


def paso(p: Params) -> float:
    """Distancia de inicio a inicio entre ranuras consecutivas = separación + ancho de ranura."""
    return p._paso if p._paso is not None else p.separacion + ancho_ranura(p)


def z_ranura(p: Params, k: int) -> float:
    """Altura (desde la base del poste) donde empieza la ranura k (0 = la más baja)."""
    return base_inferior(p) + k * paso(p)


def espacio_libre(p: Params) -> float:
    """Espacio vertical libre entre dos tablas separadas sep_min ranuras (para los libros)."""
    return p.sep_min * paso(p) - p.t


def altura_con(n_ranuras: int, t: float, h: float, separacion: float) -> float:
    """Alto del poste para n ranuras con una separación dada."""
    return BASE_A_PRIMERA_RANURA + ULTIMA_RANURA_A_TOPE + n_ranuras * (t + h) + (n_ranuras - 1) * separacion


def altura_poste(p: Params) -> float:
    w = p._ancho_ranura_poste if p._ancho_ranura_poste else ancho_ranura(p)
    return base_inferior(p) + (p.n_ranuras - 1) * paso(p) + w + ULTIMA_RANURA_A_TOPE


def alivio(p: Params) -> float:
    """Radio de los alivios de los rincones interiores = radio de la fresa, con signo negativo para
    _redondear. Con fresa 0 no se hacen alivios (solo para comparar con el modelo original)."""
    return -p.fresa / 2.0 if p.fresa > 0 else 0.0


def alto_muesca(p: Params) -> float:
    """Alto de la muesca trasera para la escuadra. La muesca (2 mm) es menos profunda que el radio de
    la fresa, así que los rincones quedan redondeados: se agranda el alto para que la chapa entre igual
    (con fresa 6 mm: 20 -> 26,7 mm). Se ajusta sola con la fresa."""
    r, d = p.fresa / 2.0, p.anclaje_espesor
    extra = 0.0 if r <= 0 else (math.sqrt(2 * r * d - d * d) if d < r else r)
    return p.anclaje_alto + 2 * extra + ANCLAJE_HOLGURA


def anclajes(p: Params) -> list:
    """Posición de las escuadras en cada poste: la superior 1 cm sobre la ranura más alta y la inferior
    1 cm bajo la ranura más baja. Devuelve [{nombre, z_ini, z_fin}] con la altura de la escuadra."""
    if p.anclaje == "ninguno":
        return []
    z_ult = z_ranura(p, p.n_ranuras - 1) + ancho_ranura(p)
    res = [{"nombre": "superior", "z_ini": z_ult + ANCLAJE_A_RANURA,
            "z_fin": z_ult + ANCLAJE_A_RANURA + p.anclaje_alto}]
    if p.anclaje == "ambos":
        z_pri = z_ranura(p, 0)
        res.append({"nombre": "inferior", "z_ini": z_pri - ANCLAJE_A_RANURA - p.anclaje_alto,
                    "z_fin": z_pri - ANCLAJE_A_RANURA})
    return res


def muescas_anclaje(p: Params) -> list:
    """(z_abajo, z_arriba) de cada muesca trasera, de arriba hacia abajo."""
    h = alto_muesca(p)
    out = [((a["z_ini"] + a["z_fin"]) / 2 - h / 2, (a["z_ini"] + a["z_fin"]) / 2 + h / 2) for a in anclajes(p)]
    return sorted(out, key=lambda t: -t[0])


def _circulo(cx: float, cz: float, r: float):
    """Contorno de un círculo: dos semicírculos antihorarios (bulge = 1)."""
    return [(cx - r, cz, 1.0), (cx + r, cz, 1.0)]


def _rect(x0, z0, x1, z1):
    """Rectángulo antihorario como contorno."""
    return [(x0, z0, 0.0), (x1, z0, 0.0), (x1, z1, 0.0), (x0, z1, 0.0)]


def _zona_escuadra(p: Params, a: dict):
    """Límites del rebaje (con holgura) y centro de la escuadra de un anclaje."""
    zc = (a["z_ini"] + a["z_fin"]) / 2
    x0, x1 = p.anclaje_espesor, p.anclaje_ancho + ANCLAJE_HOLGURA / 2
    h = p.anclaje_alto + ANCLAJE_HOLGURA
    return zc, x0, x1, zc - h / 2, zc + h / 2


def mecanizados_poste(p: Params) -> list:
    """Rebajes de profundidad parcial para la escuadra en U, en las DOS caras del poste:
      - cara de corte (+Y): lo hace la CNC, con alivios en los dos rincones del extremo según la fresa.
      - cara opuesta (-Y): lo hace a mano un router con la plantilla (ver herrajes.plantilla_router); sus rincones
        quedan redondeados con el radio de la fresa manual, así que los brazos de la escuadra deben llevar
        las puntas redondeadas con ese radio como mínimo.
    Ambos arrancan en el fondo de la muesca trasera y miden lo mismo en el plano del poste."""
    out = []
    e = p.anclaje_espesor
    al = alivio(p)
    rm = p.fresa_manual / 2.0
    for a in anclajes(p):
        zc, x0, x1, z0, z1 = _zona_escuadra(p, a)
        # CNC: horario (el espacio vaciado queda a la derecha del recorrido, igual que las ranuras)
        out.append({"tipo": "rebaje", "cara": "corte", "manual": False, "anclaje": a["nombre"], "prof": e,
                    "contorno": _redondear([(x0, z0, 0), (x0, z1, 0), (x1, z1, al), (x1, z0, al)])})
        # Manual: antihorario, con las dos esquinas del extremo redondeadas por la fresa manual
        out.append({"tipo": "rebaje", "cara": "opuesta", "manual": True, "anclaje": a["nombre"], "prof": e,
                    "contorno": _redondear([(x0, z0, 0), (x1, z0, rm), (x1, z1, rm), (x0, z1, 0)])})
    return out


def huecos_poste(p: Params) -> list:
    """Agujero PASANTE del pasador en cada escuadra, centrado en alto y en largo sobre el brazo lateral.
    Atraviesa brazo, poste y brazo; sirve de referencia para la plantilla del rebaje manual."""
    out = []
    for a in anclajes(p):
        zc = (a["z_ini"] + a["z_fin"]) / 2
        xc = p.anclaje_ancho / 2                         # centro del brazo lateral (medido desde la pared)
        out.append({"tipo": "agujero", "anclaje": a["nombre"], "centro": (xc, zc), "radio": p.agujero_radio,
                    "contorno": _circulo(xc, zc, p.agujero_radio), "pasante": True,
                    "con_broca": 2 * p.agujero_radio < p.fresa})
    return out


def cortes_3d(p: Params) -> list:
    """Cortadores para restar en el modelo 3D de cada poste (rebajes de las dos caras y agujero pasante).
    Cada uno: contorno (en el plano del poste), y_desde (distancia desde la cara -Y del poste) y largo
    (extrusión hacia +Y). Se pasan 1 mm de la cara para que la resta booleana quede limpia.
    La cara de corte es la +Y: en el montaje, la cara superior de la placa queda hacia +Y."""
    e, t = p.anclaje_espesor, p.t
    al, rm = alivio(p), p.fresa_manual / 2.0
    out = []
    for a in anclajes(p):
        zc, x0, x1, z0, z1 = _zona_escuadra(p, a)
        xs = -1.0       # el cortador arranca fuera del canto trasero: así su cara no coincide con la de la muesca
        out.append({"tipo": "rebaje_corte", "y_desde": t - e, "largo": e + 1.0,
                    "contorno": _redondear([(xs, z0, 0), (xs, z1, 0), (x1, z1, al), (x1, z0, al)])})
        out.append({"tipo": "rebaje_manual", "y_desde": -1.0, "largo": e + 1.0,
                    "contorno": _redondear([(xs, z0, 0), (x1, z0, rm), (x1, z1, rm), (xs, z1, 0)])})
    for h in huecos_poste(p):
        out.append({"tipo": "agujero", "contorno": h["contorno"], "y_desde": -1.0, "largo": t + 2.0})
    return out


def prof_ranura(p: Params) -> float:
    """Profundidad de las ranuras (postes y tablas): la mitad de la profundidad de la pieza."""
    return p.profundidad / 2.0


def largo_tabla(p: Params, n_postes_cruzados: int) -> float:
    n = n_postes_cruzados
    return n * p.t + (n - 1) * p.luz + 2 * VOLADIZO


def pos_poste(p: Params, k: int) -> float:
    """Coordenada (a lo largo del mueble) donde empieza el poste k."""
    return k * (p.t + p.luz)


# ----------------------------------------------------------------------------
# Tablas: reglas, colisiones y distribución al azar
# ----------------------------------------------------------------------------
def _comparten_poste(a: Tabla, b: Tabla) -> bool:
    return max(a.poste_ini, b.poste_ini) <= min(a.poste_fin, b.poste_fin)


def _comparten_tramo(a: Tabla, b: Tabla) -> bool:
    """¿Ambas cruzan al menos un mismo hueco entre postes contiguos?"""
    return max(a.poste_ini, b.poste_ini) < min(a.poste_fin, b.poste_fin)


def _conflicto(p: Params, a: Tabla, b: Tabla) -> Optional[str]:
    """Motivo por el que dos tablas no pueden convivir, o None si no hay problema."""
    if a.ranura == b.ranura:
        if _comparten_poste(a, b):
            return "comparten un poste en la misma ranura"
        if p.ranuras_unicas:
            return "usan la misma ranura"
        izq, der = (a, b) if a.poste_fin < b.poste_ini else (b, a)
        if der.poste_ini == izq.poste_fin + 1 and p.luz <= 2 * VOLADIZO:
            return f"sus voladizos se tocan (luz ≤ {2 * VOLADIZO:.0f})"
        return None
    if _comparten_tramo(a, b) and abs(a.ranura - b.ranura) < p.sep_min:
        return f"quedan a menos de {p.sep_min} ranuras en un mismo tramo"
    return None


def max_postes_por_tabla(p: Params) -> int:
    """Cuántos postes puede cruzar como máximo una tabla sin superar el largo útil de la placa."""
    n = int((largo_util(p.placa) - 2 * VOLADIZO + p.luz) // (p.t + p.luz))
    return max(2, min(n, p.n_postes))


def tramos_estructurales(p: Params) -> int:
    """Cantidad de tablas encadenadas que hacen falta para atar todos los postes
    (con una tabla de largo completo sería 1)."""
    return max(1, math.ceil((p.n_postes - 1) / (max_postes_por_tabla(p) - 1)))


def min_tablas(p: Params) -> int:
    """Mínimo de tablas: una cadena atando todos los postes por abajo y otra por arriba."""
    return 2 * tramos_estructurales(p)


def _cadena(p: Params, rnd: random.Random, ranuras: List[int]) -> List[Tabla]:
    """Tablas encadenadas que cubren todos los postes. Tablas consecutivas comparten
    un poste (a alturas distintas, alternando las ranuras dadas)."""
    P = p.n_postes
    m = tramos_estructurales(p)
    base, resto = divmod(P + m - 1, m)
    mayores = set(rnd.sample(range(m), resto))
    tablas, ini = [], 0
    for i in range(m):
        fin = ini + base + (1 if i in mayores else 0) - 1
        tablas.append(Tabla(ini, fin, ranuras[i % len(ranuras)]))
        ini = fin
    return tablas


_CACHE_TABLAS = {}


def generar_tablas(p: Params):
    """Distribuye p.n_tablas tablas (reproducible con p.semilla).
    1) Estructurales: una cadena de tablas que ata todos los postes por abajo
       (ranuras 0 y 1 alternadas) y otra por arriba (últimas dos ranuras). Con pocos
       postes cada cadena es una sola tabla de largo completo.
    2) El resto se ubica al azar respetando todas las reglas.
    Devuelve (tablas, avisos)."""
    clave = (p.n_postes, p.n_ranuras, p.luz, p.t, p.n_tablas, p.semilla, p.sep_min,
             p.ranuras_unicas, p.placa.largo, p.placa.margen_borde)
    if clave in _CACHE_TABLAS:
        t, a = _CACHE_TABLAS[clave]
        return list(t), list(a)
    P, R = p.n_postes, p.n_ranuras
    rnd = random.Random(p.semilla)
    tablas = _cadena(p, rnd, [0, 1]) + _cadena(p, rnd, [R - 1, R - 2])
    avisos = []
    faltan = p.n_tablas - len(tablas)
    nmax = max_postes_por_tabla(p)
    intentos, max_intentos = 0, max(3000, 600 * max(faltan, 1))
    while faltan > 0 and intentos < max_intentos:
        intentos += 1
        n = rnd.randint(2, nmax)
        ini = rnd.randrange(0, P - n + 1)
        c = Tabla(ini, ini + n - 1, rnd.randrange(0, R))
        if all(_conflicto(p, c, t) is None for t in tablas):
            tablas.append(c)
            faltan -= 1
    if faltan > 0:
        avisos.append(f"Solo se pudieron ubicar {p.n_tablas - faltan} de {p.n_tablas} tablas "
                      "con las reglas actuales. Probá otra semilla, menos tablas, más ranuras "
                      "o una separación mínima menor.")
    res = sorted(tablas, key=lambda t: (t.ranura, t.poste_ini))
    if len(_CACHE_TABLAS) > 256:
        _CACHE_TABLAS.clear()
    _CACHE_TABLAS[clave] = (list(res), list(avisos))
    return res, avisos


def tablas_efectivas(p: Params):
    """(tablas, avisos): las manuales si hay, o las generadas al azar."""
    if p.tablas is not None:
        return list(p.tablas), []
    return generar_tablas(p)


def _lista(nums, tope=12):
    nums = list(nums)
    txt = ", ".join(str(n) for n in nums[:tope])
    return txt + (f" y {len(nums) - tope} más" if len(nums) > tope else "")


def _errores_tablas(p: Params, tablas: List[Tabla]) -> List[str]:
    e = []
    P, R, Z = p.n_postes, p.n_ranuras, ZONA_ATADO
    for i, tb in enumerate(tablas, 1):
        if not (0 <= tb.poste_ini < tb.poste_fin < P):
            e.append(f"Tabla {i}: postes {tb.poste_ini}-{tb.poste_fin} inválidos "
                     "(debe cruzar al menos 2 postes existentes).")
        if not 0 <= tb.ranura < R:
            e.append(f"Tabla {i}: ranura {tb.ranura} inexistente (0 a {R - 1}).")
    if e:
        return e  # evita errores en cascada

    # Estructurales: cada poste atado por abajo y por arriba
    sin_base = [k for k in range(P)
                if not any(t.poste_ini <= k <= t.poste_fin and t.ranura < Z for t in tablas)]
    if sin_base:
        e.append(f"Postes sin atar por abajo: {_lista(sin_base)}. Cada poste necesita una tabla "
                 f"que lo cruce en las ranuras 0 a {Z - 1}.")
    sin_tope = [k for k in range(P)
                if not any(t.poste_ini <= k <= t.poste_fin and t.ranura >= R - Z for t in tablas)]
    if sin_tope:
        e.append(f"Postes sin atar por arriba: {_lista(sin_tope)}. Cada poste necesita una tabla "
                 f"que lo cruce en las ranuras {R - Z} a {R - 1}.")
    flojos = [g for g in range(P - 1)
              if sum(1 for t in tablas if t.poste_ini <= g and t.poste_fin >= g + 1) < MIN_TABLAS_POR_TRAMO]
    if flojos:
        e.append(f"Tramos (entre el poste g y g+1) con menos de {MIN_TABLAS_POR_TRAMO} tablas "
                 f"que los crucen: g = {_lista(flojos)}.")
    # Largo de pieza
    for n in sorted({t.poste_fin - t.poste_ini + 1 for t in tablas}):
        if largo_tabla(p, n) > largo_util(p.placa):
            e.append(f"Una tabla que cruza {n} postes mide {largo_tabla(p, n):.0f} mm y no entra "
                     f"en la placa ({largo_util(p.placa):.0f} mm útiles).")
    # Pares
    for i in range(len(tablas)):
        for j in range(i + 1, len(tablas)):
            motivo = _conflicto(p, tablas[i], tablas[j])
            if motivo:
                e.append(f"Tablas {i + 1} y {j + 1}: {motivo}.")
    return e


# ----------------------------------------------------------------------------
# Validación de reglas
# ----------------------------------------------------------------------------
def validar(p: Params) -> List[str]:
    e = []
    lo, hi = LIMITES["t"]
    if not lo <= p.t <= hi:
        e.append(f"Espesor t={p.t} fuera de rango [{lo}, {hi}].")
    lo, hi = LIMITES["h"]
    if not lo <= p.h <= hi:
        e.append(f"Holgura h={p.h} fuera de rango [{lo}, {hi}].")
    if p.luz < LUZ_MIN - 1e-9:
        e.append(f"Luz {p.luz:.0f} mm menor a la mínima ({LUZ_MIN:.0f} mm).")
    elif p.luz > luz_max(p.t) + 1e-9:
        e.append(f"Luz {p.luz:.0f} mm mayor a la máxima estructural ({luz_max(p.t):.0f} mm para tablas de "
                 f"{p.t:g} mm): con libros la flecha sería {flecha_final(p.luz, p.t):.1f} mm "
                 f"(luz/{p.luz / flecha_final(p.luz, p.t):.0f}); el límite es luz/{LIM_FLECHA:.0f}.")
    lo, hi = LIMITES["n_postes"]
    if not lo <= p.n_postes <= hi:
        e.append(f"Cantidad de postes {p.n_postes} fuera de rango [{lo}, {hi}].")
    lo, hi = LIMITES["n_ranuras"]
    if not lo <= p.n_ranuras <= hi:
        e.append(f"Cantidad de ranuras {p.n_ranuras} fuera de rango [{lo}, {hi}].")
    lo, hi = LIMITES["sep_min"]
    if not lo <= p.sep_min <= hi:
        e.append(f"Separación mínima {p.sep_min} fuera de rango [{lo}, {hi}].")
    if p.tablas is None:
        lo, hi = LIMITES["n_tablas"]
        if not lo <= p.n_tablas <= hi:
            e.append(f"Cantidad de tablas {p.n_tablas} fuera de rango [{lo}, {hi}].")
        elif 2 <= p.n_postes and p.n_tablas < min_tablas(p):
            m = tramos_estructurales(p)
            e.append(f"Con {p.n_postes} postes hacen falta al menos {min_tablas(p)} tablas "
                     f"({m} por abajo y {m} por arriba para atar todos los postes).")
        elif p.ranuras_unicas and tramos_estructurales(p) > ZONA_ATADO:
            e.append(f"Con {p.n_postes} postes hacen falta {tramos_estructurales(p)} tablas encadenadas "
                     f"y solo hay {ZONA_ATADO} ranuras de atado: desactivá 'ranuras_unicas'.")
        elif p.ranuras_unicas and p.n_tablas > p.n_ranuras:
            e.append(f"Con ranuras únicas no puede haber más tablas ({p.n_tablas}) "
                     f"que ranuras ({p.n_ranuras}).")

    if tramos_estructurales(p) > 1 and p.n_ranuras < p.sep_min + 3:
        e.append(f"Con {p.n_postes} postes las tablas de atado van encadenadas (alternan dos alturas abajo "
                 f"y dos arriba) y hacen falta al menos {p.sep_min + 3} ranuras "
                 f"(alto mínimo {altura_con(p.sep_min + 3, p.t, p.h, SEPARACION_MIN):.0f} mm).")

    lo, hi = LIMITES["fresa"]
    if not lo <= p.fresa <= hi:
        e.append(f"Fresa de {p.fresa:g} mm fuera de rango [{lo:g}, {hi:g}].")
    elif p.fresa * math.sqrt(2.0) > ancho_ranura(p) + 1e-9:
        e.append(f"Con una fresa de {p.fresa:g} mm los alivios de los rincones miden {p.fresa * math.sqrt(2.0):.1f} mm "
                 f"y no entran en una ranura de {ancho_ranura(p):.1f} mm. Usá una fresa de hasta "
                 f"{ancho_ranura(p) / math.sqrt(2.0):.1f} mm o tablas más gruesas.")
    rem = LIMITES["remanente_min"]
    if p.separacion < SEPARACION_MIN - 1e-9:
        e.append(f"La separación entre ranuras ({p.separacion:.1f} mm) es menor al mínimo de "
                 f"{SEPARACION_MIN:.0f} mm.")
    if p.anclaje not in ANCLAJES:
        e.append(f"anclaje '{p.anclaje}' inválido: usar {', '.join(ANCLAJES)}.")
    elif p.anclaje != "ninguno":
        n_err_antes = len(e)
        for campo in ("anclaje_alto", "anclaje_ancho", "anclaje_espesor", "agujero_radio", "fresa_manual", "buje", "holgura_u"):
            lo, hi = LIMITES[campo]
            if not lo <= getattr(p, campo) <= hi:
                e.append(f"{campo} = {getattr(p, campo):g} fuera de rango [{lo:g}, {hi:g}].")
        if len(e) == n_err_antes:             # medidas dentro de rango: se comprueban las relaciones entre ellas
            d_al = p.fresa / math.sqrt(2.0)
            h_reb = p.anclaje_alto + ANCLAJE_HOLGURA
            if p.fresa > 0 and h_reb < 2 * d_al + 0.5:
                e.append(f"Una escuadra de {p.anclaje_alto:g} mm de alto es muy baja para una fresa de {p.fresa:g} mm: "
                         f"los alivios del rebaje necesitan al menos {2 * d_al - ANCLAJE_HOLGURA + 0.5:.1f} mm.")
            if p.anclaje_ancho - p.anclaje_espesor < d_al + 1:
                e.append(f"Una escuadra de {p.anclaje_ancho:g} mm de ancho es muy corta para el alivio de la fresa.")
            if p.t - 2 * p.anclaje_espesor < NUCLEO_MIN:
                e.append(f"Dos rebajes de {p.anclaje_espesor:g} mm dejan un núcleo de {p.t - 2 * p.anclaje_espesor:g} mm "
                         f"en un poste de {p.t:g} mm; el mínimo es {NUCLEO_MIN:g} mm.")
            if p.buje < p.fresa_manual + 2:
                e.append(f"El buje ({p.buje:g} mm) debe ser al menos 2 mm mayor que la fresa manual ({p.fresa_manual:g} mm).")
            xc = p.anclaje_ancho / 2
            if 2 * p.agujero_radio + 2 > p.anclaje_alto:
                e.append(f"El agujero del pasador (Ø{2 * p.agujero_radio:g} mm) no entra en una escuadra de "
                         f"{p.anclaje_alto:g} mm de alto (se necesita 1 mm de borde a cada lado).")
            if xc - p.agujero_radio < p.anclaje_espesor + 2 or (p.anclaje_ancho + ANCLAJE_HOLGURA / 2 - xc) < p.agujero_radio + d_al + 1:
                e.append(f"El agujero del pasador (Ø{2 * p.agujero_radio:g} mm) no entra, centrado, en una escuadra de "
                         f"{p.anclaje_ancho:g} mm de ancho.")
        mu = muescas_anclaje(p)
        if mu and mu[0][1] > altura_poste(p) - 10:
            e.append("La muesca del anclaje superior queda a menos de 10 mm del extremo del poste.")
        if p.anclaje == "ambos" and p.zocalo and p.zocalo_alto > 0 and p.zocalo_prof > 0:
            zb = min(m[0] for m in mu)
            if zb - p.zocalo_alto < rem:
                e.append(f"Con anclaje inferior, el recorte del zócalo no puede superar {zb - rem:.0f} mm de alto "
                         f"(la muesca de la escuadra empieza a {zb:.0f} mm).")
    if altura_poste(p) > largo_util(p.placa):
        e.append(f"El poste mide {altura_poste(p):.0f} mm y no entra en la placa "
                 f"({largo_util(p.placa):.0f} mm útiles). Reducí la cantidad de ranuras.")
    lo, hi = LIMITES["profundidad"]
    if not lo <= p.profundidad <= hi:
        e.append(f"Profundidad {p.profundidad} fuera de rango [{lo}, {hi}].")
    if p.profundidad > ancho_util(p.placa):
        e.append(f"La profundidad de las piezas ({p.profundidad:.0f} mm) no entra en el ancho útil "
                 f"de la placa ({ancho_util(p.placa):.0f} mm).")

    if p.zocalo:
        lo, hi = LIMITES["zocalo_alto"]
        if not lo <= p.zocalo_alto <= hi:
            e.append(f"Alto del zócalo {p.zocalo_alto} fuera de rango [{lo}, {hi}].")
        if base_inferior(p) - p.zocalo_alto < rem:
            e.append("El recorte del zócalo llega demasiado cerca de la primera ranura "
                     f"(máximo {base_inferior(p) - rem:.0f} mm de alto).")
        lo, hi = LIMITES["zocalo_prof"]
        if not lo <= p.zocalo_prof <= hi:
            e.append(f"Profundidad del zócalo {p.zocalo_prof} fuera de rango [{lo}, {hi}].")
        d_al = p.fresa / math.sqrt(2.0)
        if p.zocalo_alto > 0 and p.zocalo_prof > 0 and (p.zocalo_prof < d_al or p.zocalo_alto < d_al):
            e.append(f"El recorte del zócalo es muy chico para una fresa de {p.fresa:g} mm: debe medir al menos "
                     f"{d_al:.1f} mm de alto y de profundidad (o 0 para no hacerlo).")

    if not e:  # las reglas de tablas necesitan parámetros básicos válidos
        tablas, _ = tablas_efectivas(p)
        e += _errores_tablas(p, tablas)
    return e


# ----------------------------------------------------------------------------
# Geometría
# ----------------------------------------------------------------------------
def _redondear(pts):
    """pts: [(x, y, radio)] en sentido antihorario.
      - radio > 0: el vértice (convexo) se reemplaza por un arco tangente.
      - radio < 0: ALIVIO ("dog-bone") para una fresa de radio |radio| en un rincón interior de 90°:
        el vértice se reemplaza por un semicírculo de diámetro = diámetro de la fresa que pasa
        justo por el vértice, así la fresa llega al rincón y la pieza que encastra entra.
    Devuelve [(x, y, bulge)]."""
    n = len(pts)
    info = []
    for i, (x, y, r) in enumerate(pts):
        ax, ay, _ = pts[i - 1]
        bx, by, _ = pts[(i + 1) % n]
        ux, uy, vx, vy = ax - x, ay - y, bx - x, by - y
        lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
        ux, uy, vx, vy = ux / lu, uy / lu, vx / lv, vy / lv
        alfa = math.acos(max(-1.0, min(1.0, ux * vx + uy * vy)))
        if r > 0:
            d = r / math.tan(alfa / 2)
        elif r < 0:
            if abs(alfa - math.pi / 2) > 1e-6:
                raise ValueError("Un alivio solo se puede hacer en un rincón de 90°.")
            d = abs(r) * math.sqrt(2.0)
        else:
            d = 0.0
        info.append((ux, uy, vx, vy, alfa, d, lu, lv))
    for i in range(n):  # los dos redondeos de una arista no pueden superponerse
        d_i, d_sig = info[i][5], info[(i + 1) % n][5]
        largo = info[i][7]
        if d_i + d_sig > largo + 1e-6:
            raise ValueError("Redondeos superpuestos en una arista: revisar parámetros.")
    out = []
    for (x, y, r), (ux, uy, vx, vy, alfa, d, _, _) in zip(pts, info):
        if r == 0:
            out.append((x, y, 0.0))
        elif r > 0:
            out.append((x + ux * d, y + uy * d, math.tan((math.pi - alfa) / 4)))
            out.append((x + vx * d, y + vy * d, 0.0))
        else:   # alivio: semicírculo horario (rincón interior de un contorno antihorario)
            out.append((x + ux * d, y + uy * d, -1.0))
            out.append((x + vx * d, y + vy * d, 0.0))
    return out


def contorno_poste(p: Params):
    w = p._ancho_ranura_poste if p._ancho_ranura_poste else ancho_ranura(p)
    H = altura_poste(p)
    zd = p.zocalo_prof if p.zocalo else 0.0
    zh = p.zocalo_alto if p.zocalo else 0.0
    pts = []
    if p.zocalo and zd > 0 and zh > 0:
        pts += [(zd, 0, 0)]
    else:
        pts += [(0, 0, 0)]
    D, s = p.profundidad, prof_ranura(p)
    al = alivio(p)                                    # radio del alivio (0 = sin alivios)
    pts += [(D, 0, 0)]
    for k in range(p.n_ranuras):                      # frente, de abajo hacia arriba
        z0 = z_ranura(p, k)
        pts += [(D, z0, R_BOCA),
                (D - s, z0, al),
                (D - s, z0 + w, al),
                (D, z0 + w, R_BOCA)]
    pts += [(D, H, R_FRENTE), (0, H, 0)]
    for (zb, za) in muescas_anclaje(p):               # canto trasero, de arriba hacia abajo
        pts += [(0, za, 0), (p.anclaje_espesor, za, 0), (p.anclaje_espesor, zb, 0), (0, zb, 0)]
    if p.zocalo and zd > 0 and zh > 0:
        pts += [(0, zh, 0), (zd, zh, al)]
    return _redondear(pts)


def contorno_tabla(p: Params, n_cruzados: int):
    w = ancho_ranura(p)
    L = largo_tabla(p, n_cruzados)
    D, s = p.profundidad, prof_ranura(p)
    al = alivio(p)
    pts = [(0, 0, R_BOCA), (D, 0, R_FRENTE),
           (D, L, R_FRENTE), (0, L, R_BOCA)]
    for j in reversed(range(n_cruzados)):             # borde trasero, de arriba hacia abajo
        a = VOLADIZO + j * (p.t + p.luz) - p.h / 2    # holgura centrada sobre el poste
        b = a + w
        pts += [(0, b, R_BOCA), (s, b, al), (s, a, al), (0, a, R_BOCA)]
    return _redondear(pts)


def generar_piezas(p: Params) -> List[Pieza]:
    """Devuelve la lista de piezas únicas con su cantidad."""
    err = validar(p)
    if err:
        raise ValueError("Parámetros inválidos:\n- " + "\n- ".join(err))
    piezas = [Pieza("poste", "poste", contorno_poste(p), p.t, p.n_postes,
                    p.profundidad, altura_poste(p), mecanizados_poste(p), huecos_poste(p))]
    cuenta = {}
    for tb in tablas_efectivas(p)[0]:
        n = tb.poste_fin - tb.poste_ini + 1
        cuenta[n] = cuenta.get(n, 0) + 1
    for n in sorted(cuenta):
        piezas.append(Pieza(f"tabla_{n}_postes", "tabla", contorno_tabla(p, n),
                            p.t, cuenta[n], p.profundidad, largo_tabla(p, n)))
    return piezas


def estimar_placas(p: Params) -> dict:
    """Cota inferior por superficie (el nesting real necesitará algo más)."""
    sup = sum(area(pz.contorno) * pz.cantidad for pz in generar_piezas(p))
    util = largo_util(p.placa) * ancho_util(p.placa)
    n = math.ceil(sup / util)
    return {"superficie_piezas_m2": sup / 1e6, "placas_minimas": n,
            "costo_minimo_usd": n * p.placa.precio_usd}


def ancho_total(p: Params) -> float:
    """Ancho de punta a punta del mueble: incluye el voladizo de las tablas a cada lado."""
    return p.n_postes * p.t + (p.n_postes - 1) * p.luz + 2 * VOLADIZO


def ancho_entre_postes(p: Params) -> float:
    return p.n_postes * p.t + (p.n_postes - 1) * p.luz


def resumen(p: Params) -> dict:
    return {
        "alto_total": altura_poste(p),
        "ancho_total_mueble": ancho_total(p),
        "ancho_entre_postes": ancho_entre_postes(p),
        "profundidad_total": p.profundidad,
        "ancho_ranura": ancho_ranura(p),
        "anclaje": p.anclaje,
        "anclajes": anclajes(p),
        "muesca_anclaje": (p.anclaje_espesor, alto_muesca(p)),
        "agujero": {"radio": p.agujero_radio, "diametro": 2 * p.agujero_radio, "pasante": True,
                    "con_broca": 2 * p.agujero_radio < p.fresa},
        "luz": p.luz,
        "luz_max": luz_max(p.t),
        "flecha_estimada": flecha_final(p.luz, p.t),
        "separacion": p.separacion,
        "paso": paso(p),
        "espacio_libre_entre_tablas": espacio_libre(p),
        "n_postes": p.n_postes,
        "n_tablas": len(tablas_efectivas(p)[0]),
    }


# ----------------------------------------------------------------------------
# Utilidades geométricas (arcos <-> puntos)
# ----------------------------------------------------------------------------
def punto_medio_arco(x0, y0, x1, y1, bulge):
    """Punto medio del arco entre (x0,y0) y (x1,y1) para un bulge dado."""
    return ((x0 + x1) / 2 + (y1 - y0) * bulge / 2,
            (y0 + y1) / 2 - (x1 - x0) * bulge / 2)


def muestrear(contorno, pasos_arco=24):
    """Convierte el contorno a una polilínea densa (lista de (x, y))."""
    n = len(contorno)
    pts = []
    for i in range(n):
        x0, y0, b = contorno[i]
        x1, y1, _ = contorno[(i + 1) % n]
        pts.append((x0, y0))
        if b != 0:
            # bulge con signo: > 0 arco antihorario, < 0 arco horario (p. ej. los alivios)
            theta = 4 * math.atan(b)                       # barrido con signo
            c = math.hypot(x1 - x0, y1 - y0)
            r = c * (1 + b * b) / (4 * abs(b))             # radio (positivo)
            k = c * (1 - b * b) / (4 * b)                  # desplazamiento del centro sobre la normal izquierda
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            cx, cy = mx + (-(y1 - y0) / c) * k, my + ((x1 - x0) / c) * k
            a0 = math.atan2(y0 - cy, x0 - cx)
            for s in range(1, pasos_arco):
                a = a0 + theta * s / pasos_arco
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def area(contorno):
    pts = muestrear(contorno, 64)
    s = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        s += x0 * y1 - x1 * y0
    return s / 2


# ----------------------------------------------------------------------------
# Medidas totales -> parámetros
# ----------------------------------------------------------------------------
def n_ranuras_max(alto_total: float, t: float, h: float) -> int:
    """Mayor cantidad de ranuras que entran en el alto dado respetando SEPARACION_MIN."""
    w = t + h
    x = (alto_total - BASE_A_PRIMERA_RANURA - ULTIMA_RANURA_A_TOPE - w) / (SEPARACION_MIN + w)
    return int(math.floor(x + 1e-9)) + 1


def separacion_para(alto_total: float, n_ranuras: int, t: float, h: float) -> float:
    """Separación entre ranuras que reparte n ranuras en el alto dado (alto exacto)."""
    return (alto_total - BASE_A_PRIMERA_RANURA - ULTIMA_RANURA_A_TOPE - n_ranuras * (t + h)) / (n_ranuras - 1)


def limites_dimensiones(t: float, h: float, placa: Placa) -> dict:
    """Menor y mayor alto y ancho posibles (para mensajes y para los controles de la web)."""
    nlo = LIMITES["n_ranuras"][0]
    plo, phi = LIMITES["n_postes"]
    return {"alto_min": altura_con(nlo, t, h, SEPARACION_MIN), "alto_max": largo_util(placa),
            "ancho_min": plo * t + (plo - 1) * LUZ_MIN + 2 * VOLADIZO,
            "ancho_max": phi * t + (phi - 1) * luz_max(t) + 2 * VOLADIZO}


def n_tablas_sugerido(p: Params) -> int:
    """Cantidad de tablas por defecto cuando el mueble se define por sus medidas: mantiene la
    densidad del diseño original (9 tablas en 3 tramos de 16 ranuras)."""
    return max(min_tablas(p), round((p.n_postes - 1) * p.n_ranuras / 6))


def desde_dimensiones(ancho_total: Optional[float] = None, alto_total: Optional[float] = None, **kw):
    """Arma los parámetros a partir de las medidas totales del mueble.
      - alto_total  -> el alto queda EXACTO: las n_ranuras indicadas se reparten entre la base
                       (200 mm) y el remate (100 mm) con una separación uniforme que nunca baja de
                       SEPARACION_MIN (110 mm). Si no se indica n_ranuras, se usa la mayor cantidad
                       que respeta ese mínimo.
      - ancho_total -> fija n_postes y luz; el ancho queda exacto. Si no se indica n_postes, se usa la
                       MENOR cantidad de postes cuya luz no supere la máxima estructural luz_max(t)
                       ('luz', si se indica, funciona como luz máxima deseada más baja).
      - La profundidad total es la de las piezas (parámetro 'profundidad').
      - Si no se pide n_tablas, se sugiere según el tamaño.
    kw son los demás parámetros de Params (los que valen None se ignoran).
    Devuelve (Params, notas, errores)."""
    kw = {k: v for k, v in kw.items() if v is not None}
    notas, errores = [], []
    base = Params(**kw)
    if ancho_total is None and alto_total is None:
        return base, notas, errores
    lim = limites_dimensiones(base.t, base.h, base.placa)
    cambios = {}

    if alto_total is not None:
        t, h, w = base.t, base.h, base.t + base.h
        nlo, nhi = LIMITES["n_ranuras"]
        if "separacion" in kw:
            notas.append("Se ignora 'separacion': la define el alto total.")
        nmax = min(n_ranuras_max(alto_total, t, h), nhi)
        if alto_total > largo_util(base.placa) + 1e-9:
            errores.append(f"Alto total {alto_total:.0f} mm supera el largo útil de la placa "
                           f"({largo_util(base.placa):.0f} mm).")
        elif nmax < nlo:
            errores.append(f"Alto total {alto_total:.0f} mm demasiado bajo: el mínimo es "
                           f"{lim['alto_min']:.0f} mm ({nlo} ranuras con {SEPARACION_MIN:.0f} mm entre ellas).")
        else:
            n = kw.get("n_ranuras", nmax)
            if n > nmax:
                errores.append(f"Con {n} ranuras la separación sería "
                               f"{separacion_para(alto_total, n, t, h):.1f} mm, menor al mínimo de "
                               f"{SEPARACION_MIN:.0f} mm. Para {alto_total:.0f} mm entran como máximo {nmax} "
                               f"ranuras (o hacen falta {altura_con(n, t, h, SEPARACION_MIN):.0f} mm para {n}).")
            elif n < 2:
                errores.append("Hacen falta al menos 2 ranuras.")
            else:
                sep = separacion_para(alto_total, n, t, h)
                cambios["n_ranuras"], cambios["separacion"] = n, sep
                sl = base.sep_min * (sep + w) - t
                origen = "indicadas" if "n_ranuras" in kw else f"las máximas que respetan los {SEPARACION_MIN:.0f} mm"
                notas.append(f"Alto {alto_total:.0f} mm exacto: {n} ranuras ({origen}), separación de "
                             f"{sep:.1f} mm entre ranuras; espacio libre entre tablas a {base.sep_min} "
                             f"ranuras: {sl:.0f} mm. Máximo para este alto: {nmax} ranuras.")

    if ancho_total is not None:
        t = base.t
        entre = ancho_total - 2 * VOLADIZO          # ancho entre las caras exteriores de los postes extremos
        plo, phi = LIMITES["n_postes"]
        lmax = luz_max(t)
        tope = lmax
        if "luz" in kw:
            tope = min(kw["luz"], lmax)
            if kw["luz"] > lmax:
                notas.append(f"'luz' pedida ({kw['luz']:.0f} mm) supera la máxima estructural: se usa {lmax:.0f} mm.")
            else:
                notas.append(f"'luz' se toma como luz máxima deseada ({kw['luz']:.0f} mm).")

        def luz_para(n):
            return (entre - n * t) / (n - 1)
        if "n_postes" in kw:
            n = kw["n_postes"]
            notas.append(f"Con {n} postes indicados, la luz se ajusta para llegar al ancho pedido.")
            validos = [n] if plo <= n <= phi and LUZ_MIN - 1e-9 <= luz_para(n) <= lmax + 1e-9 else []
        else:
            validos = [k for k in range(plo, phi + 1) if LUZ_MIN - 1e-9 <= luz_para(k) <= tope + 1e-9]
        if not validos:
            # anchos posibles más cercanos (por debajo y por encima)
            bordes = []
            for k in range(plo, phi + 1):
                if tope >= LUZ_MIN:
                    bordes += [(k * t + (k - 1) * LUZ_MIN + 2 * VOLADIZO, k), (k * t + (k - 1) * tope + 2 * VOLADIZO, k)]
            abajo = max((x for x in bordes if x[0] < ancho_total), default=None)
            arriba = min((x for x in bordes if x[0] > ancho_total), default=None)
            msg = (f"Ancho total {ancho_total:.0f} mm no se puede lograr con luces entre {LUZ_MIN:.0f} y "
                   f"{tope:.0f} mm")
            if "n_postes" in kw:
                msg += f" y {kw['n_postes']} postes (la luz saldría {luz_para(kw['n_postes']):.0f} mm)"
            msg += "."
            alt = []
            if abajo:
                alt.append(f"{abajo[0]:.0f} mm ({abajo[1]} postes)")
            if arriba:
                alt.append(f"{arriba[0]:.0f} mm ({arriba[1]} postes)")
            if alt and "n_postes" not in kw:
                msg += " Los anchos posibles más cercanos son " + " y ".join(alt) + "."
            errores.append(msg)
        else:
            n = min(validos)                              # la menor cantidad de postes que cumple
            cambios["n_postes"], cambios["luz"] = n, luz_para(n)
            notas.append(f"Ancho pedido {ancho_total:.0f} mm -> {n} postes (la menor cantidad con luz <= "
                         f"{tope:.0f} mm), luz de {luz_para(n):.1f} mm, ancho exacto. Luz máxima estructural: "
                         f"{lmax:.0f} mm (flecha estimada {flecha_final(luz_para(n), t):.1f} mm).")

    if errores:
        return base, notas, errores
    p = replace(base, **cambios)
    if "n_tablas" not in kw:
        p.n_tablas = n_tablas_sugerido(p)
        notas.append(f"Tablas: {p.n_tablas} (sugerido por el tamaño; mínimo {min_tablas(p)}).")
    return p, notas, errores


# ----------------------------------------------------------------------------
# Ensamblado: dónde va cada pieza en el espacio 3D
# ----------------------------------------------------------------------------
@dataclass
class Instancia:
    """Una pieza colocada en el mueble.
    El contorno 2D (x, y) se ubica con: punto = origen + x*eje_x + y*eje_y,
    y se extruye 'extrusion' (vector) para darle el espesor."""
    nombre: str
    tipo: str
    pieza: str                  # nombre de la Pieza (contorno) que usa
    origen: Tuple[float, float, float]
    eje_x: Tuple[float, float, float]
    eje_y: Tuple[float, float, float]
    extrusion: Tuple[float, float, float]


def instancias(p: Params) -> List[Instancia]:
    """Lista de todas las piezas colocadas (4 postes + N tablas).
    Ejes del mueble: X = profundidad (0 atrás, 200 frente),
    Y = a lo largo del mueble, Z = altura."""
    err = validar(p)
    if err:
        raise ValueError("Parámetros inválidos:\n- " + "\n- ".join(err))
    out = []
    for k in range(p.n_postes):
        out.append(Instancia(f"poste_{k + 1}", "poste", "poste",
                             (0.0, pos_poste(p, k), 0.0),
                             (1, 0, 0), (0, 0, 1), (0, p.t, 0)))
    for i, tb in enumerate(tablas_efectivas(p)[0]):
        n = tb.poste_fin - tb.poste_ini + 1
        z0 = z_ranura(p, tb.ranura)
        y0 = pos_poste(p, tb.poste_ini) - VOLADIZO
        out.append(Instancia(f"tabla_{i + 1}", "tabla", f"tabla_{n}_postes",
                             (0.0, y0, z0),
                             (1, 0, 0), (0, 1, 0), (0, 0, p.t)))
    return out


if __name__ == "__main__":
    p = Params()
    for pz in generar_piezas(p):
        print(f"{pz.nombre:18s} x{pz.cantidad}  {pz.ancho:.0f} x {pz.largo:.0f} x {pz.espesor:.1f}"
              f"  área {area(pz.contorno):.0f} mm²")
    print(resumen(p))
