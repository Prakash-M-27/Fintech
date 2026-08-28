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
