"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Command,
  Crosshair,
  Database,
  Gauge,
  History,
  Layers3,
  Menu,
  Moon,
  PanelLeft,
  Pause,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Target,
  TrendingUp,
  Wallet,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { TVOverviewChart } from "@/components/tv-chart";
import { assets, chartData, events, news, scenarios } from "@/lib/axiom-data";
import {
  getMarketStatus,
  getOverallMarketStatus,
  MarketStatusInfo,
} from "@/lib/market-status";
import { io } from "socket.io-client";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

const nav = [
  ["Overview", "/", Gauge],
  ["Live Trading", "/live", Activity],
  ["Markets", "/markets", TrendingUp],
  ["Agent Intelligence", "/agent", Bot],
  ["Scenarios", "/scenarios", Layers3],
  ["Risk Center", "/risk", ShieldCheck],
  ["Capital Allocation", "/capital", Wallet],
  ["Positions", "/positions", Target],
  ["Execution", "/execution", Zap],
  ["News Intelligence", "/news", Bell],
  ["Outcomes", "/outcomes", BarChart3],
  ["Decision History", "/history", History],
  ["Data Sources", "/data-sources", Database],
  ["Settings", "/settings", Settings2],
] as const;
const titles: Record<string, [string, string]> = {
  "/": [
    "Command Center",
    "Autonomous financial intelligence, continuously observing and adapting.",
  ],
  "/markets": [
    "Markets",
    "Real-time market state across monitored instruments.",
  ],
  "/agent": [
    "Agent Intelligence",
    "Understand how market evidence becomes risk-aware actions.",
  ],
  "/scenarios": [
    "Scenario Readiness",
    "Condition-dependent market responses prepared before state transitions.",
  ],
  "/risk": [
    "Risk Center",
    "Hard constraints that remain authoritative over agent decisions.",
  ],
  "/capital": [
    "Capital Allocation",
    "Capital is assigned by opportunity quality and risk-adjusted fit.",
  ],
  "/positions": [
    "Positions",
    "Monitor open and closed paper positions with full decision context.",
  ],
  "/execution": [
    "Execution Center",
    "Simulated order flow with pre-trade validation and execution quality.",
  ],
  "/news": [
    "News Intelligence",
    "Asset-linked signals classified for decision influence.",
  ],
  "/outcomes": [
    "Outcome Intelligence",
    "Compare expected decisions with observed market behaviour.",
  ],
  "/history": [
    "Decision History",
    "Institutional-style audit log of every decision version.",
  ],
  "/data-sources": [
    "Data Infrastructure",
    "Freshness, reliability, and operational health across connectors.",
  ],
  "/settings": [
    "Settings",
    "Configure workspace behaviour, safeguards, and presentation.",
  ],
};

function Metric({
  label,
  value,
  sub,
  tone = "",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: string;
}) {
  return (
    <div className="border-l border-border pl-3">
      <p className="font-mono text-[10px] uppercase tracking-[.16em] text-muted-foreground">
        {label}
      </p>
      <p
        className={`mt-1 text-lg font-semibold tracking-tight ${tone === "good" ? "text-emerald-600 dark:text-emerald-400" : tone === "warn" ? "text-amber-600 dark:text-amber-400" : tone === "bad" ? "text-rose-600 dark:text-rose-400" : ""}`}
      >
        {value}
      </p>
      {sub && <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}
function Section({
  eyebrow,
  title,
  children,
  action,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  action?: string;
}) {
  return (
    <section>
      <div className="mb-3 flex items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[.18em] text-muted-foreground">
            {eyebrow}
          </p>
          <h2 className="mt-1 text-base font-semibold tracking-tight">
            {title}
          </h2>
        </div>
        {action && (
          <span className="text-xs text-muted-foreground">{action}</span>
        )}
      </div>
      {children}
    </section>
  );
}
function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
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
        </tbody>
      </table>
    </div>
  );
}

export default function AxiomDashboard({ route = "/" }: { route?: string }) {
  const [collapsed, setCollapsed] = useState(false);
  const [dark, setDark] = useState(false);
  const [search, setSearch] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [stop, setStop] = useState(false);
  const [stream, setStream] = useState(true);
  const [asset, setAsset] = useState(0);
  const [scenario, setScenario] = useState(0);
  const [marketStatuses, setMarketStatuses] = useState<Record<string, MarketStatusInfo>>({});
  const [overallStatus, setOverallStatus] = useState<MarketStatusInfo>({ state: 'CLOSED', countdown: '' });
  const [liveData, setLiveData] = useState<
    Record<string, { price: string; change: string }>
  >({
    nifty: { price: "22458.80", change: "+0.42%" },
    gold: { price: "72418.00", change: "+0.18%" },
    usd: { price: "83.42", change: "-0.06%" },
  });

  // ── Agent live state ─────────────────────────────────────────────────────
  const [agentNews, setAgentNews] = useState<any[]>([]);
  const [agentDecisions, setAgentDecisions] = useState<any[]>([]);
  const [agentPortfolio, setAgentPortfolio] = useState<any>(null);
  const [agentSignals, setAgentSignals] = useState<any[]>([]); // real-time socket feed
  const [agentEvents, setAgentEvents] = useState<any[]>([]); // real-time decision feed

  useEffect(() => {
    const updateStatus = () => {
      setMarketStatuses({
        nifty: getMarketStatus('nifty'),
        gold: getMarketStatus('gold'),
        usd: getMarketStatus('usd')
      });
      setOverallStatus(getOverallMarketStatus());
    };
    updateStatus();
    const interval = setInterval(updateStatus, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  // ── Fetch agent REST data on relevant route ──────────────────────────────
  useEffect(() => {
    if (
      !["/news", "/agent", "/positions", "/capital", "/history", "/"].includes(
        route,
      )
    )
      return;
    const load = async () => {
      try {
        const [newsRes, decRes, portRes] = await Promise.all([
          fetch(`${BACKEND}/api/agent/news?limit=20`),
          fetch(`${BACKEND}/api/agent/decisions?limit=20`),
          fetch(`${BACKEND}/api/agent/portfolio`),
        ]);
        if (newsRes.ok) setAgentNews(await newsRes.json());
        if (decRes.ok) setAgentDecisions(await decRes.json());
        if (portRes.ok) setAgentPortfolio(await portRes.json());
      } catch (e) {
        // silently fall back to seed data if backend unavailable
      }
    };
    load();
  }, [route]);

  // ── Socket.IO: market prices + agent events ──────────────────────────────
  useEffect(() => {
    if (!stream || stop) return;
    const socket = io(BACKEND);
    socket.emit("subscribe", "nifty");
    socket.emit("subscribe", "gold");
    socket.emit("subscribe", "usd");

    // Existing price feed
    socket.on("market_update", (data) => {
      if (data.asset && data.price) {
        setLiveData((prev) => ({
          ...prev,
          [data.asset]: {
            price:
              data.asset === "gold"
                ? `₹${Number(data.price).toLocaleString("en-IN")}`
                : Number(data.price).toFixed(2),
            change: data.change_pct
              ? `${data.change_pct > 0 ? "+" : ""}${data.change_pct}%`
              : prev[data.asset]?.change || "",
          },
        }));
      }
    });

    // New: classified news signals from the agent
    socket.on("news_signal", (data) => {
      setAgentSignals((prev) => [data, ...prev.slice(0, 19)]);
      setAgentNews((prev) => [
        {
          id: Date.now(),
          title: data.title,
          source: data.source || "Tavily",
          url: "#",
          related_asset: data.asset,
          fetched_at: data.ts,
          processed: true,
          signal: {
            asset: data.asset,
            sentiment: data.sentiment,
            impact_score: data.impact_score,
            confidence: data.confidence,
            reasoning: data.reasoning,
            created_at: data.ts,
          },
        },
        ...prev.slice(0, 19),
      ]);
    });

    // New: agent BUY/SELL/EXIT/HOLD decisions
    socket.on("agent_decision", (data) => {
      setAgentEvents((prev) => [data, ...prev.slice(0, 19)]);
      setAgentDecisions((prev) => [
        {
          id: data.decision_id || Date.now(),
          asset: data.asset,
          action: data.action,
          amount_inr: data.amount_inr || 0,
          confidence: data.confidence || 0,
          reasoning: data.reasoning || data.reason || "",
          technical_snapshot: data.technical || null,
          created_at: data.ts,
        },
        ...prev.slice(0, 19),
      ]);
      // Refresh portfolio on any trade event
      fetch(`${BACKEND}/api/agent/portfolio`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => d && setAgentPortfolio(d))
        .catch(() => {});
    });

    return () => {
      socket.disconnect();
    };
  }, [stream, stop]);

  const [title, subtitle] = titles[route] || titles["/"];
  const go = (path: string) => {
    window.location.href = path;
  };

  const assetKeys = ["nifty", "gold", "usd"];
  const marketRows = assets.map((a, i) => {
    const key = assetKeys[i];
    const live = liveData[key];
    return [
      a.symbol,
      live ? live.price : a.price,
      live ? live.change : a.change,
      i === 0 ? "72.4M" : i === 1 ? "18.2K" : "4.8B",
      i === 0 ? "Risk-on" : "Balanced",
      i === 0 ? "WATCH · 72%" : i === 1 ? "BUY · 81%" : "AVOID · 31%",
    ];
  });

  // ── Live agent data for page routes ─────────────────────────────────────
  // Positions: from live portfolio or fall back to seed
  const livePositionRows: string[][] = agentPortfolio?.open_positions?.length
    ? agentPortfolio.open_positions.map((p: any) => [
        p.asset.toUpperCase(),
        "Long",
        `₹${Number(p.entry_price).toLocaleString("en-IN")}`,
        liveData[p.asset]?.price ||
          `₹${Number(p.entry_price).toLocaleString("en-IN")}`,
        "—",
        `₹${Number(p.entry_amount_inr).toLocaleString("en-IN")}`,
        p.unrealized_pnl != null
          ? `₹${Number(p.unrealized_pnl).toFixed(2)}`
          : "—",
        "—",
        "—",
        "OPEN",
      ])
    : [
        [
          "NIFTY 50",
          "Long",
          "22,402",
          liveData.nifty.price,
          "24",
          "₹537,648",
          "+₹1,363",
          "22,680",
          "22,240",
          "WATCH",
        ],
        [
          "GOLD",
          "Long",
          "72,080",
          liveData.gold.price,
          "2",
          "₹144,160",
          "+₹676",
          "73,400",
          "71,500",
          "BUY",
        ],
      ];

  // Decisions/history: from live decisions or fall back to seed
  const liveDecisionRows: string[][] = agentDecisions.length
    ? agentDecisions
        .slice(0, 10)
        .map((d: any, i: number) => [
          `#${d.id}`,
          new Date(d.created_at).toLocaleTimeString("en-IN"),
          (d.asset || "").toUpperCase(),
          d.action,
          `${Math.round((d.confidence || 0) * 100)}%`,
          "Moderate",
          `₹${Number(d.amount_inr || 0).toLocaleString("en-IN")}`,
          i === 0 ? "ACTIVE" : "SUPERSEDED",
          (d.reasoning || "").slice(0, 50),
        ])
    : [
        [
          "#144",
          "10:32:10",
          "NIFTY",
          "WATCH",
          "72%",
          "Moderate",
          "₹0",
          "ACTIVE",
          "Liquidity deterioration",
        ],
        [
          "#143",
          "10:28:44",
          "NIFTY",
          "HOLD",
          "78%",
          "Moderate",
          "₹0",
          "SUPERSEDED",
          "Breadth confirmation",
        ],
        [
          "#142",
          "09:55:02",
          "GOLD",
          "BUY",
          "81%",
          "Low",
          "₹16,000",
          "ACTIVE",
          "Risk-adjusted opportunity",
        ],
      ];

  // Capital: from live portfolio
  const capital = agentPortfolio?.capital;
  const liveCapitalRows: string[][] = agentDecisions.length
    ? agentDecisions
        .slice(0, 5)
        .map((d: any) => [
          (d.asset || "").toUpperCase(),
          d.action,
          `${Math.round((d.confidence || 0) * 100)}`,
          "—",
          "—",
          "—",
          `₹${Number(d.amount_inr || 0).toLocaleString("en-IN")}`,
          `₹${Number(d.amount_inr || 0).toLocaleString("en-IN")}`,
          d.action === "BUY"
            ? "Approved"
            : d.action === "HOLD"
              ? "Waiting"
              : "Executed",
        ])
    : [
        ["NIFTY", "WATCH", "72", "58", "Moderate", "—", "₹0", "₹0", "Waiting"],
        [
          "Gold",
          "BUY",
          "81",
          "42",
          "High",
          "2.1R",
          "₹20,000",
          "₹16,000",
          "Approved",
        ],
        ["USD", "AVOID", "31", "67", "Moderate", "—", "₹0", "₹0", "Rejected"],
      ];

  const pageRows: Record<string, { headers: string[]; rows: string[][] }> = {
    "/positions": {
      headers: [
        "Asset",
        "Direction",
        "Entry",
        "Current",
        "Quantity",
        "Capital",
        "PnL",
        "Target",
        "Stop",
        "Agent state",
      ],
      rows: livePositionRows,
    },
    "/execution": {
      headers: [
        "Time",
        "Asset",
        "Action",
        "Qty",
        "Requested",
        "Execution",
        "Slippage",
        "Cost",
        "Version",
        "Status",
      ],
      rows: [
        [
          "14:28:44",
          "GOLD",
          "BUY",
          "2",
          "72,410",
          liveData.gold.price,
          "0.01%",
          "₹18",
          "#142",
          "FILLED",
        ],
        [
          "14:16:50",
          "NIFTY",
          "HOLD",
          "—",
          "—",
          "—",
          "—",
          "—",
          "#143",
          "NO ACTION",
        ],
        [
          "13:14:21",
          "USD/INR",
          "BUY",
          "—",
          "83.42",
          "—",
          "—",
          "—",
          "#139",
          "REJECTED",
        ],
      ],
    },
    "/history": {
      headers: [
        "Version",
        "Time",
        "Asset",
        "Decision",
        "Confidence",
        "Risk",
        "Capital",
        "Status",
        "Reason",
      ],
      rows: liveDecisionRows,
    },
    "/capital": {
      headers: [
        "Asset",
        "Decision",
        "Opportunity",
        "Risk",
        "Liquidity",
        "Reward",
        "Requested",
        "Approved",
        "Status",
      ],
      rows: liveCapitalRows,
    },
    "/outcomes": {
      headers: [
        "Decision",
        "Asset",
        "Action",
        "Expected state",
        "Observed state",
        "Outcome",
        "PnL",
        "Invalidated?",
        "Primary reason",
      ],
      rows: [
        [
          "#131",
          "NIFTY",
          "BUY",
          "Bullish breakout",
          "Liquidity breakdown",
          "Reduced",
          "+₹840",
          "Yes",
          "Liquidity collapsed faster",
        ],
        [
          "#128",
          "GOLD",
          "BUY",
          "Trend continuation",
          "Trend continuation",
          "Realized",
          "+₹2,240",
          "No",
          "—",
        ],
        [
          "#124",
          "USD",
          "AVOID",
          "Risk-off",
          "Risk-off",
          "Avoided",
          "₹0",
          "No",
          "—",
        ],
      ],
    },
  };
  const generic = pageRows[route];
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur md:px-6">
        <div className="flex items-center gap-3">
          <button
            aria-label="Toggle sidebar"
            onClick={() => setCollapsed(!collapsed)}
            className="rounded-md p-2 text-muted-foreground hover:bg-muted"
          >
            <PanelLeft className="size-4" />
          </button>
          <button onClick={() => go("/")} className="flex items-center gap-2">
            <span className="flex size-7 items-center justify-center rounded-sm bg-primary text-primary-foreground">
              <Crosshair className="size-4" />
            </span>
            <span className="text-sm font-bold tracking-[.2em]">AXIOM</span>
            <span className="hidden border-l border-border pl-3 font-mono text-[10px] uppercase tracking-widest text-muted-foreground sm:inline">
              Command Center
            </span>
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setSearch(true)}
            className="hidden items-center gap-2 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground hover:bg-muted sm:flex"
          >
            <Search className="size-3.5" /> Search{" "}
            <kbd className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              ⌘K
            </kbd>
          </button>
          <button
            aria-label="Notifications"
            onClick={() => setNotifications(!notifications)}
            className="relative rounded-md p-2 text-muted-foreground hover:bg-muted"
          >
            <Bell className="size-4" />
            <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-amber-500" />
          </button>
          <button
            aria-label="Toggle theme"
            onClick={() => setDark(!dark)}
            className="rounded-md p-2 text-muted-foreground hover:bg-muted"
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
          <span className="ml-2 hidden border-l border-border pl-3 text-xs font-medium sm:inline">
            A. Kumar
          </span>
        </div>
      </header>
      <div className="flex">
        <aside
          className={`${collapsed ? "w-16" : "w-60"} hidden shrink-0 border-r border-border bg-muted/20 transition-all md:block`}
        >
          <nav className="flex flex-col gap-1 p-3">
            <p
              className={`mb-2 px-2 font-mono text-[10px] uppercase tracking-[.18em] text-muted-foreground ${collapsed ? "sr-only" : ""}`}
            >
              Workspace
            </p>
            {nav.map(([label, path, Icon]) => (
              <button
                key={path}
                onClick={() => go(path)}
                className={`flex items-center gap-3 rounded-md px-3 py-2 text-left text-xs font-medium ${route === path ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}
              >
                <Icon className="size-4 shrink-0" />
                {!collapsed && label}
              </button>
            ))}
          </nav>
          <div
            className={`${collapsed ? "hidden" : ""} mx-4 mt-8 border border-border bg-background p-3`}
          >
            <div className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-emerald-500" />
              <span className="font-mono text-[10px] uppercase tracking-wider">
                Systems nominal
              </span>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              All decision loops operating within parameters.
            </p>
          </div>
        </aside>
        <main className="min-w-0 flex-1">
          <div className="mx-auto max-w-[1500px] p-4 md:p-6 lg:p-8">
            <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <span className="size-2 rounded-full bg-emerald-500" />
                  <span className="font-mono text-[10px] uppercase tracking-[.18em] text-muted-foreground">
                    Live operating state · {stream ? "streaming" : "paused"}
                  </span>
                </div>
                <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
                  {title}
                </h1>
                <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                  {subtitle}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setStream(!stream)}
                  className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-xs font-medium hover:bg-muted"
                >
                  {stream ? (
                    <Pause className="size-3.5" />
                  ) : (
                    <Play className="size-3.5" />
                  )}
                  {stream ? "Pause stream" : "Resume stream"}
                </button>
                <button
                  onClick={() => setStop(true)}
                  className="flex items-center gap-2 rounded-md border border-destructive/40 px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/10"
                >
                  <AlertTriangle className="size-3.5" /> Emergency stop
                </button>
              </div>
            </div>
            {route === "/" && (
              <>
                <div className="mb-6 flex overflow-x-auto border-y border-border">
                  {assets.map((a, i) => {
                    const live = liveData[assetKeys[i]];
                    const changeIsPos = live?.change?.startsWith("+");
                    return (
                      <button
                        key={a.symbol}
                        onClick={() => setAsset(i)}
                        className={`min-w-[180px] flex-1 border-r border-border px-4 py-3 text-left first:border-l ${asset === i ? "bg-muted/70" : "hover:bg-muted/40"}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-[10px] font-semibold tracking-wider">
                            {a.symbol}
                          </span>
                          <span
                            className={
                              changeIsPos ? "text-emerald-500" : "text-rose-500"
                            }
                          >
                            {live ? live.change : a.change}
                          </span>
                        </div>
                        <div className="mt-1 text-lg font-semibold">
                          {live ? live.price : a.price}
                        </div>
                        <span className="font-mono text-[9px] text-muted-foreground">
                          {a.name}
                        </span>
                      </button>
                    );
                  })}
                </div>
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,.85fr)]">
                  <Section
                    eyebrow="Current decision"
                    title="NIFTY 50 · Long bias"
                  >
                    <div className="border border-border bg-card p-4 md:p-5">
                      <div className="flex flex-wrap justify-between gap-4">
                        <div>
                          <p className="text-xl font-semibold">
                            Maintain long exposure
                          </p>
                          <p className="mt-1 max-w-xl text-sm leading-relaxed text-muted-foreground">
                            Market structure remains constructive with breadth
                            expansion and stable volatility. No action required
                            while validity conditions hold.
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                            Confidence
                          </p>
                          <p className="mt-1 text-2xl font-semibold text-emerald-500">
                            78%
                          </p>
                        </div>
                      </div>
                      <div className="mt-5 grid grid-cols-2 gap-4 border-t border-border pt-4 sm:grid-cols-4">
                        <Metric
                          label="Entry zone"
                          value="22,380–22,420"
                          sub="avg. 22,402"
                        />
                        <Metric
                          label="Target"
                          value="22,680"
                          sub="+1.24% upside"
                          tone="good"
                        />
                        <Metric
                          label="Invalidation"
                          value="22,240"
                          sub="hard stop"
                          tone="warn"
                        />
                        <Metric label="Horizon" value="2–5 days" sub="swing" />
                      </div>
                      <div className="mt-5 h-64">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData}>
                            <defs>
                              <linearGradient
                                id="fill"
                                x1="0"
                                y1="0"
                                x2="0"
                                y2="1"
                              >
                                <stop
                                  offset="0%"
                                  stopColor="var(--chart-2)"
                                  stopOpacity=".2"
                                />
                                <stop
                                  offset="100%"
                                  stopColor="var(--chart-2)"
                                  stopOpacity="0"
                                />
                              </linearGradient>
                            </defs>
                            <CartesianGrid
                              stroke="var(--border)"
                              strokeDasharray="2 4"
                              vertical={false}
                            />
                            <XAxis
                              dataKey="time"
                              tick={{
                                fontSize: 10,
                                fill: "var(--muted-foreground)",
                              }}
                            />
                            <YAxis
                              domain={["dataMin - 20", "dataMax + 20"]}
                              tick={{
                                fontSize: 10,
                                fill: "var(--muted-foreground)",
                              }}
                            />
                            <Tooltip />
                            <Area
                              type="monotone"
                              dataKey="value"
                              stroke="var(--chart-2)"
                              fill="url(#fill)"
                              strokeWidth={2}
                            />
                            <Line
                              type="monotone"
                              dataKey="vwap"
                              stroke="var(--chart-4)"
                              dot={false}
                              strokeDasharray="4 4"
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </Section>
                  <div className="flex flex-col gap-6">
                    <Section
                      eyebrow="Readiness engine"
                      title="Prepared scenarios"
                    >
                      <div className="flex flex-col gap-2">
                        {scenarios.map((s, i) => (
                          <div
                            key={s.name}
                            className="border border-border bg-card"
                          >
                            <button
                              onClick={() =>
                                setScenario(scenario === i ? -1 : i)
                              }
                              className="flex w-full items-center justify-between p-3 text-left"
                            >
                              <span className="text-xs font-semibold">
                                {s.name}
                              </span>
                              <span className="flex items-center gap-2 font-mono text-xs">
                                {s.probability}
                                {scenario === i ? (
                                  <ChevronDown className="size-4" />
                                ) : (
                                  <ChevronRight className="size-4" />
                                )}
                              </span>
                            </button>
                            {scenario === i && (
                              <div className="border-t border-border bg-muted/30 p-3 text-xs">
                                <p className="text-muted-foreground">
                                  Trigger: {s.trigger}
                                </p>
                                <p className="mt-2 font-mono uppercase tracking-wider text-emerald-500">
                                  {s.state} · {s.action}
                                </p>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </Section>
                    <Section eyebrow="Autonomous loop" title="System activity">
                      <div className="border border-border bg-card p-4">
                        <div className="flex flex-wrap gap-2">
                          {[
                            "Observe",
                            "Interpret",
                            "Reason",
                            "Risk",
                            "Allocate",
                            "Execute",
                            "Outcome",
                            "Adapt",
                          ].map((x, i) => (
                            <span
                              key={x}
                              className={`border px-2 py-1 font-mono text-[10px] ${i < 5 ? "border-emerald-500/30 text-emerald-500" : "border-border text-muted-foreground"}`}
                            >
                              {x}
                            </span>
                          ))}
                        </div>
                        <p className="mt-4 text-xs text-muted-foreground">
                          Reassessing NIFTY · decision version #144 · runtime
                          1.4s
                        </p>
                      </div>
                    </Section>
                  </div>
                </div>
                <div className="mt-8 grid gap-6 lg:grid-cols-[1.1fr,.9fr]">
                  <Section eyebrow="Live event stream" title="What changed">
                    <div className="border border-border bg-card">
                      {events.map((e, i) => (
                        <div
                          key={e.time}
                          className="flex gap-3 border-b border-border p-3 last:border-0"
                        >
                          <span className="mt-1 size-2 rounded-full bg-emerald-500" />
                          <div>
                            <div className="flex flex-wrap gap-3">
                              <p className="text-xs font-semibold">{e.title}</p>
                              <span className="font-mono text-[10px] text-muted-foreground">
                                {e.time}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {e.detail}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Section>
                  <Section eyebrow="Intelligence layer" title="Relevant news">
                    <div className="border border-border bg-card">
                      {news.map((n) => (
                        <div
                          key={n.title}
                          className="border-b border-border p-3 last:border-0"
                        >
                          <span className="font-mono text-[10px] text-muted-foreground">
                            {n.source} · {n.age}
                          </span>
                          <p className="mt-2 text-xs font-medium leading-relaxed">
                            {n.title}
                          </p>
                        </div>
                      ))}
                    </div>
                  </Section>
                </div>
              </>
            )}
            {route === "/markets" && (
              <div className="grid gap-8 lg:grid-cols-[1fr_350px]">
                <div className="flex flex-col gap-6">
                  <Section
                    eyebrow="Selected asset"
                    title={assets[asset].symbol}
                    action={marketStatuses[assetKeys[asset]]?.state === 'OPEN' ? <span className="flex items-center gap-2 text-emerald-500"><span className="size-2 animate-pulse rounded-full bg-emerald-500" /> OPEN · {marketStatuses[assetKeys[asset]]?.countdown}</span> : <span className="flex items-center gap-2 text-rose-500"><span className="size-2 rounded-full bg-rose-500" /> {marketStatuses[assetKeys[asset]]?.state} · {marketStatuses[assetKeys[asset]]?.countdown}</span>}
                  >
                    <div className="border border-border bg-card p-4 md:p-5">
                      <div className="mb-6 grid grid-cols-2 gap-4 border-b border-border pb-6 md:grid-cols-4">
                        <Metric
                          label="Live Price"
                          value={liveData[assetKeys[asset]]?.price || assets[asset].price}
                          sub={liveData[assetKeys[asset]]?.change || assets[asset].change}
                          tone={liveData[assetKeys[asset]]?.change?.startsWith('+') ? 'good' : 'bad'}
                        />
                        <Metric label="Momentum" value="Positive" tone="good" />
                        <Metric label="VWAP" value="22,408" />
                        <Metric label="ATR" value="142.6" />
                      </div>
                      <div className="h-72">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={chartData}>
                            <defs>
                              <linearGradient id="fill2" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--chart-3)" stopOpacity=".2" />
                                <stop offset="100%" stopColor="var(--chart-3)" stopOpacity="0" />
                              </linearGradient>
                            </defs>
                            <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
                            <XAxis dataKey="time" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                            <YAxis domain={["dataMin - 20", "dataMax + 20"]} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
                            <Tooltip />
                            <Area type="monotone" dataKey="value" stroke="var(--chart-3)" fill="url(#fill2)" strokeWidth={2} />
                            <Line type="monotone" dataKey="vwap" stroke="var(--chart-4)" dot={false} strokeDasharray="4 4" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </Section>
                  
                  <div className="grid gap-6 md:grid-cols-4">
                    <Metric
                      label="Market status"
                      value={overallStatus.state}
                      sub={overallStatus.countdown}
                      tone={overallStatus.state === 'OPEN' ? 'good' : 'warn'}
                    />
                    <Metric label="Data freshness" value="97%" sub="84ms median" tone="good" />
                    <Metric label="Liquidity" value="Healthy" sub="Across 3 feeds" />
                    <Metric label="Volatility" value="Moderate" sub="India VIX 13.84" />
                  </div>
                </div>

                <Section eyebrow="Market status · live" title="Monitored instruments" action="Data freshness 97%">
                  <div className="flex flex-col gap-3">
                    {assets.map((a, i) => {
                      const key = assetKeys[i];
                      const live = liveData[key];
                      const changeIsPos = live?.change?.startsWith('+');
                      const status = marketStatuses[key];
                      const isOpen = status?.state === 'OPEN';
                      return (
                        <button
                          key={key}
                          onClick={() => setAsset(i)}
                          className={`flex flex-col gap-3 border p-4 text-left transition-colors hover:bg-muted/30 ${asset === i ? 'border-primary bg-primary/5' : 'border-border bg-card'}`}
                        >
                          <div className="flex items-start justify-between">
                            <div>
                              <p className="font-semibold">{a.symbol}</p>
                              <p className="font-mono text-[10px] text-muted-foreground">{a.name}</p>
                            </div>
                            <div className="text-right">
                              <p className="font-mono font-medium">{live ? live.price : a.price}</p>
                              <p className={`font-mono text-[10px] ${changeIsPos ? 'text-emerald-500' : 'text-rose-500'}`}>{live ? live.change : a.change}</p>
                            </div>
                          </div>
                          <div className="flex items-center justify-between border-t border-border pt-3">
                            <span className={`flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-wider ${isOpen ? 'text-emerald-500' : 'text-muted-foreground'}`}>
                              <span className={`size-1.5 rounded-full ${isOpen ? 'animate-pulse bg-emerald-500' : 'bg-muted-foreground'}`} />
                              {isOpen ? 'OPEN' : 'CLOSED'}
                            </span>
                            <span className={`rounded-sm px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider ${i === 0 ? 'bg-primary/20 text-primary' : i === 1 ? 'bg-emerald-500/20 text-emerald-500' : 'bg-rose-500/20 text-rose-500'}`}>
                              {i === 0 ? 'WATCH · 72%' : i === 1 ? 'BUY · 81%' : 'AVOID · 31%'}
                            </span>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </Section>
              </div>
            )}
            {route === "/agent" && (
              <>
                <Section eyebrow="Runtime · active" title="Agent orchestration">
                  <div className="grid gap-3 md:grid-cols-4">
                    {[
                      "Observe",
                      "Interpret",
                      "Reason",
                      "Risk",
                      "Allocate",
                      "Execute",
                      "Outcome",
                      "Adapt",
                    ].map((s, i) => (
                      <button
                        key={s}
                        className={`border p-4 text-left ${i === 1 ? "border-primary bg-primary/10" : "border-border bg-card"}`}
                      >
                        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                          0{i + 1}
                        </span>
                        <p className="mt-3 text-sm font-semibold">{s}</p>
                        <p className="mt-1 text-xs text-emerald-500">
                          Completed · {i + 1}83ms
                        </p>
                        <p className="mt-2 text-[11px] text-muted-foreground">
                          Inputs: {8 - (i % 4)} · Tools: {2 + (i % 3)}
                        </p>
                      </button>
                    ))}
                  </div>
                </Section>
                <div className="mt-8 grid gap-6 lg:grid-cols-2">
                  <Section eyebrow="Decision evidence" title="Why WATCH">
                    <div className="border border-border bg-card p-4">
                      {[
                        ["Technical", "Bearish pressure", "0.72"],
                        ["Liquidity", "Weakening", "0.81"],
                        ["News", "Moderately negative", "0.61"],
                        ["Cross Asset", "Risk-off alignment", "0.69"],
                        ["Data Freshness", "Strong", "0.95"],
                      ].map((r) => (
                        <div
                          key={r[0]}
                          className="flex items-center justify-between border-b border-border py-3 text-xs last:border-0"
                        >
                          <span>{r[0]}</span>
                          <span className="text-muted-foreground">{r[1]}</span>
                          <span className="font-mono">{r[2]}</span>
                        </div>
                      ))}
                    </div>
                  </Section>
                  <Section
                    eyebrow="Signal conflict"
                    title="Conviction moderated"
                  >
                    <div className="border border-border bg-card p-4">
                      <p className="text-sm font-semibold text-amber-500">
                        MODERATE conflict
                      </p>
                      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                        Technical SELL, News HOLD, Liquidity SELL, Cross Asset
                        WATCH. The system reduced conviction because evidence
                        sources disagree.
                      </p>
                      <p className="mt-4 font-mono text-[10px] uppercase tracking-wider">
                        Resolved decision · WATCH
                      </p>
                    </div>
                  </Section>
                </div>
              </>
            )}
            {route === "/scenarios" && (
              <>
                <Section eyebrow="Live monitoring" title="Prepared responses">
                  <div className="grid gap-3 lg:grid-cols-3">
                    {scenarios.map((s, i) => (
                      <button
                        key={s.name}
                        onClick={() => setScenario(i)}
                        className="border border-border bg-card p-4 text-left hover:bg-muted/30"
                      >
                        <div className="flex justify-between">
                          <p className="text-sm font-semibold">{s.name}</p>
                          <span className="font-mono text-xs">
                            {s.probability}
                          </span>
                        </div>
                        <p className="mt-3 text-xs text-muted-foreground">
                          Relevance measures evidence alignment, not an exact
                          future-price prediction.
                        </p>
                        <div className="mt-4 border-t border-border pt-3 text-xs">
                          Current alignment{" "}
                          <strong>{i + 4}/7 conditions</strong>
                          <p className="mt-2 text-emerald-500">
                            Prepared response · {s.action}
                          </p>
                        </div>
                      </button>
                    ))}
                  </div>
                </Section>
                <Section eyebrow="Transition map" title="Current market state">
                  <div className="mt-3 flex flex-wrap items-center justify-center gap-3 border border-border bg-card p-8 text-center">
                    <div className="border border-primary bg-primary/10 p-5">
                      <p className="font-mono text-[10px] uppercase">Current</p>
                      <p className="mt-2 text-sm font-semibold">
                        Risk-off / High volatility
                      </p>
                    </div>
                    {[
                      "Liquidity breakdown 61%",
                      "Recovery 31%",
                      "Bearish continuation 54%",
                      "Stable 47%",
                      "News shock 12%",
                    ].map((x) => (
                      <div
                        key={x}
                        className="border border-border px-3 py-2 text-xs text-muted-foreground"
                      >
                        → {x}
                      </div>
                    ))}
                  </div>
                </Section>
              </>
            )}
            {route === "/risk" && (
              <>
                <div className="grid gap-3 md:grid-cols-4">
                  <Metric
                    label="Risk status"
                    value="PROTECTED"
                    sub="Hard constraints active"
                    tone="good"
                  />
                  <Metric
                    label="Available capital"
                    value="₹8.42L"
                    sub="of ₹12.00L"
                  />
                  <Metric
                    label="Current exposure"
                    value="₹5.38L"
                    sub="44.8% of maximum"
                  />
                  <Metric
                    label="Daily P&L"
                    value="+₹3,240"
                    sub="limit −₹18,000"
                    tone="good"
                  />
                </div>
                <div className="mt-8 grid gap-6 lg:grid-cols-2">
                  <Section
                    eyebrow="Control plane"
                    title="AI can recommend. Risk engine can override."
                  >
                    <div className="border border-border bg-card p-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        {[
                          ["Max capital / position", "₹40,000"],
                          ["Max portfolio exposure", "₹8,00,000"],
                          ["Maximum daily loss", "₹18,000"],
                          ["Maximum drawdown", "8%"],
                          ["Default target points", "280"],
                          ["Maximum stop-loss", "160"],
                        ].map((x) => (
                          <Metric key={x[0]} label={x[0]} value={x[1]} />
                        ))}
                      </div>
                      <button className="mt-5 bg-primary px-4 py-2 text-xs font-medium text-primary-foreground">
                        Save Risk Policy
                      </button>
                    </div>
                  </Section>
                  <Section eyebrow="Hard constraints" title="Rules">
                    <div className="border border-border bg-card">
                      {[
                        "Stop-loss cannot exceed user maximum",
                        "New positions blocked after daily loss limit",
                        "Capital allocation cannot exceed maximum exposure",
                        "Trade blocked if data is stale",
                        "Trade blocked during emergency stop",
                      ].map((x) => (
                        <div
                          key={x}
                          className="flex items-center gap-3 border-b border-border p-3 text-xs last:border-0"
                        >
                          <Check className="size-4 text-emerald-500" />
                          {x}
                          <span className="ml-auto font-mono text-[10px] text-emerald-500">
                            ACTIVE
                          </span>
                        </div>
                      ))}
                    </div>
                  </Section>
                </div>
              </>
            )}
            {generic && (
              <Section eyebrow="Operational ledger" title={title}>
                <Table headers={generic.headers} rows={generic.rows} />
              </Section>
            )}
            {route === "/news" && (
              <Section eyebrow="Classified events · live" title={title}>
                <div className="flex flex-col gap-2">
                  {(agentNews.length > 0
                    ? agentNews
                    : news.map((n) => ({
                        id: n.title,
                        title: n.title,
                        source: n.source,
                        signal: {
                          sentiment: "neutral",
                          impact_score: 0.3,
                          confidence: 0.84,
                          reasoning: "",
                        },
                      }))
                  ).map((n: any) => (
                    <div
                      key={n.id}
                      className="border border-border bg-card p-3"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="text-xs font-semibold leading-snug">
                            {n.title}
                          </p>
                          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                            {n.source || "Tavily"} ·{" "}
                            {n.related_asset
                              ? n.related_asset.toUpperCase()
                              : "GENERAL"}
                          </p>
                        </div>
                        {n.signal && (
                          <span
                            className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] ${n.signal.sentiment === "positive" ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400" : n.signal.sentiment === "negative" ? "bg-rose-50 text-rose-600 dark:bg-rose-950 dark:text-rose-400" : "bg-muted text-muted-foreground"}`}
                          >
                            {n.signal.sentiment}{" "}
                            {n.signal.impact_score >= 0 ? "+" : ""}
                            {Number(n.signal.impact_score).toFixed(2)}
                          </span>
                        )}
                      </div>
                      {n.signal?.reasoning && (
                        <p className="mt-2 text-[11px] text-muted-foreground">
                          {n.signal.reasoning}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}
            {route === "/data-sources" && (
              <Section eyebrow="Connector health" title={title}>
                <div className="grid gap-3 md:grid-cols-2">
                  {[
                    "NIFTY Market Feed",
                    "Gold Market Feed",
                    "USD/INR Feed",
                    "NewsAPI Feed",
                    "Tavily Agent Feed",
                    "Groq Decision Engine",
                  ].map((n, i) => (
                    <div key={n} className="border border-border bg-card p-4">
                      <div className="flex justify-between">
                        <p className="text-sm font-semibold">{n}</p>
                        <span className="font-mono text-[10px] text-emerald-500">
                          CONNECTED
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Latency 84ms · Reliability 96%
                      </p>
                    </div>
                  ))}
                </div>
              </Section>
            )}
            {route === "/settings" && (
              <Section eyebrow="Workspace configuration" title={title}>
                <div className="grid gap-3 md:grid-cols-2">
                  {[
                    "General",
                    "Markets",
                    "Risk",
                    "Notifications",
                    "Agent",
                    "Appearance",
                  ].map((n) => (
                    <div key={n} className="border border-border bg-card p-4">
                      <div className="flex justify-between">
                        <p className="text-sm font-semibold">{n}</p>
                        <span className="font-mono text-[10px] text-emerald-500">
                          Configured
                        </span>
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Manage preferences
                      </p>
                      <button className="mt-4 text-xs text-primary">
                        Configure <ChevronRight className="inline size-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </Section>
            )}
            {/* The old Selected asset section was moved and redesigned. */}
            <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              <span className="flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-emerald-500" /> Data
                feed connected · 3 sources
              </span>
              <span>Last sync 14:32:08 IST</span>
              <span>Paper trading mode</span>
            </div>
          </div>
        </main>
      </div>
      {search && (
        <div
          className="fixed inset-0 z-40 bg-foreground/20 p-4 pt-24"
          onClick={() => setSearch(false)}
        >
          <div
            className="mx-auto max-w-lg border border-border bg-popover shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 border-b border-border p-4">
              <Search className="size-4 text-muted-foreground" />
              <input
                autoFocus
                placeholder="Search assets, decisions, scenarios..."
                className="flex-1 bg-transparent text-sm outline-none"
              />
              <button onClick={() => setSearch(false)}>
                <X className="size-4" />
              </button>
            </div>
            <div className="p-3">
              {[
                "NIFTY 50",
                "Decision #144",
                "Liquidity breakdown",
                "Risk center",
              ].map((x) => (
                <button
                  key={x}
                  onClick={() => setSearch(false)}
                  className="flex w-full items-center gap-3 p-2 text-left text-xs hover:bg-muted"
                >
                  <Command className="size-3.5 text-muted-foreground" />
                  {x}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      {notifications && (
        <div className="fixed right-4 top-16 z-40 w-80 border border-border bg-popover p-4 shadow-xl">
          <div className="flex justify-between text-sm font-semibold">
            Notifications{" "}
            <button onClick={() => setNotifications(false)}>
              <X className="size-4" />
            </button>
          </div>
          <div className="mt-4 border-t border-border pt-3 text-xs">
            <span className="text-amber-500">Decision changed</span>
            <p className="mt-1 text-muted-foreground">
              NIFTY HOLD → WATCH · 27 sec ago
            </p>
            <p className="mt-2">Liquidity deteriorated.</p>
          </div>
        </div>
      )}
      {stop && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/25 p-4">
          <div
            role="dialog"
            aria-modal="true"
            className="w-full max-w-sm border border-border bg-popover p-5 shadow-xl"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-1 size-5 text-destructive" />
              <div>
                <h2 className="text-sm font-semibold">
                  Emergency stop simulation?
                </h2>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  This pauses simulated execution while observation and analysis
                  continue.
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setStop(false)}
                className="border border-border px-3 py-2 text-xs"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setStream(false);
                  setStop(false);
                }}
                className="bg-destructive px-3 py-2 text-xs text-destructive-foreground"
              >
                Confirm stop
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export { AxiomDashboard };
