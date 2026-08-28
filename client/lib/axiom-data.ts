export type Asset = { symbol: string; name: string; price: string; change: string; positive: boolean; status: string }

export const assets: Asset[] = [
  { symbol: 'NIFTY 50', name: 'NSE · INDEX', price: '22,458.80', change: '+0.42%', positive: true, status: 'Open' },
  { symbol: 'GOLD', name: 'MCX · FUTURES', price: '₹72,418', change: '+0.18%', positive: true, status: 'Open' },
  { symbol: 'USD/INR', name: 'FOREX · SPOT', price: '83.42', change: '-0.06%', positive: false, status: 'Open' },
]

export const chartData = [
  { time: '09:15', value: 22295, vwap: 22280, ema: 22260, volume: 32 }, { time: '09:45', value: 22340, vwap: 22305, ema: 22290, volume: 46 },
  { time: '10:15', value: 22305, vwap: 22314, ema: 22310, volume: 38 }, { time: '10:45', value: 22382, vwap: 22340, ema: 22345, volume: 54 },
  { time: '11:15', value: 22412, vwap: 22368, ema: 22378, volume: 61 }, { time: '11:45', value: 22398, vwap: 22389, ema: 22395, volume: 44 },
  { time: '12:15', value: 22456, vwap: 22408, ema: 22420, volume: 67 }, { time: '12:45', value: 22428, vwap: 22422, ema: 22432, volume: 51 },
  { time: '13:15', value: 22475, vwap: 22440, ema: 22451, volume: 72 }, { time: '13:45', value: 22458, vwap: 22452, ema: 22460, volume: 57 },
]

export const events = [
  { time: '14:32:08', title: 'Momentum confirmation', detail: 'NIFTY cleared 22,450 resistance with improving breadth.', type: 'Market', tone: 'positive' },
  { time: '14:28:44', title: 'Risk envelope recalculated', detail: 'Portfolio VaR remains within daily threshold at 1.8%.', type: 'Risk', tone: 'neutral' },
  { time: '14:21:12', title: 'News signal classified', detail: 'RBI commentary scored neutral-positive for financials.', type: 'Intelligence', tone: 'positive' },
  { time: '14:16:50', title: 'Execution window updated', detail: 'Liquidity depth improved across primary venues.', type: 'Execution', tone: 'neutral' },
]

export const scenarios = [
  { name: 'Trend continuation', probability: '62%', action: 'Maintain long bias', trigger: 'Price holds above 22,400', state: 'Ready', tone: 'positive' },
  { name: 'Mean reversion', probability: '24%', action: 'Reduce exposure', trigger: 'VWAP loss + breadth < 45', state: 'Armed', tone: 'amber' },
  { name: 'Volatility expansion', probability: '14%', action: 'Move to capital preservation', trigger: 'India VIX > 15.2', state: 'Watching', tone: 'neutral' },
]

export const news = [
  { source: 'REUTERS', title: 'Indian shares edge higher as banks lead; investors await central bank cues', age: '18 min ago', relevance: '0.91' },
  { source: 'MINT', title: 'FII flows turn positive after three sessions of selling pressure', age: '42 min ago', relevance: '0.84' },
  { source: 'BLOOMBERG', title: 'Gold steadies as dollar retreats ahead of US inflation print', age: '1 hr ago', relevance: '0.77' },
]
