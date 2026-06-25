# Speed to Lead v5 — Dashboard Fix & Role-Split — Mimo Execution Spec

> **Runner:** DeepSeek (Mimo) + headroom. **Owner:** Manav. **Planner:** Claude.
> **How to read:** Each TASK is self-contained (restates its files, steps, acceptance) so compression can't lose context. If something drops, re-read PROJECT FACTS + DECISIONS LOCKED + ROOT-CAUSE MAP below.
> **North star:** `v5-MIGRATION-BIBLE/PRD_HUMAN.md`. If a task contradicts it, STOP and ask.

---

## PROJECT FACTS (stable — preserve through compression)
- Stack: FastAPI + SQLAlchemy/SQLModel + PostgreSQL on Render. Live: `https://speed-to-lead-v5.onrender.com`. Push to `main` auto-deploys.
- Dashboard code: `app/dashboard/__init__.py` (~2098 lines). Templates: `app/dashboard/templates/` (base.html, leads.html, leads_partial.html, lead_detail.html, appointments.html, stats.html, team.html, settings.html, login.html).
- UI stack: custom CSS via CSS variables in `base.html` (no framework), HTMX 1.9.12, Jinja2, dark theme, Inter font. Mobile: viewport meta present, `@media (max-width:768px)` hides sidebar + shows a mobile bottom bar (`base.html:885-966`, nav `base.html:1076-1135`).
- Router mounted at `/dashboard`. Auth via signed cookie `session` = `{role:"rep"|"manager", rep_name, dealer_slug, ts}`. Helpers: `require_auth` (`:612`), `get_auth_role` (`:639`), `_check_lead_access` (`:650`), `get_dealer_from_auth` (`:164`). Logout route exists (`:846`).
- Lead pipeline entry for manual adds: `tools/route_lead.py::ingest_lead(session, dealer, NormalizedLead)`. `NormalizedLead` is in `app/adapters/intake`.
- Legal lead-state transitions: `app/engine/lifecycle.py::TRANSITIONS` + `transition()` (raises ValueError on illegal edge).
- **Run tests scoped:** `pytest tests/` (bare `pytest` errors on the `v4 archived/` copy). Baseline before this work: 184 passed, 1 skipped.
- Test dealer: `dealers/premier-auto.yaml`. Manager PIN `1234`; rep "Helly" PIN `7721` (active), "Vishva" PIN `4826`.

## DECISIONS LOCKED (Manav, final)
1. **Rep lead view:** a rep sees **ONLY their own assigned leads**. The unassigned/AI pool is **manager-only**; the manager assigns leads out. (Today reps wrongly see the shared unassigned pool — that's the "duplicate leads across reps" complaint.)
2. **New Lead button:** opens a **create-lead form** (manual add → real pipeline via `ingest_lead`).
3. **Rep stats:** reps see **their own** stats; manager sees full-team stats.
4. **Manager Suite** = Team + Settings + full-team Stats + all leads (incl. unassigned). Reps get Leads + Appointments + My Stats only.
5. **Mobile-first:** dashboard is used mostly on iOS/Android browsers; every fix must work on a phone viewport.
6. **UI aesthetic refresh is OUT OF SCOPE for this spec** — fixes only. (Beautification is a later batch.)

## OPERATING RULES FOR MIMO
1. Keep `pytest tests/` green after every task; report pass/fail.
2. Make the smallest change that fixes the root cause (cited below). Don't redesign working code.
3. Multi-tenancy is sacred: every dashboard DB query MUST filter by the logged-in dealer's `dealer_id` (already true — don't regress it).
4. Don't break the existing CSRF/login flow or the working `/leads` page — use it as the reference for how a route should pass context.
5. After all tasks pass, push to `main` (deploys). Report exactly what changed.

---

## ROOT-CAUSE MAP (already diagnosed — do not re-investigate)
- **"John Doe" name + grey-screen 500 on Appointments/Team/Settings/Stats/lead-detail:** these routes don't pass `user_name`/`user_role`/`user_initials` to `base.html`. Only `leads_list` does (`__init__.py:939-941`). Base footer has `|default('John Doe')` (`base.html:1040-1043`) so the *name* is cosmetic; the **500 must be confirmed at runtime** — likely a template var with no default in a page template, or a route exception. Fix by passing full context to every page (TASK D1) and then confirming each page renders (TASK D2).
- **Status dropdown "something went wrong":** dropdown renders all 10 states (`lead_detail.html:230`); illegal jump → `transition()` ValueError → route returns 400 (`__init__.py:1660-1669`) → HTMX `htmx:responseError` shows generic error (`base.html:1205-1207`).
- **Mark-lost double toast:** inline `onclick="showToast('Lead marked as lost')"` (`lead_detail.html:305`) + route returns 303 RedirectResponse w/ `HX-Trigger` (`__init__.py:1943-1945`) → HTMX treats redirect as error → 2nd toast. Same shape in mark-sold (`:1896-1898`).
- **Duplicate leads across reps:** rep query is `assigned_rep == rep_name OR assigned_rep IS NULL` (`__init__.py:876-886`); AND `/leads/partial` has **no** rep scoping (`__init__.py:967`) — cross-rep leak.
- **Manager pages exposed:** `/stats`, `/team`, `/settings`, `/appointments` have no role check.
- **No logout button:** route works (`__init__.py:846-850`); no link in any template.
- **New Lead dead:** button navigates to `?filter=new` which nothing reads (`leads.html:6-14`).
- **`logger` undefined:** dashboard imports `logging` only; `logger.exception` at `__init__.py:2114` NameErrors in the inventory-upload error path. Define `logger = logging.getLogger("speed-to-lead.dashboard")` at module top.
- Multi-tenancy (`dealer_id`) is solid — no cross-dealer leak.

---

# TASKS (in order)

## D1 — Shared base context + module logger (fixes the name bug, sets up the 500 fix)
**Files:** `app/dashboard/__init__.py`.
**Steps:**
1. Add at module top: `logger = logging.getLogger("speed-to-lead.dashboard")`.
2. Add a helper `_base_context(auth: dict) -> dict` returning `{"user_role": auth.get("role","rep").title(), "user_name": auth.get("rep_name") or auth.get("role","").title(), "user_initials": (auth["rep_name"][:2].upper() if auth.get("rep_name") else (auth.get("role","U")[0].upper()))}`. Reuse the exact logic already in `leads_list` (`:939-941`).
3. Merge `**_base_context(_auth)` into the template context of EVERY page route: `lead_detail` (`:1024`), `appointments_page` (`:1278`), `stats_page` (`:1117`), `team_page` (`:1206`), `settings_page` (`:1348`). (`leads_list` already has it — leave it or switch to the helper.)
**Acceptance:** Logged in as Helly, the sidebar shows "Helly"/"HE"/"Rep" on Leads AND Appointments/Stats/lead-detail (no "John Doe"). `pytest tests/` green.

## D2 — Confirm + fix the per-page 500s
**Goal:** No dashboard page returns a 500/grey screen for either role.
**Steps:**
1. Run the app locally (sqlite) and hit each page, OR drive it with `fastapi.testclient.TestClient` + a valid manager/rep session cookie (build via `app.dashboard._get_serializer().dumps({...})`), asserting status 200 for `/dashboard/leads`, `/appointments`, `/stats`, `/team`, `/settings`, `/leads/{id}`.
2. For any page still 500ing after D1, read the captured traceback and fix the specific cause (most likely an un-defaulted Jinja var in that page's template, or a None access in the route). Fix at the source.
**Acceptance:** All listed pages return 200 for manager; rep returns 200 for the pages a rep is allowed (see D3). Add a pytest in `tests/` that TestClient-loads each page for both roles and asserts 200/redirect (not 500).

## D3 — Role separation (Manager Suite)
**Files:** `app/dashboard/__init__.py`, `app/dashboard/templates/base.html`.
**Steps:**
1. Add a guard (dependency or inline) that redirects role!="manager" to `/dashboard/leads` (303) on: `team_page`, `settings_page`, and all `/settings/*` POST routes. Managers pass.
2. `stats_page`: branch on role — rep → stats computed over ONLY `assigned_rep == rep_name` leads ("My Stats"); manager → full-team stats (current behavior).
3. `base.html`: wrap the **Team** and **Settings** nav links in `{% if user_role == 'Manager' %} … {% endif %}` in BOTH the desktop sidebar (`:987-1035`) and the mobile bottom bar (`:1076-1135`). Stats stays visible to both (rep sees personal).
**Acceptance:** Rep Helly: no Team/Settings links (desktop + mobile); directly visiting `/dashboard/team` or `/dashboard/settings` redirects to Leads; `/dashboard/stats` shows only her numbers. Manager: sees and can open all. `pytest tests/` green.

## D4 — Lead scoping: a rep sees only their own
**Files:** `app/dashboard/__init__.py`.
**Steps:**
1. `leads_list` rep branch (`:876-886`): change `(assigned_rep == rep_name) | (assigned_rep.is_(None))` → `assigned_rep == rep_name`. Keep the `dealer_id` filter. Manager branch unchanged (sees all incl. unassigned).
2. `leads_partial` (`:951-1020`): add the SAME role scoping (rep → `assigned_rep == rep_name`; manager → all) — currently it has none and leaks all dealer leads.
3. `_check_lead_access` (`:650-662`) rep branch: `return lead.assigned_rep == rep_name` (drop the `or lead.assigned_rep is None`). Manager bypass stays.
4. `lead_detail` rep guard (`:1043`): a rep may view only `assigned_rep == rep_name` (404/redirect otherwise).
5. `appointments_page` (`:1278`): reps → only appointments whose lead `assigned_rep == rep_name`; managers → all. (Join already filters `dealer_id`.)
**Acceptance:** Helly and Vishva no longer see the same leads — each sees only leads assigned to her; unassigned leads appear only for the manager. Filtering (HTMX partial) respects this. Appointments scoped per role. Add a pytest covering rep vs manager `leads_list`/`leads_partial`/`_check_lead_access`. `pytest tests/` green.

## D5 — Logout button
**Files:** `app/dashboard/templates/base.html`.
**Steps:** Add a visible logout link/button in the sidebar footer (near the user info, `:1038-1046`) and in the mobile nav → `href="/dashboard/logout"`. (Route already clears the cookie and redirects to login.)
**Acceptance:** Clicking Logout (desktop + mobile) returns to the login page and the session is cleared (revisiting `/dashboard/leads` redirects to login).

## D6 — New Lead → create-lead form
**Files:** `app/dashboard/templates/leads.html`, `app/dashboard/__init__.py`, reuse `tools/route_lead.py::ingest_lead`.
**Steps:**
1. Replace the dead New Lead button (`leads.html:6-14`) with a button that opens a modal (the base.html `.modal-overlay/.modal` styles already exist) containing a form: name, phone, vehicle interest (all simple inputs), CSRF token, posting (hx-post) to `POST /dashboard/leads/new`.
2. Add route `POST /dashboard/leads/new` (require_auth + CSRF check like login): build a `NormalizedLead` (source = web/manual, name, phone, vehicle_ref) and call `ingest_lead(session, current_dealer, lead_data)`. If the creator is a rep, set the new lead's `assigned_rep` to them; if manager, leave unassigned. Return a 200 success toast (`X-Toast-Message` header, see D8) and trigger a list refresh (`HX-Trigger` to reload the leads list, or `HX-Redirect: /dashboard/leads`).
**Acceptance:** Clicking New Lead opens a form; submitting creates a lead that appears in the list (under the creating rep) and enters the pipeline; cancel closes the modal. Works on mobile. `pytest tests/` green (add a TestClient test that POSTs and asserts a Lead row is created).

## D7 — Status dropdown shows only legal next-states
**Files:** `app/dashboard/__init__.py` (`lead_detail`, `update_lead_status`), `app/dashboard/templates/lead_detail.html`.
**Steps:**
1. In `lead_detail`, compute `allowed = sorted(s.value for s in TRANSITIONS.get(lead.state, set()))` from `app/engine/lifecycle.py::TRANSITIONS`; pass to the template.
2. In `lead_detail.html:230`, render only `[current_state] + allowed` in the dropdown (current shown as selected/disabled).
3. In `update_lead_status` (`:1638-1687`): on a rejected/illegal transition, return a friendly toast (200 with `X-Toast-Message: "Can't move a {state} lead to {target}"`, type=error) instead of a bare 400 that shows the generic error.
**Acceptance:** The dropdown never offers an illegal jump (e.g. a SOLD lead shows no options; an APPT_SET lead offers only SHOWED/LOST/OPTED_OUT). Selecting a valid one works; no generic "something went wrong." `pytest tests/` green.

## D8 — Toast / HTMX standardization (kill double + generic toasts)
**Files:** `app/dashboard/templates/base.html`, `lead_detail.html`, mutating routes in `app/dashboard/__init__.py` (reassign `:1575`, status `:1638`, mark-sold `:1860`, mark-lost `:1903`, messages, follow-up, activity).
**Steps:**
1. Remove inline `onclick="showToast(...)"` from mark-lost (`lead_detail.html:305`) and any other action button (the premature toast).
2. Standardize every mutating route to return **200** `HTMLResponse` (small body) with headers `X-Toast-Message` + `X-Toast-Type` — the existing `htmx:afterRequest` handler (`base.html:1195-1204`) already shows those. For navigation, use `HX-Redirect: /dashboard/leads` instead of a 303 `RedirectResponse`.
3. Improve `htmx:responseError` (`base.html:1205-1207`) to show `e.detail.xhr.getResponseHeader('X-Toast-Message')` when present, else the generic message.
4. In `reassign_lead` (`:1575-1635`) wrap the `notify_rep` call in try/except (it shouldn't raise, but a raise currently 500s the action) and still return the success toast.
**Acceptance:** Mark-lost / mark-sold / reassign / status each show EXACTLY ONE correct toast; success actions never show "something went wrong"; the list updates. `pytest tests/` green.

## D9 — Playwright e2e harness (the real-user test Manav asked for)
**Files (new):** `tests/e2e/` — `package.json`, `playwright.config.ts`, a launch/seed helper, `dashboard.spec.ts`. (Node v22 + `npx playwright@1.61` are available.)
**Steps:**
1. Launch helper: start uvicorn locally with env `DATABASE_URL=sqlite:///./e2e.db`, `OUTBOUND_ENABLED=false`, `QUIET_HOURS_DISABLED=true`, `REQUIRE_TWILIO_SIGNATURE=false`, dashboard secret + the premier-auto PINs; capture uvicorn stderr to a log file so 500 tracebacks are visible. App auto-provisions `premier-auto` on startup.
2. Seed step: insert leads (some `assigned_rep="Helly"`, some `"Vishva"`, some unassigned), one Appointment, a couple Messages — directly via the sqlite DB or a seed endpoint/script.
3. `dashboard.spec.ts`: for **rep (Helly/7721)** and **manager (1234)**, on **desktop AND iPhone viewport** — log in; visit every nav page and assert 200 + no `.error`/grey screen + capture console errors + screenshot; click New Lead (form opens, submit creates), reassign dropdown, status dropdown (only legal opts), mark-lost (single toast), mark-sold, logout. Assert rep does NOT see Team/Settings and sees only her leads; manager sees all.
4. Output a per-feature pass/fail report.
**Acceptance:** `npx playwright test` (from `tests/e2e/`) passes for both roles on desktop + mobile. Commit the harness so it's reusable. (If a browser can't launch in Mimo's env, still deliver the script + seed and run `pytest tests/`; Manav/Claude will run Playwright for real-time confirmation.)

## D10 — Mobile verification + targeted fixes
**Files:** `app/dashboard/templates/base.html` (CSS/mobile bottom bar), affected templates.
**Steps:** Using the iPhone-viewport Playwright run, fix anything broken on mobile: role-gated bottom bar (Team/Settings hidden for reps), the New Lead modal sizing, status/reassign dropdown usability, toast position, tap-target sizes. Layout is already responsive (`base.html:885-966`) — this is verification + small CSS fixes, not a rewrite.
**Acceptance:** The full Playwright suite passes at iPhone viewport; no horizontal overflow; all actions usable by thumb.

## D11 — Final verify + deploy
**Steps:**
1. `pytest tests/` green (≥184 + the new tests).
2. `npx playwright test` green (or script delivered if no browser).
3. Commit (clear message) and push to `main` (Render auto-deploys). Do NOT commit the `v4 archived/` submodule or the `e2e.db` sqlite file (gitignore it).
4. Report a before/after summary of every file changed.
**Acceptance:** Live dashboard: rep logs in → only own leads, no Team/Settings, working logout, correct name, single toasts, working New Lead form, legal-only status options; manager → full access; all good on a phone.

---

## OUT OF SCOPE (do NOT do now)
- UI aesthetic/theme refresh (separate later batch — Claude will compile inspiration links; Manav picks; then restyle via base.html CSS variables).
- Backend issues already tracked elsewhere (CSRF on all POSTs, web-form abuse, per-rep booking, scheduler-per-worker, etc.) — not part of this dashboard spec unless a task above touches them.

## ORDER RECAP
D1 base context+logger → D2 confirm/fix 500s → D3 role split → D4 rep lead scoping → D5 logout → D6 New Lead form → D7 status dropdown → D8 toast standardization → D9 Playwright harness → D10 mobile → D11 verify+deploy.
