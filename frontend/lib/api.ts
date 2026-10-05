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
  account_id: string | null;
};

export type Account = {
  id: string;
  name: string;
  profile_dir: string;
  role: "searcher" | "seller";
  proxy_label: string | null;
  status: "active" | "paused";
  notes: string | null;
  is_default: boolean;
  cookies_at: string | null;
  last_check_at: string | null;
  last_check_ok: boolean | null;
  last_error: string | null;
  searches_count: number;
  profile_exists: boolean;
  pages_today: number;
  daily_limit: number;
  last_activity: string | null;
  warmup_last: string | null;
  rest_until: string | null;
  rest_reason: string | null;
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
  flagged_count: number;
  flag_categories: Record<string, number>;
  keyword_excluded: number;
  stopword_excluded: number;
  region_excluded: number;
  manual_excluded: number;
  max_age_days: number;
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
  is_flagged: boolean;
  flag_category: string | null;
  flag_reasons: string[] | null;
  relevance_score: number | null;
  description_snippet: string | null;
  region: string | null;
  manual_excluded: boolean;
  exclude_reason: "manual" | "keyword" | "stopword" | "region" | null;
  exclude_detail: string | null;
  excluded: boolean;
  first_seen: string | null;
};

export type ListingSort = "position" | "price_asc" | "price_desc" | "new" | "status";

export type SearchStats = {
  total: number;
  excluded: number;
  fresh: number;
  max_age_days: number;
  regions: { region: string; count: number }[];
};

export const fetchSearchStats = (searchId: string) =>
  getJson<SearchStats>(`/api/v1/searches/${searchId}/listings/stats`);

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
  created_at?: string | null;
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
  status: "idle" | "queued" | "running" | "done" | "failed";
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

export const fetchAccounts = async (): Promise<Account[]> =>
  (await getJson<Account[]>("/api/v1/accounts")) ?? [];

export const fetchSummary = (searchId: string) =>
  getJson<MarketSummary>(`/api/v1/searches/${searchId}/summary`);

export const fetchHistory = async (searchId: string, days = 30): Promise<DailyPoint[]> =>
  (await getJson<DailyPoint[]>(`/api/v1/searches/${searchId}/history?days=${days}`)) ?? [];

export const fetchListings = async (
  searchId: string,
  options: {
    limit?: number;
    flagged?: boolean;
    category?: string;
    excluded?: boolean;
    region?: string;
    sort?: ListingSort;
    fresh?: boolean;
    offset?: number;
  } = {},
): Promise<Listing[]> => {
  const parts = [`limit=${options.limit ?? 0}`];
  if (options.flagged !== undefined) {
    parts.push(`flagged=${options.flagged}`);
  }
  if (options.category) {
    parts.push(`category=${encodeURIComponent(options.category)}`);
  }
  if (options.excluded !== undefined) {
    parts.push(`excluded=${options.excluded}`);
  }
  if (options.region) {
    parts.push(`region=${encodeURIComponent(options.region)}`);
  }
  if (options.sort && options.sort !== "position") {
    parts.push(`sort=${options.sort}`);
  }
  if (options.fresh) {
    parts.push("fresh=1");
  }
  if (options.offset) {
    parts.push(`offset=${options.offset}`);
  }
  return (
    (await getJson<Listing[]>(`/api/v1/searches/${searchId}/listings?${parts.join("&")}`)) ??
    []
  );
};

export const fetchAlerts = async (searchId: string): Promise<Alert[]> =>
  (await getJson<Alert[]>(`/api/v1/alerts?search_id=${searchId}`)) ?? [];

export const fetchOurListingsOverview = async (): Promise<OurListingOverview[]> =>
  (await getJson<OurListingOverview[]>("/api/v1/our-listings/overview")) ?? [];

export const fetchRecommendations = async (): Promise<Recommendation[]> =>
  (await getJson<Recommendation[]>("/api/v1/our-listings/recommendations")) ?? [];

export const fetchDashboard = () => getJson<Dashboard>("/api/v1/dashboard");

export type ProxyEntryStatus = {
  id: string;
  label: string;
  scheme: string;
  enabled: boolean;
  note: string | null;
  healthy: boolean | null;
  failures: number;
  cooldown_seconds_left: number;
  antibot_blocked: boolean;
  antibot_seconds_left: number;
  last_ok: string | null;
  last_error: string | null;
  latency_ms: number | null;
  exit_ip: string | null;
};

export type ProxyStatus = {
  enabled: boolean;
  configured: boolean;
  mode: string | null;
  count: number;
  alive: number;
  in_cooldown: number;
  antibot_blocked: number;
  entries: ProxyEntryStatus[];
};

export async function fetchProxiesClient(): Promise<ProxyStatus | null> {
  try {
    const response = await fetch(`${API_URL}/api/v1/proxies`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as ProxyStatus;
  } catch {
    return null;
  }
}

export const createProxyClient = (url: string, note?: string | null) =>
  mutate<ProxyEntryStatus>("/api/v1/proxies", {
    method: "POST",
    body: JSON.stringify({ url, note: note || null }),
  });

export const updateProxyClient = (
  id: string,
  payload: { enabled?: boolean; note?: string | null },
) =>
  mutate<ProxyEntryStatus>(`/api/v1/proxies/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteProxyClient = (id: string) =>
  mutate<void>(`/api/v1/proxies/${id}`, { method: "DELETE" });

export async function checkProxiesClient(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/api/v1/proxies/check?avito=true`, {
      method: "POST",
    });
    return response.ok;
  } catch {
    return false;
  }
}

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

export async function fetchDigestClient(searchId: string): Promise<Digest | null> {
  try {
    const response = await fetch(`${API_URL}/api/v1/searches/${searchId}/digest`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as Digest;
  } catch {
    return null;
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

export type ListingEdit = {
  id: string;
  sku: string;
  title: string | null;
  old_price: number;
  target_price: number;
  delta_pct: number;
  strategy: string;
  status: string;
  mode: string;
  error: string | null;
  screenshot_path: string | null;
  created_at: string;
  applied_at: string | null;
  reverted_at: string | null;
};

export type EditsList = {
  mode: string;
  live_edits: boolean;
  items: ListingEdit[];
};

export const fetchEdits = async (): Promise<EditsList> =>
  (await getJson<EditsList>("/api/v1/our-listings/edits")) ?? {
    mode: "dry_run",
    live_edits: false,
    items: [],
  };

export const fetchEditsClient = async (): Promise<EditsList | null> => {
  try {
    const response = await fetch(`${API_URL}/api/v1/our-listings/edits`, {
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as EditsList;
  } catch {
    return null;
  }
};

export type MutationResult<T = unknown> =
  | { ok: true; data: T }
  | { ok: false; error: string };

async function mutate<T>(path: string, init: RequestInit): Promise<MutationResult<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    });
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null);
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : `HTTP ${response.status}`;
      return { ok: false, error: detail };
    }
    const data =
      response.status === 204 ? ((undefined as unknown) as T) : ((await response.json()) as T);
    return { ok: true, data };
  } catch {
    return { ok: false, error: "API недоступен" };
  }
}

export type SearchPayload = {
  name: string;
  url: string;
  params: Record<string, unknown>;
  schedule_cron: string;
  priority: number;
  account_id: string | null;
};

export const createSearchClient = (payload: SearchPayload) =>
  mutate<Search>("/api/v1/searches", { method: "POST", body: JSON.stringify(payload) });

export const updateSearchClient = (
  id: string,
  payload: Partial<SearchPayload & { is_active: boolean }>,
) =>
  mutate<Search>(`/api/v1/searches/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteSearchClient = (id: string) =>
  mutate<void>(`/api/v1/searches/${id}`, { method: "DELETE" });

export const createEditsClient = (payload: { sku?: string; max_items?: number }) =>
  mutate<{ created: number; items: ListingEdit[] }>("/api/v1/our-listings/edits", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const editActionClient = (
  id: string,
  action: "approve" | "reject" | "apply" | "revert",
) =>
  mutate<ListingEdit>(`/api/v1/our-listings/edits/${id}/${action}`, { method: "POST" });

export const createAccountClient = (payload: {
  name: string;
  notes?: string | null;
  role?: "searcher" | "seller";
  proxy_label?: string | null;
}) =>
  mutate<Account>("/api/v1/accounts", { method: "POST", body: JSON.stringify(payload) });

export const updateAccountClient = (
  id: string,
  payload: {
    name?: string;
    notes?: string | null;
    status?: string;
    role?: string;
    proxy_label?: string | null;
  },
) =>
  mutate<Account>(`/api/v1/accounts/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const deleteAccountClient = (id: string) =>
  mutate<void>(`/api/v1/accounts/${id}`, { method: "DELETE" });

export const checkAccountClient = (id: string) =>
  mutate<{ status: string; seconds_left?: number }>(`/api/v1/accounts/${id}/check`, {
    method: "POST",
  });

export const warmupAccountClient = (id: string) =>
  mutate<{ status: string; message_id?: string }>(`/api/v1/accounts/${id}/warmup`, {
    method: "POST",
  });

export const restAccountClient = (id: string, minutes?: number) =>
  mutate<{ status: string; until: number; minutes: number }>(`/api/v1/accounts/${id}/rest`, {
    method: "POST",
    body: JSON.stringify({ minutes: minutes ?? null }),
  });

export const resumeAccountClient = (id: string) =>
  mutate<{ status: string }>(`/api/v1/accounts/${id}/resume`, { method: "POST" });

export const uploadAccountCookiesClient = (id: string, cookies: string, fresh = true) =>
  mutate<{ status: string }>(`/api/v1/accounts/${id}/cookies`, {
    method: "POST",
    body: JSON.stringify({ cookies, fresh }),
  });

export const setListingsExcludedClient = (
  searchId: string,
  listingIds: number[],
  excluded: boolean,
  reason?: string,
) =>
  mutate<{ excluded: boolean; updated: number; total_excluded: number }>(
    `/api/v1/searches/${searchId}/listings/exclusions`,
    {
      method: "POST",
      body: JSON.stringify({ listing_ids: listingIds, excluded, reason }),
    },
  );

export const clearAlertsClient = (payload: {
  search_id?: string | null;
  status?: string | null;
}) =>
  mutate<{ deleted: number }>("/api/v1/alerts/clear", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const deleteAlertClient = (id: string) =>
  mutate<void>(`/api/v1/alerts/${id}`, { method: "DELETE" });

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
