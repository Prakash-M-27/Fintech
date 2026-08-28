'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { io } from 'socket.io-client'
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight,
  BarChart2, Bell, Bot, CheckCircle2, Circle, Clock,
  Cpu, Crosshair, Database, Gauge, History, Layers3,
  PanelLeft, Settings2, ShieldCheck, TrendingDown, TrendingUp,
  Wallet, Zap, RefreshCw, Target,
} from 'lucide-react'
import { type OHLC, calcUTBotAlerts, calcFairValueGap, calcVolumeProfile } from '@/lib/indicators'
import { TVPriceChart, TVRSIChart, TVMACDChart } from '@/components/tv-chart'

type Order = { id: string; side: 'BUY' | 'SELL'; qty: number; price: number; status: 'FILLED' | 'PENDING' | 'CANCELLED'; ts: string }
type AgentLog = { id: number; ts: string; agent: string; msg: string; tone: 'green' | 'amber' | 'red' | 'blue' }
type Position = { symbol: string; qty: number; entry: number; current: number }
type AISuggestion = {
  action: 'BUY' | 'SELL' | 'HOLD'; confidence: number; entry: number; target: number; stopLoss: number
  reasoning: string; riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'; trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL'; loading?: boolean
}

const fmt = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
const nowT = () => new Date().toLocaleTimeString('en-IN', { hour12: false })
const rand = (min: number, max: number) => Math.random() * (max - min) + min

const AGENTS = ['Observer', 'Analyst', 'Risk Engine', 'Allocator', 'Executor']
const SYMBOLS = ['NIFTY 50', 'BANKNIFTY', 'SENSEX', 'GOLD', 'USD/INR']
const TIMEFRAMES = [
  { label: '1m', value: '1min' }, { label: '5m', value: '5min' }, { label: '15m', value: '15min' },
  { label: '30m', value: '30min' }, { label: '1h', value: '1h' }, { label: '4h', value: '4h' },
  { label: '1D', value: '1day' }, { label: '1W', value: '1week' }, { label: '1M', value: '1month' },
]

const BASE: Record<string, number> = {
  'NIFTY 50': 26800, 'BANKNIFTY': 54000, 'SENSEX': 88500, 'GOLD': 72418, 'USD/INR': 83.42,
}

const SYMBOL_TO_ASSET: Record<string, string> = {
  'NIFTY 50': 'nifty', 'BANKNIFTY': 'banknifty', 'SENSEX': 'sensex', 'GOLD': 'gold', 'USD/INR': 'usd',
}

const NAV_LINKS = [
  { label: 'Overview', path: '/', Icon: Gauge },
  { label: 'Live Room', path: '/live', Icon: Activity },
  { label: 'Markets', path: '/markets', Icon: TrendingUp },
  { label: 'Agent Intel', path: '/agent', Icon: Bot },
  { label: 'Scenarios', path: '/scenarios', Icon: Layers3 },
  { label: 'Risk', path: '/risk', Icon: ShieldCheck },
  { label: 'Capital', path: '/capital', Icon: Wallet },
  { label: 'Positions', path: '/positions', Icon: Target },
  { label: 'History', path: '/history', Icon: History },
  { label: 'Data', path: '/data-sources', Icon: Database },
  { label: 'Settings', path: '/settings', Icon: Settings2 },
]

const agentMessages: Record<string, string[]> = {
  Observer: ['Price crossed VWAP', 'Volume spike detected', 'Breadth expanding', 'ATR rising', 'New high formed', 'Support level tested'],
  Analyst: ['Bullish structure intact', 'RSI entering overbought', 'MACD crossover confirmed', 'BB squeeze detected', 'EMA20 > EMA50 confirmed'],
  'Risk Engine': ['VaR within threshold', 'Exposure limit checked', 'Stop-loss validated', 'Drawdown within bounds', 'Position size approved'],
  Allocator: ['Capital allocated ₹40,000', 'Opportunity score 81%', 'Risk-adjusted fit: HIGH', 'Reward ratio 2.1R', 'Allocation approved'],
  Executor: ['Order placed at market', 'Slippage 0.01%', 'Fill confirmed', 'Execution quality: GOOD', 'Order book depth checked'],
}
const tones: AgentLog['tone'][] = ['blue', 'green', 'amber', 'green', 'green']

const BACKEND = 'http://localhost:8000'

function Navbar({ pulse }: { pulse: boolean }) {
  const [collapsed, setCollapsed] = useState(false)
  return (
    <aside className={`${collapsed ? 'w-14' : 'w-56'} hidden shrink-0 border-r border-gray-100 bg-white transition-all duration-200 md:flex flex-col`}>
      <div className="flex h-14 items-center justify-between border-b border-gray-100 px-3">
        {!collapsed && (
          <div className="flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-sm bg-gray-900">
              <Crosshair className="size-3.5 text-white" />
            </span>
            <span className="text-xs font-bold tracking-[.2em]">AXIOM</span>
          </div>
        )}
        <button onClick={() => setCollapsed(v => !v)} className="rounded p-1.5 text-gray-400 hover:bg-gray-100">
          <PanelLeft className="size-4" />
        </button>
      </div>
      <nav className="flex flex-col gap-0.5 p-2 flex-1">
        {!collapsed && <p className="mb-1 px-2 font-mono text-[9px] uppercase tracking-[.18em] text-gray-300">Workspace</p>}
        {NAV_LINKS.map(({ label, path, Icon }) => (
          <a key={path} href={path} className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors ${
            path === '/live' ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
          }`}>
            <Icon className="size-3.5 shrink-0" />
            {!collapsed && label}
          </a>
        ))}
      </nav>
      {!collapsed && (
        <div className="m-3 rounded-md border border-gray-100 bg-gray-50 p-3">
          <div className="flex items-center gap-1.5">
            <span className={`size-1.5 rounded-full ${pulse ? 'bg-emerald-500' : 'bg-emerald-300'}`} />
            <span className="font-mono text-[9px] uppercase tracking-wider text-gray-500">Live · streaming</span>
          </div>
          <p className="mt-1 font-mono text-[9px] text-gray-400">Paper trading mode</p>
        </div>
      )}
    </aside>
  )
}

function SuggestionCard({ s, onRefresh }: { s: AISuggestion | null; onRefresh: () => void }) {
  if (!s) return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-gray-300">
      <Bot className="size-8" />
      <p className="font-mono text-[10px]">Waiting for AI analysis…</p>
    </div>
  )
  if (s.loading) return (
    <div className="flex flex-col items-center justify-center gap-2 py-8 text-gray-400">
      <RefreshCw className="size-5 animate-spin" />
      <p className="font-mono text-[10px]">Groq AI analysing…</p>
    </div>
  )

  const actionColor = s.action === 'BUY' ? 'text-emerald-600 bg-emerald-50 border-emerald-200'
    : s.action === 'SELL' ? 'text-rose-600 bg-rose-50 border-rose-200'
    : 'text-amber-600 bg-amber-50 border-amber-200'
  const trendColor = s.trend === 'BULLISH' ? 'text-emerald-600' : s.trend === 'BEARISH' ? 'text-rose-600' : 'text-amber-600'

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className={`rounded-md border px-3 py-1 font-mono text-sm font-bold ${actionColor}`}>{s.action}</span>
        <div className="flex items-center gap-2">
          <span className={`font-mono text-xs font-semibold ${trendColor}`}>{s.trend}</span>
          <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
            s.riskLevel === 'LOW' ? 'bg-emerald-50 text-emerald-600' :
            s.riskLevel === 'HIGH' ? 'bg-rose-50 text-rose-600' : 'bg-amber-50 text-amber-600'
          }`}>{s.riskLevel} RISK</span>
        </div>
      </div>
      <div className="h-2 w-full rounded-full bg-gray-100">
        <div className={`h-2 rounded-full transition-all ${
          s.action === 'BUY' ? 'bg-emerald-400' : s.action === 'SELL' ? 'bg-rose-400' : 'bg-amber-400'
        }`} style={{ width: `${s.confidence}%` }} />
      </div>
      <p className="font-mono text-[10px] text-gray-400">Confidence: {s.confidence}%</p>
      <div className="grid grid-cols-3 gap-2">
        {[['Entry', fmt(s.entry), 'text-gray-700'], ['Target', fmt(s.target), 'text-emerald-600'], ['Stop', fmt(s.stopLoss), 'text-rose-600']].map(([l, v, c]) => (
          <div key={l} className="rounded-md border border-gray-100 p-2 text-center">
            <p className="font-mono text-[9px] text-gray-400">{l}</p>
            <p className={`mt-0.5 font-mono text-xs font-semibold ${c}`}>{v}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] leading-relaxed text-gray-500">{s.reasoning}</p>
      <button onClick={onRefresh} className="flex items-center justify-center gap-1.5 rounded-md border border-gray-200 py-1.5 text-xs text-gray-500 hover:bg-gray-50">
        <RefreshCw className="size-3" /> Refresh analysis
      </button>
    </div>
  )
}

export default function LiveTradingPage() {
  const [symbol, setSymbol] = useState('NIFTY 50')
  const [timeframe, setTimeframe] = useState('1min')
  const [candles, setCandles] = useState<OHLC[]>([])
  const [loading, setLoading] = useState(true)
  const [orders, setOrders] = useState<Order[]>([])
  const [logs, setLogs] = useState<AgentLog[]>([])
  const [positions, setPositions] = useState<Position[]>([
    { symbol: 'NIFTY 50', qty: 24, entry: 26750, current: 26800 },
    { symbol: 'BANKNIFTY', qty: 4, entry: 53900, current: 54000 },
    { symbol: 'GOLD', qty: 2, entry: 72080, current: 72418 },
  ])
  const [agentStep, setAgentStep] = useState(0)
  const [pulse, setPulse] = useState(false)
  const [suggestion, setSuggestion] = useState<AISuggestion | null>(null)
  const [activeTab, setActiveTab] = useState<'price' | 'rsi' | 'macd'>('price')
  const [livePrice, setLivePrice] = useState<number | null>(null)
  const [showIndicators, setShowIndicators] = useState({
    ema20: true, ema50: true, bb: true, vwap: true,
    utBot: false, fvg: false, volumeProfile: false, volume: true,
  })
  const logId = useRef(0)
  const orderId = useRef(100)

  const assetKey = SYMBOL_TO_ASSET[symbol] || 'nifty'

  const fetchCandles = useCallback(async (sym: string, tf: string) => {
    setLoading(true)
    setLivePrice(null)
    const asset = SYMBOL_TO_ASSET[sym] || 'nifty'
    try {
      const res = await fetch(`${BACKEND}/api/market/${asset}/candles?timeframe=${tf}&limit=200`)
      const data = await res.json()
      if (Array.isArray(data) && data.length > 0) {
        const ohlc: OHLC[] = data.map((c: any) => ({
          time: c.time, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume || 0,
        }))
        setCandles(ohlc)
      }
    } catch {
      // fallback: fetch history from existing endpoint
      try {
        const res = await fetch(`${BACKEND}/api/market/${asset}/history?limit=200`)
        const data = await res.json()
        if (Array.isArray(data)) {
          const ohlc: OHLC[] = data.reverse().map((p: any, i: number) => ({
            time: p.timestamp || new Date(Date.now() - (data.length - i) * 60000).toISOString(),
            open: i > 0 ? data[i - 1].price : p.price,
            high: p.price + rand(2, 8), low: p.price - rand(2, 8),
            close: p.price, volume: p.volume || Math.floor(rand(50, 200)),
          }))
          setCandles(ohlc)
        }
      } catch {}
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchCandles(symbol, timeframe)
  }, [symbol, timeframe, fetchCandles])

  // ── Client-side live tick generator (1.5s interval) ─────────────────────
  useEffect(() => {
    if (!candles.length) return
    const cfg = { vol: 0.0006, mr: 0.003 }
    const tick = setInterval(() => {
      setCandles(prev => {
        if (!prev.length) return prev
        const last = prev[prev.length - 1]
        const mid = (BASE[symbol] || 26800)
        const drift = cfg.mr * (mid - last.close) / mid
        const noise = (Math.random() - 0.5) * 2 * cfg.vol
        const pct = drift + noise
        const newPrice = +(last.close * (1 + pct)).toFixed(2)
        const updated = [...prev]
        updated[prev.length - 1] = {
          ...last,
          close: newPrice,
          high: Math.max(last.high, newPrice),
          low: Math.min(last.low, newPrice),
        }
        return updated.slice(-200)
      })
      setLivePrice(p => {
        const cfg2 = { vol: 0.0006, mr: 0.003 }
        const base = BASE[symbol] || 26800
        const current = p ?? base
        const drift = cfg2.mr * (base - current) / base
        const noise = (Math.random() - 0.5) * 2 * cfg2.vol
        return +(current * (1 + drift + noise)).toFixed(2)
      })
      setPulse(v => !v)
    }, 1500)
    return () => clearInterval(tick)
  }, [symbol, timeframe, candles.length])

  useEffect(() => {
    if (!assetKey) return
    const socket = io(BACKEND)
    socket.emit('subscribe', assetKey)

    socket.on('market_update', (data: { asset?: string; price?: number; time?: string }) => {
      if (data?.price && (data.asset === assetKey || !data.asset)) {
        const newPrice = Number(data.price)
        setLivePrice(newPrice)
        setCandles(prev => {
          if (!prev.length) return prev
          const updated = [...prev]
          const idx = updated.length - 1
          updated[idx] = {
            ...updated[idx],
            close: newPrice,
            high: Math.max(updated[idx].high, newPrice),
            low: Math.min(updated[idx].low, newPrice),
          }
          return updated
        })

        setPositions(prev => prev.map(p => p.symbol === symbol ? { ...p, current: newPrice } : p))
        setPulse(v => !v)
      }
    })

    return () => { socket.disconnect() }
  }, [assetKey, symbol])

  const fetchSuggestion = useCallback(async (c: OHLC[]) => {
    const last = c[c.length - 1]
    const prev = c[c.length - 2]
    if (!last || !prev) return
    setSuggestion(s => s ? { ...s, loading: true } : { action: 'HOLD', confidence: 0, entry: 0, target: 0, stopLoss: 0, reasoning: '', riskLevel: 'MEDIUM', trend: 'NEUTRAL', loading: true })
    try {
      const closes = c.map(d => d.close)
      const k12 = 2 / 13, k26 = 2 / 27
      let ema12 = closes[0], ema26 = closes[0]
      let rsi = 50, gains = 0, losses = 0
      const ema20k = 2 / 21
      let ema20 = closes[0]
      for (let i = 0; i < closes.length; i++) {
        ema12 = i === 0 ? closes[0] : closes[i] * k12 + ema12 * (1 - k12)
        ema26 = i === 0 ? closes[0] : closes[i] * k26 + ema26 * (1 - k26)
        ema20 = i === 0 ? closes[0] : closes[i] * ema20k + ema20 * (1 - ema20k)
        if (i > 0) {
          const d = closes[i] - closes[i - 1]
          if (i <= 14) { if (d >= 0) gains += d; else losses -= d; if (i === 14) { gains /= 14; losses /= 14 } }
          else { gains = (gains * 13 + Math.max(d, 0)) / 14; losses = (losses * 13 + Math.max(-d, 0)) / 14 }
          if (i >= 14) rsi = +(100 - 100 / (1 + (losses === 0 ? 100 : gains / losses))).toFixed(2)
        }
      }
      const macd = +(ema12 - ema26).toFixed(2)
      const period = 20
      let bbUpper = last.close, bbLower = last.close
      if (closes.length >= period) {
        const slice = closes.slice(-period)
        const mean = slice.reduce((a, b) => a + b, 0) / period
        const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
        bbUpper = +(mean + 2 * std).toFixed(2)
        bbLower = +(mean - 2 * std).toFixed(2)
      }
      const vwap = +(closes.reduce((a, b) => a + b, 0) / closes.length).toFixed(2)

      const res = await fetch('/api/groq-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol, price: last.close,
          change: (((last.close - prev.close) / prev.close) * 100).toFixed(2),
          rsi, macd, signal: macd, ema20, ema50: ema26,
          bbUpper, bbLower, vwap, volume: last.volume,
        }),
      })
      const data = await res.json()
      if (!data.error) setSuggestion({ ...data, loading: false })
    } catch { setSuggestion(s => s ? { ...s, loading: false } : null) }
  }, [symbol])

  useEffect(() => {
    if (candles.length > 2) fetchSuggestion(candles)
    const t = setInterval(() => { if (candles.length > 2) fetchSuggestion(candles) }, 30000)
    return () => clearInterval(t)
  }, [symbol, candles.length])

  useEffect(() => {
    const t = setInterval(() => {
      setAgentStep(step => {
        const idx = step % AGENTS.length
        const agent = AGENTS[idx]
        const msgs = agentMessages[agent]
        const msg = msgs[Math.floor(Math.random() * msgs.length)]
        setLogs(prev => [{ id: logId.current++, ts: nowT(), agent, msg, tone: tones[idx] }, ...prev.slice(0, 49)])
        if (agent === 'Executor') {
          setCandles(c => {
            const price = c[c.length - 1]?.close ?? BASE[symbol]
            const side: Order['side'] = Math.random() > 0.4 ? 'BUY' : 'SELL'
            setOrders(prev => [{
              id: `ORD-${orderId.current++}`, side, qty: Math.floor(rand(1, 5)),
              price: +(price + rand(-2, 2)).toFixed(2),
              status: Math.random() > 0.15 ? 'FILLED' : 'PENDING', ts: nowT(),
            }, ...prev.slice(0, 19)])
            return c
          })
        }
        return step + 1
      })
    }, 2200)
    return () => clearInterval(t)
  }, [symbol])

  const latest = candles[candles.length - 1]
  const prev2 = candles[candles.length - 2]
  const displayPrice = livePrice ?? latest?.close ?? 0
  const change = latest && prev2 ? displayPrice - prev2.close : 0
  const pct = prev2 ? ((change / prev2.close) * 100).toFixed(2) : '0.00'
  const up = change >= 0

  const fvgZones = calcFairValueGap(candles)
  const volumeProfile = calcVolumeProfile(candles)
  const utBotSignals = calcUTBotAlerts(candles)

  return (
    <div className="flex min-h-screen bg-white text-gray-900">
      <Navbar pulse={pulse} />

      <div className="flex flex-1 flex-col min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-gray-100 bg-white/95 px-4 backdrop-blur md:px-6">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10px] uppercase tracking-widest text-gray-400 md:hidden">AXIOM · Live</span>
            <div className="hidden md:flex items-center gap-2">
              <span className="flex size-2 rounded-full bg-emerald-500" />
              <span className="font-mono text-[10px] uppercase tracking-widest text-gray-500">Live Trading Room</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-4 font-mono text-xs">
              <span suppressHydrationWarning className={up ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>
                {symbol} {displayPrice ? fmt(displayPrice) : '—'} {up ? '▲' : '▼'} {Math.abs(+pct)}%
              </span>
            </div>
            <span suppressHydrationWarning className={`flex items-center gap-1.5 font-mono text-[10px] ${pulse ? 'text-emerald-500' : 'text-emerald-400'}`}>
              <span className={`size-2 rounded-full ${pulse ? 'bg-emerald-500' : 'bg-emerald-300'} transition-colors`} />
              Streaming
            </span>
            <span suppressHydrationWarning className="font-mono text-[10px] text-gray-400">{nowT()}</span>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-4 md:p-5">
          {/* Symbol Tabs */}
          <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
            {SYMBOLS.map(s => (
              <button key={s} onClick={() => setSymbol(s)}
                className={`shrink-0 rounded-md border px-3 py-1.5 font-mono text-xs font-semibold transition-colors ${
                  symbol === s ? 'border-gray-900 bg-gray-900 text-white' : 'border-gray-200 text-gray-500 hover:border-gray-400 hover:text-gray-800'
                }`}>
                {s}
              </button>
            ))}
          </div>

          {/* Timeframe Selector */}
          <div className="mb-4 flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-gray-400">Timeframe</span>
            <div className="flex gap-1 bg-gray-100 p-0.5 rounded-md">
              {TIMEFRAMES.map(tf => (
                <button key={tf.value} onClick={() => setTimeframe(tf.value)}
                  className={`rounded px-2.5 py-1 font-mono text-[11px] font-medium transition-all ${
                    timeframe === tf.value ? 'bg-white text-gray-900 shadow-sm font-semibold' : 'text-gray-500 hover:text-gray-900'
                  }`}>
                  {tf.label}
                </button>
              ))}
            </div>
          </div>

          {/* Price Hero */}
          <div className="mb-4 flex flex-wrap items-end gap-5">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">{symbol}</p>
              <p className="mt-0.5 font-mono text-3xl font-bold tracking-tight">{displayPrice ? fmt(displayPrice) : '—'}</p>
            </div>
            <div className={`flex items-center gap-1 text-base font-semibold ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
              {up ? <ArrowUpRight className="size-4" /> : <ArrowDownRight className="size-4" />}
              {up ? '+' : ''}{change.toFixed(2)} ({up ? '+' : ''}{pct}%)
            </div>
          </div>

          {/* Main Grid */}
          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            <div className="flex flex-col gap-4">
              {/* Chart Card */}
              <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-gray-100 pb-3">
                  <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-md">
                    {(['price', 'rsi', 'macd'] as const).map(tab => (
                      <button key={tab} onClick={() => setActiveTab(tab)}
                        className={`rounded px-3 py-1 font-mono text-xs font-medium transition-all ${
                          activeTab === tab ? 'bg-white text-gray-900 shadow-sm font-semibold' : 'text-gray-500 hover:text-gray-900'
                        }`}>
                        {tab === 'price' ? 'Candlestick' : tab.toUpperCase()}
                      </button>
                    ))}
                  </div>

                  {activeTab === 'price' && (
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-mono text-[10px] text-gray-400 uppercase tracking-wider mr-1">Indicators:</span>
                      {([
                        ['ema20', 'EMA 20', '#f97316'], ['ema50', 'EMA 50', '#c084fc'],
                        ['bb', 'Bollinger', '#94a3b8'], ['vwap', 'VWAP', '#818cf8'],
                        ['utBot', 'UT Bot', '#e11d48'], ['fvg', 'FVG', '#10b981'],
                        ['volumeProfile', 'Vol Profile', '#6366f1'], ['volume', 'Volume', '#6b7280'],
                      ] as const).map(([k, label, colorHex]) => {
                        const active = showIndicators[k as keyof typeof showIndicators]
                        return (
                          <button key={k} onClick={() => setShowIndicators(s => ({ ...s, [k]: !s[k as keyof typeof s] }))}
                            className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 font-mono text-[10px] transition-all border ${
                              active ? 'bg-gray-900 text-white border-gray-900' : 'bg-gray-50 text-gray-400 border-gray-200 hover:border-gray-300'
                            }`}>
                            <span className="size-1.5 rounded-full" style={{ backgroundColor: active ? colorHex : '#cbd5e1' }} />
                            {label}
                          </button>
                        )
                      })}
                    </div>
                  )}

                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 font-mono text-[10px] text-emerald-600 border border-emerald-200/60 font-semibold">
                      <Activity className="size-3 animate-pulse" /> Live
                    </span>
                  </div>
                </div>

                {loading ? (
                  <div className="flex h-[440px] items-center justify-center">
                    <RefreshCw className="size-6 animate-spin text-gray-300" />
                    <span className="ml-2 font-mono text-xs text-gray-400">Loading candles…</span>
                  </div>
                ) : activeTab === 'price' ? (
                  <TVPriceChart
                    data={candles}
                    showIndicators={showIndicators}
                    fvgZones={showIndicators.fvg ? fvgZones : undefined}
                    volumeProfile={showIndicators.volumeProfile ? volumeProfile : undefined}
                    utBotSignals={showIndicators.utBot ? utBotSignals : undefined}
                  />
                ) : activeTab === 'rsi' ? (
                  <div className="space-y-2">
                    <p className="font-mono text-[10px] text-gray-500 bg-gray-50 p-2 rounded border border-gray-100">
                      RSI (14) — Overbought &gt;70 · Oversold &lt;30
                    </p>
                    <TVRSIChart data={candles} />
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="font-mono text-[10px] text-gray-500 bg-gray-50 p-2 rounded border border-gray-100">
                      MACD (12,26,9) — Blue: MACD · Orange: Signal · Green/Red: Histogram
                    </p>
                    <TVMACDChart data={candles} />
                  </div>
                )}
              </div>

              {/* Agent Pipeline */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Agent Pipeline</p>
                <div className="flex items-center">
                  {AGENTS.map((a, i) => {
                    const active = i === agentStep % AGENTS.length
                    const done = i < agentStep % AGENTS.length
                    return (
                      <div key={a} className="flex flex-1 items-center">
                        <div className={`flex flex-1 flex-col items-center gap-1 rounded-md border px-1 py-2.5 text-center transition-all ${
                          active ? 'border-emerald-400 bg-emerald-50' : done ? 'border-gray-200 bg-gray-50' : 'border-gray-100 bg-white'
                        }`}>
                          {active ? <Cpu className="size-3.5 text-emerald-500 animate-pulse" />
                            : done ? <CheckCircle2 className="size-3.5 text-gray-400" />
                            : <Circle className="size-3.5 text-gray-200" />}
                          <span className={`font-mono text-[9px] uppercase tracking-wide ${active ? 'text-emerald-600 font-semibold' : 'text-gray-400'}`}>{a}</span>
                        </div>
                        {i < AGENTS.length - 1 && <div className={`h-px w-2 shrink-0 ${done || active ? 'bg-emerald-300' : 'bg-gray-200'}`} />}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Order Blotter */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Order Blotter · Live</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-100 font-mono text-[10px] uppercase tracking-wider text-gray-400">
                        {['Order ID', 'Side', 'Qty', 'Price', 'Status', 'Time'].map(h => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {orders.length === 0 && <tr><td colSpan={6} className="py-6 text-center font-mono text-[10px] text-gray-300">Waiting for agent orders…</td></tr>}
                      {orders.map(o => (
                        <tr key={o.id} className="border-b border-gray-50 last:border-0">
                          <td className="py-2 pr-4 font-mono text-gray-400">{o.id}</td>
                          <td className={`py-2 pr-4 font-semibold ${o.side === 'BUY' ? 'text-emerald-600' : 'text-rose-600'}`}>{o.side}</td>
                          <td className="py-2 pr-4 text-gray-700">{o.qty}</td>
                          <td className="py-2 pr-4 font-mono text-gray-700">{fmt(o.price)}</td>
                          <td className="py-2 pr-4">
                            <span className={`rounded px-1.5 py-0.5 font-mono text-[10px] ${
                              o.status === 'FILLED' ? 'bg-emerald-50 text-emerald-600' :
                              o.status === 'PENDING' ? 'bg-amber-50 text-amber-600' : 'bg-rose-50 text-rose-600'
                            }`}>{o.status}</span>
                          </td>
                          <td className="py-2 font-mono text-gray-400">{o.ts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            {/* Right Column */}
            <div className="flex flex-col gap-4">
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bot className="size-4 text-gray-400" />
                    <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">Groq AI Suggestion</p>
                  </div>
                  <span className="font-mono text-[9px] text-gray-300">Every 30s</span>
                </div>
                <SuggestionCard s={suggestion} onRefresh={() => fetchSuggestion(candles)} />
              </div>

              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Open Positions</p>
                <div className="flex flex-col gap-2">
                  {positions.map(p => {
                    const pnl = (p.current - p.entry) * p.qty
                    const pnlPct = (((p.current - p.entry) / p.entry) * 100).toFixed(2)
                    const pos = pnl >= 0
                    return (
                      <div key={p.symbol} className="rounded-md border border-gray-100 p-3">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-xs font-semibold">{p.symbol}</span>
                          <span className={`flex items-center gap-1 font-mono text-xs font-semibold ${pos ? 'text-emerald-600' : 'text-rose-600'}`}>
                            {pos ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
                            {pos ? '+' : ''}₹{fmt(Math.abs(pnl))}
                          </span>
                        </div>
                        <div className="mt-2 grid grid-cols-3 gap-1 text-[10px]">
                          {[['Entry', fmt(p.entry), ''], ['Now', fmt(p.current), pos ? 'text-emerald-600' : 'text-rose-600'], ['P&L%', `${pos ? '+' : ''}${pnlPct}%`, pos ? 'text-emerald-600' : 'text-rose-600']].map(([l, v, c]) => (
                            <div key={l}><p className="text-gray-400">{l}</p><p className={`font-mono font-medium ${c}`}>{v}</p></div>
                          ))}
                        </div>
                        <div className="mt-2 h-1 w-full rounded-full bg-gray-100">
                          <div className={`h-1 rounded-full transition-all ${pos ? 'bg-emerald-400' : 'bg-rose-400'}`} style={{ width: `${Math.min(100, Math.abs(parseFloat(pnlPct)) * 10)}%` }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">Agent Activity</p>
                  <span className="font-mono text-[10px] text-gray-300">{logs.length} events</span>
                </div>
                <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto pr-1">
                  {logs.length === 0 && <p className="py-4 text-center font-mono text-[10px] text-gray-300">Agents initialising…</p>}
                  {logs.map(l => (
                    <div key={l.id} className="flex gap-2 rounded px-2 py-1 hover:bg-gray-50">
                      <span className={`mt-1 size-1.5 shrink-0 rounded-full ${l.tone === 'green' ? 'bg-emerald-400' : l.tone === 'amber' ? 'bg-amber-400' : l.tone === 'red' ? 'bg-rose-400' : 'bg-blue-400'}`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[10px] font-semibold text-gray-700">{l.agent}</span>
                          <span className="font-mono text-[9px] text-gray-300">{l.ts}</span>
                        </div>
                        <p className="text-[11px] text-gray-500">{l.msg}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Risk Summary</p>
                <div className="grid grid-cols-2 gap-2">
                  {[['Daily P&L', '+₹3,240', 'text-emerald-600'], ['Exposure', '44.8%', 'text-amber-600'], ['VaR (1d)', '1.8%', 'text-emerald-600'], ['Status', 'ACTIVE', 'text-emerald-600']].map(([l, v, c]) => (
                    <div key={l} className="rounded-md border border-gray-100 p-2">
                      <p className="font-mono text-[9px] text-gray-400">{l}</p>
                      <p className={`mt-0.5 font-mono text-sm font-semibold ${c}`}>{v}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-gray-100 pt-4 font-mono text-[10px] uppercase tracking-wider text-gray-300">
            <span className="flex items-center gap-2"><span className="size-1.5 rounded-full bg-emerald-400" /> All feeds connected</span>
            <span>Paper trading · No real capital at risk</span>
            <span suppressHydrationWarning className="flex items-center gap-1"><Clock className="size-3" /> {nowT()}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
