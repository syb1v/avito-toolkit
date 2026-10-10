# Market Workspace Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard-as-navigation architecture with focused seller-aware workspaces and make search filtering, product matching, AI recommendations, web evidence, agents, and chat understandable and correct.

**Architecture:** Deliver the redesign in five independently testable slices. First establish real routes and a seller context shared by pages; then move search configuration and competitor rules into a search workspace; then enforce structured product identity before market statistics; finally expose item-level recommendations, evidence-backed agent runs, and a full chat page. The dashboard becomes a summary surface only.

**Tech Stack:** Next.js App Router, React, Tailwind CSS, FastAPI, SQLAlchemy async, PostgreSQL migrations, Redis worker/scheduler, existing LLM client, existing Avito API-only seller editing flow.

**Spec:** `docs/superpowers/specs/2026-10-10-market-workspace-redesign-design.md`

## Global Constraints

- No primary sidebar item may point to a dashboard anchor.
- Seller-scoped pages must carry an explicit `seller` context and must not silently mix sellers.
- A search being enabled is distinct from a crawl currently running.
- Blacklist wins when a seller occurs in both whitelist and blacklist.
- A title similarity score cannot override a hard product-identity conflict.
- Ambiguous matches are excluded from market statistics until confirmed.
- Web research provides evidence and sources; it does not replace Avito market data.
- Price mutations remain API-only and require the existing approval gates.
- Existing seller/searcher account-role separation remains intact.
- Every slice must have focused tests before integration checks.

## File Map

### Frontend

- Modify `frontend/app/components/app-shell.tsx`: route-based sidebar, icons, seller context, responsive navigation.
- Modify `frontend/app/page.tsx`: summary-only overview.
- Create `frontend/app/searches/page.tsx`: search index and bulk controls.
- Move/compose existing search controls from `frontend/app/components/search-manager.tsx` into the searches workspace.
- Create `frontend/app/searches/[id]/page.tsx`: search workspace and competitor rules.
- Create `frontend/app/recommendations/page.tsx`: recommendation review queue.
- Create `frontend/app/agents/page.tsx`: agent workspace.
- Create `frontend/app/chat/page.tsx`: full chat workspace.
- Create `frontend/app/accounts/page.tsx`, `frontend/app/proxies/page.tsx`, `frontend/app/alerts/page.tsx`: focused settings and alert screens.
- Create `frontend/app/components/icon.tsx`: one typed icon registry using inline SVG with accessible labels.
- Create `frontend/app/components/seller-switcher.tsx`: seller selection and URL/local persistence.
- Create `frontend/app/components/search-status-badge.tsx`: scheduled/running/paused/error states.
- Create `frontend/app/components/competitor-rules-editor.tsx`: whitelist/blacklist editor and preview.
- Create `frontend/app/components/recommendation-card.tsx`: item-level recommendation review.
- Create `frontend/app/components/match-evidence.tsx`: accepted/conflicting/excluded match evidence.
- Create `frontend/app/components/agent-run-view.tsx`: inputs, sources, outputs, conflicts, decisions.
- Refactor `frontend/app/components/chat-panel.tsx`: shared message primitives for the full chat page.
- Modify `frontend/lib/api.ts`: route clients, seller-aware query parameters, search rules, matching, research, and recommendation types.

### Backend

- Modify `backend/app/api/routes/searches.py`: search detail, status, competitor-rule updates, and bulk rule operations.
- Create or extend `backend/app/api/routes/recommendations.py`: seller-scoped queue, item edit/recalculate/approve/reject endpoints.
- Modify `backend/app/api/routes/agent.py`: seller/search selection, run evidence, per-item decisions.
- Modify `backend/app/api/routes/chat.py`: full-page history and citation/action payloads.
- Modify `backend/app/services/seller_filter.py`: typed whitelist/blacklist rules and blacklist precedence.
- Modify `backend/app/services/searches.py` and crawl services: persist and report running/paused/error state and exclusion reasons.
- Modify `backend/app/services/matching.py`: structured identity extraction, hard conflicts, manual decision precedence, and safer ranking.
- Modify `backend/app/services/agents.py`: select data through explicit playbook searches/seller, not category-name substring matches.
- Create `backend/app/services/web_research.py`: provider abstraction, source metadata, retrieval time, and claim evidence.
- Modify `backend/app/ai/schemas.py` and `backend/app/ai/prompts.py`: structured identity, research citations, uncertainty, and item-level proposals.
- Modify `backend/app/db/models.py` and add migrations: seller context, competitor rules, crawl state, canonical identity, match decisions, research sources, and recommendation review state.
- Modify `backend/app/workers/tasks.py` and `backend/app/scheduler.py`: research/matching/recommendation jobs with explicit seller/search inputs.

### Tests and docs

- Backend unit tests under `backend/tests/` for rules, identity conflicts, seller isolation, and research citation validation.
- Frontend type/build checks plus component tests where existing test infrastructure supports them.
- Update `docs/user-guide.md`, `docs/accuracy.md`, `docs/plan.md`, and `CHANGELOG.md` as each slice lands.

---

### Task 1: Establish route and seller-context primitives

**Files:**
- Modify: `frontend/app/components/app-shell.tsx`
- Create: `frontend/app/components/icon.tsx`
- Create: `frontend/app/components/seller-switcher.tsx`
- Modify: `frontend/lib/api.ts`
- Create: `frontend/app/components/__tests__/seller-switcher.test.tsx` if the existing frontend test setup supports it

**Interfaces:**
- `SellerSwitcher` consumes `Account[]` and the current route query; produces `?seller=<accountId>` or `?seller=all`.
- API helpers accept `sellerId?: string | "all"` and append it only to seller-scoped requests.
- `Icon` accepts a finite icon name and an optional decorative flag.

- [ ] **Step 1: Add route constants and seller-context helpers**

  Define a typed route map for `/`, `/searches`, `/our-listings`, `/recommendations`, `/agents`, `/chat`, `/accounts`, `/proxies`, and `/alerts`. Add a helper that reads and normalizes `seller` from `searchParams` without treating an absent seller as a silently selected seller.

- [ ] **Step 2: Add failing tests for seller URL behavior**

  Cover selecting a seller, preserving unrelated query parameters, selecting `all`, and rejecting an unknown seller ID from the available account list.

- [ ] **Step 3: Implement the icon registry and seller switcher**

  Use inline SVG icons with `aria-hidden="true"` when a visible label exists. Render seller name, role, and an explicit “Все продавцы” option only on aggregate pages. Use a native `<select>` or labeled menu rather than a click-only div.

- [ ] **Step 4: Replace hash links in the app shell**

  Replace `/#searches`, `/#accounts`, `/#proxies`, and `/#alerts` with real routes. Add route-based active styling, mobile parity, visible focus states, and a compact header seller switcher.

- [ ] **Step 5: Run focused checks**

  Run `cd frontend && npx tsc --noEmit && npm run build`. Verify source search contains no primary sidebar `/#` links.

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/app frontend/lib/api.ts
  git commit -m "feat(ui): add real routes and seller context"
  ```

### Task 2: Split the dashboard and add focused settings pages

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/accounts/page.tsx`
- Create: `frontend/app/proxies/page.tsx`
- Create: `frontend/app/alerts/page.tsx`
- Create: `frontend/app/searches/page.tsx`
- Modify: `frontend/app/components/search-manager.tsx`

**Interfaces:**
- Overview consumes health, summary metrics, alert summary, and pending-decision counts only.
- Focused pages own the existing `AccountManager`, `ProxyPanel`, `AlertsPanel`, and search management components.

- [ ] **Step 1: Write route smoke tests/checklist**

  Verify that each route renders its own page title and no page imports the entire dashboard collection of unrelated panels.

- [ ] **Step 2: Move panels into focused routes**

  Keep the dashboard to health, crawl summary, alert summary, pending decisions, and links. Move account, proxy, alert, search, and agent controls to their route pages.

- [ ] **Step 3: Add search index status presentation**

  Render account, schedule, active state, last crawl, next crawl, and an explicit status badge. Do not label `is_active` as “running”.

- [ ] **Step 4: Add focused page empty/loading/error states**

  Each page must state what is empty and provide the next action. Use `aria-live="polite"` for async changes and preserve seller context in links.

- [ ] **Step 5: Run frontend checks**

  Run `cd frontend && npx tsc --noEmit && npm run build` and manually inspect all new routes at desktop and mobile widths.

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/app
  git commit -m "feat(ui): split dashboard into focused workspaces"
  ```

### Task 3: Model crawl state and per-search competitor rules

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/0020_search_competitor_rules.py`
- Modify: `backend/app/services/seller_filter.py`
- Modify: `backend/app/api/routes/searches.py`
- Modify: `backend/app/services/searches.py`
- Modify: `backend/app/workers/tasks.py`
- Create: `backend/tests/test_seller_filter.py`
- Create: `backend/tests/test_search_rules_api.py`
- Create: `frontend/app/components/competitor-rules-editor.tsx`
- Modify: `frontend/app/searches/[id]/page.tsx`

**Interfaces:**
- `apply_competitor_rules(seller_id, whitelist, blacklist) -> bool` returns inclusion; blacklist wins.
- `Search` exposes `crawl_status`, `crawl_started_at`, `crawl_finished_at`, `crawl_progress`, and `last_crawl_error`.
- Bulk rule endpoint accepts `{search_ids, mode, sellers}` where mode is exactly `add`, `remove`, or `replace`, and returns a dry-run preview before mutation.

- [ ] **Step 1: Write failing rule tests**

  Test whitelist-only inclusion, blacklist-only exclusion, empty lists, blacklist precedence, and bulk add/remove/replace preview behavior.

- [ ] **Step 2: Add migration/model fields**

  Store normalized competitor seller IDs per search and crawl state separately from `Search.is_active`. Backfill current searches to empty rules and a completed/unknown crawl state without disabling them.

- [ ] **Step 3: Implement rule service and API**

  Validate seller IDs, normalize duplicates, return affected search counts, and require a confirmation token or explicit `apply=true` after preview for bulk mutation.

- [ ] **Step 4: Connect crawl lifecycle state**

  Set running at task start, completed at successful finish, error with a bounded message at failure, and paused when `is_active=false`. Do not claim a crawl is running from the active flag.

- [ ] **Step 5: Build the search workspace UI**

  Add tabs/sections for results, settings, competitors, and crawl history. The competitor editor supports seller search, whitelist/blacklist, add/remove/replace bulk operations, preview, and confirmation.

- [ ] **Step 6: Run focused checks**

  Run `cd backend && .venv/bin/pytest -q tests/test_seller_filter.py tests/test_search_rules_api.py`; run migration upgrade/downgrade in the project’s configured test database; run frontend typecheck.

- [ ] **Step 7: Commit**

  ```bash
  git add backend frontend
  git commit -m "feat(searches): add crawl states and competitor rules"
  ```

### Task 4: Enforce structured product identity and manual match decisions

**Files:**
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/0021_product_identity_and_match_decisions.py`
- Modify: `backend/app/services/matching.py`
- Modify: `backend/app/services/search_filter.py`
- Modify: `backend/app/api/routes/matching.py`
- Create: `backend/tests/test_matching_identity.py`
- Create: `frontend/app/components/match-evidence.tsx`
- Modify: `frontend/app/components/sku-modal.tsx`

**Interfaces:**
- `parse_product_identity(title, description) -> ProductIdentity` extracts brand, model family, generation, edition, capacity, configuration, and condition with confidence.
- `identity_conflict(left, right) -> list[str]` returns hard conflicts such as different model families or numeric generations.
- `rank_candidates` never returns candidates with hard identity conflicts unless a stored manual confirmation exists.
- Match endpoints support confirm, reject, and edit for one SKU/listing pair.

- [ ] **Step 1: Write regression tests first**

  Assert that `Devialet Gemini 2 Opera de Paris` does not match `Devialet Mania Opera de Paris` because model families conflict, while identical model/edition variants remain eligible. Add tests for numeric generation, capacity, bundle, and explicit manual confirmation.

- [ ] **Step 2: Implement deterministic identity normalization**

  Use explicit aliases and model-family tokens per search/category. Preserve unknown tokens instead of discarding them. Keep fuzzy similarity as a ranking signal only after hard-conflict checks.

- [ ] **Step 3: Persist match evidence and manual decisions**

  Store parsed fields, conflicts, accepted/rejected status, operator, timestamp, and reason. Manual decisions take precedence over future automatic refreshes.

- [ ] **Step 4: Restrict collection and statistics**

  Apply search include/exclude groups and model-family aliases before ranking. Excluded listings retain a machine-readable reason. Exclude ambiguous matches from price statistics.

- [ ] **Step 5: Add evidence UI and point editing**

  Show accepted fields, conflicting fields, source listing, confidence, and exclusion reason. Provide one-item confirm/reject/edit actions with a recalculation action.

- [ ] **Step 6: Run focused checks**

  Run `cd backend && .venv/bin/pytest -q tests/test_matching_identity.py tests/test_matching.py`; verify the Gemini/Mania regression through the API fixture; run frontend typecheck/build.

- [ ] **Step 7: Commit**

  ```bash
  git add backend frontend
  git commit -m "fix(matching): enforce product identity before pricing"
  ```

### Task 5: Make recommendations seller-scoped and item-level

**Files:**
- Create: `backend/app/api/routes/recommendations.py`
- Modify: `backend/app/api/main.py` or route registration module
- Modify: `backend/app/services/orchestrator.py`
- Modify: `backend/app/services/agents.py`
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/0022_recommendation_reviews.py`
- Create: `backend/tests/test_recommendations.py`
- Create: `frontend/app/recommendations/page.tsx`
- Create: `frontend/app/components/recommendation-card.tsx`
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- `GET /api/v1/recommendations?seller=<id>&status=<status>` returns item-level proposals with exact match IDs and evidence.
- `PATCH /api/v1/recommendations/{id}` edits only the proposed price/reason fields and records the operator.
- `POST /api/v1/recommendations/{id}/recalculate` refreshes evidence without applying a price.
- Approve/reject endpoints operate on one item; bulk approve requires a preview token.

- [ ] **Step 1: Write seller-isolation and approval tests**

  Assert seller A cannot receive seller B’s listings, point edits do not apply prices, rejected items cannot be approved without a new calculation, and bulk approval requires an explicit preview confirmation.

- [ ] **Step 2: Add review persistence and API**

  Link each proposal to seller, SKU, match snapshot, market sample, calculation time, confidence, reason, and review state. Preserve old snapshots when recalculating.

- [ ] **Step 3: Narrow agent data collection**

  Replace category-name substring selection with explicit playbook search IDs and seller ID. Return data lineage: which searches, listings, matches, and edits entered the report.

- [ ] **Step 4: Build the recommendation queue**

  Add filters for seller, confidence, status, category, and stale evidence. Cards show current/proposed price, exact comparison set, excluded set, freshness, risks, and point actions.

- [ ] **Step 5: Run focused checks and commit**

  Run backend recommendation tests, full backend tests, frontend typecheck/build, then commit:

  ```bash
  git add backend frontend
  git commit -m "feat(recommendations): add seller-scoped review queue"
  ```

### Task 6: Add source-backed web research

**Files:**
- Create: `backend/app/services/web_research.py`
- Modify: `backend/app/ai/schemas.py`
- Modify: `backend/app/ai/prompts.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/db/models.py`
- Create: `backend/migrations/versions/0023_research_sources.py`
- Create: `backend/tests/test_web_research.py`
- Modify: `backend/app/api/routes/recommendations.py`
- Create: `frontend/app/components/research-sources.tsx`

**Interfaces:**
- `research_product_identity(identity) -> ResearchResult` returns claims, source URL/title, retrieved time, and confidence.
- A claim without a URL is invalid and cannot be shown as verified evidence.
- Provider failures produce “Нужна проверка”, never fabricated certainty.

- [ ] **Step 1: Write tests for citation validation**

  Test valid sources, missing URLs, duplicate sources, provider timeout, and a research result that cannot resolve Gemini vs Mania.

- [ ] **Step 2: Implement provider abstraction and persistence**

  Keep the external search provider behind a small interface, store source metadata and claims, and configure timeout, result limit, and opt-in behavior explicitly.

- [ ] **Step 3: Add identity-verification integration**

  Use research to verify product identity/specification/edition only. Keep Avito listings as the sole source for observed market prices.

- [ ] **Step 4: Show citations in recommendations and agent evidence**

  Display source title, URL, retrieval time, supported claim, and confidence. Mark unresolved identity as “Нужна проверка”.

- [ ] **Step 5: Run focused checks and commit**

  Run `cd backend && .venv/bin/pytest -q tests/test_web_research.py tests/test_recommendations.py`; run typecheck/build; commit:

  ```bash
  git add backend frontend
  git commit -m "feat(ai): add source-backed product research"
  ```

### Task 7: Make agents and chat understandable

**Files:**
- Create: `frontend/app/agents/page.tsx`
- Create: `frontend/app/chat/page.tsx`
- Create: `frontend/app/components/agent-run-view.tsx`
- Modify: `frontend/app/components/agents-panel.tsx`
- Modify: `frontend/app/components/chat-panel.tsx`
- Modify: `backend/app/api/routes/agent.py`
- Modify: `backend/app/api/routes/chat.py`
- Create: `backend/tests/test_agent_lineage.py`

**Interfaces:**
- Agent run response contains selected seller/searches, input snapshot, source IDs, agent reports, consensus, conflicts, and item decisions.
- Chat responses distinguish explanation, research citation, and proposed action; action execution requires confirmation.

- [ ] **Step 1: Add lineage tests**

  Assert an agent report identifies its seller and searches, every proposal maps to an input/match snapshot, and chat action previews do not mutate state.

- [ ] **Step 2: Extend agent API and persistence**

  Return plain-language stages: “Что проверяем”, “Какие данные использованы”, “Что нашли”, “Где не уверены”, “Что предлагаем”. Persist conflicts and per-item decisions.

- [ ] **Step 3: Build the agent workspace**

  Add playbook selection, seller/search scope, run progress, evidence drawer, per-agent output, consensus explanation, conflicts, and per-item approve/reject/edit.

- [ ] **Step 4: Build the full chat page**

  Use a conversation column and evidence/action column. Render sources beside claims and structured previews beside mutations. Keep the compact header button as a link to `/chat`.

- [ ] **Step 5: Run checks and commit**

  Run backend agent/chat tests, full backend tests, frontend typecheck/build, and commit:

  ```bash
  git add backend frontend
  git commit -m "feat(workspaces): add transparent agents and chat"
  ```

### Task 8: Full UI/UX, accessibility, and release verification

**Files:**
- Modify: affected frontend components and docs
- Modify: `docs/user-guide.md`, `docs/accuracy.md`, `docs/plan.md`, `CHANGELOG.md`
- Test: `backend/tests/` and frontend build/typecheck

- [ ] **Step 1: Review each route at desktop/mobile widths**

  Check route title, active navigation, seller context, empty/loading/error states, focus order, keyboard operation, responsive overflow, and destructive-action confirmation.

- [ ] **Step 2: Run accessibility rule review**

  Check icon labels, form labels, semantic buttons/links, live regions, dialog focus, reduced motion, URL state, and long-content handling using the current Web Interface Guidelines.

- [ ] **Step 3: Run complete verification**

  ```bash
  cd backend
  .venv/bin/ruff check app tests scripts
  .venv/bin/mypy app
  .venv/bin/pytest -q
  cd ../frontend
  npx tsc --noEmit
  npm run build
  ```

- [ ] **Step 4: Verify production smoke paths**

  Check `/healthz`, each primary route, one seller switch, one search status, one competitor preview, one Gemini/Mania match decision, one recommendation edit preview, one citation, and one agent run without approving a price.

- [ ] **Step 5: Update documentation and commit release**

  Document the new navigation, seller context, search rules, identity matching, web evidence, and agent workflow. Commit only intended files and create a release after all checks pass.

## Self-review

- Spec coverage: navigation/settings (Tasks 1–2), search state/rules (Task 3), identity and manual matching (Task 4), item recommendations (Task 5), web evidence (Task 6), agents/chat (Task 7), accessibility/release (Task 8).
- No primary sidebar hash links remain after Task 1.
- Gemini/Mania regression is explicitly tested before recommendation work is accepted.
- Seller isolation is tested at API and UI-context boundaries.
- Price application remains behind existing API-only and approval gates.
- No task depends on an undefined interface; route/API names are explicitly specified above.
