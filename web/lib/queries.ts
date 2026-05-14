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
  vadym_total: number;
  lisa_total: number | null;
  joint_total: number | null;
  self_managed: number;
  /**
   * Sum of each held stock's "Tracking Started Value" (sheet col I).
   * Anchor for organic stocks performance: self_managed / stocks_started_value - 1.
   * Insulated from new BUYs because cost basis is added to both sides equally.
   */
  stocks_started_value: number | null;
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
    .select("date, vadym_total, lisa_total, joint_total, self_managed, stocks_started_value, managed, cash, net_deposits, spx, ftse, ndx, msci, gold")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot | null> {
  const { data, error } = await supabase
    .from("portfolio_snapshots")
    .select("date, vadym_total, lisa_total, joint_total, self_managed, stocks_started_value, managed, cash, net_deposits, spx, ftse, ndx, msci, gold")
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
  return s.vadym_total + s.joint_total * JOINT_SHARE;
}

export type SavingsSnapshot = {
  date: string;
  total: number;
  vadym_total: number;
  lisa_total: number | null;
  joint_total: number;
  updated_at: string;
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
  // Vadym personal
  daily: SavingsDelta | null;
  wow: SavingsDelta | null;
  mom: SavingsDelta | null;
  sinceStart: SavingsDelta | null;
  // Lisa
  lisaDaily: SavingsDelta | null;
  lisaWow: SavingsDelta | null;
  lisaMom: SavingsDelta | null;
  lisaSinceStart: SavingsDelta | null;
  // Joint full (not halved)
  jointDaily: SavingsDelta | null;
  jointWow: SavingsDelta | null;
  jointMom: SavingsDelta | null;
  jointSinceStart: SavingsDelta | null;
  // Total (all three combined)
  totalDaily: SavingsDelta | null;
  totalWow: SavingsDelta | null;
  totalMom: SavingsDelta | null;
  totalSinceStart: SavingsDelta | null;
};

export async function getSavingsSnapshots(): Promise<SavingsSnapshot[]> {
  const { data, error } = await supabase
    .from("savings_snapshots")
    .select("date, total, vadym_total, lisa_total, joint_total, updated_at")
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

function savingsDeltaField(
  latest: SavingsSnapshot,
  prev: SavingsSnapshot | null,
  getVal: (s: SavingsSnapshot) => number,
): SavingsDelta | null {
  if (!prev) return null;
  const latestVal = getVal(latest);
  const prevVal = getVal(prev);
  const absolute = latestVal - prevVal;
  const pct = prevVal === 0 ? 0 : (absolute / prevVal) * 100;
  return { absolute, pct, fromDate: prev.date };
}

function findOnOrBefore<T extends { date: string }>(snapshots: T[], targetISO: string): T | null {
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
  const prev1 = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const wowSnap = findOnOrBefore(prior, daysAgoISO(7));
  const momSnap = findOnOrBefore(prior, daysAgoISO(30));
  const momFallback = prior.length > 0 ? prior[0] : null;

  function ownerDeltas(getVal: (s: SavingsSnapshot) => number) {
    const daily = prev1 ? savingsDeltaField(latest, prev1, getVal) : null;
    const wowDelta = savingsDeltaField(latest, wowSnap, getVal);
    const wow = wowDelta ? { ...wowDelta, fromDate: daysAgoISO(7) } : null;
    const mom = savingsDeltaField(latest, momSnap ?? momFallback, getVal);
    const sinceStart = baseline.date !== latest.date ? savingsDeltaField(latest, baseline, getVal) : null;
    return { daily, wow, mom, sinceStart };
  }

  const vadym = ownerDeltas((s) => s.vadym_total);
  const lisa  = ownerDeltas((s) => s.lisa_total ?? 0);
  const joint = ownerDeltas((s) => s.joint_total);
  const total = ownerDeltas((s) => s.vadym_total + (s.lisa_total ?? 0) + s.joint_total);

  return {
    latest,
    baselineDate: baseline.date,
    daily: vadym.daily, wow: vadym.wow, mom: vadym.mom, sinceStart: vadym.sinceStart,
    lisaDaily: lisa.daily, lisaWow: lisa.wow, lisaMom: lisa.mom, lisaSinceStart: lisa.sinceStart,
    jointDaily: joint.daily, jointWow: joint.wow, jointMom: joint.mom, jointSinceStart: joint.sinceStart,
    totalDaily: total.daily, totalWow: total.wow, totalMom: total.mom, totalSinceStart: total.sinceStart,
  };
}

// ─── Pensions ─────────────────────────────────────────────────────────────────

export type PensionSnapshot = {
  date: string;
  total: number;
  vadym_total: number;
  lisa_total: number | null;
  updated_at: string;
};

export type PensionAccount = {
  id: number;
  date: string;
  provider: string;
  account_name: string;
  account_type: string | null;
  balance_gbp: number;
  owner: string;
};

export type PensionDelta = { absolute: number; pct: number; fromDate: string };

export type PensionDeltasResult = {
  latest: PensionSnapshot;
  baselineDate: string;
  // Joint (vadym+lisa combined)
  daily: PensionDelta | null;
  wow: PensionDelta | null;
  mom: PensionDelta | null;
  sinceStart: PensionDelta | null;
  // Vadym
  vadymDaily: PensionDelta | null;
  vadymWow: PensionDelta | null;
  vadymMom: PensionDelta | null;
  vadymSinceStart: PensionDelta | null;
  // Lisa
  lisaDaily: PensionDelta | null;
  lisaWow: PensionDelta | null;
  lisaMom: PensionDelta | null;
  lisaSinceStart: PensionDelta | null;
};

export async function getPensionSnapshots(): Promise<PensionSnapshot[]> {
  const { data, error } = await supabase
    .from("pension_snapshots")
    .select("date, total, vadym_total, lisa_total, updated_at")
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
    .select("id, date, provider, account_name, account_type, owner, balance_gbp")
    .eq("date", latest.data.date)
    .order("balance_gbp", { ascending: false });
  if (error) throw error;
  return data ?? [];
}

function pensionDeltaField(
  latest: PensionSnapshot,
  prev: PensionSnapshot | null,
  getVal: (s: PensionSnapshot) => number,
): PensionDelta | null {
  if (!prev) return null;
  const latestVal = getVal(latest);
  const prevVal = getVal(prev);
  const absolute = latestVal - prevVal;
  const pct = prevVal === 0 ? 0 : (absolute / prevVal) * 100;
  return { absolute, pct, fromDate: prev.date };
}

export function computePensionDeltas(snapshots: PensionSnapshot[]): PensionDeltasResult | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const baseline = sorted[0];
  const latest = sorted[sorted.length - 1];
  const prior = sorted.slice(0, -1);
  const prev1 = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  const wowSnap = findOnOrBefore(prior, daysAgoISO(7));
  const momSnap = findOnOrBefore(prior, daysAgoISO(30));
  const momFallback = prior.length > 0 ? prior[0] : null;

  function ownerDeltas(getVal: (s: PensionSnapshot) => number) {
    const d = prev1 ? pensionDeltaField(latest, prev1, getVal) : null;
    const wowDelta = pensionDeltaField(latest, wowSnap, getVal);
    const w = wowDelta ? { ...wowDelta, fromDate: daysAgoISO(7) } : null;
    const m = pensionDeltaField(latest, momSnap ?? momFallback, getVal);
    const ss = baseline.date !== latest.date ? pensionDeltaField(latest, baseline, getVal) : null;
    return { daily: d, wow: w, mom: m, sinceStart: ss };
  }

  const joint = ownerDeltas((s) => s.total);
  const vadym = ownerDeltas((s) => s.vadym_total);
  const lisa  = ownerDeltas((s) => s.lisa_total ?? 0);

  return {
    latest, baselineDate: baseline.date,
    daily: joint.daily, wow: joint.wow, mom: joint.mom, sinceStart: joint.sinceStart,
    vadymDaily: vadym.daily, vadymWow: vadym.wow, vadymMom: vadym.mom, vadymSinceStart: vadym.sinceStart,
    lisaDaily: lisa.daily, lisaWow: lisa.wow, lisaMom: lisa.mom, lisaSinceStart: lisa.sinceStart,
  };
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
  updated_at: string;
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
    .select("date, balance, property_value, equity, equity_half, monthly_payment, rate, lender, updated_at")
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
    supabase.from("portfolio_snapshots").select("date, vadym_total, joint_total").order("date", { ascending: true }),
    supabase.from("savings_snapshots").select("date, total, vadym_total, lisa_total, joint_total").order("date", { ascending: true }),
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
      investments: i.vadym_total,
      savings: savingsEff,
      pensions: pensionTotal,
      mortgage_equity: mortgageEquity,
      net_worth: i.vadym_total + savingsEff + pensionTotal + mortgageEquity,
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
  // Vadym
  daily: Delta | null;
  wow: Delta | null;
  mom: Delta | null;
  ytd: Delta | null;
  sinceBaseline: Delta | null;
  // Lisa
  lisaDaily: Delta | null;
  lisaWow: Delta | null;
  lisaMom: Delta | null;
  lisaSinceBaseline: Delta | null;
  // Joint
  jointDaily: Delta | null;
  jointWow: Delta | null;
  jointMom: Delta | null;
  jointSinceBaseline: Delta | null;
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

function delta(latest: PortfolioSnapshot, prev: PortfolioSnapshot | null): Delta | null {
  if (!prev) return null;
  const absolute = latest.vadym_total - prev.vadym_total;
  // % is organic stocks P&L only: strip the change in tracking-started value
  // (which moves when positions are added or sold) from the numerator. New
  // BUYs add equal £ to self_managed AND stocks_started_value, so they cancel.
  const ls = latest.stocks_started_value ?? 0;
  const ps = prev.stocks_started_value ?? 0;
  const stockBasisChange = ls - ps;
  const stockValueChange = latest.self_managed - prev.self_managed;
  const pct = prev.self_managed === 0 ? 0 : ((stockValueChange - stockBasisChange) / prev.self_managed) * 100;
  return { absolute, pct, fromDate: prev.date };
}

function deltaField(
  latest: PortfolioSnapshot,
  prev: PortfolioSnapshot | null,
  field: "lisa_total" | "joint_total",
): Delta | null {
  if (!prev) return null;
  const latestVal = latest[field] ?? 0;
  const prevVal = prev[field] ?? 0;
  if (prevVal === 0) return null;
  const absolute = latestVal - prevVal;
  const pct = (absolute / prevVal) * 100;
  return { absolute, pct, fromDate: prev.date };
}

export function computeDeltas(snapshots: PortfolioSnapshot[]): DashboardDeltas | null {
  if (snapshots.length === 0) return null;
  const sorted = [...snapshots].sort((a, b) => a.date.localeCompare(b.date));
  const latest = sorted[sorted.length - 1];
  const baseline = sorted[0];
  const prior = sorted.slice(0, -1);
  const prev7 = findClosestOnOrBefore(prior, daysAgoISO(7));
  const prev30 = findClosestOnOrBefore(prior, daysAgoISO(30));
  const prevFallback = prior.length > 0 ? prior[0] : null;

  const daily = sorted.length >= 2 ? delta(latest, sorted[sorted.length - 2]) : null;
  const sinceBaseline = baseline.date !== latest.date ? delta(latest, baseline) : null;
  const wow = delta(latest, prev7);
  const mom = delta(latest, prev30 ?? prevFallback);
  const yearStart = `${new Date().getUTCFullYear()}-01-01`;
  const ytd = delta(latest, findClosestOnOrBefore(prior, yearStart));

  const lisaDaily = sorted.length >= 2 ? deltaField(latest, sorted[sorted.length - 2], "lisa_total") : null;
  const lisaWow = deltaField(latest, prev7, "lisa_total");
  const lisaMom = deltaField(latest, prev30 ?? prevFallback, "lisa_total");
  const lisaSinceBaseline = baseline.date !== latest.date ? deltaField(latest, baseline, "lisa_total") : null;

  const jointDaily = sorted.length >= 2 ? deltaField(latest, sorted[sorted.length - 2], "joint_total") : null;
  const jointWow = deltaField(latest, prev7, "joint_total");
  const jointMom = deltaField(latest, prev30 ?? prevFallback, "joint_total");
  const jointSinceBaseline = baseline.date !== latest.date ? deltaField(latest, baseline, "joint_total") : null;

  return {
    latest, baselineDate: baseline.date,
    daily, sinceBaseline, wow, mom, ytd,
    lisaDaily, lisaWow, lisaMom, lisaSinceBaseline,
    jointDaily, jointWow, jointMom, jointSinceBaseline,
  };
}

// ─── Performance Comparison ───────────────────────────────────────────────────

export type ComparisonPoint = {
  date: string;
  customStocks: number;
  managed: number | null;
  spx: number | null;
  pensions: number | null;
  lisa: number | null;
};

export function buildComparisonData(
  portfolioSnapshots: PortfolioSnapshot[],
  pensionSnapshots: PensionSnapshot[],
): ComparisonPoint[] {
  if (portfolioSnapshots.length === 0) return [];
  const sorted = [...portfolioSnapshots].sort((a, b) => a.date.localeCompare(b.date));
  const sortedPensions = [...pensionSnapshots].sort((a, b) => a.date.localeCompare(b.date));
  const base = sorted[0];
  const baseSpx = sorted.find((s) => s.spx != null && s.spx > 0)?.spx ?? null;
  const basePension = sortedPensions.find((s) => s.total > 0)?.total ?? null;
  const baseLisa = sorted.find((s) => s.lisa_total != null && s.lisa_total > 0)?.lisa_total ?? null;
  // Anchor Custom Stocks to its own organic ratio at baseline (∼1.0 on tracking
  // start) so the line shows organic stocks performance, not cost-basis growth.
  const baseStockRatio =
    base.stocks_started_value && base.stocks_started_value > 0
      ? base.self_managed / base.stocks_started_value
      : null;
  return sorted.map((s) => {
    const pensionRow = sortedPensions.filter((p) => p.date <= s.date).slice(-1)[0] ?? null;
    const stockRatio =
      s.stocks_started_value && s.stocks_started_value > 0
        ? s.self_managed / s.stocks_started_value
        : null;
    return {
      date: s.date,
      customStocks:
        stockRatio != null && baseStockRatio != null
          ? (stockRatio / baseStockRatio) * 100
          : 100,
      managed:
        s.managed != null && base.managed != null && base.managed > 0
          ? (s.managed / base.managed) * 100
          : null,
      spx: s.spx != null && baseSpx != null ? (s.spx / baseSpx) * 100 : null,
      pensions: pensionRow && basePension ? (pensionRow.total / basePension) * 100 : null,
      lisa: s.lisa_total != null && baseLisa != null ? (s.lisa_total / baseLisa) * 100 : null,
    };
  });
}

// ─── Halifax amortisation schedule ───────────────────────────────────────────

export type HalifaxRow = {
  date: string;
  balance: number;
  interest: number;
  principal: number;
  ltv: number;
};

const HALIFAX_LOAN = 585999;
const HALIFAX_PROPERTY = 650000;
const HALIFAX_RATE_SWITCH = "2024-10-01";
const HALIFAX_RATE_1 = 0.0275;
const HALIFAX_RATE_2 = 0.0449;
const HALIFAX_PAYMENT_1 = 2207.34;
const HALIFAX_PAYMENT_2 = 2761.78;

export function generateHalifaxSchedule(untilDate: string): HalifaxRow[] {
  const rows: HalifaxRow[] = [];
  let balance = HALIFAX_LOAN;
  let y = 2022, m = 9;

  while (true) {
    const mm = String(m).padStart(2, "0");
    const dateStr = `${y}-${mm}-01`;
    if (dateStr >= untilDate) break;

    const rate = dateStr < HALIFAX_RATE_SWITCH ? HALIFAX_RATE_1 : HALIFAX_RATE_2;
    const payment = dateStr < HALIFAX_RATE_SWITCH ? HALIFAX_PAYMENT_1 : HALIFAX_PAYMENT_2;
    const interest = balance * (rate / 12);
    const principal = payment - interest;
    balance = Math.max(0, balance - principal);

    rows.push({
      date: dateStr,
      balance: Math.round(balance),
      interest: Math.round(interest),
      principal: Math.round(principal),
      ltv: parseFloat(((balance / HALIFAX_PROPERTY) * 100).toFixed(2)),
    });

    m++;
    if (m > 12) { m = 1; y++; }
  }
  return rows;
}

export const COOP_LOAN = 570999;

export { HALIFAX_LOAN, HALIFAX_PROPERTY };
