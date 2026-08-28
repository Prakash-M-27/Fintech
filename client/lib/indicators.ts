export type OHLC = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export function calcEMA(data: number[], period: number): number[] {
  const k = 2 / (period + 1)
  const result: number[] = []
  let ema = data[0]
  for (let i = 0; i < data.length; i++) {
    ema = i === 0 ? data[0] : data[i] * k + ema * (1 - k)
    result.push(+ema.toFixed(2))
  }
  return result
}

export function calcRSI(data: number[], period = 14): number[] {
  const result: number[] = new Array(period).fill(50)
  let gains = 0, losses = 0
  for (let i = 1; i <= period; i++) {
    const d = data[i] - data[i - 1]
    if (d >= 0) gains += d; else losses -= d
  }
  let avgGain = gains / period
  let avgLoss = losses / period
  for (let i = period; i < data.length; i++) {
    const d = data[i] - data[i - 1]
    avgGain = (avgGain * (period - 1) + Math.max(d, 0)) / period
    avgLoss = (avgLoss * (period - 1) + Math.max(-d, 0)) / period
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
    result.push(+(100 - 100 / (1 + rs)).toFixed(2))
  }
  return result
}

export function calcMACD(data: number[]): { macd: number[]; signal: number[]; hist: number[] } {
  const ema12 = calcEMA(data, 12)
  const ema26 = calcEMA(data, 26)
  const macd  = ema12.map((v, i) => +(v - ema26[i]).toFixed(2))
  const signal = calcEMA(macd, 9)
  const hist   = macd.map((v, i) => +(v - signal[i]).toFixed(2))
  return { macd, signal, hist }
}

export function calcBollinger(data: number[], period = 20, mult = 2) {
  const upper: number[] = [], lower: number[] = [], mid: number[] = []
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) { upper.push(data[i]); lower.push(data[i]); mid.push(data[i]); continue }
    const slice = data.slice(i - period + 1, i + 1)
    const mean  = slice.reduce((a, b) => a + b, 0) / period
    const std   = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period)
    mid.push(+mean.toFixed(2))
    upper.push(+(mean + mult * std).toFixed(2))
    lower.push(+(mean - mult * std).toFixed(2))
  }
  return { upper, lower, mid }
}

export function calcATR(candles: OHLC[], period = 14): number[] {
  const tr: number[] = []
  for (let i = 0; i < candles.length; i++) {
    if (i === 0) {
      tr.push(candles[i].high - candles[i].low)
      continue
    }
    const prev = candles[i - 1].close
    const curr = candles[i]
    tr.push(Math.max(curr.high - curr.low, Math.abs(curr.high - prev), Math.abs(curr.low - prev)))
  }
  const atr: number[] = []
  let sum = 0
  for (let i = 0; i < tr.length; i++) {
    if (i < period) {
      sum += tr[i]
      atr.push(i === period - 1 ? +(sum / period).toFixed(4) : 0)
      continue
    }
    const prev = atr[i - 1]
    atr.push(+((prev * (period - 1) + tr[i]) / period).toFixed(4))
  }
  return atr
}

export function calcUTBotAlerts(
  candles: OHLC[],
  keyLength = 10,
  atrPeriod = 1,
): { buy: { time: string; price: number }[]; sell: { time: string; price: number }[] } {
  const closes = candles.map(c => c.close)
  const atr = calcATR(candles, atrPeriod)
  const buy: { time: string; price: number }[] = []
  const sell: { time: string; price: number }[] = []
  let stop = 0
  let dir = 0

  for (let i = keyLength; i < candles.length; i++) {
    const highest = Math.max(...candles.slice(i - keyLength, i).map(c => c.high))
    const lowest = Math.min(...candles.slice(i - keyLength, i).map(c => c.low))
    const atrVal = atr[i] || atr[i - 1] || 1

    if (closes[i] > highest) {
      stop = closes[i] - atrVal * 2
      if (dir !== 1) {
        buy.push({ time: candles[i].time, price: candles[i].low - atrVal * 0.5 })
        dir = 1
      }
    } else if (closes[i] < lowest) {
      stop = closes[i] + atrVal * 2
      if (dir !== -1) {
        sell.push({ time: candles[i].time, price: candles[i].high + atrVal * 0.5 })
        dir = -1
      }
    }
    if (dir === 1 && closes[i] < stop) {
      stop = closes[i] + atrVal * 2
      sell.push({ time: candles[i].time, price: candles[i].high + atrVal * 0.5 })
      dir = -1
    } else if (dir === -1 && closes[i] > stop) {
      stop = closes[i] - atrVal * 2
      buy.push({ time: candles[i].time, price: candles[i].low - atrVal * 0.5 })
      dir = 1
    }
  }

  return { buy, sell }
}

export type FVGZone = {
  time: string
  timeEnd: string
  high: number
  low: number
  direction: 'bullish' | 'bearish'
}

export function calcFairValueGap(candles: OHLC[]): FVGZone[] {
  const zones: FVGZone[] = []
  for (let i = 2; i < candles.length; i++) {
    const a = candles[i - 2]
    const b = candles[i - 1]
    const c = candles[i]
    if (a.high < c.low && b.close > b.open) {
      zones.push({
        time: a.time,
        timeEnd: c.time,
        high: c.low,
        low: a.high,
        direction: 'bullish',
      })
    }
    if (a.low > c.high && b.close < b.open) {
      zones.push({
        time: a.time,
        timeEnd: c.time,
        high: a.low,
        low: c.high,
        direction: 'bearish',
      })
    }
  }
  return zones
}

export type VolumeProfileBar = {
  price: number
  volume: number
  high: number
  low: number
}

export function calcVolumeProfile(candles: OHLC[], bins = 24): VolumeProfileBar[] {
  if (!candles.length) return []
  const allPrices = candles.flatMap(c => [c.high, c.low])
  const minP = Math.min(...allPrices)
  const maxP = Math.max(...allPrices)
  const range = maxP - minP || 1
  const step = range / bins
  const profile: VolumeProfileBar[] = []

  for (let i = 0; i < bins; i++) {
    const levelLow = minP + i * step
    const levelHigh = levelLow + step
    let vol = 0
    for (const c of candles) {
      if (c.high >= levelLow && c.low <= levelHigh) {
        const overlap = (Math.min(c.high, levelHigh) - Math.max(c.low, levelLow)) / (c.high - c.low || 1)
        vol += Math.round(c.volume * overlap)
      }
    }
    profile.push({ price: +(levelLow + step / 2).toFixed(2), volume: vol, high: levelHigh, low: levelLow })
  }
  return profile
}
