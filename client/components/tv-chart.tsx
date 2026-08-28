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
} from 'lightweight-charts'

export type Candle = {
  time: string
  value: number
  open?: number
  high?: number
  low?: number
  close?: number
  vwap: number
  vol: number
  ema20: number
  ema50: number
  bbUpper: number
  bbLower: number
  bbMid: number
  rsi: number
  macd: number
  macdSignal: number
  macdHist: number
}

// Format numbers nicely with commas and 2 decimals
const fmt = (n: number) => n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Convert "HH:mm:ss" or ISO string or timestamp to UNIX seconds (UTCTimestamp)
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

// Ensure timestamps are strictly increasing (required by lightweight-charts)
function ensureStrictTime<T extends { time: string | number }>(data: T[]): (T & { time: number })[] {
  const result: (T & { time: number })[] = []
  let lastTime = 0

  data.forEach((item, index) => {
    let t = parseTimeToSeconds(item.time, index)
    if (t <= lastTime) {
      t = lastTime + 1
    }
    lastTime = t
    result.push({ ...item, time: t })
  })

  return result
}

// ── Overview Chart (Japanese Candlestick + VWAP) ────────────────────────────
export function TVOverviewChart({ data }: { data: { time: string; value: number; open?: number; high?: number; low?: number; close?: number; vwap?: number }[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
      },
      rightPriceScale: {
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      timeScale: {
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6366f1', style: LineStyle.Dashed },
        horzLine: { color: '#6366f1', style: LineStyle.Dashed },
      },
      handleScale: true,
      handleScroll: true,
    })

    chartRef.current = chart

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    })

    const vwapSeries = chart.addSeries(LineSeries, {
      color: '#6366f1',
      lineWidth: 1.5,
      lineStyle: LineStyle.Dashed,
    })

    const formatted = ensureStrictTime(data)
    candleSeries.setData(
      formatted.map((d, i) => {
        const close = d.close ?? d.value
        const open = d.open ?? (i > 0 ? (formatted[i - 1].close ?? formatted[i - 1].value) : close - 3)
        const high = d.high ?? Math.max(open, close) + (Math.abs(Math.sin(i)) * 5 + 1)
        const low = d.low ?? Math.min(open, close) - (Math.abs(Math.cos(i)) * 5 + 1)
        return {
          time: d.time as any,
          open,
          high,
          low,
          close,
        }
      })
    )

    const vwapData = formatted.filter(d => d.vwap != null).map(d => ({ time: d.time as any, value: d.vwap! }))
    if (vwapData.length > 0) {
      vwapSeries.setData(vwapData)
    }

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }

    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="h-full w-full rounded-md border border-slate-800 overflow-hidden" />
}

// ── Main Price Chart (Japanese Candlesticks + Volume + Live Legend) ──────────
export function TVPriceChart({
  data,
  showIndicators,
}: {
  data: Candle[]
  showIndicators: { ema20: boolean; ema50: boolean; bb: boolean; vwap: boolean }
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const [legend, setLegend] = useState<{ open: number; high: number; low: number; close: number; vol: number; change: number; isUp: boolean } | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const formatted = ensureStrictTime(data)
    const latestItem = formatted[formatted.length - 1]
    const initClose = latestItem.close ?? latestItem.value
    const initOpen = latestItem.open ?? (formatted.length > 1 ? (formatted[formatted.length - 2].close ?? formatted[formatted.length - 2].value) : initClose - 5)
    const initHigh = latestItem.high ?? Math.max(initOpen, initClose) + 4
    const initLow = latestItem.low ?? Math.min(initOpen, initClose) - 4
    
    setLegend({
      open: initOpen,
      high: initHigh,
      low: initLow,
      close: initClose,
      vol: latestItem.vol || 50,
      change: +(initClose - initOpen).toFixed(2),
      isUp: initClose >= initOpen,
    })

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 11,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
      },
      rightPriceScale: {
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      timeScale: {
        borderVisible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
        timeVisible: true,
        secondsVisible: true,
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6366f1', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#4f46e5' },
        horzLine: { color: '#6366f1', width: 1, style: LineStyle.Dashed, labelBackgroundColor: '#4f46e5' },
      },
    })

    chartRef.current = chart

    // Volume Histogram Series (scaled to bottom 22% of chart canvas)
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
    })
    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    })
    volumeSeries.setData(
      formatted.map((d, i) => {
        const close = d.close ?? d.value
        const open = d.open ?? (i > 0 ? (formatted[i - 1].close ?? formatted[i - 1].value) : close - 5)
        return {
          time: d.time as any,
          value: d.vol || 50,
          color: close >= open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(244, 63, 94, 0.35)',
        }
      })
    )

    // Japanese Candlestick Series
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
    })
    const candleData = formatted.map((d, i) => {
      const close = d.close ?? d.value
      const open = d.open ?? (i > 0 ? (formatted[i - 1].close ?? formatted[i - 1].value) : close - 5)
      const high = d.high ?? Math.max(open, close) + (Math.abs(Math.sin(i * 0.7)) * 8 + 2)
      const low = d.low ?? Math.min(open, close) - (Math.abs(Math.cos(i * 0.7)) * 8 + 2)
      return {
        time: d.time as any,
        open: +open.toFixed(2),
        high: +high.toFixed(2),
        low: +low.toFixed(2),
        close: +close.toFixed(2),
      }
    })
    candleSeries.setData(candleData)

    // VWAP Overlay
    if (showIndicators.vwap) {
      const vwapSeries = chart.addSeries(LineSeries, {
        color: '#818cf8',
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
      })
      vwapSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.vwap })))
    }

    // EMA20 Overlay
    if (showIndicators.ema20) {
      const ema20Series = chart.addSeries(LineSeries, {
        color: '#f97316',
        lineWidth: 1.5,
      })
      ema20Series.setData(formatted.map(d => ({ time: d.time as any, value: d.ema20 })))
    }

    // EMA50 Overlay
    if (showIndicators.ema50) {
      const ema50Series = chart.addSeries(LineSeries, {
        color: '#c084fc',
        lineWidth: 1.5,
      })
      ema50Series.setData(formatted.map(d => ({ time: d.time as any, value: d.ema50 })))
    }

    // Bollinger Bands Overlay
    if (showIndicators.bb) {
      const bbUpperSeries = chart.addSeries(LineSeries, {
        color: '#94a3b8',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
      })
      bbUpperSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.bbUpper })))

      const bbLowerSeries = chart.addSeries(LineSeries, {
        color: '#94a3b8',
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
      })
      bbLowerSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.bbLower })))
    }

    // Crosshair hover listener for live legend header
    chart.subscribeCrosshairMove(param => {
      if (param.time && param.seriesData.get(candleSeries)) {
        const dataPoint = param.seriesData.get(candleSeries) as any
        if (dataPoint) {
          const idx = formatted.findIndex(item => (item.time as any) === param.time)
          const volVal = idx !== -1 ? formatted[idx].vol : 50
          const changeVal = +(dataPoint.close - dataPoint.open).toFixed(2)
          setLegend({
            open: dataPoint.open,
            high: dataPoint.high,
            low: dataPoint.low,
            close: dataPoint.close,
            vol: volVal,
            change: changeVal,
            isUp: dataPoint.close >= dataPoint.open,
          })
        }
      }
    })

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }

    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data, showIndicators])

  return (
    <div className="relative w-full rounded-lg border border-slate-800 bg-[#090d16] overflow-hidden shadow-2xl">
      {/* TradingView Legend Overlay */}
      {legend && (
        <div className="absolute top-2 left-3 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] bg-slate-950/80 px-3 py-1.5 rounded border border-slate-800/80 backdrop-blur pointer-events-none">
          <span className="text-slate-400">O <strong className="text-slate-100">{fmt(legend.open)}</strong></span>
          <span className="text-slate-400">H <strong className="text-emerald-400">{fmt(legend.high)}</strong></span>
          <span className="text-slate-400">L <strong className="text-rose-400">{fmt(legend.low)}</strong></span>
          <span className="text-slate-400">C <strong className={legend.isUp ? 'text-emerald-400' : 'text-rose-400'}>{fmt(legend.close)}</strong></span>
          <span className={legend.isUp ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
            {legend.isUp ? '+' : ''}{legend.change}
          </span>
          <span className="text-slate-400 border-l border-slate-800 pl-3">Vol <strong className="text-slate-200">{legend.vol}K</strong></span>
        </div>
      )}

      {/* Chart Canvas */}
      <div ref={containerRef} className="h-[440px] w-full" />
    </div>
  )
}

// ── RSI Chart ───────────────────────────────────────────────────────────────
export function TVRSIChart({ data }: { data: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
      },
      rightPriceScale: { borderVisible: true, borderColor: 'rgba(255, 255, 255, 0.1)' },
      timeScale: { borderVisible: true, borderColor: 'rgba(255, 255, 255, 0.1)', timeVisible: true, secondsVisible: true },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6366f1', style: LineStyle.Dashed },
        horzLine: { color: '#6366f1', style: LineStyle.Dashed },
      },
    })

    chartRef.current = chart

    const formatted = ensureStrictTime(data)

    const rsiSeries = chart.addSeries(LineSeries, {
      color: '#a855f7',
      lineWidth: 2,
    })
    rsiSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.rsi })))

    // Overbought 70 Line
    const overboughtSeries = chart.addSeries(LineSeries, {
      color: '#f43f5e',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
    })
    overboughtSeries.setData(formatted.map(d => ({ time: d.time as any, value: 70 })))

    // Oversold 30 Line
    const oversoldSeries = chart.addSeries(LineSeries, {
      color: '#10b981',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
    })
    oversoldSeries.setData(formatted.map(d => ({ time: d.time as any, value: 30 })))

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }

    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="h-[180px] w-full rounded-lg border border-slate-800 bg-[#090d16] overflow-hidden" />
}

// ── MACD Chart ──────────────────────────────────────────────────────────────
export function TVMACDChart({ data }: { data: Candle[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || !data.length) return

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: '#090d16' },
        textColor: '#94a3b8',
        fontSize: 10,
        fontFamily: 'monospace',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
        horzLines: { color: 'rgba(255, 255, 255, 0.04)', style: LineStyle.Solid },
      },
      rightPriceScale: { borderVisible: true, borderColor: 'rgba(255, 255, 255, 0.1)' },
      timeScale: { borderVisible: true, borderColor: 'rgba(255, 255, 255, 0.1)', timeVisible: true, secondsVisible: true },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#6366f1', style: LineStyle.Dashed },
        horzLine: { color: '#6366f1', style: LineStyle.Dashed },
      },
    })

    chartRef.current = chart

    const formatted = ensureStrictTime(data)

    // MACD Histogram Series
    const histSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
    })
    histSeries.setData(
      formatted.map(d => ({
        time: d.time as any,
        value: d.macdHist,
        color: d.macdHist >= 0 ? 'rgba(16, 185, 129, 0.8)' : 'rgba(244, 63, 94, 0.8)',
      }))
    )

    // MACD Line
    const macdSeries = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 1.5,
    })
    macdSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.macd })))

    // Signal Line
    const signalSeries = chart.addSeries(LineSeries, {
      color: '#f97316',
      lineWidth: 1.5,
    })
    signalSeries.setData(formatted.map(d => ({ time: d.time as any, value: d.macdSignal })))

    chart.timeScale().fitContent()

    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        })
      }
    }

    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
    }
  }, [data])

  return <div ref={containerRef} className="h-[180px] w-full rounded-lg border border-slate-800 bg-[#090d16] overflow-hidden" />
}
