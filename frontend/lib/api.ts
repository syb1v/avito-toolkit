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

export type Alert = {
  id: string;
  type: string;
  payload: Record<string, unknown> | null;
  status: string;
  created_at: string;
};

export type Digest = {
  search_id: string;
  headline: string;
  demand_signal: string;
  price_range_comment: string;
  competitor_notes: string[];
  recommended_actions: string[];
  model: string;
  tokens_in: number | null;
  tokens_out: number | null;
  cost_usd: number | null;
};

export type OurListingOverview = {
  sku: string;
  title: string;
  our_price: number;
  cost_price: number | null;
  is_active: boolean;
  avito_status: string | null;
  avito_url: string | null;
  matched_count: number;
  market_median: number | null;
  market_p25: number | null;
  market_p75: number | null;
  delta_to_median_pct: number | null;
  cheaper_share: number | null;
};

export type Recommendation = {
  sku: string;
  title: string;
  our_price: number;
  cost_price: number | null;
  market_median: number | null;
  matched_count: number;
  strategy: string;
  target_price: number;
  clamped_price: number;
  delta_pct: number;
  requires_approval: boolean;
};

export type DashboardAlert = {
  id: string;
  type: string;
  payload: Record<string, unknown> | null;
  created_at: string;
};

export type Dashboard = {
  searches_total: number;
  searches_active: number;
  listings_active: number;
  our_listings_active: number;
  alerts_new: number;
  worker_alive: boolean;
  queues: { crawl: number; analytics: number };
  active_crawls: {
    search_id: string;
    search_name: string | null;
    stage: string | null;
    page: number | null;
    max_pages: number | null;
    listings_seen: number | null;
    started_at: string | null;
  }[];
  latest_alerts: DashboardAlert[];
};

export type SearchProgress = {
  search_id: string;
  status: "idle" | "running" | "done" | "failed";
  stage: string | null;
  page: number | null;
  max_pages: number | null;
  listings_seen: number | null;
  result: Record<string, unknown> | null;
  error: string | null;
  updated_at: string | null;
  last_crawl_at: string | null;
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

export const fetchAlerts = async (searchId: string): Promise<Alert[]> =>
  (await getJson<Alert[]>(`/api/v1/alerts?search_id=${searchId}`)) ?? [];

export const fetchOurListingsOverview = async (): Promise<OurListingOverview[]> =>
  (await getJson<OurListingOverview[]>("/api/v1/our-listings/overview")) ?? [];

export const fetchRecommendations = async (): Promise<Recommendation[]> =>
  (await getJson<Recommendation[]>("/api/v1/our-listings/recommendations")) ?? [];

export const fetchDashboard = () => getJson<Dashboard>("/api/v1/dashboard");

export async function fetchDashboardClient(): Promise<Dashboard | null> {
  try {
    const response = await fetch(`${API_URL}/api/v1/dashboard`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Dashboard;
  } catch {
    return null;
  }
}

export async function fetchProgressClient(
  searchId: string,
): Promise<SearchProgress | null> {
  try {
    const response = await fetch(`${API_URL}/api/v1/searches/${searchId}/progress`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as SearchProgress;
  } catch {
    return null;
  }
}

export async function triggerCrawl(searchId: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/api/v1/searches/${searchId}/crawl`, {
      method: "POST",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function createDigest(
  searchId: string,
): Promise<{ digest?: Digest; error?: string }> {
  try {
    const response = await fetch(`${API_URL}/api/v1/searches/${searchId}/digest`, {
      method: "POST",
    });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : "Не удалось сгенерировать дайджест";
      return { error: detail };
    }
    return { digest: body as Digest };
  } catch {
    return { error: "API недоступен" };
  }
}

export async function ackAlert(alertId: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/api/v1/alerts/${alertId}/ack`, {
      method: "POST",
    });
    return response.ok;
  } catch {
    return false;
  }
}
