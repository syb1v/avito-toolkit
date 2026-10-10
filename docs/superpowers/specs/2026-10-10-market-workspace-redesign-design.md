# Market Workspace Redesign

**Status:** design for review  
**Scope:** IA/UX, seller context, searches, product matching, AI recommendations, agent transparency.

## Problem

The dashboard currently acts as the destination for unrelated sidebar items. Search configuration, accounts, proxies, alerts, agents, chat, and analytics are rendered together. AI recommendations also use broad fuzzy matching and category-level data, so distinct products can enter the same comparison set.

## Goals

1. Make every primary sidebar item a real page with a stable URL and one job.
2. Make seller context explicit and persistent for seller-owned data.
3. Show whether a search is scheduled, currently crawling, paused, or failing.
4. Give each search independent competitor allow/block filters, including bulk editing.
5. Make product identity and match decisions explainable and manually correctable.
6. Make recommendations and subagents understandable, source-backed, and reviewable item by item.
7. Reduce dashboard density; keep the overview as a summary, not a toolbox.

## Information architecture

Primary navigation uses icons plus labels and real routes:

- `/` — Обзор: health, crawl summary, alerts summary, pending decisions.
- `/searches` — Поиски: all searches, status, schedule, account, bulk actions.
- `/searches/:id` — Search workspace: results, filters, competitors, crawl history.
- `/our-listings` — Мои объявления: seller-scoped inventory and price position.
- `/recommendations` — Рекомендации: review queue, filters, item-level actions.
- `/agents` — Агенты: playbooks, inputs, runs, reports, consensus decisions.
- `/chat` — Чат: full conversation workspace, actions, sources, history.
- `/accounts` — Accounts: seller/searcher accounts and seller switcher settings.
- `/proxies` — Proxies and health.
- `/alerts` — Alerts and notification rules.

The sidebar active state is route-based, not hash-based. The dashboard only contains summaries linking to these pages.

## Seller context

A seller switcher is present in the global header on seller-scoped pages. It has an explicit “Все продавцы” option only on aggregate pages. The selected seller is represented by a URL query parameter (`seller=`) and persisted locally for convenience. API requests receive the selected seller ID; pages must not silently mix seller-owned listings or recommendations.

## Search workspace

Each search card exposes:

- status: `По расписанию`, `Обход идёт`, `Пауза`, or `Ошибка`;
- last crawl, next crawl, current page/progress, and last error;
- account, schedule, region, include/exclude keywords;
- competitor rules in a dedicated section.

Competitor rules are per search and contain:

- whitelist: only selected sellers are included;
- blacklist: selected sellers are excluded;
- explicit precedence: blacklist wins if a seller occurs in both;
- bulk editor with add/remove/replace modes, dry-run preview, and confirmation.

A search can be active while no crawl is currently running. These states must never be represented by one ambiguous checkmark.

## Product identity and matching

Matching is structured in this order:

1. brand;
2. canonical model family;
3. generation/version and numeric model markers;
4. edition/finish (for example Opera de Paris);
5. capacity, color, configuration, and bundle;
6. condition and completeness.

A title similarity score cannot override a hard identity conflict. `Gemini 2` and `Mania` are separate model families even when edition words overlap. Ambiguous matches are excluded from market statistics until confirmed.

Each match displays accepted fields, conflicting fields, score, source listing, and reason. Operators can confirm, reject, or edit a match for one SKU. Manual decisions are stored and take precedence over auto-matching.

Search parsing uses explicit include groups and exclusions at collection time. Model-family aliases and series terms are configurable per search; a broad token match must not pull neighbouring models into the dataset. Rejected listings retain a reason for audit.

## Recommendations

Each recommendation is an item-level review card containing:

- seller and SKU;
- current price and proposed price;
- exact matched listings and excluded listings;
- market sample size, freshness, and calculation window;
- identity/matching confidence;
- recommendation reason and risk;
- web research status and cited sources;
- actions: edit proposal, recalculate, approve, reject, inspect matches.

A bulk approve action is available only after the user selects items and sees a preview. No recommendation is applied implicitly.

## Web research

Web research is a separate evidence layer used to verify product identity, specifications, editions, and official positioning. It must return source URLs, source title, retrieval time, and the claims supported. Search-result snippets without a source URL are not evidence. Web research cannot invent market prices or silently replace Avito crawl data. If identity remains uncertain, the recommendation is marked “Нужна проверка”.

## Agents

An agent run page shows the playbook, selected searches, selected seller, input snapshot, web sources, agent outputs, consensus, conflicts, and decision history. The user can inspect one agent’s evidence and one SKU’s proposal without opening a technical log. Decisions are approved or rejected per item; the system records who, when, and what changed.

## Chat

Chat becomes a full page with a clear conversation column and an evidence/action column. Messages that produce an action show a structured preview and confirmation. Research answers show citations. The chat cannot silently mutate prices or search rules.

## Delivery slices

1. **Navigation and shells:** routes, sidebar icons, dashboard reduction, seller context.
2. **Search workspace:** status model, search page, competitor rules, bulk editor.
3. **Matching correctness:** canonical identity fields, hard conflicts, manual match decisions, regression cases for Gemini/Mania.
4. **Recommendations and agents:** item-level review, explainability, web evidence, per-item approvals.
5. **Chat and polish:** full chat page, responsive layout, accessibility and visual review.

Each slice must keep existing API-only seller price edits and approval gates intact.

## Acceptance criteria

- No primary sidebar item points to a dashboard anchor.
- A user can identify the selected seller and never mistake “active search” for “crawl running”.
- Whitelist/blacklist can be edited per search and in bulk with preview.
- Gemini 2 and Mania never auto-match solely because they share edition words.
- Every recommendation exposes its exact comparison set and offers point editing.
- Web-backed claims include clickable sources and retrieval time.
- Agent runs show inputs, evidence, output, conflicts, and per-item decisions.
- Dashboard has summaries only; detailed workflows live on their own pages.
