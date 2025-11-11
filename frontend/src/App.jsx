import React, { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

//  Format HTML with indentation for readability
function prettyHtml(html) {
  if (!html) return ''
  const cleaned = html
    .replace(/\r?\n|\r/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/>\s*</g, '>\n<')
  const lines = cleaned.split('\n')
  let indent = 0
  const formatted = lines.map(line => {
    const trimmed = line.trim()
    if (/^<\/[^>]+>/.test(trimmed)) indent = Math.max(indent - 1, 0)
    const padded = '  '.repeat(indent) + trimmed
    if (
      /^<([a-zA-Z]+)(?=\s|>)/.test(trimmed) &&
      !/\/>$/.test(trimmed) &&
      !/^<!/.test(trimmed) &&
      !/^<.*<\/.*>$/.test(trimmed)
    ) {
      indent += 1
    }
    return padded
  })
  return formatted.join('\n')
}

// Each search result card
function ResultCard({ item, idx }) {
  const [open, setOpen] = useState(false)
  const formattedHtml = prettyHtml(item.chunk_html || '')

  return (
    <div className="result">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
        <div style={{ fontWeight: 800, fontSize: 18 }}>{item.title || `Match #${idx + 1}`}</div>
        <div className="badge">{item.score_percent}% match</div>
      </div>

      <div className="path">
        Path: <span>{item.path || '/'}</span>
        {item.page_url && (
          <>
            {' '}| <a href={item.page_url} target="_blank" rel="noopener noreferrer" className="link">Open Page</a>
          </>
        )}
      </div>

      <button className="link" onClick={() => setOpen(!open)}>
        {open ? '▾ Hide HTML' : '▸ View HTML'}
      </button>

      {open && (
        <pre className="code"><code>{formattedHtml}</code></pre>
      )}
    </div>
  )
}

//  Main app
export default function App() {
  const [url, setUrl] = useState('https://smarter.codes')
  const [query, setQuery] = useState('AI')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState([])
  const [error, setError] = useState(null)

  const onSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    setResults([])
    try {
      const res = await fetch(`${API_BASE}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, query })
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      //  Sort & keep only top 10 results
      const topResults = (data.results || []).sort((a, b) => b.raw_score - a.raw_score).slice(0, 10)
      setResults(topResults)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="container">
      <div className="card">
        <div className="title">Website Content Search</div>
        <div className="subtitle">Search through website content with precision (Pinecone + semantic search).</div>

        {/* --- Form --- */}
        <form onSubmit={onSubmit}>
          <div className="form">
            <div className="field">
              <label>Website URL</label>
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://example.com"
                required
              />
            </div>
            <div className="field">
              <label>Search Query</label>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g., AI, automation"
                required
              />
            </div>
            <div className="actions">
              <button disabled={loading}>{loading ? 'Searching...' : 'Search'}</button>
            </div>
          </div>
        </form>

        {error && <p style={{ color: '#fca5a5', marginTop: 10 }}>Error: {error}</p>}

        <div className="results">
          {results.length > 0 && <div className="sectionTitle">Search Results</div>}
          {results.map((r, idx) => (
            <ResultCard key={idx} item={r} idx={idx} />
          ))}
          {!loading && results.length === 0 && !error && (
            <div style={{ opacity: 0.8, marginTop: 8 }}>No results yet. Try a search.</div>
          )}
        </div>
      </div>

      <div style={{ opacity: 0.6, marginTop: 12, fontSize: 12 }}>
        Tip: Configure API base with <code>VITE_API_BASE</code> (defaults to <code>http://localhost:8000</code>).
      </div>

      {/* --- Styling --- */}
      <style>{`
        body {
          font-family: ui-sans-serif, system-ui, Arial, sans-serif;
          background: #0b1020;
          color: #e9ecf1;
          margin: 0;
        }
        .container { max-width: 980px; margin: 24px auto; padding: 0 16px; }
        .card {
          background: #0f1530;
          border: 1px solid #1e2445;
          border-radius: 14px;
          padding: 16px;
          box-shadow: 0 10px 24px rgba(0,0,0,0.25);
        }
        .title { font-size: 28px; font-weight: 800; margin-bottom: 6px; }
        .subtitle { opacity: .8; margin-bottom: 18px; }
        .form { display: grid; gap: 14px; }
        .field { display: flex; flex-direction: column; }
        .actions { display: flex; justify-content: flex-end; padding-right: 4px; }
        label { font-size: 12px; opacity: .8; margin-bottom: 6px; }
        input {
          width: 98%;
          padding: 12px 14px;
          border-radius: 10px;
          border: 1px solid #263058;
          background: #0b1228;
          color: #e9ecf1;
        }
        button {
          padding: 10px 20px;
          border-radius: 10px;
          border: 0;
          font-weight: 700;
          background: #3b82f6;
          color: white;
          cursor: pointer;
        }
        button:disabled { opacity: .6; cursor: not-allowed; }
        .results { margin-top: 18px; display: grid; grid-template-columns: 1fr; gap: 12px; }
        .result {
          background: #0f1738;
          border: 1px solid #222b56;
          border-radius: 12px;
          padding: 14px;
        }
        .badge {
          background: #1f2937;
          padding: 4px 8px;
          border-radius: 8px;
          font-size: 12px;
        }
        .path { margin: 6px 0 8px 0; font-size: 12px; opacity: .85; }
        .link {
          background: transparent;
          border: 0;
          color: #93c5fd;
          font-weight: 700;
          cursor: pointer;
          padding: 0;
        }
        .code {
          background: #0b1228;
          border: 1px dashed #2a3363;
          border-radius: 8px;
          padding: 10px;
          white-space: pre-wrap;
          word-break: break-word;
          overflow: auto;
          max-height: 260px;
          color: #e9ecf1;
          font-family: "Consolas","Courier New",monospace;
          font-size: 13px;
          line-height: 1.4;
        }
        .sectionTitle { font-weight: 800; font-size: 16px; opacity: .9; margin-bottom: 6px; }
      `}</style>
    </div>
  )
}
