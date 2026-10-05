/* Worker: carga Pyodide y corre la lógica del diseño (los .py de este mismo archivo) sin bloquear la pantalla. */
let pyodide = null, api = null;
const avisar = texto => self.postMessage({ progreso: texto });

self.onmessage = async (e) => {
  const { id, tipo, datos } = e.data;
  try {
    if (tipo === 'init') {
      avisar('Descargando Python (la primera vez son unos 10 MB)…');
      importScripts(datos.pyodideUrl + 'pyodide.js');
      pyodide = await loadPyodide({ indexURL: datos.pyodideUrl });
      avisar('Cargando las reglas de diseño…');
      for (const [nombre, codigo] of Object.entries(datos.archivos)) pyodide.FS.writeFile('/home/pyodide/' + nombre, codigo);
      pyodide.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
      api = pyodide.pyimport('web_api');
      self.postMessage({ id, resultado: api.valores_iniciales() });
    } else {
      const t0 = performance.now();
      const r = api[tipo](datos);
      self.postMessage({ id, resultado: r, ms: Math.round(performance.now() - t0) });
    }
  } catch (err) {
    self.postMessage({ id, error: String(err && err.message ? err.message : err) });
  }
};
