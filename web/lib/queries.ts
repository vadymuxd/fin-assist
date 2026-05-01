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
  suggested_action: string | null;
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
  // Show BUY discoveries from the last 7 days, deduplicated by ticker (newest first).
  // The new alert_dispatcher only logs BUY-worthy prospects, so no PASS/filtered noise.
  const { data: latest, error: le } = await supabase
    .from("discoveries")
    .select("run_time")
    .order("run_time", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (le) throw le;
  if (!latest) return { run_time: "", items: [] };

  const { data, error } = await supabase
    .from("discoveries")
    .select("*")
    .eq("recommendation", "BUY")
    .gte("run_time", daysAgoISO(7))
    .order("run_time", { ascending: false })
    .limit(60);
  if (error) throw error;

  // Dedup by ticker: keep most recent BUY per ticker
  const seen = new Set<string>();
  const items = (data ?? []).filter((d) => {
    if (seen.has(d.ticker)) return false;
    seen.add(d.ticker);
    return true;
  }).sort((a, b) => (b.score ?? 0) - (a.score ?? 0));

  return { run_time: latest.run_time, items };
}

export async function getRecentAlerts(limit = 20): Promise<HoldingsAlert[]> {
  // Fetch recent ACT-level alerts from the last 7 days, deduplicated by ticker
  // (only the most recent alert per ticker is shown — no duplicate rows for the same stock)
  const { data, error } = await supabase
    .from("holdings_alerts")
    .select("*")
    .eq("alert_level", "ACT")
    .not("suggested_action", "is", null)
    .gte("run_time", daysAgoISO(7))
    .order("run_time", { ascending: false })
    .limit(limit * 3); // over-fetch so dedup has enough to work with
  if (error) throw error;
  const seen = new Set<string>();
  return (data ?? []).filter((a) => {
    if (seen.has(a.ticker)) return false;
    seen.add(a.ticker);
    return true;
  }).slice(0, limit);
}

export async function getLatestAlertsRun(): Promise<{ run_time: string; items: HoldingsAlert[] }> {
  // Most recent dispatch run_time (used for the "Latest run · X ago" header)
  const { data: latest, error: le } = await supabase
    .from("holdings_alerts")
    .select("run_time")
    .order("run_time", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (le) throw le;
  if (!latest) return { run_time: "", items: [] };

  // Items = same 7-day deduped set as getRecentAlerts (drives the count in alerts-list header)
  const { data, error } = await supabase
    .from("holdings_alerts")
    .select("*")
    .eq("alert_level", "ACT")
    .not("suggested_action", "is", null)
    .gte("run_time", daysAgoISO(7))
    .order("run_time", { ascending: false })
    .limit(60);
  if (error) throw error;
  const seen = new Set<string>();
  const items = (data ?? []).filter((a) => {
    if (seen.has(a.ticker)) return false;
    seen.add(a.ticker);
    return true;
  });
  return { run_time: latest.run_time, items };
}

const NEWS_FRESH_DAYS = 14;

function freshNewsCutoffISO(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - NEWS_FRESH_DAYS);
  return d.toISOString();
}

export async function getRecentNews(limit = 40): Promise<NewsItem[]> {
  const { data, error } = await supabase
    .from("news_items")
    .select("id, published_at, tickers, source, title, url, image_url, snippet, sentiment")
    .eq("source_type", "per_holding")
    .gte("published_at", freshNewsCutoffISO())
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
    .eq("source_type", "per_holding")
    .overlaps("tickers", tickers)
    .gte("published_at", freshNewsCutoffISO())
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

// ─── Savings ─────────────────────────────────────────────────────────────────

/** Vadym owns 50% of any joint account — partner owns the other half */
export const JOINT_SHARE = 0.5;

/** Effective savings total attributable to Vadym (personal + half of joint) */
export function effectiveSavingsTotal(s: SavingsSnapshot): number {
  return s.personal_total + s.joint_total * JOINT_SHARE;
}

export type SavingsSnapshot = {
  date: string;
  total: number;
  personal_total: number;
  joint_total: number;
};

export type SavingsAccount = {
  id: number;
  date: string;
  bank: string;
  account_name: string;
  account_type: string | null;
  owner: string;
  balance_gbp: number;
};

export type SavingsDelta = { absolute: number; pct: number; fromDate: string };

export type SavingsDeltasResult = {
  latest: SavingsSnapshot;
  baselineDate: string;
  daily: SavingsDelta | null;
  wow: SavingsDelta | null;
  mom: SavingsDelta | null;
  sinceStart: SavingsDelta | null;
};

export async function getSavingsSnapshots(): Promise<SavingsSnapshot[]> {
  const { data, error } = await supabase
    .from("savings_snapshots")
    .select("date, total, personal_total, joint_total")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export async function getSavingsAccounts(): Promise<SavingsAccount[]> {
  const latest = await supabase
    .from("savings_snapshots")
    .select("date")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!latest.data) return [];
  const { data, error } = await supabase
    .from("savings_accounts")
    .select("id, date, bank, account_name, account_type, owner, balance_gbp")
    .eq("date", latest.data.date)
    .order("balance_gbp", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

function savingsDelta(
  latest: SavingsSnapshot,
  prev: SavingsSnapshot | null,
): SavingsDelta | null {
  if (!prev) return null;
  const latestEff = effectiveSavingsTotal(latest);
  const prevEff = effectiveSavingsTotal(prev);
  const absolute = latestEff - prevEff;
  const pct = prevEff === 0 ? 0 : (absolute / prevEff) * 100;
  return { absolute, pct, fromDate: prev.date };
}

function findSavingsOnOrBefore(
  snapshots: SavingsSnapshot[],
  targetISO: string,
): SavingsSnapshot | null {
  const candidates = snapshots.filter((s) => s.date <= targetISO);
  return candidates.length === 0 ? null : candidates[candidates.length - 1];
}

export function computeSavingsDeltas(
  snapshots: SavingsSnapshot[],
): SavingsDeltasResult | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const baseline = sorted[0];
  const prior = sorted.slice(0, -1);
  const daily = sorted.length >= 2 ? savingsDelta(latest, sorted[sorted.length - 2]) : null;
  const wow = savingsDelta(latest, findSavingsOnOrBefore(prior, daysAgoISO(7)));
  const mom30 = findSavingsOnOrBefore(prior, daysAgoISO(30));
  const mom = savingsDelta(latest, mom30 ?? (prior.length > 0 ? prior[0] : null));
  const sinceStart = baseline.date !== latest.date ? savingsDelta(latest, baseline) : null;
  return { latest, baselineDate: baseline.date, daily, wow, mom, sinceStart };
}

// ─── Pensions ─────────────────────────────────────────────────────────────────

export type PensionSnapshot = {
  date: string;
  total: number;
};

export type PensionAccount = {
  id: number;
  date: string;
  provider: string;
  account_name: string;
  account_type: string | null;
  balance_gbp: number;
};

export type PensionDelta = { absolute: number; pct: number; fromDate: string };

export type PensionDeltasResult = {
  latest: PensionSnapshot;
  baselineDate: string;
  daily: PensionDelta | null;
  wow: PensionDelta | null;
  mom: PensionDelta | null;
  sinceStart: PensionDelta | null;
};

export async function getPensionSnapshots(): Promise<PensionSnapshot[]> {
  const { data, error } = await supabase
    .from("pension_snapshots")
    .select("date, total")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export async function getPensionAccounts(): Promise<PensionAccount[]> {
  const latest = await supabase
    .from("pension_snapshots")
    .select("date")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!latest.data) return [];
  const { data, error } = await supabase
    .from("pension_accounts")
    .select("id, date, provider, account_name, account_type, balance_gbp")
    .eq("date", latest.data.date)
    .order("balance_gbp", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

function pensionDelta(latest: PensionSnapshot, prev: PensionSnapshot | null): PensionDelta | null {
  if (!prev) return null;
  const absolute = latest.total - prev.total;
  const pct = prev.total === 0 ? 0 : (absolute / prev.total) * 100;
  return { absolute, pct, fromDate: prev.date };
}

function findPensionOnOrBefore(snapshots: PensionSnapshot[], targetISO: string): PensionSnapshot | null {
  const candidates = snapshots.filter((s) => s.date <= targetISO);
  return candidates.length === 0 ? null : candidates[candidates.length - 1];
}

export function computePensionDeltas(snapshots: PensionSnapshot[]): PensionDeltasResult | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const baseline = sorted[0];
  const latest = sorted[sorted.length - 1];
  const prior = sorted.slice(0, -1);
  const daily = sorted.length >= 2 ? pensionDelta(latest, sorted[sorted.length - 2]) : null;
  const wow = pensionDelta(latest, findPensionOnOrBefore(prior, daysAgoISO(7)));
  const mom30 = findPensionOnOrBefore(prior, daysAgoISO(30));
  const mom = pensionDelta(latest, mom30 ?? (prior.length > 0 ? prior[0] : null));
  const sinceStart = baseline.date !== latest.date ? pensionDelta(latest, baseline) : null;
  return { latest, baselineDate: baseline.date, daily, wow, mom, sinceStart };
}

// ─── Mortgage ─────────────────────────────────────────────────────────────────

export type MortgageSnapshot = {
  date: string;
  balance: number;
  property_value: number;
  equity: number;
  equity_half: number;
  monthly_payment: number;
  rate: number;
  lender: string;
};

export type MortgageDelta = { absolute: number; pct: number; fromDate: string };

export type MortgageDeltasResult = {
  latest: MortgageSnapshot;
  mom: MortgageDelta | null;
  ytd: MortgageDelta | null;
  sinceStart: MortgageDelta | null;
};

export async function getMortgageSnapshots(): Promise<MortgageSnapshot[]> {
  const { data, error } = await supabase
    .from("mortgage_snapshots")
    .select("date, balance, property_value, equity, equity_half, monthly_payment, rate, lender")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

function findMortgageOnOrBefore(
  snapshots: MortgageSnapshot[],
  targetISO: string,
): MortgageSnapshot | null {
  const c = snapshots.filter((s) => s.date <= targetISO);
  return c.length === 0 ? null : c[c.length - 1];
}

function mortgageDelta(
  latest: MortgageSnapshot,
  prev: MortgageSnapshot | null,
): MortgageDelta | null {
  if (!prev) return null;
  // Delta is on equity (the positive metric building over time)
  const absolute = latest.equity_half - prev.equity_half;
  const pct = prev.equity_half === 0 ? 0 : (absolute / prev.equity_half) * 100;
  return { absolute, pct, fromDate: prev.date };
}

export function computeMortgageDeltas(
  snapshots: MortgageSnapshot[],
): MortgageDeltasResult | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const first = sorted[0];
  const prior = sorted.slice(0, -1);
  const mom = mortgageDelta(latest, findMortgageOnOrBefore(prior, daysAgoISO(30)));
  const yearStart = `${new Date().getUTCFullYear()}-01-01`;
  const ytd = mortgageDelta(latest, findMortgageOnOrBefore(prior, yearStart));
  const sinceStart = first.date !== latest.date ? mortgageDelta(latest, first) : null;
  return { latest, mom, ytd, sinceStart };
}

// ─── Net Worth ────────────────────────────────────────────────────────────────

export type NetWorthPoint = {
  date: string;
  net_worth: number;
  investments: number;
  savings: number;
  pensions: number;
  mortgage_equity: number;
};

export async function getNetWorthData(): Promise<NetWorthPoint[]> {
  const [{ data: inv }, { data: sav }, { data: pen }, { data: mort }] = await Promise.all([
    supabase.from("portfolio_snapshots").select("date, grand_total").order("date", { ascending: true }),
    supabase.from("savings_snapshots").select("date, total, personal_total, joint_total").order("date", { ascending: true }),
    supabase.from("pension_snapshots").select("date, total").order("date", { ascending: true }),
    supabase.from("mortgage_snapshots").select("date, equity_half").order("date", { ascending: true }),
  ]);
  if (!inv || !inv.length) return [];
  // Key off portfolio_snapshots (most frequent — daily). For each investment date,
  // find the latest savings, pension, and mortgage snapshot on or before that date.
  // Falls back to the earliest available record if all data is after the target date,
  // so components that were added to the app later don't create a fake spike in net worth.
  function latestOnOrBefore<T extends { date: string }>(arr: T[] | null, date: string): T | null {
    if (!arr || arr.length === 0) return null;
    const c = arr.filter((r) => r.date <= date);
    return c.length > 0 ? c[c.length - 1] : arr[0];
  }
  return inv.map((i) => {
    const savRow = latestOnOrBefore(sav, i.date);
    const savingsEff = savRow ? effectiveSavingsTotal(savRow as SavingsSnapshot) : 0;
    const penRow = latestOnOrBefore(pen, i.date);
    const pensionTotal = penRow ? Number(penRow.total) : 0;
    const mortRow = latestOnOrBefore(mort, i.date);
    const mortgageEquity = mortRow ? Number(mortRow.equity_half) : 0;
    return {
      date: i.date,
      investments: i.grand_total,
      savings: savingsEff,
      pensions: pensionTotal,
      mortgage_equity: mortgageEquity,
      net_worth: i.grand_total + savingsEff + pensionTotal + mortgageEquity,
    };
  });
}

// ─────────────────────────────────────────────────────────────────────────────

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
  const mom30 = findClosestOnOrBefore(prior, daysAgoISO(30));
  const mom = delta(latest, mom30 ?? (prior.length > 0 ? prior[0] : null));
  const yearStart = `${new Date().getUTCFullYear()}-01-01`;
  const ytd = delta(latest, findClosestOnOrBefore(prior, yearStart));
  return { latest, baselineDate: baseline.date, daily, sinceBaseline, wow, mom, ytd };
}
