'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Area, AreaChart, CartesianGrid, ComposedChart, Line,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, Bar,
} from 'recharts'
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight,
  BarChart2, Bell, Bot, CheckCircle2, Circle, Clock,
  Cpu, Crosshair, Database, Gauge, History, Layers3,
  PanelLeft, Settings2, ShieldCheck, TrendingDown, TrendingUp,
  Wallet, Zap, RefreshCw, Target,
} from 'lucide-react'
import { calcEMA, calcRSI, calcMACD, calcBollinger } from '@/lib/indicators'

// ── types ──────────────────────────────────────────────────────────────────
type Candle = {
  time: string; value: number; vwap: number; vol: number
  ema20: number; ema50: number; bbUpper: number; bbLower: number; bbMid: number
  rsi: number; macd: number; macdSignal: number; macdHist: number
}
type Order = { id: string; side: 'BUY' | 'SELL'; qty: number; price: number; status: 'FILLED' | 'PENDING' | 'CANCELLED'; ts: string }
type AgentLog = { id: number; ts: string; agent: string; msg: string; tone: 'green' | 'amber' | 'red' | 'blue' }
type Position = { symbol: string; qty: number; entry: number; current: number }
type AISuggestion = {
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  entry: number
  target: number
  stopLoss: number
  reasoning: string
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  loading?: boolean
}

// ── constants ──────────────────────────────────────────────────────────────
const fmt  = (n: number) => n.toLocaleString('en-IN', { maximumFractionDigits: 2 })
const nowT = () => new Date().toLocaleTimeString('en-IN', { hour12: false })
const rand = (min: number, max: number) => Math.random() * (max - min) + min

const AGENTS  = ['Observer', 'Analyst', 'Risk Engine', 'Allocator', 'Executor']
const SYMBOLS = ['NIFTY 50', 'BANKNIFTY', 'SENSEX', 'GOLD', 'USD/INR']
const BASE: Record<string, number> = {
  'NIFTY 50': 22458, BANKNIFTY: 48210, SENSEX: 73820, GOLD: 72418, 'USD/INR': 83.42,
}

const NAV_LINKS = [
  { label: 'Overview',    path: '/',            Icon: Gauge },
  { label: 'Live Room',   path: '/live',         Icon: Activity },
  { label: 'Markets',     path: '/markets',      Icon: TrendingUp },
  { label: 'Agent Intel', path: '/agent',        Icon: Bot },
  { label: 'Scenarios',   path: '/scenarios',    Icon: Layers3 },
  { label: 'Risk',        path: '/risk',         Icon: ShieldCheck },
  { label: 'Capital',     path: '/capital',      Icon: Wallet },
  { label: 'Positions',   path: '/positions',    Icon: Target },
  { label: 'History',     path: '/history',      Icon: History },
  { label: 'Data',        path: '/data-sources', Icon: Database },
  { label: 'Settings',    path: '/settings',     Icon: Settings2 },
]

const agentMessages: Record<string, string[]> = {
  Observer:      ['Price crossed VWAP', 'Volume spike detected', 'Breadth expanding', 'ATR rising', 'New high formed', 'Support level tested'],
  Analyst:       ['Bullish structure intact', 'RSI entering overbought', 'MACD crossover confirmed', 'BB squeeze detected', 'EMA20 > EMA50 confirmed'],
  'Risk Engine': ['VaR within threshold', 'Exposure limit checked', 'Stop-loss validated', 'Drawdown within bounds', 'Position size approved'],
  Allocator:     ['Capital allocated ₹40,000', 'Opportunity score 81%', 'Risk-adjusted fit: HIGH', 'Reward ratio 2.1R', 'Allocation approved'],
  Executor:      ['Order placed at market', 'Slippage 0.01%', 'Fill confirmed', 'Execution quality: GOOD', 'Order book depth checked'],
}
const tones: AgentLog['tone'][] = ['blue', 'green', 'amber', 'green', 'green']

// ── seed chart with indicators ─────────────────────────────────────────────
function buildCandles(symbol: string): Candle[] {
  const base = BASE[symbol]
  const prices: number[] = []
  const vols:   number[] = []
  let v = base - rand(80, 160)
  for (let i = 59; i >= 0; i--) {
    v += rand(-18, 22)
    prices.push(+v.toFixed(2))
    vols.push(Math.floor(rand(20, 90)))
  }

  const ema20arr = calcEMA(prices, 20)
  const ema50arr = calcEMA(prices, 50)
  const rsiArr   = calcRSI(prices, 14)
  const { macd, signal, hist } = calcMACD(prices)
  const { upper, lower, mid }  = calcBollinger(prices, 20)

  return prices.map((p, i) => {
    const t = new Date(Date.now() - (59 - i) * 10000)
    return {
      time:       t.toLocaleTimeString('en-IN', { hour12: false }),
      value:      p,
      vwap:       +(p - rand(2, 8)).toFixed(2),
      vol:        vols[i],
      ema20:      ema20arr[i],
      ema50:      ema50arr[i],
      bbUpper:    upper[i],
      bbLower:    lower[i],
      bbMid:      mid[i],
      rsi:        rsiArr[i],
      macd:       macd[i],
      macdSignal: signal[i],
      macdHist:   hist[i],
    }
  })
}

// ── chart tooltip ──────────────────────────────────────────────────────────
function ChartTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as Candle
  return (
    <div className="border border-gray-200 bg-white px-3 py-2 text-xs shadow-xl rounded-md">
      <p className="font-mono font-bold text-gray-800 mb-1">{d.time}</p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <span className="text-gray-400">Price</span><span className="font-mono font-semibold text-gray-900">{fmt(d.value)}</span>
        <span className="text-gray-400">VWAP</span><span className="font-mono text-indigo-600">{fmt(d.vwap)}</span>
        <span className="text-gray-400">EMA20</span><span className="font-mono text-orange-500">{fmt(d.ema20)}</span>
        <span className="text-gray-400">EMA50</span><span className="font-mono text-purple-500">{fmt(d.ema50)}</span>
        <span className="text-gray-400">BB Up</span><span className="font-mono text-gray-500">{fmt(d.bbUpper)}</span>
        <span className="text-gray-400">BB Lo</span><span className="font-mono text-gray-500">{fmt(d.bbLower)}</span>
        <span className="text-gray-400">RSI</span><span className={`font-mono font-semibold ${d.rsi > 70 ? 'text-rose-500' : d.rsi < 30 ? 'text-emerald-500' : 'text-gray-700'}`}>{d.rsi}</span>
        <span className="text-gray-400">Vol</span><span className="font-mono text-gray-700">{d.vol}K</span>
      </div>
    </div>
  )
}

// ── navbar ─────────────────────────────────────────────────────────────────
function Navbar({ pulse }: { pulse: boolean }) {
  const [collapsed, setCollapsed] = useState(false)
  const path = '/live'
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
        {NAV_LINKS.map(({ label, path: p, Icon }) => (
          <a key={p} href={p} className={`flex items-center gap-2.5 rounded-md px-2.5 py-2 text-xs font-medium transition-colors ${
            p === path ? 'bg-gray-900 text-white' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-800'
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

// ── RSI panel ─────────────────────────────────────────────────────────────
function RSIPanel({ data }: { data: Candle[] }) {
  return (
    <ResponsiveContainer width="100%" height={80}>
      <ComposedChart data={data} margin={{ top: 2, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="#f5f5f5" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="time" hide />
        <YAxis domain={[0, 100]} tick={{ fontSize: 8, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={24} ticks={[30, 50, 70]} />
        <Tooltip formatter={(v: any) => [v, 'RSI']} contentStyle={{ fontSize: 10 }} />
        <ReferenceLine y={70} stroke="#f43f5e" strokeDasharray="3 3" strokeWidth={1} />
        <ReferenceLine y={30} stroke="#10b981" strokeDasharray="3 3" strokeWidth={1} />
        <Line type="monotone" dataKey="rsi" stroke="#8b5cf6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── MACD panel ────────────────────────────────────────────────────────────
function MACDPanel({ data }: { data: Candle[] }) {
  return (
    <ResponsiveContainer width="100%" height={80}>
      <ComposedChart data={data} margin={{ top: 2, right: 8, bottom: 0, left: 8 }}>
        <CartesianGrid stroke="#f5f5f5" strokeDasharray="2 4" vertical={false} />
        <XAxis dataKey="time" hide />
        <YAxis tick={{ fontSize: 8, fill: '#9ca3af' }} tickLine={false} axisLine={false} width={32} />
        <Tooltip contentStyle={{ fontSize: 10 }} />
        <ReferenceLine y={0} stroke="#e5e7eb" strokeWidth={1} />
        <Bar dataKey="macdHist" fill="#10b981" opacity={0.6} isAnimationActive={false}
          label={false}
          // negative bars red
          // recharts doesn't support per-bar color easily, use a fixed color
        />
        <Line type="monotone" dataKey="macd" stroke="#3b82f6" strokeWidth={1.5} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="macdSignal" stroke="#f97316" strokeWidth={1.5} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

// ── AI suggestion card ────────────────────────────────────────────────────
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
        <span className={`rounded-md border px-3 py-1 font-mono text-sm font-bold ${actionColor}`}>
          {s.action}
        </span>
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

// ── main component ─────────────────────────────────────────────────────────
export default function LiveTradingPage() {
  const [symbol, setSymbol]       = useState('NIFTY 50')
  const [candles, setCandles]     = useState<Candle[]>(() => buildCandles('NIFTY 50'))
  const [orders, setOrders]       = useState<Order[]>([])
  const [logs, setLogs]           = useState<AgentLog[]>([])
  const [positions, setPositions] = useState<Position[]>([
    { symbol: 'NIFTY 50',  qty: 24, entry: 22402, current: 22458 },
    { symbol: 'BANKNIFTY', qty: 4,  entry: 48100, current: 48210 },
    { symbol: 'GOLD',      qty: 2,  entry: 72080, current: 72418 },
  ])
  const [agentStep, setAgentStep]     = useState(0)
  const [pulse, setPulse]             = useState(false)
  const [suggestion, setSuggestion]   = useState<AISuggestion | null>(null)
  const [activeTab, setActiveTab]     = useState<'price'|'rsi'|'macd'>('price')
  const [showIndicators, setShowIndicators] = useState({ ema20: true, ema50: true, bb: true, vwap: true })
  const logId   = useRef(0)
  const orderId = useRef(100)
  const aiTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // symbol change → rebuild candles
  useEffect(() => { setCandles(buildCandles(symbol)) }, [symbol])

  // fetch AI suggestion
  const fetchSuggestion = useCallback(async (c: Candle[]) => {
    const last = c[c.length - 1]
    const prev = c[c.length - 2]
    if (!last || !prev) return
    setSuggestion(s => s ? { ...s, loading: true } : { action: 'HOLD', confidence: 0, entry: 0, target: 0, stopLoss: 0, reasoning: '', riskLevel: 'MEDIUM', trend: 'NEUTRAL', loading: true })
    try {
      const res = await fetch('/api/groq-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol,
          price:   last.value,
          change:  (((last.value - prev.value) / prev.value) * 100).toFixed(2),
          rsi:     last.rsi,
          macd:    last.macd,
          signal:  last.macdSignal,
          ema20:   last.ema20,
          ema50:   last.ema50,
          bbUpper: last.bbUpper,
          bbLower: last.bbLower,
          vwap:    last.vwap,
          volume:  last.vol,
        }),
      })
      const data = await res.json()
      if (!data.error) setSuggestion({ ...data, loading: false })
    } catch { setSuggestion(s => s ? { ...s, loading: false } : null) }
  }, [symbol])

  // price tick every 1.5s
  useEffect(() => {
    const t = setInterval(() => {
      setCandles(prev => {
        const last  = prev[prev.length - 1]
        const delta = rand(-14, 16)
        const newPrices = [...prev.map(c => c.value).slice(0, -1), +(last.value + delta).toFixed(2)]
        const ema20arr  = calcEMA(newPrices, 20)
        const ema50arr  = calcEMA(newPrices, 50)
        const rsiArr    = calcRSI(newPrices, 14)
        const { macd, signal, hist } = calcMACD(newPrices)
        const { upper, lower, mid }  = calcBollinger(newPrices, 20)
        const updated = prev.map((c, i) => ({
          ...c,
          value:      newPrices[i],
          vwap:       +(newPrices[i] - rand(2, 8)).toFixed(2),
          vol:        Math.floor(rand(20, 90)),
          ema20:      ema20arr[i],
          ema50:      ema50arr[i],
          bbUpper:    upper[i],
          bbLower:    lower[i],
          bbMid:      mid[i],
          rsi:        rsiArr[i],
          macd:       macd[i],
          macdSignal: signal[i],
          macdHist:   hist[i],
        }))
        // append new candle every ~10s
        const nowStr = nowT()
        if (nowStr !== last.time) {
          const np = +(last.value + delta).toFixed(2)
          const allP = [...newPrices, np]
          updated.push({
            time: nowStr, value: np,
            vwap: +(np - rand(2,8)).toFixed(2), vol: Math.floor(rand(20,90)),
            ema20: calcEMA(allP,20)[allP.length-1],
            ema50: calcEMA(allP,50)[allP.length-1],
            bbUpper: calcBollinger(allP,20).upper[allP.length-1],
            bbLower: calcBollinger(allP,20).lower[allP.length-1],
            bbMid:   calcBollinger(allP,20).mid[allP.length-1],
            rsi:     calcRSI(allP,14)[allP.length-1],
            macd:    calcMACD(allP).macd[allP.length-1],
            macdSignal: calcMACD(allP).signal[allP.length-1],
            macdHist:   calcMACD(allP).hist[allP.length-1],
          })
          return updated.slice(-60)
        }
        return updated
      })
      setPositions(prev => prev.map(p =>
        p.symbol === symbol ? { ...p, current: +(p.current + rand(-10, 12)).toFixed(2) } : p
      ))
      setPulse(v => !v)
    }, 1500)
    return () => clearInterval(t)
  }, [symbol])

  // AI refresh every 30s
  useEffect(() => {
    fetchSuggestion(candles)
    const t = setInterval(() => fetchSuggestion(candles), 30000)
    return () => clearInterval(t)
  }, [symbol])

  // agent loop every 2.2s
  useEffect(() => {
    const t = setInterval(() => {
      setAgentStep(step => {
        const idx   = step % AGENTS.length
        const agent = AGENTS[idx]
        const msgs  = agentMessages[agent]
        const msg   = msgs[Math.floor(Math.random() * msgs.length)]
        setLogs(prev => [{ id: logId.current++, ts: nowT(), agent, msg, tone: tones[idx] }, ...prev.slice(0, 49)])
        if (agent === 'Executor') {
          setCandles(c => {
            const price = c[c.length - 1]?.value ?? BASE[symbol]
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
  const prev2  = candles[candles.length - 2]
  const change = latest && prev2 ? latest.value - prev2.value : 0
  const pct    = prev2 ? ((change / prev2.value) * 100).toFixed(2) : '0.00'
  const up     = change >= 0

  return (
    <div className="flex min-h-screen bg-white text-gray-900">
      <Navbar pulse={pulse} />

      <div className="flex flex-1 flex-col min-w-0">
        {/* ── topbar ── */}
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
                {symbol} {latest ? fmt(latest.value) : '—'} {up ? '▲' : '▼'} {Math.abs(+pct)}%
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
          {/* symbol tabs */}
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

          {/* price hero */}
          <div className="mb-4 flex flex-wrap items-end gap-5">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">{symbol}</p>
              <p className="mt-0.5 font-mono text-3xl font-bold tracking-tight">{latest ? fmt(latest.value) : '—'}</p>
            </div>
            <div className={`flex items-center gap-1 text-base font-semibold ${up ? 'text-emerald-600' : 'text-rose-600'}`}>
              {up ? <ArrowUpRight className="size-4" /> : <ArrowDownRight className="size-4" />}
              {up ? '+' : ''}{change.toFixed(2)} ({up ? '+' : ''}{pct}%)
            </div>
            <div className="flex flex-wrap gap-5 border-l border-gray-100 pl-5">
              {[
                ['VWAP',  latest ? fmt(latest.vwap)   : '—', 'text-indigo-600'],
                ['EMA20', latest ? fmt(latest.ema20)  : '—', 'text-orange-500'],
                ['EMA50', latest ? fmt(latest.ema50)  : '—', 'text-purple-500'],
                ['RSI',   latest ? String(latest.rsi) : '—', latest && latest.rsi > 70 ? 'text-rose-500' : latest && latest.rsi < 30 ? 'text-emerald-500' : 'text-gray-700'],
                ['Vol',   latest ? `${latest.vol}K`   : '—', 'text-gray-700'],
              ].map(([l, v, c]) => (
                <div key={l}>
                  <p className="font-mono text-[9px] uppercase text-gray-400">{l}</p>
                  <p className={`mt-0.5 font-mono text-sm font-semibold ${c}`}>{v}</p>
                </div>
              ))}
            </div>
          </div>

          {/* main grid */}
          <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
            {/* left */}
            <div className="flex flex-col gap-4">

              {/* chart card */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                {/* chart tabs + indicator toggles */}
                <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex gap-1">
                    {(['price','rsi','macd'] as const).map(tab => (
                      <button key={tab} onClick={() => setActiveTab(tab)}
                        className={`rounded px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider transition-colors ${
                          activeTab === tab ? 'bg-gray-900 text-white' : 'text-gray-400 hover:text-gray-700'
                        }`}>
                        {tab === 'price' ? 'Price' : tab.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  {activeTab === 'price' && (
                    <div className="flex gap-2">
                      {([['ema20','EMA20','text-orange-500'],['ema50','EMA50','text-purple-500'],['bb','BB','text-gray-400'],['vwap','VWAP','text-indigo-500']] as const).map(([k, label, color]) => (
                        <button key={k} onClick={() => setShowIndicators(s => ({ ...s, [k]: !s[k as keyof typeof s] }))}
                          className={`rounded border px-2 py-0.5 font-mono text-[9px] transition-colors ${
                            showIndicators[k as keyof typeof showIndicators] ? `border-current ${color}` : 'border-gray-200 text-gray-300'
                          }`}>
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                  <span className="flex items-center gap-1 font-mono text-[10px] text-emerald-500">
                    <Activity className="size-3" /> Live
                  </span>
                </div>

                {activeTab === 'price' && (
                  <ResponsiveContainer width="100%" height={300}>
                    <ComposedChart data={candles} margin={{ top: 4, right: 8, bottom: 0, left: 8 }}>
                      <defs>
                        <linearGradient id="pg" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#10b981" stopOpacity={0.15} />
                          <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#f5f5f5" strokeDasharray="2 4" vertical={false} />
                      <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#9ca3af' }} tickLine={false} interval="preserveStartEnd" />
                      <YAxis domain={['auto','auto']} tick={{ fontSize: 9, fill: '#9ca3af' }} tickLine={false} axisLine={false} tickFormatter={v => fmt(v)} width={72} />
                      <Tooltip content={<ChartTooltip />} />
                      {showIndicators.bb && <Area type="monotone" dataKey="bbUpper" stroke="#d1d5db" strokeWidth={1} fill="none" dot={false} isAnimationActive={false} strokeDasharray="3 3" />}
                      {showIndicators.bb && <Area type="monotone" dataKey="bbLower" stroke="#d1d5db" strokeWidth={1} fill="none" dot={false} isAnimationActive={false} strokeDasharray="3 3" />}
                      <Area type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} fill="url(#pg)" dot={false} isAnimationActive={false} />
                      {showIndicators.vwap  && <Line type="monotone" dataKey="vwap"  stroke="#6366f1" strokeWidth={1.5} dot={false} isAnimationActive={false} strokeDasharray="4 3" />}
                      {showIndicators.ema20 && <Line type="monotone" dataKey="ema20" stroke="#f97316" strokeWidth={1.5} dot={false} isAnimationActive={false} />}
                      {showIndicators.ema50 && <Line type="monotone" dataKey="ema50" stroke="#a855f7" strokeWidth={1.5} dot={false} isAnimationActive={false} />}
                    </ComposedChart>
                  </ResponsiveContainer>
                )}
                {activeTab === 'rsi'  && <><p className="mb-1 font-mono text-[9px] text-gray-400">RSI (14) — Overbought &gt;70 · Oversold &lt;30</p><RSIPanel  data={candles} /></>}
                {activeTab === 'macd' && <><p className="mb-1 font-mono text-[9px] text-gray-400">MACD (12,26,9) — Blue: MACD · Orange: Signal · Green: Histogram</p><MACDPanel data={candles} /></>}
              </div>

              {/* agent pipeline */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Agent Pipeline</p>
                <div className="flex items-center">
                  {AGENTS.map((a, i) => {
                    const active = i === agentStep % AGENTS.length
                    const done   = i < agentStep % AGENTS.length
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

              {/* order blotter */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Order Blotter · Live</p>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-gray-100 font-mono text-[10px] uppercase tracking-wider text-gray-400">
                        {['Order ID','Side','Qty','Price','Status','Time'].map(h => <th key={h} className="pb-2 pr-4 font-medium">{h}</th>)}
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

            {/* right col */}
            <div className="flex flex-col gap-4">

              {/* AI suggestion */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Bot className="size-4 text-gray-400" />
                    <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">Groq AI Suggestion</p>
                  </div>
                  <span className="font-mono text-[9px] text-gray-300">Updates every 30s</span>
                </div>
                <SuggestionCard s={suggestion} onRefresh={() => fetchSuggestion(candles)} />
              </div>

              {/* positions */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Open Positions</p>
                <div className="flex flex-col gap-2">
                  {positions.map(p => {
                    const pnl    = (p.current - p.entry) * p.qty
                    const pnlPct = (((p.current - p.entry) / p.entry) * 100).toFixed(2)
                    const pos    = pnl >= 0
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
                          {[['Entry', fmt(p.entry), ''], ['Now', fmt(p.current), pos ? 'text-emerald-600' : 'text-rose-600'], ['P&L%', `${pos?'+':''}${pnlPct}%`, pos ? 'text-emerald-600' : 'text-rose-600']].map(([l,v,c]) => (
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

              {/* agent log */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-gray-400">Agent Activity</p>
                  <span className="font-mono text-[10px] text-gray-300">{logs.length} events</span>
                </div>
                <div className="flex max-h-64 flex-col gap-0.5 overflow-y-auto pr-1">
                  {logs.length === 0 && <p className="py-4 text-center font-mono text-[10px] text-gray-300">Agents initialising…</p>}
                  {logs.map(l => (
                    <div key={l.id} className="flex gap-2 rounded px-2 py-1 hover:bg-gray-50">
                      <span className={`mt-1 size-1.5 shrink-0 rounded-full ${l.tone==='green'?'bg-emerald-400':l.tone==='amber'?'bg-amber-400':l.tone==='red'?'bg-rose-400':'bg-blue-400'}`} />
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

              {/* risk */}
              <div className="rounded-lg border border-gray-200 bg-white p-4">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-widest text-gray-400">Risk Summary</p>
                <div className="grid grid-cols-2 gap-2">
                  {[['Daily P&L','+₹3,240','text-emerald-600'],['Exposure','44.8%','text-amber-600'],['VaR (1d)','1.8%','text-emerald-600'],['Status','ACTIVE','text-emerald-600']].map(([l,v,c]) => (
                    <div key={l} className="rounded-md border border-gray-100 p-2">
                      <p className="font-mono text-[9px] text-gray-400">{l}</p>
                      <p className={`mt-0.5 font-mono text-sm font-semibold ${c}`}>{v}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* footer */}
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
