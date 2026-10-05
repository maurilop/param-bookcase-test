# param-bookcase-test

Biblioteca de madera **paramétrica**: se elige el ancho, el alto y la profundidad, y el sistema decide la
cantidad de postes, reparte las ranuras, valida la estructura, genera el plan de corte sobre las placas y
muestra el resultado en 3D en el navegador.

Toda la lógica de diseño está escrita **una sola vez**, en Python puro, y la usan tanto el componente de
Grasshopper como el configurador web (que corre ese mismo Python en el navegador con Pyodide). Así no hay
reglas duplicadas que puedan diferir.

## Configurador web

`docs/index.html` es un único archivo con todo adentro (el motor de cálculo incluido).

- **Publicarlo con GitHub Pages:** Settings → Pages → *Deploy from a branch* → rama `main`, carpeta `/docs`.
- **Probarlo en tu computadora:** `cd docs && python3 -m http.server 8000` y abrir <http://localhost:8000>.
- Necesita internet: baja Pyodide (unos 10 MB, la primera vez tarda unos segundos) y three.js desde jsDelivr.
- La configuración queda guardada en el enlace (`#c=...`), así que se puede compartir.

Qué hace: medidas totales exactas (ancho, alto, profundidad), distribución de tablas al azar o por cantidad,
zócalo, anclaje a la pared, cotas, plano de corte sobre las placas con costo de material y datos técnicos
(escuadra en U, replanteo en la pared).

## Estructura

| Ruta | Qué es |
|---|---|
| `biblioteca_param.py` | Diseño paramétrico: postes, tablas, reglas estructurales, medidas totales, anclajes |
| `herrajes.py` | Escuadra en U, plantilla del router, regla de replanteo y sus modelos 3D |
| `nesting.py` | Acomodo de piezas en placas (respeta la veta), inventario de placas y sobrantes, SVG |
| `web_api.py` | Puente JSON entre el navegador y la lógica anterior |
| `web/` | Código del configurador: `geometria.js`, `app.js`, `worker.js`, `estilos.css`, `plantilla.html` |
| `construir_web.py` | Arma `docs/index.html` a partir de lo anterior |
| `grasshopper/` | Componente de Grasshopper y scripts de Rhino |
| `tests/` | Pruebas automáticas (Pyodide contra Python y navegador real) |

## Reconstruir la web

Después de cambiar cualquier `.py` del diseño o algo de `web/`:

```
python3 construir_web.py
```

## Pruebas

```
npm install
npm test
```

Comprueban que Pyodide da los mismos resultados que Python normal y que el configurador, en un Chromium
real, dibuja un mueble de las medidas pedidas, muestra los errores, aguanta 20 postes y 60 tablas y no
produce errores en la consola. Las capturas quedan en `tests/capturas/`.

## Grasshopper

Copiar a una misma carpeta los `.py` de la raíz (menos `construir_web.py` y `web_api.py`, que son para la web)
y los de `grasshopper/`. Pegar `grasshopper_biblioteca.py` en un componente *Python 3 Script* y editar la línea
`CARPETA = ...` con la ruta de esa carpeta. Para comparar contra un modelo de Rhino existente:

```
PYTHONPATH=. python3 grasshopper/validar_contra_3dm.py ruta/al/modelo.3dm
```

## Lo que son estimaciones

Son valores provisorios, a confirmar con un prototipo físico: módulo de elasticidad y carga de libros que
fijan la luz máxima entre postes (`E_DISENO`, `CARGA_LIBROS`), holguras de los encastres, margen de borde de la
placa, medidas de la escuadra en U. El peso y el costo que muestra la web son aproximados. **No es un cálculo
estructural certificado**: antes de vender, el anclaje a la pared conviene que lo revise un profesional.
