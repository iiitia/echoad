import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip } from 'recharts'

const WS_URL      = "wss://echoad.onrender.com/ws"
const POLLING_URL = "https://echoad.onrender.com/ads?limit=5"
const POLL_INTERVAL_MS = 3000  // poll every 3 seconds

// ─── Dual-mode transport hook ──────────────────────────────────────────────────
function useAdStream(onMessage) {
  const [status, setStatus]     = useState('connecting')
  const [mode, setMode]         = useState('ws')       // 'ws' | 'polling'
  const wsRef                   = useRef(null)
  const pingRef                 = useRef(null)
  const retryRef                = useRef(null)
  const pollRef                 = useRef(null)
  const retryCount              = useRef(0)
  const seenIds                 = useRef(new Set())    // dedup polling ads
  const wsFailCount             = useRef(0)

  // ── Polling mode ─────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (pollRef.current) return
    setMode('polling')
    setStatus('polling')
    console.log("📡 Switching to polling mode")

    pollRef.current = setInterval(async () => {
      try {
        const res  = await fetch(POLLING_URL)
        const data = await res.json()
        if (Array.isArray(data.ads)) {
          data.ads.forEach(ad => {
            // Only push ads we haven't seen yet
            if (!seenIds.current.has(ad.ad_id)) {
              seenIds.current.add(ad.ad_id)
              // Keep seen set lean
              if (seenIds.current.size > 200) {
                const first = seenIds.current.values().next().value
                seenIds.current.delete(first)
              }
              onMessage(ad)
            }
          })
        }
        setStatus('polling')
      } catch (e) {
        console.error("❌ Poll failed:", e)
        setStatus('error')
      }
    }, POLL_INTERVAL_MS)
  }, [onMessage])

  const stopPolling = useCallback(() => {
    clearInterval(pollRef.current)
    pollRef.current = null
  }, [])

  // ── WebSocket mode ────────────────────────────────────────────
  const connectWS = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    clearTimeout(retryRef.current)
    setMode('ws')
    setStatus('connecting')
    console.log("🔌 Connecting WebSocket...")

    try {
      const ws     = new WebSocket(WS_URL)
      wsRef.current = ws

      // If WS doesn't open within 5s → fallback to polling
      const openTimeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          console.warn("⏱️ WS open timeout — falling back to polling")
          ws.close()
          startPolling()
        }
      }, 5000)

      ws.onopen = () => {
        clearTimeout(openTimeout)
        console.log("✅ WebSocket connected")
        setStatus('connected')
        setMode('ws')
        wsFailCount.current = 0
        retryCount.current  = 0
        stopPolling()

        clearInterval(pingRef.current)
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping")
        }, 30000)
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessage(data)
        } catch {
          console.log("📩 Non-JSON:", event.data)
        }
      }

      ws.onclose = (e) => {
        clearTimeout(openTimeout)
        clearInterval(pingRef.current)
        wsFailCount.current += 1
        console.log(`🔌 WS closed — code: ${e.code} | failures: ${wsFailCount.current}`)

        // After 2 failures → give up on WS, use polling
        if (wsFailCount.current >= 2) {
          console.warn("⚠️ WS repeatedly failing — switching to polling permanently")
          setMode('polling')
          startPolling()
          return
        }

        // Otherwise retry WS with backoff
        setStatus('disconnected')
        const delay = Math.min(1000 * 2 ** retryCount.current, 15000)
        retryCount.current += 1
        console.log(`🔁 Retrying WS in ${delay / 1000}s`)
        retryRef.current = setTimeout(connectWS, delay)
      }

      ws.onerror = () => {
        clearTimeout(openTimeout)
        setStatus('error')
      }

    } catch (err) {
      console.error("❌ WS failed:", err)
      startPolling()
    }
  }, [onMessage, startPolling, stopPolling])

  useEffect(() => {
    connectWS()
    return () => {
      clearInterval(pingRef.current)
      clearInterval(pollRef.current)
      clearTimeout(retryRef.current)
      retryCount.current  = 999
      wsFailCount.current = 999
      wsRef.current?.close()
    }
  }, [connectWS])

  const reconnect = useCallback(() => {
    stopPolling()
    wsFailCount.current = 0
    retryCount.current  = 0
    wsRef.current?.close()
    connectWS()
  }, [connectWS, stopPolling])

  return { status, mode, reconnect }
}

// ─── Sparkline ─────────────────────────────────────────────────────────────────
function Sparkline({ data, color = '#00e5ff', height = 40 }) {
  if (data.length < 2) return null
  const w = 200, h = height
  const min = Math.min(...data), max = Math.max(...data, min + 0.001)
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / (max - min)) * (h - 6) - 3
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const area = `M0,${h} L${data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - ((v - min) / (max - min)) * (h - 6) - 3
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' L')} L${w},${h} Z`
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <defs>
        <linearGradient id={`sg${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#sg${color.replace('#', '')})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}

// ─── Donut ─────────────────────────────────────────────────────────────────────
function Donut({ pct, color, size = 56 }) {
  const r = 20, cx = 28, cy = 28
  const circ = 2 * Math.PI * r
  const dash = (pct / 100) * circ
  return (
    <svg width={size} height={size} viewBox="0 0 56 56">
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="6" />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="6"
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        transform="rotate(-90 28 28)" style={{ transition: 'stroke-dasharray 0.8s ease' }} />
    </svg>
  )
}

// ─── ScoreBadge ────────────────────────────────────────────────────────────────
function ScoreBadge({ score }) {
  const s = typeof score === 'number' ? score : 0
  if (s > 0.7) return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#00e676', fontWeight: 700, fontFamily: 'Share Tech Mono, monospace', fontSize: 13 }}>
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#00e676', display: 'inline-block', boxShadow: '0 0 6px #00e676' }} />
      {s.toFixed(2)} <span style={{ opacity: 0.8, fontSize: 12 }}>(High Value)</span>
    </span>
  )
  if (s < 0.3) return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#ff5252', fontWeight: 700, fontFamily: 'Share Tech Mono, monospace', fontSize: 13 }}>
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5252', display: 'inline-block', boxShadow: '0 0 6px #ff5252' }} />
      {s.toFixed(2)} <span style={{ opacity: 0.8, fontSize: 12 }}>(Low Value)</span>
    </span>
  )
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: '#90a4ae', fontWeight: 600, fontFamily: 'Share Tech Mono, monospace', fontSize: 13 }}>
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#90a4ae', display: 'inline-block' }} />
      {s.toFixed(2)} <span style={{ opacity: 0.8, fontSize: 12 }}>(Average)</span>
    </span>
  )
}

// ─── Heatmap ───────────────────────────────────────────────────────────────────
const CATS = ['Finance', 'Gaming', 'News', 'Travel', 'Tech', 'Health']
const DEVS = ['Mobile', 'Desktop', 'Tablet']

function Heatmap({ ads }) {
  const grid = useMemo(() => {
    const g = {}
    CATS.forEach(c => { g[c] = {}; DEVS.forEach(d => { g[c][d] = 0 }) })
    ads.forEach(a => {
      const c = CATS.includes(a.category) ? a.category : null
      const d = DEVS.includes(a.device) ? a.device : null
      if (c && d) g[c][d]++
    })
    return g
  }, [ads])
  const max = Math.max(...CATS.flatMap(c => DEVS.map(d => grid[c][d])), 1)
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={{ padding: '4px 12px', color: '#546e7a', fontFamily: 'Share Tech Mono, monospace', fontSize: 11, textAlign: 'left' }}></th>
            {DEVS.map(d => <th key={d} style={{ padding: '4px 12px', color: '#546e7a', fontFamily: 'Share Tech Mono, monospace', fontSize: 11, textTransform: 'uppercase', fontWeight: 600 }}>{d}</th>)}
          </tr>
        </thead>
        <tbody>
          {CATS.map(c => (
            <tr key={c}>
              <td style={{ padding: '6px 12px', color: '#90a4ae', fontFamily: 'Share Tech Mono, monospace', fontSize: 12, fontWeight: 600 }}>{c}</td>
              {DEVS.map(d => {
                const v = grid[c][d], pct = v / max
                const bg = pct > 0.6 ? 'rgba(0,230,118,0.65)' : pct > 0.3 ? 'rgba(0,230,118,0.3)' : pct > 0.05 ? 'rgba(0,230,118,0.1)' : 'rgba(255,255,255,0.02)'
                return (
                  <td key={d} style={{ padding: '5px 12px', textAlign: 'center' }}>
                    <div style={{ background: bg, borderRadius: 6, padding: '6px 0', fontSize: 12, color: pct > 0.05 ? '#e8f5e9' : '#263238', fontFamily: 'Share Tech Mono, monospace', transition: 'background 0.5s', minWidth: 40 }}>{v}</div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── LiveCTRChart ──────────────────────────────────────────────────────────────
function LiveCTRChart({ data }) {
  return (
    <div className="stat-card" style={{ height: 300, borderColor: 'rgba(0,176,255,0.2)' }}>
      <div style={{ fontSize: 12, color: '#78909c', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 12, fontWeight: 600 }}>Live CTR Trend (Last 20 Bids)</div>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 20, left: -10, bottom: 10 }}>
          <CartesianGrid vertical={false} stroke="rgba(255,255,255,0.03)" strokeDasharray="3 3" />
          <XAxis dataKey="timestamp" axisLine={false} tickLine={false} tick={{ fontSize: 11, fontFamily: 'Share Tech Mono, monospace', fill: '#546e7a' }} tickMargin={8} />
          <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fontFamily: 'Share Tech Mono, monospace', fill: '#546e7a' }} tickMargin={8} domain={[0, 1]} />
          <Tooltip contentStyle={{ background: '#0d1221', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontFamily: 'Share Tech Mono, monospace' }} labelStyle={{ color: '#00b0ff' }} itemStyle={{ color: '#b0bec5' }} />
          <Line type="monotone" dataKey="score" stroke="#00b0ff" strokeWidth={2} dot={{ fill: '#00b0ff', strokeWidth: 1 }} activeDot={{ r: 6, strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── VelocityGauge ─────────────────────────────────────────────────────────────
function VelocityGauge({ ratePerMin }) {
  const max = 60, pct = Math.min(ratePerMin / max, 1)
  const angle = -135 + pct * 270
  const color = pct > 0.7 ? '#ff5252' : pct > 0.4 ? '#ffab40' : '#00e676'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <svg width="96" height="58" viewBox="0 0 100 60">
        <path d="M10,55 A40,40 0 0,1 90,55" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" strokeLinecap="round" />
        <path d="M10,55 A40,40 0 0,1 90,55" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round" strokeDasharray={`${pct * 125.6} 125.6`} style={{ transition: 'all 0.6s ease' }} />
        <line x1="50" y1="55" x2={50 + 28 * Math.cos((angle * Math.PI) / 180)} y2={55 + 28 * Math.sin((angle * Math.PI) / 180)} stroke={color} strokeWidth="2" strokeLinecap="round" style={{ transition: 'all 0.6s ease' }} />
        <circle cx="50" cy="55" r="3" fill={color} />
      </svg>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: 'Share Tech Mono, monospace', lineHeight: 1 }}>{ratePerMin.toFixed(0)}</div>
      <div style={{ fontSize: 10, color: '#78909c', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', fontWeight: 600 }}>BIDS / MIN</div>
    </div>
  )
}

// ─── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ toasts }) {
  return (
    <div style={{ position: 'fixed', top: 16, right: 16, zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 280 }}>
      {toasts.map(t => (
        <div key={t.id} style={{ background: '#0a1f14', border: '1px solid #00e676', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: '#00e676', fontFamily: 'Share Tech Mono, monospace', boxShadow: '0 0 24px rgba(0,230,118,0.15)', animation: 'toastIn 0.3s ease' }}>
          🎯 <strong>High-Value Bid</strong> — {t.ad_id}<br />
          <span style={{ color: '#80cbc4', fontSize: 11 }}>{t.category} · Score: {t.score?.toFixed(3)}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Mode Badge ────────────────────────────────────────────────────────────────
function ModeBadge({ mode, status }) {
  if (mode === 'polling') return (
    <span className="pill" style={{ background: 'rgba(255,171,64,0.08)', color: '#ffab40', borderColor: 'rgba(255,171,64,0.5)' }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#ffab40', display: 'inline-block' }} className="blink" />
      HTTP POLLING
    </span>
  )
  if (status === 'connected') return (
    <span className="pill pill-live">
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#00e676', display: 'inline-block' }} className="blink" />
      WS LIVE
    </span>
  )
  return (
    <span className="pill pill-offline">
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#455a64', display: 'inline-block' }} />
      {status.toUpperCase()}
    </span>
  )
}

// ─── Demo generator ────────────────────────────────────────────────────────────
const ALL_CATS = ['Finance', 'Gaming', 'News', 'Travel', 'Tech', 'Health']
const ALL_DEVS = ['Mobile', 'Desktop', 'Tablet']
function generateAd() {
  return {
    ad_id:     `#${String.fromCharCode(65 + Math.floor(Math.random() * 26))}${Math.floor(Math.random() * 900 + 100)}`,
    timestamp: new Date().toISOString(),
    score:     Math.random(),
    category:  ALL_CATS[Math.floor(Math.random() * ALL_CATS.length)],
    device:    ALL_DEVS[Math.floor(Math.random() * ALL_DEVS.length)],
  }
}

// ─── App ───────────────────────────────────────────────────────────────────────
const MAX_ADS = 100

export default function App() {
  const [ads, setAds]                   = useState([])
  const [scoreHistory, setScoreHistory] = useState([])
  const [filter, setFilter]             = useState('all')
  const [toasts, setToasts]             = useState([])
  const [newId, setNewId]               = useState(null)
  const [activeTab, setActiveTab]       = useState('feed')
  const [bidsPerMin, setBidsPerMin]     = useState(0)
  const [useDemo, setUseDemo]           = useState(false)
  const [showHighValue, setShowHighValue] = useState(false)
  const bidTimestamps = useRef([])

  const pushAd = useCallback((raw) => {
    const ad = {
      ad_id:     raw.ad_id     ?? `#${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
      timestamp: raw.timestamp ?? new Date().toISOString(),
      score:     typeof raw.score === 'number' ? raw.score : 0,
      category:  raw.category  ?? 'Unknown',
      device:    raw.device    ?? 'Unknown',
    }
    setAds(prev => [ad, ...prev].slice(0, MAX_ADS))
    setScoreHistory(prev => [...prev, ad.score].slice(-50))
    setNewId(ad.ad_id)
    setTimeout(() => setNewId(null), 500)

    const now = Date.now()
    bidTimestamps.current = [...bidTimestamps.current, now].filter(t => now - t < 60000)
    setBidsPerMin(bidTimestamps.current.length)

    if (ad.score > 0.85) {
      const id = now + Math.random()
      setToasts(prev => [{ ...ad, id }, ...prev].slice(0, 3))
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000)
    }
  }, [])

  // ✅ Dual-mode: WS → polling fallback
  const { status, mode, reconnect } = useAdStream(pushAd)

  useEffect(() => {
    if (!useDemo) return
    const iv = setInterval(() => pushAd(generateAd()), 1800)
    return () => clearInterval(iv)
  }, [useDemo, pushAd])

  const metrics = useMemo(() => {
    const total    = ads.length
    const high     = ads.filter(a => a.score > 0.7).length
    const low      = ads.filter(a => a.score < 0.3).length
    const avg      = total ? ads.reduce((s, a) => s + a.score, 0) / total : 0
    const highRate = total ? (high / total) * 100 : 0
    return { total, high, low, avg, highRate }
  }, [ads])

  const filtered = useMemo(() => {
    if (filter === 'high') return ads.filter(a => a.score > 0.7)
    if (filter === 'mid')  return ads.filter(a => a.score >= 0.3 && a.score <= 0.7)
    if (filter === 'low')  return ads.filter(a => a.score < 0.3)
    return ads
  }, [ads, filter])

  const chartData = useMemo(() =>
    ads.slice(0, 20).reverse().map(ad => ({
      timestamp: new Date(ad.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      score: ad.score ?? 0
    }))
  , [ads])

  const tableAds = useMemo(() =>
    showHighValue ? filtered.filter(ad => (ad.score ?? 0) > 0.4) : filtered
  , [filtered, showHighValue])

  const isLive = status === 'connected' || mode === 'polling' || useDemo

  return (
    <>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&display=swap');
        *{box-sizing:border-box;margin:0;padding:0;}
        body{background:#0a0e1a;font-family:'Rajdhani',sans-serif;color:#cfd8dc;min-height:100vh;}
        @keyframes toastIn{from{opacity:0;transform:translateX(20px);}to{opacity:1;transform:translateX(0);}}
        @keyframes rowFlash{0%{background:rgba(0,230,118,0.12);}100%{background:transparent;}}
        @keyframes blink{0%,100%{opacity:1}50%{opacity:0.35}}
        .row-new{animation:rowFlash 0.6s ease-out;}
        .blink{animation:blink 1.4s infinite;}
        .pill{display:inline-flex;align-items:center;gap:5px;padding:4px 12px;border-radius:20px;font-size:11px;font-family:'Share Tech Mono',monospace;border:1px solid;white-space:nowrap;}
        .pill-live{background:rgba(0,230,118,0.08);color:#00e676;border-color:rgba(0,230,118,0.5);}
        .pill-pipeline{background:rgba(0,176,255,0.08);color:#00b0ff;border-color:rgba(0,176,255,0.5);}
        .pill-offline{background:rgba(255,255,255,0.03);color:#546e7a;border-color:rgba(255,255,255,0.1);}
        .stat-card{background:#0d1221;border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:18px 22px;position:relative;overflow:hidden;}
        .stat-card::before{content:'';position:absolute;inset:0;background:linear-gradient(135deg,rgba(255,255,255,0.015) 0%,transparent 60%);pointer-events:none;}
        .panel{background:#0d1221;border:1px solid rgba(255,255,255,0.06);border-radius:10px;overflow:hidden;}
        .tab-btn{background:none;border:none;border-bottom:2px solid transparent;cursor:pointer;padding:9px 16px;font-family:'Rajdhani',sans-serif;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#37474f;transition:all 0.2s;}
        .tab-btn.active{color:#00b0ff;border-bottom-color:#00b0ff;}
        .tab-btn:hover{color:#78909c;}
        .chip{background:none;border:1px solid rgba(255,255,255,0.15);border-radius:20px;padding:3px 12px;font-family:'Share Tech Mono',monospace;font-size:10px;color:#cfd8dc;cursor:pointer;transition:all 0.15s;}
        .chip.active{border-color:rgba(0,176,255,0.6);color:#00b0ff;background:rgba(0,176,255,0.12);}
        .chip:hover{color:#fff;border-color:rgba(255,255,255,0.3);}
        table{width:100%;border-collapse:collapse;}
        thead th{padding:10px 14px;font-family:'Share Tech Mono',monospace;font-size:11px;letter-spacing:0.13em;text-transform:uppercase;color:#546e7a;border-bottom:1px solid rgba(255,255,255,0.05);text-align:left;font-weight:600;}
        tbody tr{border-bottom:1px solid rgba(255,255,255,0.025);transition:background 0.12s;}
        tbody tr:hover{background:rgba(255,255,255,0.018);}
        tbody td{padding:10px 14px;font-size:13px;}
        .action-btn{background:rgba(0,176,255,0.07);border:1px solid rgba(0,176,255,0.25);color:#00b0ff;border-radius:6px;padding:5px 12px;font-family:'Share Tech Mono',monospace;font-size:10px;cursor:pointer;transition:all 0.15s;white-space:nowrap;}
        .action-btn:hover{background:rgba(0,176,255,0.16);}
        .action-btn.demo-on{background:rgba(255,171,64,0.1);border-color:rgba(255,171,64,0.4);color:#ffab40;}
        ::-webkit-scrollbar{width:3px;height:3px;}
        ::-webkit-scrollbar-track{background:transparent;}
        ::-webkit-scrollbar-thumb{background:#1e2a3a;border-radius:2px;}
      `}</style>

      <Toast toasts={toasts} />

      <div style={{ minHeight: '100vh', padding: '18px 20px', maxWidth: 1180, margin: '0 auto' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18, flexWrap: 'wrap', gap: 10 }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#00b0ff', letterSpacing: '0.14em', textTransform: 'uppercase', fontFamily: 'Rajdhani, sans-serif' }}>
            Echo-Ad Dashboard
          </h1>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className={`action-btn ${useDemo ? 'demo-on' : ''}`} onClick={() => setUseDemo(v => !v)}>
              {useDemo ? '⏹ Stop Demo' : '▶ Demo Mode'}
            </button>
            {!useDemo && (
              <button className="action-btn" onClick={reconnect}>↺ Reconnect</button>
            )}
            {/* ✅ Shows WS LIVE or HTTP POLLING automatically */}
            <ModeBadge mode={mode} status={status} />
            <span className="pill pill-pipeline">
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#00b0ff', display: 'inline-block' }} />
              PIPELINE ACTIVE
            </span>
          </div>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 12, marginBottom: 14 }}>
          <div className="stat-card">
            <div style={{ fontSize: 11, color: '#78909c', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 8, fontWeight: 600 }}>Total Ads Processed</div>
            <div style={{ fontSize: 34, fontWeight: 700, color: '#eceff1', fontFamily: 'Share Tech Mono, monospace', lineHeight: 1 }}>{metrics.total.toLocaleString()}</div>
            <div style={{ marginTop: 12, height: 38 }}><Sparkline data={scoreHistory} color="#546e7a" height={38} /></div>
          </div>
          <div className="stat-card" style={{ borderColor: 'rgba(0,230,118,0.18)' }}>
            <div style={{ fontSize: 11, color: '#4caf50', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 8, fontWeight: 600 }}>High Value Ads (&gt;0.70)</div>
            <div style={{ fontSize: 34, fontWeight: 700, color: '#00e676', fontFamily: 'Share Tech Mono, monospace', lineHeight: 1 }}>{metrics.high.toLocaleString()}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
              <Donut pct={metrics.highRate} color="#00e676" />
              <span style={{ fontSize: 13, color: '#78909c', fontFamily: 'Share Tech Mono, monospace', fontWeight: 600 }}>{metrics.highRate.toFixed(1)}%</span>
            </div>
          </div>
          <div className="stat-card">
            <div style={{ fontSize: 11, color: '#78909c', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 8, fontWeight: 600 }}>Avg CTR Score</div>
            <div style={{ fontSize: 34, fontWeight: 700, color: '#00b0ff', fontFamily: 'Share Tech Mono, monospace', lineHeight: 1 }}>{metrics.avg.toFixed(3)}</div>
            <div style={{ marginTop: 12, height: 38 }}><Sparkline data={scoreHistory} color="#00b0ff" height={38} /></div>
          </div>
          <div className="stat-card" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ fontSize: 11, color: '#78909c', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 6, textAlign: 'center', fontWeight: 600 }}>Auction Velocity</div>
            <VelocityGauge ratePerMin={bidsPerMin} />
          </div>
          <div className="stat-card" style={{ borderColor: 'rgba(255,82,82,0.12)' }}>
            <div style={{ fontSize: 11, color: '#ef9a9a', letterSpacing: '0.12em', textTransform: 'uppercase', fontFamily: 'Share Tech Mono, monospace', marginBottom: 8, fontWeight: 600 }}>Low Value Ads (&lt;0.30)</div>
            <div style={{ fontSize: 34, fontWeight: 700, color: '#ff5252', fontFamily: 'Share Tech Mono, monospace', lineHeight: 1 }}>{metrics.low.toLocaleString()}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
              <Donut pct={metrics.total ? (metrics.low / metrics.total) * 100 : 0} color="#ff5252" />
              <span style={{ fontSize: 13, color: '#78909c', fontFamily: 'Share Tech Mono, monospace', fontWeight: 600 }}>
                {metrics.total ? ((metrics.low / metrics.total) * 100).toFixed(1) : 0}%
              </span>
            </div>
          </div>
        </div>

        {/* Chart */}
        <div style={{ marginBottom: 14 }}><LiveCTRChart data={chartData} /></div>

        {/* Main Panel */}
        <div className="panel">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 18px', borderBottom: '1px solid rgba(255,255,255,0.04)', flexWrap: 'wrap', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className="blink" style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5252', display: 'inline-block', boxShadow: '0 0 7px #ff5252' }} />
              <span style={{ fontSize: 13, fontWeight: 700, color: '#00b0ff', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Live Ad Auction Feed</span>
              {/* ✅ Shows polling interval hint */}
              {mode === 'polling' && (
                <span style={{ fontSize: 10, color: '#ffab40', fontFamily: 'Share Tech Mono, monospace', opacity: 0.7 }}>
                  (polling every {POLL_INTERVAL_MS / 1000}s)
                </span>
              )}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
              <button className={`tab-btn ${activeTab === 'feed' ? 'active' : ''}`} onClick={() => setActiveTab('feed')}>Feed</button>
              <button className={`tab-btn ${activeTab === 'heatmap' ? 'active' : ''}`} onClick={() => setActiveTab('heatmap')}>Heatmap</button>
              {activeTab === 'feed' && (
                <>
                  <div style={{ display: 'flex', gap: 4, marginLeft: 8 }}>
                    {[['all', 'All'], ['high', '🟢 High'], ['mid', '🟡 Mid'], ['low', '🔴 Low']].map(([k, l]) => (
                      <button key={k} className={`chip ${filter === k ? 'active' : ''}`} onClick={() => setFilter(k)}>{l}</button>
                    ))}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginLeft: 8 }}>
                    <button className={`chip ${showHighValue ? 'active' : ''}`} onClick={() => setShowHighValue(v => !v)}>
                      {showHighValue ? 'High Value Only' : 'All Scores'}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          <div style={{ padding: activeTab === 'heatmap' ? '18px 22px' : 0, minHeight: 280 }}>
            {activeTab === 'heatmap' ? <Heatmap ads={ads} /> : (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr><th>Ad ID</th><th>Time</th><th>Category</th><th>Device</th><th>CTR Score</th></tr>
                  </thead>
                  <tbody>
                    {tableAds.length === 0 ? (
                      <tr>
                        <td colSpan={5} style={{ textAlign: 'center', color: '#37474f', padding: '40px 0', fontFamily: 'Share Tech Mono, monospace', fontSize: 12 }}>
                          {useDemo ? 'Loading...' : 'Connecting to stream...'}
                        </td>
                      </tr>
                    ) : tableAds.map((ad) => (
                      <tr key={`${ad.ad_id}-${ad.timestamp}`} className={ad.ad_id === newId ? 'row-new' : ''}>
                        <td style={{ color: '#00b0ff', fontFamily: 'Share Tech Mono, monospace', fontWeight: 700, fontSize: 13 }}>{ad.ad_id}</td>
                        <td style={{ color: '#546e7a', fontFamily: 'Share Tech Mono, monospace', fontSize: 12 }}>
                          {new Date(ad.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </td>
                        <td>
                          <span style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 4, padding: '2px 8px', fontSize: 11, fontFamily: 'Share Tech Mono, monospace', color: '#90a4ae', border: '1px solid rgba(255,255,255,0.06)' }}>
                            {ad.category}
                          </span>
                        </td>
                        <td style={{ color: '#78909c', fontFamily: 'Share Tech Mono, monospace', fontSize: 12 }}>{ad.device}</td>
                        <td><ScoreBadge score={ad.score} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div style={{ padding: '8px 18px', borderTop: '1px solid rgba(255,255,255,0.04)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
            <span style={{ fontSize: 11, color: '#37474f', fontFamily: 'Share Tech Mono, monospace' }}>Showing {tableAds.length} / {ads.length} records</span>
            <span style={{ fontSize: 11, color: '#37474f', fontFamily: 'Share Tech Mono, monospace' }}>Buffer: {ads.length}/{MAX_ADS}</span>
          </div>
        </div>
      </div>
    </>
  )
}
