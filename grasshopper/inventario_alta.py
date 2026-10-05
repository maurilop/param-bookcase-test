"""
inventario_alta.py
------------------
Gestiona el inventario: lista lo que hay, carga placas enteras, borra los sobrantes o lo reinicia.
Se puede correr desde el ScriptEditor de Rhino 8 o desde una terminal (python3 inventario_alta.py).

CÓMO USARLO
1. Guardá este archivo en la misma carpeta que biblioteca_param.py y nesting.py.
2. Editá el bloque CONFIGURACIÓN de abajo y ejecutalo.

El inventario se guarda en inventario.json, en la misma carpeta.
Antes de borrar algo ("quitar_sobrantes" o "reiniciar") se guarda una copia de seguridad
(inventario_respaldo_FECHA.json) en la misma carpeta, por si hubiera que recuperarlo.
Las placas que usa un pedido se descuentan al confirmarlo desde Grasshopper (entrada 'confirmar').
"""
import os
import shutil
import sys
from datetime import datetime

# ----------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------
ACCION = "listar"      # "listar"           = muestra el inventario
                       # "alta"             = suma placas enteras (usa CANTIDAD)
                       # "quitar_sobrantes" = borra TODOS los sobrantes (deja las placas y el historial)
                       # "reiniciar"        = deja el inventario completamente vacío (placas, sobrantes y pedidos)
CANTIDAD = 2           # cuántas placas sumar (solo para "alta")
CARPETA = ""           # si hace falta, ruta de la carpeta del proyecto; si no, la de este archivo
# ----------------------------------------------------------------------------

try:
    _aqui = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _aqui = ""
CARPETA = CARPETA or _aqui
if CARPETA and CARPETA not in sys.path:
    sys.path.append(CARPETA)

import biblioteca_param as bp
import nesting as ns

RUTA = os.path.join(CARPETA, "inventario.json")


def respaldar():
    """Copia inventario.json antes de borrar. Devuelve la ruta de la copia (o None si no había archivo)."""
    if not os.path.exists(RUTA):
        return None
    copia = RUTA.replace(".json", "_respaldo_%s.json" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(RUTA, copia)
    return copia


def main():
    inv = ns.Inventario.cargar(RUTA)
    if ACCION == "alta":
        placa = bp.PLACA_ABEDUL_15
        ids = inv.agregar_placas(placa, int(CANTIDAD))
        inv.guardar(RUTA)
        print("Se agregaron %d placa(s) de %s (%s): %s" % (len(ids), placa.nombre, placa.codigo, ", ".join(ids)))
    elif ACCION == "quitar_sobrantes":
        sobrantes = [i for i in inv.items if i.tipo == "sobrante"]
        if not sobrantes:
            print("No había sobrantes: no se cambió nada.")
        else:
            copia = respaldar()
            inv.items = [i for i in inv.items if i.tipo != "sobrante"]
            inv.guardar(RUTA)
            print("Se borraron %d sobrante(s) (%d disponibles). Copia de seguridad: %s"
                  % (len(sobrantes), sum(1 for i in sobrantes if i.estado == "disponible"), copia))
    elif ACCION == "reiniciar":
        copia = respaldar()
        inv = ns.Inventario()
        inv.guardar(RUTA)
        print("Inventario reiniciado: sin placas, sin sobrantes y sin pedidos. Copia de seguridad: %s" % copia)
    elif ACCION != "listar":
        print("ACCION debe ser 'listar', 'alta', 'quitar_sobrantes' o 'reiniciar'.")
        return
    print(inv.resumen())
    print("Archivo: " + RUTA)


main()
