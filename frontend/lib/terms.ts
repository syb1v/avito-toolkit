export const STRATEGY_LABELS: Record<string, string> = {
  undercut_p25: "Ниже четверти рынка",
  match_median: "По медиане",
  premium_p75: "Выше четверти рынка",
  keep_current: "Оставить цену",
  manual: "Своя цена",
};

export const EDIT_STATUS_LABELS: Record<string, string> = {
  draft: "ждёт подтверждения",
  approved: "одобрена",
  applying: "применяется",
  applied: "применена",
  reverting: "откатывается",
  reverted: "откачена",
  rejected: "отклонена",
  failed: "ошибка",
};

export const EDIT_MODE_LABELS: Record<string, string> = {
  dry_run: "тренировка (без изменений)",
  live: "боевой режим (меняет на Авито)",
};

export const EXCLUDE_REASON_LABELS: Record<string, string> = {
  manual: "скрыто вручную",
  keyword: "не по теме",
  stopword: "стоп-слово",
  seller: "продавец",
  region: "другой город",
};

export const FLAG_CATEGORY_LABELS: Record<string, string> = {
  copy: "копия/реплика",
  fake_bait: "приманка",
  irrelevant: "не по теме",
  duplicate: "дубль",
};

export const ALERT_TYPE_LABELS: Record<string, string> = {
  price_above_market: "Наша цена выше рынка",
  worker_down: "Воркер не отвечает",
  queue_backlog: "Очередь забита",
  account_stale: "Пора обновить вход (cookies)",
  proxy_dead: "Прокси не работают",
  ai_balance_low: "Заканчивается баланс AI",
  auto_reprice: "Итог ночных правок цен",
};

export const AI_TASK_LABELS: Record<string, string> = {
  market_digest: "Сводки по рынку",
  listing_moderation: "Проверка объявлений",
  description_context: "Разбор описаний",
  price_advice: "Советы по цене",
  reprice_summary: "Объяснения правок",
  search_filters: "Настройка поисков",
  chat: "Чат-ассистент",
};

export function label(
  dictionary: Record<string, string>,
  key: string | null | undefined,
  fallback = "—",
): string {
  if (!key) {
    return fallback;
  }
  return dictionary[key] ?? key;
}
