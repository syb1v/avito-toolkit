export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const SERVER_API_URL = process.env.API_URL_INTERNAL ?? API_URL;

export type Health = {
  status: string;
  version: string;
  environment: string;
};

export type Search = {
  id: string;
  name: string;
  url: string;
  params: Record<string, unknown> | null;
  schedule_cron: string;
  priority: number;
  is_active: boolean;
};

export type PriceStats = {
  count: number;
  price_min: number;
  price_max: number;
  mean: number;
  median: number;
  p25: number;
  p75: number;
};

export type MarketSummary = {
  search_id: string;
  name: string;
  url: string;
  is_active: boolean;
  active_count: number;
  new_today_count: number;
  delisted_today_count: number;
  delisted_7d: number;
  delisting_velocity: number;
  avg_lifetime_days: number | null;
  stats: PriceStats | null;
};

export type DailyPoint = {
  calc_date: string;
  active_count: number;
  new_today_count: number;
  delisted_today_count: number;
  price_min: number | null;
  price_max: number | null;
  price_median: number | null;
  price_p25: number | null;
  price_p75: number | null;
  avg_lifetime_days: number | null;
};

export type Listing = {
  id: number;
  title: string;
  price: number | null;
  url: string | null;
  status: string;
  last_position: number | null;
};

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${SERVER_API_URL}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export const fetchHealth = () => getJson<Health>("/healthz");

export const fetchSearches = async (): Promise<Search[]> =>
  (await getJson<Search[]>("/api/v1/searches")) ?? [];

export const fetchSummary = (searchId: string) =>
  getJson<MarketSummary>(`/api/v1/searches/${searchId}/summary`);

export const fetchHistory = async (searchId: string, days = 30): Promise<DailyPoint[]> =>
  (await getJson<DailyPoint[]>(`/api/v1/searches/${searchId}/history?days=${days}`)) ?? [];

export const fetchListings = async (searchId: string, limit = 100): Promise<Listing[]> =>
  (await getJson<Listing[]>(`/api/v1/searches/${searchId}/listings?limit=${limit}`)) ?? [];
