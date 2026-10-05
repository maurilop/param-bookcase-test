"""
construir_web.py
----------------
Arma el configurador web en UN solo archivo HTML (docs/index.html) con el motor de cálculo adentro:
los mismos .py del diseño (biblioteca_param, herrajes, nesting) más web_api. Cuando cambie algo del
diseño, volvé a correr este script para actualizar la web.

Uso:  python3 construir_web.py            -> docs/index.html (usa librerías de internet: CDN; es lo que se publica)
      python3 construir_web.py --local    -> configurador_local.html (usa node_modules, para las pruebas)
"""
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
PY = ["biblioteca_param.py", "herrajes.py", "nesting.py", "web_api.py"]
THREE_V, PYODIDE_V = "0.160.0", "0.26.4"


def construir(local: bool = False) -> pathlib.Path:
    web = RAIZ / "web"
    geometria = (web / "geometria.js").read_text(encoding="utf-8")
    geometria = re.sub(r"^import .*\n", "", geometria, flags=re.M).replace("export function", "function")
    app = (web / "app.js").read_text(encoding="utf-8").replace("// @@GEOMETRIA@@", geometria)
    if local:
        imp = {"three": "/node_modules/three/build/three.module.js", "three/addons/": "/node_modules/three/examples/jsm/"}
        pyodide_url = "/node_modules/pyodide/"
    else:
        imp = {"three": f"https://cdn.jsdelivr.net/npm/three@{THREE_V}/build/three.module.js",
               "three/addons/": f"https://cdn.jsdelivr.net/npm/three@{THREE_V}/examples/jsm/"}
        pyodide_url = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_V}/full/"
    bloques = "\n".join(f'<script type="text/plain" id="py_{n[:-3]}">{(RAIZ / n).read_text(encoding="utf-8")}</script>' for n in PY)
    for n in PY:
        assert "</script" not in (RAIZ / n).read_text(encoding="utf-8")
    html = (web / "plantilla.html").read_text(encoding="utf-8")
    for clave, valor in (("{{CSS}}", (web / "estilos.css").read_text(encoding="utf-8")),
                         ("{{IMPORTMAP}}", json.dumps({"imports": imp})),
                         ("{{PYTHON}}", bloques),
                         ("{{WORKER}}", (web / "worker.js").read_text(encoding="utf-8")),
                         ("{{CFG}}", json.dumps({"pyodideUrl": pyodide_url, "archivos": PY})),
                         ("{{APP}}", app)):
        html = html.replace(clave, valor)
    if local:
        salida = RAIZ / "configurador_local.html"
    else:
        (RAIZ / "docs").mkdir(exist_ok=True)
        salida = RAIZ / "docs" / "index.html"
        assert "/node_modules/" not in html, "la versión publicada no debe apuntar a copias locales"
    salida.write_text(html, encoding="utf-8")
    return salida


if __name__ == "__main__":
    ruta = construir(local="--local" in sys.argv)
    print(f"Creado {ruta} ({ruta.stat().st_size // 1024} kB)")
