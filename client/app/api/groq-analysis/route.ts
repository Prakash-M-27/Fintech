import { NextRequest, NextResponse } from 'next/server'

const GROQ_API = 'https://api.groq.com/openai/v1/chat/completions'
const GROQ_KEY = process.env.GROQ_API_KEY || ''

export async function POST(req: NextRequest) {
  const body = await req.json()
  const { symbol, price, change, rsi, macd, signal, ema20, ema50, bbUpper, bbLower, vwap, volume } = body

  const prompt = `You are an autonomous financial decision agent. Your role is NOT to predict exact future prices. Instead, assess the current market state and produce a condition-aware decision that remains valid only while specific conditions hold.

Symbol: ${symbol}
Current Price: ${price}
Change: ${change}%
RSI (14): ${rsi}
MACD: ${macd} | Signal: ${signal} | Histogram: ${(macd - signal).toFixed(2)}
EMA 20: ${ema20} | EMA 50: ${ema50}
Bollinger Upper: ${bbUpper} | Lower: ${bbLower}
VWAP: ${vwap}
Volume: ${volume}K

Respond in this exact JSON format (no markdown, no extra text):
{
  "action": "BUY" or "SELL" or "HOLD" or "WATCH" or "REDUCE" or "EXIT",
  "confidence": number between 0-100,
  "entry": suggested entry price as number,
  "target": price target as number,
  "stopLoss": stop loss price as number,
  "reasoning": "2-3 sentence explanation of current market state, not a price prediction",
  "riskLevel": "LOW" or "MEDIUM" or "HIGH",
  "trend": "BULLISH" or "BEARISH" or "NEUTRAL",
  "validityConditions": ["up to 3 short conditions that must remain true for this decision to stay valid"],
  "invalidationConditions": ["up to 3 short conditions that would immediately invalidate this decision"]
}`

  const res = await fetch(GROQ_API, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${GROQ_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model: 'meta-llama/llama-4-scout-17b-16e-instruct',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 300,
      temperature: 0.3,
    }),
  })

  if (!res.ok) {
    return NextResponse.json({ error: 'Groq API error' }, { status: 500 })
  }

  const data = await res.json()
  const text = data.choices[0].message.content.trim()

  try {
    const jsonMatch = text.match(/\{[\s\S]*\}/)
    const parsed = JSON.parse(jsonMatch ? jsonMatch[0] : text)
    return NextResponse.json(parsed)
  } catch {
    return NextResponse.json({ error: 'Parse error', raw: text }, { status: 500 })
  }
}
