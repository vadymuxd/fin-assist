import { supabase } from "./supabase";

export type Holding = {
  ticker: string;
  name: string | null;
  platform: string | null;
  qty: number | null;
  avg_buy: number | null;
  current_price: number | null;
  value_gbp: number | null;
  pnl_abs: number | null;
  pnl_pct: number | null;
  sector: string | null;
  market: string | null;
  last_updated: string | null;
};

export type PortfolioSnapshot = {
  date: string;
  grand_total: number;
  self_managed: number;
  managed: number;
  cash: number;
  net_deposits: number;
  spx: number | null;
  ftse: number | null;
  ndx: number | null;
  msci: number | null;
  gold: number | null;
};

export type SectorLookup = {
  ticker: string;
  sector: string | null;
  market: string | null;
};

export type NewsItem = {
  id: string;
  published_at: string | null;
  tickers: string[] | null;
  source: string | null;
  title: string | null;
  url: string | null;
  image_url: string | null;
  snippet: string | null;
  sentiment: string | null;
};

export type HoldingsAlert = {
  id: number;
  run_id: string;
  run_time: string;
  ticker: string;
  alert_level: string;
  score: number | null;
  event: string | null;
  rationale: string | null;
};

export async function getPortfolioSnapshots(): Promise<PortfolioSnapshot[]> {
  const { data, error } = await supabase
    .from("portfolio_snapshots")
    .select("date, grand_total, self_managed, managed, cash, net_deposits, spx, ftse, ndx, msci, gold")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot | null> {
  const { data, error } = await supabase
    .from("portfolio_snapshots")
    .select("date, grand_total, self_managed, managed, cash, net_deposits, spx, ftse, ndx, msci, gold")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export async function getHoldings(): Promise<Holding[]> {
  const { data, error } = await supabase
    .from("holdings")
    .select("*")
    .order("ticker");
  if (error) throw error;
  return data ?? [];
}

export async function getSectors(): Promise<SectorLookup[]> {
  const { data, error } = await supabase.from("sectors").select("ticker, sector, market");
  if (error) throw error;
  return data ?? [];
}

export async function getHoldingByTicker(ticker: string): Promise<Holding | null> {
  const [{ data: h, error: he }, { data: s }] = await Promise.all([
    supabase.from("holdings").select("*").eq("ticker", ticker).maybeSingle(),
    supabase.from("sectors").select("sector, market").eq("ticker", ticker).maybeSingle(),
  ]);
  if (he) throw he;
  if (!h) return null;
  return {
    ...h,
    sector: h.sector ?? s?.sector ?? null,
    market: h.market ?? s?.market ?? null,
  };
}

export async function getNewsForTicker(ticker: string, limit = 10): Promise<NewsItem[]> {
  const { data, error } = await supabase
    .from("news_items")
    .select("id, published_at, tickers, source, title, url, image_url, snippet, sentiment")
    .contains("tickers", [ticker])
    .order("published_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export async function getLatestAlertForTicker(ticker: string): Promise<HoldingsAlert | null> {
  const { data, error } = await supabase
    .from("holdings_alerts")
    .select("*")
    .eq("ticker", ticker)
    .order("run_time", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export type Discovery = {
  id: number;
  run_id: string;
  run_time: string;
  ticker: string;
  score: number | null;
  recommendation: string | null;
  sources: string[] | null;
  rationale: string | null;
  filtered_reason: string | null;
  surfaced_to_telegram: boolean | null;
};

export async function getLatestDiscoveries(): Promise<{ run_time: string; items: Discovery[] }> {
  // find the most recent run_id
  const { data: latest, error: le } = await supabase
    .from("discoveries")
    .select("run_id, run_time")
    .order("run_time", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (le) throw le;
  if (!latest) return { run_time: "", items: [] };

  const { data, error } = await supabase
    .from("discoveries")
    .select("*")
    .eq("run_id", latest.run_id)
    .order("score", { ascending: false });
  if (error) throw error;
  return { run_time: latest.run_time, items: data ?? [] };
}

export async function getRecentAlerts(limit = 20): Promise<HoldingsAlert[]> {
  const { data, error } = await supabase
    .from("holdings_alerts")
    .select("*")
    .in("alert_level", ["ACT", "WATCH"])
    .order("run_time", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export async function getLatestAlertsRun(): Promise<{ run_time: string; items: HoldingsAlert[] }> {
  const { data: latest, error: le } = await supabase
    .from("holdings_alerts")
    .select("run_id, run_time")
    .order("run_time", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (le) throw le;
  if (!latest) return { run_time: "", items: [] };
  const { data, error } = await supabase
    .from("holdings_alerts")
    .select("*")
    .eq("run_id", latest.run_id)
    .order("alert_level", { ascending: true });
  if (error) throw error;
  return { run_time: latest.run_time, items: data ?? [] };
}

export async function getRecentNews(limit = 40): Promise<NewsItem[]> {
  const { data, error } = await supabase
    .from("news_items")
    .select("id, published_at, tickers, source, title, url, image_url, snippet, sentiment")
    .order("published_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export async function getNewsForHoldings(tickers: string[], limit = 40): Promise<NewsItem[]> {
  if (tickers.length === 0) return getRecentNews(limit);
  const { data, error } = await supabase
    .from("news_items")
    .select("id, published_at, tickers, source, title, url, image_url, snippet, sentiment")
    .overlaps("tickers", tickers)
    .order("published_at", { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data ?? [];
}

export async function getHoldingTickers(): Promise<string[]> {
  const { data, error } = await supabase.from("holdings").select("ticker");
  if (error) throw error;
  return (data ?? []).map((h) => h.ticker);
}

export async function getHoldingsWithSectors(): Promise<Holding[]> {
  const [holdings, sectors] = await Promise.all([getHoldings(), getSectors()]);
  const lookup = new Map(sectors.map((s) => [s.ticker, s]));
  return holdings.map((h) => {
    const match = lookup.get(h.ticker);
    return {
      ...h,
      sector: h.sector ?? match?.sector ?? null,
      market: h.market ?? match?.market ?? null,
    };
  });
}

export type Delta = { absolute: number; pct: number; fromDate: string };

export type DashboardDeltas = {
  latest: PortfolioSnapshot;
  baselineDate: string;
  daily: Delta | null;
  wow: Delta | null;
  mom: Delta | null;
  ytd: Delta | null;
  sinceBaseline: Delta | null;
};

function daysAgoISO(days: number): string {
  const d = new Date();
  d.setUTCHours(0, 0, 0, 0);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function findClosestOnOrBefore(
  snapshots: PortfolioSnapshot[],
  targetISO: string
): PortfolioSnapshot | null {
  const candidates = snapshots.filter((s) => s.date <= targetISO);
  if (candidates.length === 0) return null;
  return candidates[candidates.length - 1];
}

function delta(latest: PortfolioSnapshot, prev: PortfolioSnapshot | null) {
  if (!prev) return null;
  const absolute = latest.grand_total - prev.grand_total;
  const pct = prev.grand_total === 0 ? 0 : (absolute / prev.grand_total) * 100;
  return { absolute, pct, fromDate: prev.date };
}

export function computeDeltas(snapshots: PortfolioSnapshot[]): DashboardDeltas | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const baseline = sorted[0];
  const prior = sorted.slice(0, -1);
  const daily = sorted.length >= 2 ? delta(latest, sorted[sorted.length - 2]) : null;
  const sinceBaseline = baseline.date !== latest.date ? delta(latest, baseline) : null;
  const wow = delta(latest, findClosestOnOrBefore(prior, daysAgoISO(7)));
  const mom = delta(latest, findClosestOnOrBefore(prior, daysAgoISO(30)));
  const yearStart = `${new Date().getUTCFullYear()}-01-01`;
  const ytd = delta(latest, findClosestOnOrBefore(prior, yearStart));
  return { latest, baselineDate: baseline.date, daily, sinceBaseline, wow, mom, ytd };
}
