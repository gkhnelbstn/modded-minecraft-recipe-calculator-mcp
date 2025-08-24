(() => {
  const { createElement: h, useState, useEffect, useMemo } = React;

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
    const [viewMode, setViewMode] = useState("mermaid"); // 'mermaid' | 'tree'

    // Search state
    const [searchText, setSearchText] = useState("");
    const [suggest, setSuggest] = useState([]);
    const [showSuggest, setShowSuggest] = useState(false);
    const [activeIdx, setActiveIdx] = useState(-1);
    const [fetchingSuggest, setFetchingSuggest] = useState(false);
    const [suggestError, setSuggestError] = useState("");

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

    // Debounced suggestions fetch
    useEffect(() => {
      const q = searchText.trim();
      if (!q || q.length < 2) {
        setSuggest([]);
        setActiveIdx(-1);
        return;
      }
      const ctrl = new AbortController();
      const t = setTimeout(async () => {
        try {
          setFetchingSuggest(true);
          setSuggestError("");
          const base = apiBase.replace(/\/$/, "");
          const url = `${base}/items?query=${encodeURIComponent(q)}&limit=20&instance_path=${encodeURIComponent(instancePath)}`;
          const res = await fetch(url, { signal: ctrl.signal });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          setSuggest(data.items || []);
          setActiveIdx(-1);
        } catch (e) {
          if (e.name !== 'AbortError') setSuggestError(e.message || String(e));
        } finally {
          setFetchingSuggest(false);
        }
      }, 250);
      return () => { clearTimeout(t); ctrl.abort(); };
    }, [searchText, apiBase, instancePath]);

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

    // Build a quick lookup from analysis steps for Tree view
    const stepMap = useMemo(() => {
      const m = new Map();
      const steps = result?.analysis?.steps || [];
      for (const s of steps) m.set(s.item, s);
      return m;
    }, [result]);

    function TreeNode({ item, count, depth = 0 }) {
      const [open, setOpen] = useState(true);
      const step = stepMap.get(item);
      const hasChildren = !!(step && step.ingredients && step.ingredients.length);
      const indent = { marginLeft: depth * 16 };
      const label = `${item}  x${Number(count).toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
      return h('div', {}, [
        h('div', { style: indent }, [
          hasChildren ? h('span', { style: { cursor: 'pointer', marginRight: 6 }, onClick: () => setOpen(!open) }, open ? '▼' : '▶') : h('span', { style: { marginRight: 12 } }, '•'),
          h('span', {}, label),
        ]),
        (hasChildren && open) ? h('div', {}, step.ingredients.map((ing, idx) => (
          h(TreeNode, { key: `${item}-${idx}-${ing.item}`, item: ing.item, count: ing.count, depth: depth + 1 })
        ))) : null
      ]);
    }

    return h('div', { className: 'grid' }, [
      h('div', {}, [
        h('label', {}, 'API Base URL (e.g., http://localhost:8000)'),
        h('input', { type: 'text', value: apiBase, onChange: e => setApiBase(e.target.value) }),
      ]),
      h('div', { className: 'suggest' }, [
        h('label', {}, 'Search item by name or ID'),
        h('input', {
          type: 'text',
          value: searchText,
          placeholder: 'e.g., stick, oak log, diamond sword',
          onChange: e => { setSearchText(e.target.value); setShowSuggest(true); },
          onFocus: () => setShowSuggest(true),
          onBlur: () => setTimeout(() => setShowSuggest(false), 150),
          onKeyDown: e => {
            if (!showSuggest) return;
            if (e.key === 'ArrowDown') { e.preventDefault(); setActiveIdx(i => Math.min(i + 1, (suggest?.length || 1) - 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setActiveIdx(i => Math.max(i - 1, 0)); }
            else if (e.key === 'Enter') {
              if (activeIdx >= 0 && suggest[activeIdx]) {
                const it = suggest[activeIdx];
                setItemId(it.id);
                setSearchText(it.name);
                setShowSuggest(false);
              }
            } else if (e.key === 'Escape') { setShowSuggest(false); }
          }
        }),
        showSuggest && (suggest?.length || fetchingSuggest || suggestError) ? h('div', { className: 'suggest-list' }, [
          ...((suggest || []).map((it, idx) => h('div', {
            key: it.id,
            className: 'suggest-item' + (idx === activeIdx ? ' active' : ''),
            onMouseDown: () => { setItemId(it.id); setSearchText(it.name); setShowSuggest(false); }
          }, [
            h('div', { className: 'pill' }, it.name.slice(0,2).toUpperCase()),
            h('div', {}, [ h('div', {}, it.name), h('div', { className: 'id-mono' }, it.id) ]),
            h('div', { className: 'muted' }, 'select')
          ]))),
          fetchingSuggest ? h('div', { className: 'suggest-item' }, [ h('div', { className: 'pill' }, '…'), h('div', {}, 'Searching...') ]) : null,
          suggestError ? h('div', { className: 'suggest-item bad' }, `Error: ${suggestError}`) : null,
        ]) : null,
        h('div', { className: 'muted' }, itemId ? `Selected ID: ${itemId}` : 'No item selected'),
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
        // View mode tabs
        h('div', { className: 'tabs' }, [
          h('div', { className: 'tab' + (viewMode==='mermaid' ? ' active' : ''), onClick: () => setViewMode('mermaid') }, 'Mermaid'),
          h('div', { className: 'tab' + (viewMode==='tree' ? ' active' : ''), onClick: () => setViewMode('tree') }, 'Tree'),
        ]),
        // Mermaid diagram
        (viewMode === 'mermaid' && result.mermaid && diagram) ? h('div', {}, [
          h('h2', {}, 'Diagram'),
          h('div', { id: 'diagram' })
        ]) : null,
        // Tree view fallback/alternative
        (viewMode === 'tree') ? h('div', {}, [
          h('h2', {}, 'Tree View'),
          h(TreeNode, { item: result.analysis?.target, count: result.analysis?.quantity || 1 })
        ]) : null,
      ]) : null,
    ]);
  }

  ReactDOM.createRoot(document.getElementById('root')).render(h(App));
})();
