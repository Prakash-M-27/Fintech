"use client";

import { ReactNode, useCallback, useEffect, useState } from "react";

const FOREX_BACKEND =
  process.env.NEXT_PUBLIC_FOREX_URL || "http://localhost:8001";

type Decision = {
  trace_id: string;
  ts: string;
  instrument: string;
  action: string;
  rule: string;
  reason: string;
  sentiment: string;
  rsi: number | null;
  close: number | null;
  risk_approved: boolean;
  risk_reason: string;
  stop_loss: number | null;
  take_profit: number | null;
  position_size: number;
  execution_status: string;
};

type Rule = {
  name: string;
  description?: string;
  action?: string;
  [key: string]: unknown;
};

function tone(action: string, approved: boolean) {
  if (action === "BUY" && approved) return "text-emerald-600 dark:text-emerald-400";
  if (action === "SELL" && approved) return "text-rose-600 dark:text-rose-400";
  if (action === "HOLD") return "text-muted-foreground";
  return "text-amber-600 dark:text-amber-400";
}

function fmt(v: number | null | undefined) {
  return v == null ? "—" : typeof v === "number" ? v.toFixed(2) : String(v);
}

function timeAgo(ts: string) {
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return ts;
  const s = Math.floor((Date.now() - then) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

export default function ForexDashboard() {
  const [health, setHealth] = useState<any>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [signals, setSignals] = useState<Decision[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [h, d, s, r] = await Promise.all([
        fetch(`${FOREX_BACKEND}/api/forex/health`),
        fetch(`${FOREX_BACKEND}/api/forex/decisions?limit=25`),
        fetch(`${FOREX_BACKEND}/api/forex/signals?limit=15`),
        fetch(`${FOREX_BACKEND}/api/forex/rules`),
      ]);
      if (!h.ok) throw new Error(`forex backend unreachable (${h.status})`);
      setHealth(await h.json());
      setDecisions(await d.json());
      setSignals(await s.json());
      setRules(await r.json());
      setError("");
    } catch (e: any) {
      setError(e.message || String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const runNow = async () => {
    setRunning(true);
    try {
      await fetch(`${FOREX_BACKEND}/api/forex/run`, { method: "POST" });
      await load();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setRunning(false);
    }
  };

  const metric = (label: string, value: string, sub?: string, t = "") => (
    <div className="border-l border-border pl-3">
      <p className="font-mono text-[10px] uppercase tracking-[.16em] text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-1 text-lg font-semibold tracking-tight ${
          t === "good"
            ? "text-emerald-600 dark:text-emerald-400"
            : t === "bad"
              ? "text-rose-600 dark:text-rose-400"
              : ""
        }`}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );

  const section = (
    eyebrow: string,
    title: string,
    children: ReactNode,
    action?: string,
  ) => (
    <section>
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">
            {eyebrow}
          </p>
          <h2 className="mt-1 text-base font-semibold tracking-tight">{title}</h2>
        </div>
        {action && <span className="text-xs text-muted-foreground">{action}</span>}
      </div>
      {children}
    </section>
  );

  const table = (headers: string[], rows: (string | ReactNode)[][]) => (
    <div className="overflow-x-auto border border-border bg-card">
      <table className="w-full min-w-[760px] text-left text-xs">
        <thead className="border-b border-border bg-muted/30 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-3 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className="border-b border-border last:border-0 hover:bg-muted/30"
            >
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`px-3 py-3 ${j === 0 ? "font-medium" : "text-muted-foreground"}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={headers.length}
                className="px-3 py-6 text-center text-muted-foreground"
              >
                No data yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-8">
      {error && (
        <div className="border border-destructive/40 bg-destructive/5 px-4 py-3 text-xs text-destructive">
          <span className="font-mono uppercase tracking-wide">forex backend error:</span>{" "}
          {error}{" "}
          <span className="text-muted-foreground">
            (start it with{" "}
            <code className="font-mono">PYTHONPATH=.:.deps python -m api_server</code>{" "}
            in forex-agent-system/)
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4 border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <span
            className={`size-2 rounded-full ${
              health?.status === "running" ? "bg-emerald-500" : "bg-amber-500"
            }`}
          />
          <span className="font-mono text-[10px] uppercase tracking-[.18em] text-muted-foreground">
            forex-agent-system · {health?.status || "…"}
          </span>
        </div>
        <button
          onClick={runNow}
          disabled={running}
          className="flex items-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {running ? "Running cycle…" : "Run Cycle Now"}
        </button>
        <span className="ml-auto font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          endpoint · {FOREX_BACKEND}
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {metric("Mode", health?.trading_mode || "—")}
        {metric(
          "Status",
          health?.status || "—",
          undefined,
          health?.status === "idle" ? "bad" : "good",
        )}
        {metric("Cycles", String(health?.cycles_total ?? "—"))}
        {metric(
          "Last cycle",
          health?.last_cycle_at ? timeAgo(health.last_cycle_at) : "—",
          health?.last_error || undefined,
          health?.last_error ? "bad" : "",
        )}
      </div>

      {section(
        "Live signals",
        "Risk-approved trade signals",
        table(
          ["Time", "Pair", "Action", "Rule", "Reason", "Stop", "Target", "Size"],
          signals.map((s) => [
            timeAgo(s.ts),
            s.instrument,
            <span key="a" className={`font-semibold ${tone(s.action, s.risk_approved)}`}>
              {s.action}
            </span>,
            s.rule,
            s.reason,
            fmt(s.stop_loss),
            fmt(s.take_profit),
            fmt(s.position_size),
          ]),
        ),
      )}

      {section(
        "Pipeline decisions",
        "Every recent forex-agent cycle through data → analysis → strategy → risk → execution",
        table(
          ["Time", "Pair", "Action", "RSI", "Close", "Risk", "Execution"],
          decisions.map((d) => [
            timeAgo(d.ts),
            d.instrument,
            <span key="a" className={`font-semibold ${tone(d.action, d.risk_approved)}`}>
              {d.action}
            </span>,
            fmt(d.rsi),
            fmt(d.close),
            <span key="r" className={d.risk_approved ? "text-emerald-500" : "text-rose-500"}>
              {d.risk_approved ? "APPROVED" : "REJECTED"}
            </span>,
            d.execution_status,
          ]),
        ),
      )}

      {section(
        "Strategy rules",
        "Declarative signal rules that gate strategy decisions",
        table(
          ["Rule", "Description", "Action"],
          rules.map((r) => [
            r.name,
            (r.description as string) || "—",
            (r.action as string) || (r.direction as string) || "—",
          ]),
        ),
      )}
    </div>
  );
}
