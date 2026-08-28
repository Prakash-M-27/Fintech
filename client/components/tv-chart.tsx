'use client'

import { useEffect, useRef, useState } from 'react'
import {
  createChart,
  AreaSeries,
  LineSeries,
  HistogramSeries,
  CandlestickSeries,
  ColorType,
  LineStyle,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts'
import { type OHLC, type FVGZone, type VolumeProfileBar } from '@/lib/indicators'

const fmt = (n: number) => n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function parseTimeToSeconds(timeStr: string | number, fallbackIndex: number): number {
  if (typeof timeStr === 'number') {
    return timeStr > 2000000000 ? Math.floor(timeStr / 1000) : timeStr
  }
  if (!timeStr) return Math.floor(Date.now() / 1000) - (600 - fallbackIndex * 10)

  if (/^\d{2}:\d{2}:\d{2}$/.test(timeStr)) {
    const today = new Date()
    const [h, m, s] = timeStr.split(':').map(Number)
    today.setHours(h, m, s, 0)
    return Math.floor(today.getTime() / 1000)
  }

  const parsed = Date.parse(timeStr)
  if (!isNaN(parsed)) return Math.floor(parsed / 1000)

  return Math.floor(Date.now() / 1000) - (600 - fallbackIndex * 10)
}

function ensureStrictTime<T extends { time: string | number }>(data: T[]): (T & { time: number })[] {
  const result: (T & { time: number })[] = []
  let lastTime = 0
  data.forEach((item, index) => {
    let t = parseTimeToSeconds(item.time, index)
    if (t <= lastTime) t = lastTime + 1
    lastTime = t
    result.push({ ...item, time: t })
  })
  return result
}

const LIGHT_THEME = {
  layout: {
    background: { type: ColorType.Solid, color: '#ffffff' } as const,
    textColor: '#6b7280',
    fontSize: 11,
    fontFamily: 'monospace',
  },
  grid: {
    vertLines: { color: 'rgba(0, 0, 0, 0.04)', style: LineStyle.Solid },
    horzLines: { color: 'rgba(0, 0, 0, 0.04)', style: LineStyle.Solid },
  },
  rightPriceScale: { borderVisible: true, borderColor: 'rgba(0, 0, 0, 0.08)' },
  timeScale: { borderVisible: true, borderColor: 'rgba(0, 0, 0, 0.08)', timeVisible: true, secondsVisible: true },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: '#6366f1', style: LineStyle.Dashed, labelBackgroundColor: '#6366f1' },
    horzLine: { color: '#6366f1', style: LineStyle.Dashed, labelBackgroundColor: '#6366f1' },
  },
}

type ShowIndicators = {
  ema20: boolean; ema50: boolean; bb: boolean; vwap: boolean
  utBot: boolean; fvg: boolean; volumeProfile: boolean; volume: boolean
}

export function TVPriceChart({
  data,
  showIndicators,
  fvgZones,
  volumeProfile,
  utBotSignals,
}: {
  data: OHLC[]
  showIndicators: ShowIndicators
  fvgZones?: FVGZone[]
  volumeProfile?: VolumeProfileBar[]
  utBotSignals?: { buy: { time: string; price: number }[]; sell: { time: string; price: number }[] }
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [legend, setLegend] = useState<{ open: number; high: number; low: number; close: number; vol: number; change: number; isUp: boolean } | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const formatted = ensureStrictTime(data)
    const latestItem = formatted[formatted.length - 1]
    const initClose = latestItem.close
    const initOpen = latestItem.open || (formatted.length > 1 ? (formatted[formatted.length - 2].close) : initClose - 5)
    const initHigh = latestItem.high || Math.max(initOpen, initClose) + 4
    const initLow = latestItem.low || Math.min(initOpen, initClose) - 4

    setLegend({
      open: initOpen, high: initHigh, low: initLow, close: initClose,
      vol: latestItem.volume || 50,
      change: +(initClose - initOpen).toFixed(2),
      isUp: initClose >= initOpen,
    })

    const chart = createChart(containerRef.current, { ...LIGHT_THEME, autoSize: true, height: 440 })

    chartRef.current = chart

    // Volume Histogram
    if (showIndicators.volume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: 'volume',
        priceFormat: { type: 'volume' },
      })
      chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } })
      volumeSeries.setData(
        formatted.map(d => ({
          time: d.time as Time,
          value: d.volume || 0,
          color: d.close >= d.open ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
        }))
      )
    }

    // Candlestick
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    })
    candleSeries.setData(
      formatted.map(d => ({
        time: d.time as Time,
        open: d.open, high: d.high, low: d.low, close: d.close,
      }))
    )

    // VWAP
    if (showIndicators.vwap) {
      const closes = formatted.map(d => d.close)
      const cumPV = closes.reduce((acc, c, i) => { acc.push((acc[i - 1] || 0) + c * (formatted[i].volume || 1)); return acc }, [] as number[])
      const cumV = formatted.reduce((acc, d, i) => { acc.push((acc[i - 1] || 0) + (d.volume || 1)); return acc }, [] as number[])
      const vwap = cumPV.map((p, i) => +(p / (cumV[i] || 1)).toFixed(2))
      const vwapSeries = chart.addSeries(LineSeries, { color: '#818cf8', lineWidth: 2, lineStyle: LineStyle.Dashed })
      vwapSeries.setData(formatted.map((d, i) => ({ time: d.time as Time, value: vwap[i] })))
    }

    // EMA20
    if (showIndicators.ema20) {
      const k = 2 / 21
      let ema = formatted[0].close
      const ema20 = formatted.map((d, i) => { ema = i === 0 ? d.close : d.close * k + ema * (1 - k); return +ema.toFixed(2) })
      const s = chart.addSeries(LineSeries, { color: '#f97316', lineWidth: 2 })
      s.setData(formatted.map((d, i) => ({ time: d.time as Time, value: ema20[i] })))
    }

    // EMA50
    if (showIndicators.ema50) {
      const k = 2 / 51
      let ema = formatted[0].close
      const ema50 = formatted.map((d, i) => { ema = i === 0 ? d.close : d.close * k + ema * (1 - k); return +ema.toFixed(2) })
      const s = chart.addSeries(LineSeries, { color: '#c084fc', lineWidth: 2 })
      s.setData(formatted.map((d, i) => ({ time: d.time as Time, value: ema50[i] })))
    }

    // Bollinger Bands
    if (showIndicators.bb) {
      const period = 20
      const upper: number[] = [], lower: number[] = []
      for (let i = 0; i < formatted.length; i++) {
        if (i < period - 1) { upper.push(formatted[i].close); lower.push(formatted[i].close); continue }
        const slice = formatted.slice(i - period + 1, i + 1).map(d => d.close)
        const mean = slice.reduce((a, b) => a + b, 0) / period
        const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
        upper.push(+(mean + 2 * std).toFixed(2))
        lower.push(+(mean - 2 * std).toFixed(2))
      }
      const upperS = chart.addSeries(LineSeries, { color: '#94a3b8', lineWidth: 1, lineStyle: LineStyle.Dotted })
      upperS.setData(formatted.map((d, i) => ({ time: d.time as Time, value: upper[i] })))
      const lowerS = chart.addSeries(LineSeries, { color: '#94a3b8', lineWidth: 1, lineStyle: LineStyle.Dotted })
      lowerS.setData(formatted.map((d, i) => ({ time: d.time as Time, value: lower[i] })))
    }

    // FVG Zones
    if (showIndicators.fvg && fvgZones?.length) {
      for (const zone of fvgZones) {
        const startTime = parseTimeToSeconds(zone.time, 0) as Time
        const endTime = parseTimeToSeconds(zone.timeEnd, 0) as Time
        const isBullish = zone.direction === 'bullish'
        const series = chart.addSeries(LineSeries, {
          color: isBullish ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)',
          lineWidth: 2,
          lineStyle: LineStyle.LargeDashed,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        series.setData([
          { time: startTime, value: zone.high },
          { time: endTime, value: zone.high },
        ])
        const series2 = chart.addSeries(LineSeries, {
          color: isBullish ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)',
          lineWidth: 2,
          lineStyle: LineStyle.LargeDashed,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        series2.setData([
          { time: startTime, value: zone.low },
          { time: endTime, value: zone.low },
        ])
      }
    }

    // UT Bot Alerts
    if (showIndicators.utBot && utBotSignals) {
      if (utBotSignals.buy.length) {
        const markerSeries = chart.addSeries(LineSeries, {
          color: 'transparent',
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const buys = utBotSignals.buy.map(s => {
          const t = parseTimeToSeconds(s.time, 0)
          return { time: t as Time, value: s.price }
        }).filter((v, i, a) => i === 0 || (a[i].time as number) > (a[i - 1].time as number))
        if (buys.length) markerSeries.setData(buys)
      }
      if (utBotSignals.sell.length) {
        const markerSeries = chart.addSeries(LineSeries, {
          color: 'transparent',
          priceLineVisible: false,
          lastValueVisible: false,
        })
        const sells = utBotSignals.sell.map(s => {
          const t = parseTimeToSeconds(s.time, 0)
          return { time: t as Time, value: s.price }
        }).filter((v, i, a) => i === 0 || (a[i].time as number) > (a[i - 1].time as number))
        if (sells.length) markerSeries.setData(sells)
      }
    }

    chart.timeScale().fitContent()

    chart.subscribeCrosshairMove(param => {
      if (param.time && param.seriesData.get(candleSeries)) {
        const d = param.seriesData.get(candleSeries) as any
        if (d) {
          const idx = formatted.findIndex(item => (item.time as any) === param.time)
          setLegend({
            open: d.open, high: d.high, low: d.low, close: d.close,
            vol: idx !== -1 ? formatted[idx].volume : 50,
            change: +(d.close - d.open).toFixed(2),
            isUp: d.close >= d.open,
          })
        }
      }
    })

    return () => { chart.remove() }
  }, [data, showIndicators, fvgZones, utBotSignals])

  return (
    <div className="relative w-full rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
      {legend && (
        <div className="absolute top-2 left-3 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] bg-white/90 px-3 py-1.5 rounded border border-gray-200 backdrop-blur pointer-events-none">
          <span className="text-gray-500">O <strong className="text-gray-900">{fmt(legend.open)}</strong></span>
          <span className="text-gray-500">H <strong className="text-emerald-600">{fmt(legend.high)}</strong></span>
          <span className="text-gray-500">L <strong className="text-rose-600">{fmt(legend.low)}</strong></span>
          <span className="text-gray-500">C <strong className={legend.isUp ? 'text-emerald-600' : 'text-rose-600'}>{fmt(legend.close)}</strong></span>
          <span className={legend.isUp ? 'text-emerald-600 font-semibold' : 'text-rose-600 font-semibold'}>
            {legend.isUp ? '+' : ''}{legend.change}
          </span>
          <span className="text-gray-500 border-l border-gray-200 pl-3">Vol <strong className="text-gray-700">{legend.vol}</strong></span>
        </div>
      )}
      <div ref={containerRef} className="h-[440px] w-full" />
    </div>
  )
}

export function TVOverviewChart({ data }: { data: OHLC[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return
    const formatted = ensureStrictTime(data)
    const chart = createChart(containerRef.current, { ...LIGHT_THEME, autoSize: true, height: 300 })
    chartRef.current = chart

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444', borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#ef4444',
    })
    candleSeries.setData(formatted.map(d => ({ time: d.time as Time, open: d.open, high: d.high, low: d.low, close: d.close })))

    chart.timeScale().fitContent()
    return () => { chart.remove() }
  }, [data])

  return <div ref={containerRef} className="h-[300px] w-full rounded-md border border-gray-200 overflow-hidden" />
}

export function TVRSIChart({ data }: { data: OHLC[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return
    const formatted = ensureStrictTime(data)
    const chart = createChart(containerRef.current, { ...LIGHT_THEME, autoSize: true, height: 180 })
    chartRef.current = chart

    const closes = formatted.map(d => d.close)
    const period = 14
    const rsiData: number[] = new Array(period).fill(50)
    let gains = 0, losses = 0
    for (let i = 1; i <= period; i++) { const d = closes[i] - closes[i - 1]; if (d >= 0) gains += d; else losses -= d }
    let avgG = gains / period, avgL = losses / period
    for (let i = period; i < closes.length; i++) {
      const d = closes[i] - closes[i - 1]
      avgG = (avgG * (period - 1) + Math.max(d, 0)) / period
      avgL = (avgL * (period - 1) + Math.max(-d, 0)) / period
      rsiData.push(+(100 - 100 / (1 + (avgL === 0 ? 100 : avgG / avgL))).toFixed(2))
    }

    const rsiSeries = chart.addSeries(LineSeries, { color: '#a855f7', lineWidth: 2 })
    rsiSeries.setData(formatted.map((d, i) => ({ time: d.time as Time, value: rsiData[i] })))

    const ob = chart.addSeries(LineSeries, { color: '#ef4444', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    ob.setData(formatted.map(d => ({ time: d.time as Time, value: 70 })))
    const os = chart.addSeries(LineSeries, { color: '#10b981', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    os.setData(formatted.map(d => ({ time: d.time as Time, value: 30 })))

    chart.timeScale().fitContent()
    return () => { chart.remove() }
  }, [data])

  return <div ref={containerRef} className="h-[180px] w-full rounded-lg border border-gray-200 bg-white overflow-hidden" />
}

export function TVMACDChart({ data }: { data: OHLC[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return
    const formatted = ensureStrictTime(data)
    const chart = createChart(containerRef.current, { ...LIGHT_THEME, autoSize: true, height: 180 })
    chartRef.current = chart

    const closes = formatted.map(d => d.close)
    const k12 = 2 / 13, k26 = 2 / 27
    let ema12 = closes[0], ema26 = closes[0]
    const macdLine: number[] = []
    for (let i = 0; i < closes.length; i++) {
      ema12 = i === 0 ? closes[0] : closes[i] * k12 + ema12 * (1 - k12)
      ema26 = i === 0 ? closes[0] : closes[i] * k26 + ema26 * (1 - k26)
      macdLine.push(+(ema12 - ema26).toFixed(2))
    }
    const k9 = 2 / 10
    let sig = macdLine[0]
    const signalLine = macdLine.map((v, i) => { sig = i === 0 ? v : v * k9 + sig * (1 - k9); return +sig.toFixed(2) })
    const hist = macdLine.map((v, i) => +(v - signalLine[i]).toFixed(2))

    const histSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } })
    histSeries.setData(formatted.map((d, i) => ({
      time: d.time as Time, value: hist[i],
      color: hist[i] >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)',
    })))

    const macdS = chart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 2 })
    macdS.setData(formatted.map((d, i) => ({ time: d.time as Time, value: macdLine[i] })))

    const sigS = chart.addSeries(LineSeries, { color: '#f97316', lineWidth: 2 })
    sigS.setData(formatted.map((d, i) => ({ time: d.time as Time, value: signalLine[i] })))

    chart.timeScale().fitContent()
    return () => { chart.remove() }
  }, [data])

  return <div ref={containerRef} className="h-[180px] w-full rounded-lg border border-gray-200 bg-white overflow-hidden" />
}

export function TVVolumeProfileChart({ profile }: { profile: VolumeProfileBar[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !profile.length) return
    const chart = createChart(containerRef.current, { ...LIGHT_THEME, autoSize: true, height: 440 })
    chartRef.current = chart

    const maxVol = Math.max(...profile.map(p => p.volume))
    const histSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'right',
      priceFormat: { type: 'price', precision: 2 },
    })
    histSeries.setData(profile.map(p => ({
      time: p.price as unknown as Time,
      value: p.volume,
      color: p.volume > maxVol * 0.7 ? 'rgba(99, 102, 241, 0.5)' : 'rgba(99, 102, 241, 0.25)',
    })))

    chart.timeScale().fitContent()
    return () => { chart.remove() }
  }, [profile])

  return <div ref={containerRef} className="h-[440px] w-full rounded-lg border border-gray-200 bg-white overflow-hidden" />
}
