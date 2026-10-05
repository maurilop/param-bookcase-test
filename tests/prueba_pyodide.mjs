// Comprueba que el motor de cálculo corre igual dentro de Pyodide (el que usa el navegador) que en Python normal.
import { loadPyodide } from 'pyodide';
import fs from 'fs'; import path from 'path'; import { execFileSync } from 'child_process'; import { fileURLToPath } from 'url';
const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const casos = [
  { ancho_total: 1880, alto_total: 2000, profundidad: 193, semilla: 0 },
  { ancho_total: 2990, alto_total: 1815, profundidad: 300, n_tablas: 27, semilla: 61 },
  { ancho_total: 10760, alto_total: 2200, n_tablas: 60 },
  { ancho_total: 300, alto_total: 2000 },
];
const py = await loadPyodide({ indexURL: path.join(RAIZ, 'node_modules', 'pyodide') + '/' });
for (const f of ['biblioteca_param.py', 'herrajes.py', 'nesting.py', 'web_api.py']) py.FS.writeFile('/home/pyodide/' + f, fs.readFileSync(path.join(RAIZ, f), 'utf8'));
py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
const api = py.pyimport('web_api');
const esperado = JSON.parse(execFileSync('python3', ['-c', `
import json, sys; sys.path.insert(0, '${RAIZ}')
import web_api as w
casos = json.loads(sys.argv[1])
print(json.dumps([[w.calcular(json.dumps(c)), w.plan_corte(json.dumps(c))] for c in casos]))`, JSON.stringify(casos)], { encoding: 'utf8', maxBuffer: 1 << 28 }));
// El SVG del plan de corte puede diferir en un décimo de píxel en algún punto de un arco, porque sin/cos
// redondean distinto en el último bit entre el Python de escritorio y el de WebAssembly. Todo lo demás debe ser
// idéntico; del SVG se compara el largo y la cantidad de polígonos.
const normal = (s) => { const j = JSON.parse(s); const svg = j.svg || ''; delete j.svg; return JSON.stringify([j, svg.length, (svg.match(/<polygon/g) || []).length]); };
let fallos = 0;
casos.forEach((c, i) => {
  const t = Date.now(), a = api.calcular(JSON.stringify(c)), b = api.plan_corte(JSON.stringify(c));
  const igual = a === esperado[i][0] && normal(b) === normal(esperado[i][1]); if (!igual) fallos++;
  console.log(`caso ${i}: ${igual ? 'IGUAL' : 'DISTINTO'} entre Pyodide y Python normal (${Date.now() - t} ms)`);
});
if (fallos) { console.error(`FALLÓ: ${fallos} caso(s) distintos`); process.exit(1); }
console.log('OK: Pyodide y Python normal dan resultados idénticos.');
