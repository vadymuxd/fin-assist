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
  /** Sheet col I — value of the position at tracking start (Apr 13), or cost if acquired later. */
  tracking_started_value: number | null;
  /** Sheet col K — real return since tracking start (Apr 13), money-weighted across actual buys. */
  tracking_pnl_pct: number | null;
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
  /**
   * Total capital Lisa has invested in her GIC ISA (updated when she deposits).
   * Used as denominator for her organic performance: (lisa_total - lisa_started_value) / lisa_started_value.
   */
  lisa_started_value: number | null;
  managed: number;
  /**
   * MANAGED FUNDS "Tracking Started Value" (sheet col I on the aggregate row),
   * bumped by deposits. Anchor for organic managed performance:
   * managed / managed_started_value - 1. Insulated from contributions because a
   * deposit raises both managed and managed_started_value equally — mirrors
   * stocks_started_value / lisa_started_value.
   */
  managed_started_value: number | null;
  cash: number;
  net_deposits: number;
  spx: number | null;
  ftse: number | null;
  ndx: number | null;
  msci: number | null;
  gold: number | null;
  magg: number | null;
  sgln_price: number | null;
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
  const [{ data: snaps, error }, { data: sglnRows }] = await Promise.all([
    supabase
      .from("portfolio_snapshots")
      .select("date, vadym_total, lisa_total, joint_total, self_managed, stocks_started_value, lisa_started_value, managed, managed_started_value, cash, net_deposits, spx, ftse, ndx, msci, gold, magg")
      .order("date", { ascending: true }),
    supabase
      .from("holding_price_history")
      .select("date, price")
      .eq("ticker", "SGLN"),
  ]);
  if (error) throw error;
  const sglnMap = new Map<string, number>((sglnRows ?? []).map((r) => [r.date as string, Number(r.price)]));
  return (snaps ?? []).map((s) => ({ ...s, sgln_price: sglnMap.get(s.date) ?? null }));
}

export async function getLatestSnapshot(): Promise<PortfolioSnapshot | null> {
  const { data, error } = await supabase
    .from("portfolio_snapshots")
    .select("date, vadym_total, lisa_total, joint_total, self_managed, stocks_started_value, lisa_started_value, managed, managed_started_value, cash, net_deposits, spx, ftse, ndx, msci, gold, magg")
    .order("date", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data ? { ...data, sgln_price: null } : null;
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

export type PricePoint = { date: string; price: number };
export type HoldingPriceHistoryMap = Record<string, PricePoint[]>;

export type HoldingTrade = {
  id: number;
  date: string;
  ticker: string;
  action: "BUY" | "SELL";
  qty: number;
  price_gbp: number;
  total_gbp: number;
  platform: string | null;
  notes: string | null;
};

export async function getHoldingTrades(ticker: string): Promise<HoldingTrade[]> {
  const { data, error } = await supabase
    .from("holding_trades")
    .select("id, date, ticker, action, qty, price_gbp, total_gbp, platform, notes")
    .eq("ticker", ticker)
    .order("date");
  if (error) throw error;
  return (data ?? []) as HoldingTrade[];
}

export async function getAllHoldingsPriceHistoryFrom(fromDate: string): Promise<HoldingPriceHistoryMap> {
  const { data, error } = await supabase
    .from("holding_price_history")
    .select("ticker, date, price")
    .gte("date", fromDate)
    .order("date");
  if (error) throw error;
  const map: HoldingPriceHistoryMap = {};
  for (const row of data ?? []) {
    const t = row.ticker as string;
    if (!map[t]) map[t] = [];
    map[t].push({ date: row.date as string, price: Number(row.price) });
  }
  return map;
}

export async function getHoldingPriceHistory(ticker: string): Promise<PricePoint[]> {
  const { data, error } = await supabase
    .from("holding_price_history")
    .select("date, price")
    .eq("ticker", ticker)
    .order("date");
  if (error) throw error;
  return (data ?? []).map((r) => ({ date: r.date as string, price: Number(r.price) }));
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
  // Fetch recent rows (all accounts × ~10 dates = well under 500) and pick the
  // latest entry per account client-side. This avoids the previous bug where
  // accounts last updated on an older date were invisible because the query
  // filtered to the exact latest snapshot date.
  const { data, error } = await supabase
    .from("savings_accounts")
    .select("id, date, bank, account_name, account_type, owner, balance_gbp")
    .order("date", { ascending: false })
    .limit(500);
  if (error) throw error;
  const rows = data ?? [];
  const seen = new Map<string, (typeof rows)[0]>();
  for (const row of rows) {
    const key = `${row.bank}|${row.account_name}`;
    if (!seen.has(key)) seen.set(key, row); // rows ordered date DESC → first = latest
  }
  return [...seen.values()].sort((a, b) => b.balance_gbp - a.balance_gbp);
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
  deal_expires: string | null;
  deal_term_years: number | null;
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
    .select("date, balance, property_value, equity, equity_half, monthly_payment, rate, lender, updated_at, deal_expires, deal_term_years")
    .order("date", { ascending: true });
  if (error) throw error;
  return data ?? [];
}

export type MortgageInsight = {
  id: number;
  created_at: string;
  report_date: string;
  report_md: string;
  telegram_text: string | null;
  base_rate: number | null;
  avg_2yr_rate: number | null;
  avg_5yr_rate: number | null;
  avg_2yr_wow_bps: number | null;
  avg_5yr_wow_bps: number | null;
  next_mpc: string | null;
  triggered_by: string;
};

export async function getMortgageInsights(limit = 50): Promise<MortgageInsight[]> {
  const { data, error } = await supabase
    .from("mortgage_insights")
    .select(
      "id, created_at, report_date, report_md, telegram_text, base_rate, avg_2yr_rate, avg_5yr_rate, avg_2yr_wow_bps, avg_5yr_wow_bps, next_mpc, triggered_by",
    )
    .order("created_at", { ascending: false })
    .limit(limit);
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
  // Joint (full combined) — default view
  net_worth: number;
  investments: number;
  savings: number;
  pensions: number;
  mortgage_equity: number;  // full equity (equity_half * 2)
  // Vadym
  vadym_net_worth: number;
  vadym_investments: number;
  vadym_savings: number;    // personal + half of joint savings
  vadym_pensions: number;
  // Lisa
  lisa_net_worth: number;
  lisa_investments: number;
  lisa_savings: number;     // personal + half of joint savings
  lisa_pensions: number;
};

export async function getNetWorthData(): Promise<NetWorthPoint[]> {
  const [{ data: inv }, { data: sav }, { data: pen }, { data: mort }] = await Promise.all([
    supabase.from("portfolio_snapshots").select("date, vadym_total, lisa_total, joint_total, self_managed, managed, cash").order("date", { ascending: true }),
    supabase.from("savings_snapshots").select("date, vadym_total, lisa_total, joint_total").order("date", { ascending: true }),
    supabase.from("pension_snapshots").select("date, total, vadym_total, lisa_total").order("date", { ascending: true }),
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
    const penRow = latestOnOrBefore(pen, i.date);
    const mortRow = latestOnOrBefore(mort, i.date);

    const equityHalf = mortRow ? Number(mortRow.equity_half) : 0;

    const vadymInv = Number(i.self_managed ?? 0) + Number(i.managed ?? 0) + Number(i.cash ?? 0);
    const lisaInv  = Number(i.lisa_total ?? 0);
    const jointInv = Number(i.joint_total ?? (vadymInv + lisaInv));

    const savVadym = savRow ? Number(savRow.vadym_total ?? 0) : 0;
    const savLisa  = savRow ? Number(savRow.lisa_total ?? 0) : 0;
    const savJoint = savRow ? Number(savRow.joint_total ?? 0) : 0;
    const vadymSav = savVadym + savJoint * JOINT_SHARE;
    const lisaSav  = savLisa  + savJoint * JOINT_SHARE;
    const jointSav = savVadym + savLisa + savJoint;

    const vadymPen = penRow ? Number(penRow.vadym_total ?? 0) : 0;
    const lisaPen  = penRow ? Number(penRow.lisa_total ?? 0) : 0;
    const jointPen = penRow ? Number(penRow.total ?? 0) : 0;

    const vadymNW = vadymInv + vadymSav + vadymPen + equityHalf;
    const lisaNW  = lisaInv  + lisaSav  + lisaPen  + equityHalf;

    return {
      date: i.date,
      net_worth: vadymNW + lisaNW,
      investments: jointInv,
      savings: jointSav,
      pensions: jointPen,
      mortgage_equity: equityHalf * 2,
      vadym_net_worth: vadymNW,
      vadym_investments: vadymInv,
      vadym_savings: vadymSav,
      vadym_pensions: vadymPen,
      lisa_net_worth: lisaNW,
      lisa_investments: lisaInv,
      lisa_savings: lisaSav,
      lisa_pensions: lisaPen,
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
  // Organic change only (£ and %), for invested assets (stocks + managed funds).
  // Strip the change in each tracking-started value: a BUY or a fund deposit adds
  // equal £ to the value AND its started-value baseline, so they cancel — leaving
  // pure market movement. Without this, a contribution (e.g. a Nutmeg deposit)
  // would show as a phantom gain and the £ would disagree with the %.
  // NOTE: vadym_total now INCLUDES uninvested cash (sheet G7 = stocks + cash,
  // 2026-06), so the % base must be the invested-assets total (self_managed +
  // managed) — not vadym_total — to keep the performance % undistorted by cash.
  const stockOrganic =
    (latest.self_managed - prev.self_managed) -
    ((latest.stocks_started_value ?? 0) - (prev.stocks_started_value ?? 0));
  const managedOrganic =
    (latest.managed - prev.managed) -
    ((latest.managed_started_value ?? 0) - (prev.managed_started_value ?? 0));
  const absolute = stockOrganic + managedOrganic;
  const prevBase = prev.self_managed + prev.managed;
  const pct = prevBase === 0 ? 0 : (absolute / prevBase) * 100;
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
  const lisaSinceBaseline = (() => {
    const val = latest.lisa_total ?? 0;
    const started = latest.lisa_started_value;
    if (!started || started === 0 || baseline.date === latest.date) return null;
    const absolute = val - started;
    const pct = (absolute / started) * 100;
    return { absolute, pct, fromDate: baseline.date };
  })();

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
  magg: number | null;
  spx: number | null;
  gold: number | null;
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

  const baseSpx  = sorted.find((s) => s.spx  != null && s.spx  > 0)?.spx  ?? null;
  const baseMagg = sorted.find((s) => s.magg != null && s.magg > 0)?.magg ?? null;
  const baseGold = sorted.find((s) => s.gold != null && s.gold > 0)?.gold ?? null;
  const basePension = sortedPensions.find((s) => s.total > 0)?.total ?? null;

  // Time-Weighted Return: chain sub-period returns between each cash flow.
  // A deposit or withdrawal adjusts the sub-period base by the change in
  // started_value, so the cash flow itself contributes 0% return — only real
  // market movement moves the TWR line. Completely deposit-neutral.
  let stocksTwr = 1.0;
  let lisaTwr = 1.0;

  return sorted.map((s, i) => {
    if (i > 0) {
      const prev = sorted[i - 1];

      // stocks: deposit/buy = increase in stocks_started_value; sell = decrease
      const stocksBase = prev.self_managed + ((s.stocks_started_value ?? 0) - (prev.stocks_started_value ?? 0));
      if (stocksBase > 0) stocksTwr *= 1 + (s.self_managed - stocksBase) / stocksBase;

      // Lisa
      const lisaBase = (prev.lisa_total ?? 0) + ((s.lisa_started_value ?? 0) - (prev.lisa_started_value ?? 0));
      if (lisaBase > 0) lisaTwr *= 1 + ((s.lisa_total ?? 0) - lisaBase) / lisaBase;
    }

    const pensionRow = sortedPensions.filter((p) => p.date <= s.date).slice(-1)[0] ?? null;
    return {
      date: s.date,
      customStocks: stocksTwr * 100,
      magg: s.magg != null && baseMagg != null ? (s.magg / baseMagg) * 100 : null,
      spx:  s.spx  != null && baseSpx  != null ? (s.spx  / baseSpx)  * 100 : null,
      gold: s.gold != null && baseGold != null ? (s.gold / baseGold) * 100 : null,
      pensions: pensionRow && basePension ? (pensionRow.total / basePension) * 100 : null,
      lisa: (s.lisa_total ?? 0) > 0 && (s.lisa_started_value ?? 0) > 0 ? lisaTwr * 100 : null,
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
export const DEPOSIT = 60000;
export const MORTGAGE_START = "2022-09-01";

export { HALIFAX_LOAN, HALIFAX_PROPERTY };

// ─── Monzo Transactions ───────────────────────────────────────────────────────

export type MonzoTransaction = {
  id: number;
  transaction_id: string;
  account_type: "personal" | "joint";
  row_index: number;
  date: string | null;
  time: string | null;
  type: string | null;
  name: string | null;
  emoji: string | null;
  category: string | null;
  amount: number | null;
  currency: string | null;
  local_amount: number | null;
  local_currency: string | null;
  notes: string | null;
  address: string | null;
  receipt: string | null;
  description: string | null;
  category_split: string | null;
  pot_name: string | null;
  synced_at: string;
};

export type MonzoFilters = {
  account?: string;
  category?: string;
  type?: string;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  amountMin?: string;
  amountMax?: string;
  pot?: string;
  page?: number;
  perPage?: number;
};

export async function getMonzoTransactions(
  filters: MonzoFilters = {}
): Promise<{ rows: MonzoTransaction[]; total: number }> {
  const perPage = filters.perPage ?? 50;
  const page = filters.page ?? 1;
  const offset = (page - 1) * perPage;

  let q = supabase
    .from("monzo_transactions")
    .select("*", { count: "exact" });

  if (filters.account && filters.account !== "all") {
    q = q.eq("account_type", filters.account);
  }
  if (filters.category) {
    q = q.ilike("category", `%${filters.category}%`);
  }
  if (filters.type) {
    q = q.ilike("type", `%${filters.type}%`);
  }
  if (filters.search) {
    q = q.or(
      `name.ilike.%${filters.search}%,description.ilike.%${filters.search}%,notes.ilike.%${filters.search}%`
    );
  }
  if (filters.dateFrom) {
    q = q.gte("date", filters.dateFrom);
  }
  if (filters.dateTo) {
    q = q.lte("date", filters.dateTo);
  }
  if (filters.amountMin) {
    const v = parseFloat(filters.amountMin);
    if (!isNaN(v)) q = q.gte("amount", -Math.abs(v));
  }
  if (filters.amountMax) {
    const v = parseFloat(filters.amountMax);
    if (!isNaN(v)) q = q.lte("amount", -Math.abs(v));
  }
  if (filters.pot) {
    q = q.ilike("pot_name", `%${filters.pot}%`);
  }

  const { data, count, error } = await q
    .order("date", { ascending: false })
    .order("time", { ascending: false })
    .range(offset, offset + perPage - 1);

  if (error) throw error;
  return { rows: (data ?? []) as MonzoTransaction[], total: count ?? 0 };
}

// ─── Spending analytics ───────────────────────────────────────────────────────

export type SpendingRow = { month: string; category: string; total: number };
export type MonthlySpend = { month: string; total: number };
export type WeeklySpend = { week: string; total: number };
export type MerchantSpend = { name: string; total: number; count: number };
export type DaySpend = { day: string; total: number };

export type SpendingAccountData = {
  byCategory: SpendingRow[];
  monthly: MonthlySpend[];
  weekly: WeeklySpend[];
  topMerchants: MerchantSpend[];
  byDayOfWeek: DaySpend[];
};

export type SpendingData = {
  personal: SpendingAccountData;
  joint: SpendingAccountData;
  all: SpendingAccountData;
};

const EXCLUDED_CATEGORIES = new Set(["Savings", "Transfers"]);
const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function aggregateSpending(
  rows: { date: string | null; category: string | null; amount: number | null; name: string | null }[]
): SpendingAccountData {
  const catMap: Record<string, number> = {};
  const monthMap: Record<string, number> = {};
  const weekMap: Record<string, number> = {};
  const merchantMap: Record<string, { total: number; count: number }> = {};
  const dayMap: Record<string, number> = {};

  for (const row of rows) {
    if (!row.date || !row.amount) continue;
    const d = new Date(row.date + "T12:00:00Z");
    const month = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
    const cat = row.category ?? "General";
    const abs = Math.abs(Number(row.amount));

    catMap[`${month}|${cat}`] = (catMap[`${month}|${cat}`] ?? 0) + abs;
    monthMap[month] = (monthMap[month] ?? 0) + abs;

    const dayIdx = d.getUTCDay();
    const diff = dayIdx === 0 ? -6 : 1 - dayIdx;
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() + diff);
    weekMap[monday.toISOString().slice(0, 10)] = (weekMap[monday.toISOString().slice(0, 10)] ?? 0) + abs;

    const merchant = row.name ?? "Unknown";
    if (!merchantMap[merchant]) merchantMap[merchant] = { total: 0, count: 0 };
    merchantMap[merchant].total += abs;
    merchantMap[merchant].count++;

    dayMap[DAY_NAMES[d.getUTCDay()]] = (dayMap[DAY_NAMES[d.getUTCDay()]] ?? 0) + abs;
  }

  const round2 = (n: number) => Math.round(n * 100) / 100;

  return {
    byCategory: Object.entries(catMap).map(([k, total]) => {
      const pipe = k.indexOf("|");
      return { month: k.slice(0, pipe), category: k.slice(pipe + 1), total: round2(total) };
    }).sort((a, b) => a.month.localeCompare(b.month)),

    monthly: Object.entries(monthMap)
      .map(([month, total]) => ({ month, total: round2(total) }))
      .sort((a, b) => a.month.localeCompare(b.month)),

    weekly: Object.entries(weekMap)
      .map(([week, total]) => ({ week, total: round2(total) }))
      .sort((a, b) => a.week.localeCompare(b.week)),

    topMerchants: Object.entries(merchantMap)
      .map(([name, { total, count }]) => ({ name, total: round2(total), count }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10),

    byDayOfWeek: DAY_ORDER.map(d => ({ day: d, total: round2(dayMap[d] ?? 0) })),
  };
}

export async function getSpendingData(): Promise<SpendingData> {
  const { data, error } = await supabase
    .from("monzo_transactions")
    .select("date, category, amount, account_type, name, type")
    .lt("amount", 0)
    .gte("date", "2025-01-01")
    .limit(10000);

  const empty: SpendingAccountData = {
    byCategory: [], monthly: [], weekly: [], topMerchants: [], byDayOfWeek: [],
  };

  if (error || !data) return { personal: empty, joint: empty, all: empty };

  const spending = data.filter(
    r => r.type !== "Pot transfer" && !EXCLUDED_CATEGORIES.has(r.category ?? "")
  );

  return {
    personal: aggregateSpending(spending.filter(r => r.account_type === "personal")),
    joint:    aggregateSpending(spending.filter(r => r.account_type === "joint")),
    all:      aggregateSpending(spending),
  };
}
