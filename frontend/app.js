(() => {
  const { createElement: h, useState, useEffect } = React;

  // TODO(roadmap-frontend):
  // - Item search/autocomplete using loaded namespaces.
  // - Better error display and retry; validation for item_id.
  // - Diagram UX: expand/collapse, tooltips, export as SVG/PNG.
  // - Persist last used instance_path in localStorage.
  // - Optionally integrate with async endpoints for long runs.

  function App() {
    const [itemId, setItemId] = useState("minecraft:stick");
    const [qty, setQty] = useState(1);
    const [apiBase, setApiBase] = useState("http://localhost:8000");
    const [instancePath, setInstancePath] = useState("/data/instance");
    const [diagram, setDiagram] = useState(true);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [result, setResult] = useState(null);

    useEffect(() => {
      if (result && result.mermaid) {
        try {
          mermaid.initialize({ startOnLoad: false, theme: 'dark' });
          const target = document.getElementById('diagram');
          if (target) {
            mermaid.render('theGraph', result.mermaid).then(({ svg }) => {
              target.innerHTML = svg;
            }).catch(() => {
              target.innerHTML = "<em class='bad'>Mermaid render failed</em>";
            });
          }
        } catch (e) {
          console.error(e);
        }
      }
    }, [result]);

    async function onCalculate() {
      setLoading(true);
      setError("");
      setResult(null);
      try {
        const base = apiBase.replace(/\/$/, "");
        const res = await fetch(`${base}/calculate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ item_id: itemId, quantity: Number(qty), instance_path: instancePath, diagram }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        setResult(data);
      } catch (e) {
        setError(e.message || String(e));
      } finally {
        setLoading(false);
      }
    }

    return h('div', { className: 'grid' }, [
      h('div', {}, [
        h('label', {}, 'API Base URL (e.g., http://localhost:8000)'),
        h('input', { type: 'text', value: apiBase, onChange: e => setApiBase(e.target.value) }),
      ]),
      h('div', {}, [
        h('label', {}, 'Item ID (e.g., minecraft:stick)'),
        h('input', { type: 'text', value: itemId, onChange: e => setItemId(e.target.value) }),
      ]),
      h('div', { className: 'row' }, [
        h('div', {}, [
          h('label', {}, 'Quantity'),
          h('input', { type: 'number', min: 1, value: qty, onChange: e => setQty(e.target.value) }),
        ]),
        h('div', {}, [
          h('label', {}, 'Mermaid'),
          h('div', { className: 'checkbox' }, [
            h('input', { id: 'cb', type: 'checkbox', checked: diagram, onChange: e => setDiagram(e.target.checked) }),
            h('label', { htmlFor: 'cb' }, 'Diagram')
          ])
        ]),
        h('div', {}, [
          h('label', {}, '\u00A0'),
          h('button', { onClick: onCalculate, disabled: loading }, loading ? 'Working...' : 'Calculate'),
        ]),
      ]),
      h('div', {}, [
        h('label', {}, 'Instance path inside container'),
        h('input', { type: 'text', value: instancePath, onChange: e => setInstancePath(e.target.value) }),
        h('div', { className: 'muted' }, 'Default /data/instance. Map your local instance "minecraft" folder to /data/instance using docker-compose.'),
      ]),
      error ? h('div', { className: 'bad' }, `Error: ${error}`) : null,
      result ? h('div', {}, [
        h('h2', {}, 'Analysis'),
        h('pre', {}, JSON.stringify(result.analysis || result, null, 2)),
        (result.mermaid && diagram) ? h('div', {}, [
          h('h2', {}, 'Diagram'),
          h('div', { id: 'diagram' })
        ]) : null,
      ]) : null,
    ]);
  }

  ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();
