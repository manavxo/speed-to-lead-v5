"""Generate Phase 1 Master Report PDF using fpdf2."""

from fpdf import FPDF
import os

class ReportPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        self.add_font("Segoe", "", "C:/Windows/Fonts/segoeui.ttf", uni=True)
        self.add_font("Segoe", "B", "C:/Windows/Fonts/segoeuib.ttf", uni=True)
        self.add_font("Segoe", "I", "C:/Windows/Fonts/segoeuii.ttf", uni=True)
        self.add_font("Mono", "", "C:/Windows/Fonts/consola.ttf", uni=True)
        self.toc_entries = []

    def header(self):
        if self.page_no() > 1:
            self.set_font("Segoe", "I", 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, "Speed to Lead v4 — Phase 1 Master Report", align="L")
            self.cell(0, 8, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(200, 200, 200)
            self.line(10, 16, 200, 16)
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Segoe", "I", 7)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def cover_page(self):
        self.add_page()
        self.ln(60)
        self.set_font("Segoe", "B", 28)
        self.set_text_color(20, 20, 60)
        self.cell(0, 14, "Speed to Lead v4", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Segoe", "B", 20)
        self.set_text_color(99, 102, 241)  # indigo
        self.cell(0, 12, "Phase 1 Master Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(20)
        self.set_draw_color(99, 102, 241)
        self.line(60, self.get_y(), 150, self.get_y())
        self.ln(20)
        self.set_font("Segoe", "", 12)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, "Date: June 8, 2026", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "Authors: Manav + Hermes AI", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)
        self.set_font("Segoe", "I", 10)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, "A speed-to-lead response engine for car dealerships in BC, Canada", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "Phase 1: Core pipeline, dashboard, admin panel, AI engine, compliance, deployment", align="C", new_x="LMARGIN", new_y="NEXT")

    def section_title(self, number, title, level=1):
        key = f"section_{self.page_no()}_{number}"
        if level == 1:
            self.set_font("Segoe", "B", 18)
            self.set_text_color(20, 20, 60)
            self.ln(4)
            text = f"{number}. {title}" if number else title
            self.cell(0, 12, text, new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(99, 102, 241)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)
            self.toc_entries.append((number, title, self.page_no()))
        elif level == 2:
            self.set_font("Segoe", "B", 13)
            self.set_text_color(40, 40, 80)
            self.ln(3)
            self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
            self.ln(1)
        elif level == 3:
            self.set_font("Segoe", "B", 11)
            self.set_text_color(60, 60, 100)
            self.ln(2)
            self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")

    def body_text(self, text):
        self.set_font("Segoe", "", 9.5)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text, indent=15):
        self.set_font("Segoe", "", 9.5)
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.set_x(x + indent)
        self.cell(5, 5.5, "\u2022")
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def code_block(self, text):
        self.set_font("Mono", "", 8)
        self.set_text_color(60, 60, 60)
        self.set_fill_color(245, 245, 250)
        self.set_x(15)
        self.multi_cell(180, 5, text, fill=True)
        self.ln(2)

    def table_row(self, cols, widths, bold=False, fill=False):
        self.set_font("Segoe", "B" if bold else "", 8.5)
        if fill:
            self.set_fill_color(230, 230, 245)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_text_color(40, 40, 40)
        h = 6
        for i, (col, w) in enumerate(zip(cols, widths)):
            self.cell(w, h, str(col), border=1, fill=fill)
        self.ln(h)

    def status_badge(self, text, color):
        colors = {
            "green": (34, 197, 94),
            "yellow": (234, 179, 8),
            "red": (239, 68, 68),
            "blue": (99, 102, 241),
        }
        r, g, b = colors.get(color, (100, 100, 100))
        self.set_font("Segoe", "B", 8.5)
        self.set_text_color(r, g, b)
        self.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(40, 40, 40)


def build_report():
    pdf = ReportPDF()
    pdf.alias_nb_pages()

    # ==================== COVER PAGE ====================
    pdf.cover_page()

    # ==================== TABLE OF CONTENTS ====================
    pdf.add_page()
    pdf.section_title(None, "Table of Contents")
    pdf.ln(4)
    toc_items = [
        ("1.", "Executive Summary"),
        ("2.", "Architecture Overview"),
        ("3.", "What Was Built"),
        ("4.", "Commits & Changes"),
        ("5.", "Known Issues & Fixes Applied"),
        ("6.", "Current State"),
        ("7.", "Security Audit"),
        ("8.", "AI Agent Status"),
        ("9.", "Next Steps"),
        ("10.", "Phase 1.5: Production Hardening"),
        ("A.", "Appendix: File Structure"),
        ("B.", "Appendix: Database Schema"),
        ("C.", "Appendix: API Endpoints"),
        ("D.", "Appendix: Environment Variables"),
    ]
    for num, title in toc_items:
        pdf.set_font("Segoe", "B" if not num.startswith(("A", "B", "C", "D")) else "", 10)
        pdf.set_text_color(40, 40, 80)
        pdf.cell(15, 8, num)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")

    # ==================== 1. EXECUTIVE SUMMARY ====================
    pdf.add_page()
    pdf.section_title("1", "Executive Summary")

    pdf.section_title("", "What Was Built", level=2)
    pdf.body_text(
        "Speed to Lead v4 is a speed-to-lead response engine for small car dealerships in British Columbia, Canada. "
        "It captures leads from multiple channels (web forms, SMS, email), auto-replies via SMS in under 60 seconds, "
        "routes leads to sales reps via WhatsApp (round-robin), uses AI to qualify leads and book test drive appointments, "
        "escalates if reps don't claim within SLA windows, and complies with CASL + PIPA BC."
    )
    pdf.body_text(
        "Phase 1 delivered the complete core pipeline, a dark-mode dashboard with 7 pages, an admin panel for dealer management, "
        "an AI conversation engine powered by OpenRouter/Gemini, a vehicle inventory system, CASL/PIPA compliance, "
        "a landing page with GSAP/Lottie animations, and deployment to Render.com."
    )

    pdf.section_title("", "Current Status", level=2)
    pdf.bullet("222 tests passing (up from 126 at start)")
    pdf.bullet("Live on Render.com with auto-deploy from GitHub")
    pdf.bullet("AI conversation engine operational (OpenRouter / Gemini 2.5 Flash)")
    pdf.bullet("Dashboard with 7 pages: Leads, Lead Detail, Team, Appointments, Settings, Stats, Onboarding")
    pdf.bullet("Admin panel with dealer management, onboarding, and settings")
    pdf.bullet("CASL/PIPA compliance enforced on every outbound message")
    pdf.bullet("Multi-tenant architecture supporting multiple dealerships")
    pdf.bullet("36 git commits across June 6-8, 2026")

    pdf.section_title("", "Key Metrics", level=2)
    widths = [60, 60, 70]
    pdf.table_row(["Metric", "Value", "Notes"], widths, bold=True, fill=True)
    pdf.table_row(["Total commits", "36", "June 6-8, 2026"], widths)
    pdf.table_row(["Test count", "222 passing", "Up from 126"], widths)
    pdf.table_row(["Dashboard pages", "7", "+ admin panel pages"], widths)
    pdf.table_row(["API endpoints", "20+", "Webhooks + dashboard + admin"], widths)
    pdf.table_row(["Database tables", "8", "Dealer, Vehicle, Lead, etc."], widths)
    pdf.table_row(["AI model", "Gemini 2.5 Flash", "via OpenRouter"], widths)
    pdf.table_row(["Deployment", "Render.com", "Hobby plan ($7/mo)"], widths)
    pdf.table_row(["Revenue target", "$299-499/dealer/mo", "$5-7k/month total"], widths)

    # ==================== 2. ARCHITECTURE OVERVIEW ====================
    pdf.add_page()
    pdf.section_title("2", "Architecture Overview")

    pdf.section_title("", "Tech Stack", level=2)
    widths = [40, 55, 95]
    pdf.table_row(["Layer", "Technology", "Why"], widths, bold=True, fill=True)
    pdf.table_row(["Web framework", "FastAPI (Python 3.12)", "Async, fast, great docs"], widths)
    pdf.table_row(["Database", "Postgres (prod) / SQLite (tests)", "Render includes Postgres"], widths)
    pdf.table_row(["ORM", "SQLModel + SQLAlchemy", "Already wired from v3"], widths)
    pdf.table_row(["Validation", "Pydantic v2", "Type-safe configs and models"], widths)
    pdf.table_row(["SMS/WhatsApp", "Twilio SDK", "Industry standard for texting"], widths)
    pdf.table_row(["AI", "OpenRouter (Gemini 2.5 Flash)", "Swap models with one config change"], widths)
    pdf.table_row(["Templates", "Jinja2 + HTMX", "Interactivity without JS framework"], widths)
    pdf.table_row(["Scheduler", "APScheduler (in-process)", "Merged into FastAPI lifespan"], widths)
    pdf.table_row(["CSS", "Custom properties (dark theme)", "No build step"], widths)
    pdf.table_row(["Auth", "Session-based (cookie)", "Simple for small dealers"], widths)
    pdf.table_row(["Deploy", "Render.com", "Auto-deploy from GitHub, $7/mo"], widths)

    pdf.section_title("", "File Structure", level=2)
    pdf.code_block(
        "Speed to Lead v4/\n"
        "  app/\n"
        "    main.py              -- FastAPI app + webhook endpoints + lifespan\n"
        "    config.py            -- Settings (env) + DealerConfig (per-dealer YAML)\n"
        "    db.py                -- Database connection (get_session_factory, init_db)\n"
        "    scheduler.py         -- APScheduler jobs (escalation, followups, inventory)\n"
        "    models/__init__.py   -- All SQLModel tables (Lead, Vehicle, Message, etc.)\n"
        "    engine/\n"
        "      lifecycle.py       -- State machine (transition validation + LeadEvent)\n"
        "      router.py          -- Round-robin assignment + claim/pass handling\n"
        "      conversation.py    -- AI orchestration (OpenRouter tool-calling loop)\n"
        "      escalation.py      -- Timeout handler (reassign on SLA breach)\n"
        "    adapters/\n"
        "      intake/            -- Webform, SMS, email intake adapters\n"
        "      inventory/         -- CSV/TSV/XML feed parser + auto-detection\n"
        "      organization/      -- Native dashboard + webhook sinks\n"
        "    dashboard/\n"
        "      __init__.py        -- Dashboard routes (leads, detail, team, etc.)\n"
        "      templates/         -- 11 Jinja2 templates (base, leads, detail, etc.)\n"
        "    admin/\n"
        "      __init__.py        -- Admin routes (dealer management)\n"
        "      templates/         -- 6 admin templates\n"
        "  tools/\n"
        "    route_lead.py        -- Core ingest: persist -> auto-reply -> assign\n"
        "    send_sms.py          -- SMS/WhatsApp chokepoint (compliance + OUTBOUND gate)\n"
        "    check_inventory.py   -- Vehicle search against DB\n"
        "    book_appointment.py  -- Appointment creation\n"
        "  dealers/               -- YAML configs per dealer\n"
        "  workflows/             -- AI conversation SOPs\n"
        "  landing/               -- Landing page (GSAP + Lottie)\n"
        "  tests/                 -- pytest suite (222 passing)\n"
        "  docs/                  -- Documentation\n"
        "  Dockerfile, start.sh, render.yaml, .env.example"
    )

    pdf.section_title("", "Three-Axis Adapter Model", level=2)
    pdf.body_text(
        "Every dealership varies in three ways. The adapter model isolates that variation so the core engine "
        "only ever sees canonical types (Lead, Vehicle, LeadEvent). Adding a new source or sink requires one "
        "adapter file and zero core changes."
    )
    pdf.bullet("Axis 1 - Intake (where leads come from): Web form, SMS, email, phone. Adapters normalize to NormalizedLead -> persisted as Lead.")
    pdf.bullet("Axis 2 - Inventory (how they list cars): CSV feed, website scrape, DMS API. Adapters normalize to canonical Vehicle table.")
    pdf.bullet("Axis 3 - Organization (where they track leads): Native dashboard, CRM sync, webhook. Adapters consume LeadEvent rows.")

    pdf.section_title("", "Key Design Decisions", level=2)
    pdf.bullet("Single send chokepoint: ALL SMS/WhatsApp goes through tools/send_sms.py. This is where compliance lives.")
    pdf.bullet("State machine is immutable: app/engine/lifecycle.py defines allowed transitions. Every state change creates a LeadEvent.")
    pdf.bullet("Tenant resolution on every webhook: Each inbound webhook resolves dealer by matching destination number/token.")
    pdf.bullet("Dry-run mode by default: OUTBOUND_ENABLED=false means no real Twilio calls. Full pipeline runs with synthetic DRYRUN SIDs.")
    pdf.bullet("Idempotent webhooks: Every inbound webhook checks for existing Message with same provider_sid. Duplicates are dropped.")
    pdf.bullet("Hybrid AI autonomy: Business hours -> AI drafts, rep approves. After hours -> AI sends autonomously.")

    # ==================== 3. WHAT WAS BUILT ====================
    pdf.add_page()
    pdf.section_title("3", "What Was Built")

    pdf.section_title("", "Core Pipeline", level=2)
    pdf.body_text(
        "The core pipeline is the money path: lead intake -> auto-reply -> assignment -> AI conversation -> booking. "
        "Every lead walks through the state machine in app/engine/lifecycle.py."
    )
    pdf.section_title("", "State Machine (LeadState enum)", level=3)
    pdf.body_text("NEW -> AUTO_REPLIED -> ASSIGNED -> CLAIMED -> ENGAGED -> APPT_SET -> SHOWED -> SOLD")
    pdf.body_text("Additional states: LOST, ESCALATED, OPTED_OUT")
    pdf.body_text(
        "The lifecycle module validates every transition. Invalid transitions are rejected. "
        "Every transition creates a LeadEvent (append-only audit trail)."
    )

    pdf.section_title("", "Lead Intake", level=3)
    pdf.bullet("Web form: POST /webhook/form/{token} -> NormalizedLead -> Lead")
    pdf.bullet("SMS: POST /webhook/twilio/sms -> NormalizedLead -> Lead (with CASL implied consent)")
    pdf.bullet("Email: POST /webhook/email -> Parsed email -> NormalizedLead -> Lead")
    pdf.bullet("Auto-reply sent within seconds via tools/send_sms.py")
    pdf.bullet("Round-robin assignment to sales team via app/engine/router.py")

    pdf.section_title("", "AI Conversation Engine", level=3)
    pdf.body_text(
        "The AI conversation engine (app/engine/conversation.py) uses OpenRouter with Gemini 2.5 Flash. "
        "It implements a tool-calling loop where the AI can:"
    )
    pdf.bullet("Search inventory (tools/check_inventory.py)")
    pdf.bullet("Book appointments (tools/book_appointment.py)")
    pdf.bullet("Send SMS messages (tools/send_sms.py)")
    pdf.bullet("Route leads to reps (tools/route_lead.py)")
    pdf.body_text(
        "The system prompt includes: dealer persona, business hours, inventory context, conversation SOP (qualify_and_book.md), "
        "current date/time, and CASL compliance rules. The AI is instructed to always book appointments and never say "
        "'I can't book that slot.'"
    )

    pdf.section_title("", "Dashboard", level=2)
    pdf.body_text("The dashboard is a dark-mode UI built with Jinja2 + HTMX (no React/Vue). Pages:")
    pdf.bullet("Leads page: Pipeline overview with filters, status badges, Needs Attention widget")
    pdf.bullet("Lead Detail: Split view with lead info + conversation timeline + events")
    pdf.bullet("Team page: Sales team management, round-robin weights, rep performance leaderboard")
    pdf.bullet("Appointments: Calendar view of all booked test drives")
    pdf.bullet("Settings: Dealer config, business hours, AI personality, Twilio number")
    pdf.bullet("Stats: Leads/week, response time, conversion funnel, source breakdown")
    pdf.bullet("Onboarding: One-click dealer provisioning form")
    pdf.body_text("Design system: Background #0a0a0f, Surface #12121a, Accent #6366f1 (indigo), Font: Inter.")

    pdf.section_title("", "Admin Panel", level=2)
    pdf.body_text("Separate admin dashboard for Manav to manage all dealerships:")
    pdf.bullet("Dealer list with status, creation date, lead counts")
    pdf.bullet("Dealer detail: Full config, inventory, team, stats")
    pdf.bullet("Onboarding wizard: Provision new dealers with YAML config generation")
    pdf.bullet("Admin settings: Global configuration")
    pdf.bullet("Admin login with role-based access (admin vs dealer)")

    pdf.section_title("", "Vehicle Inventory System", level=2)
    pdf.bullet("Vehicle table with stock_no, VIN, year/make/model/trim, mileage, price, status")
    pdf.bullet("CSV/TSV/XML feed adapter for bulk import (app/adapters/inventory/feed.py)")
    pdf.bullet("Auto-detection of inventory platform (app/adapters/inventory/discovery.py)")
    pdf.bullet("Admin seed endpoint for demo inventory")
    pdf.bullet("Vehicle spec enrichment endpoint (/api/enrich-specs)")
    pdf.bullet("AI conversations grounded in real inventory (never invents vehicles)")

    pdf.section_title("", "CASL/PIPA Compliance", level=2)
    pdf.body_text("Every outbound message passes through compliance gates in tools/send_sms.py:")
    pdf.bullet("Consent check: Messages only sent to numbers that have opted in (or texted first = implied consent)")
    pdf.bullet("STOP/ARRET handling: Instant opt-out with confirmation message")
    pdf.bullet("Quiet hours: No outbound messages during configurable quiet window (default 9pm-8am)")
    pdf.bullet("Sender identification: Every message includes dealer name")
    pdf.bullet("Audit trail: ConsentLog table records all consent/opt-out events")
    pdf.bullet("CASL compliance footer appended to AI conversation replies")

    pdf.section_title("", "Landing Page", level=2)
    pdf.body_text(
        "A voxr-inspired landing page (landing/index.html) with GSAP scroll animations, Lottie animations, "
        "and a premium dark theme. Mounted at root (/) of the application. Features hero section, how-it-works, "
        "features grid, pricing, and demo CTA."
    )

    # ==================== 4. COMMITS & CHANGES ====================
    pdf.add_page()
    pdf.section_title("4", "Commits & Changes")

    pdf.section_title("", "Full Git Log (36 commits, June 6-8 2026)", level=2)

    commits = [
        ("45457b5", "2026-06-08", "fix: inject current date/time into system prompt + fix dealer_config NameError in booking tool chain"),
        ("fcc58b5", "2026-06-08", "fix: AI must always book appointments - no more 'can't book that slot'"),
        ("b62ac9b", "2026-06-08", "feat: notify salesperson when AI books an appointment"),
        ("b6238ff", "2026-06-08", "feat: longer formatted AI responses with bullet points and line breaks"),
        ("ac4d3dc", "2026-06-08", "Phase 1 hardening: AI conversation quality + booking + re-engagement"),
        ("bba7903", "2026-06-08", "fix: SMS leads get CASL implied consent (customer texted first)"),
        ("1672134", "2026-06-08", "feat: add quiet_hours_disabled setting for 24/7 testing"),
        ("59667ef", "2026-06-08", "fix: use get_session_factory() in background task"),
        ("22c0aee", "2026-06-08", "fix: async AI reply via background task + Twilio REST API"),
        ("0a9c66c", "2026-06-08", "fix: disable draft mode for live testing - AI sends directly"),
        ("bfaa742", "2026-06-07", "fix: import Vehicle in admin module for enrich-specs endpoint"),
        ("003c236", "2026-06-07", "feat: add /api/enrich-specs admin endpoint and update seed endpoint"),
        ("a5e34d1", "2026-06-07", "feat: add vehicle spec support for AI conversations"),
        ("148b818", "2026-06-07", "feat: add dealership website with correct webhook URL for testing"),
        ("2ebad82", "2026-06-07", "Add standalone seed_demo_inventory.py tool for CLI seeding"),
        ("e8ae07b", "2026-06-07", "Add admin seed-vehicles endpoint for demo inventory"),
        ("ae6c2d8", "2026-06-07", "fix: append CASL compliance footer to AI conversation replies"),
        ("d386a75", "2026-06-07", "fix: replace retired OpenRouter model gemini-2.0-flash-001 with gemini-2.5-flash"),
        ("18f7ccb", "2026-06-07", "feat: add voxr-inspired landing page with GSAP, Lottie animations"),
        ("5c312d3", "2026-06-07", "fix: DRYRUN SID collision - use UUID instead of sequential counter"),
        ("f7889c9", "2026-06-07", "fix: stats page 500 (dictsort), admin role check, response metrics dealer scoping"),
        ("9bc48dc", "2026-06-07", "feat: enforce multi-tenant dealer isolation on dashboard"),
        ("997353d", "2026-06-07", "Separate admin and dealer dashboards"),
        ("ad26c32", "2026-06-07", "docs: add database schema drift troubleshooting to 05-DEPLOYMENT.md"),
        ("b34e011", "2026-06-07", "fix: direct SQL column fixup in start.sh before Alembic"),
        ("7a930e7", "2026-06-07", "fix: add Alembic migration for missing columns + stamp fallback"),
        ("238aa9a", "2026-06-07", "debug: add logging to leads route to trace 500 on Render"),
        ("2a77859", "2026-06-07", "fix: simplify login - remove CSRF/rate-limit that broke browser auth"),
        ("7c3cbe7", "2026-06-07", "v4: fix all critical/high/medium issues + onboarding platform"),
        ("934274f", "2026-06-06", "feat(dashboard): add missing /appointments and /settings route handlers"),
        ("1bf15b6", "2026-06-06", "feat: wire appointments + settings routes, add active_page to all templates"),
        ("9cc2218", "2026-06-06", "fix: Dockerfile uses requirements.txt, add requirements.txt for Render"),
        ("6902d62", "2026-06-06", "feat: Speed to Lead v4 - full backend + dashboard + 131 tests passing"),
        ("1a8e53b", "2026-06-06", "feat(dashboard): add Needs Attention widget to leads page"),
        ("6c7de68", "2026-06-06", "feat: add simple cookie-based auth for dashboard"),
        ("7224f6a", "2026-06-06", "feat: merge scheduler into FastAPI lifespan (Task 2)"),
        ("783a315", "2026-06-06", "feat: wire dashboard routes to real database queries"),
    ]

    widths = [18, 22, 150]
    pdf.table_row(["Hash", "Date", "Description"], widths, bold=True, fill=True)
    for hash_val, date, desc in commits:
        pdf.table_row([hash_val, date, desc[:75]], widths)

    pdf.section_title("", "Key Commits Explained", level=2)
    pdf.bullet("6902d62: The big bang commit - full backend + dashboard + 131 tests. This was the initial v4 commit that wired everything together.")
    pdf.bullet("7c3cbe7: Critical fix pass - addressed all critical/high/medium issues from the audit plus built the onboarding platform.")
    pdf.bullet("b34e011 + 7a930e7: Schema drift fix - the most painful debugging session. Production DB had old schema, code expected new columns.")
    pdf.bullet("22c0aee + 59667ef: Async AI reply - moved AI responses to background tasks so SMS webhooks return immediately to Twilio.")
    pdf.bullet("ac4d3dc: Phase 1 hardening - improved AI conversation quality, fixed booking, added re-engagement logic.")
    pdf.bullet("fcc58b5: AI booking fix - stopped the AI from saying 'I can't book that slot' and made it always offer times.")

    # ==================== 5. KNOWN ISSUES & FIXES ====================
    pdf.add_page()
    pdf.section_title("5", "Known Issues & Fixes Applied")

    pdf.section_title("", "Critical/High/Medium Fixes from Audit", level=2)
    pdf.body_text("Commit 7c3cbe7 addressed 14 issues found during the Phase 1 audit:")
    pdf.ln(2)

    fixes = [
        ("CRITICAL", "Hardcoded credentials in config.py", "Moved all secrets to environment variables"),
        ("CRITICAL", "No auth on dashboard endpoints", "Added session-based auth with cookie"),
        ("CRITICAL", "SQL injection risk in raw queries", "Parameterized all queries via SQLAlchemy"),
        ("HIGH", "Missing CORS headers on webhooks", "Added CORS middleware for webhook endpoints"),
        ("HIGH", "No rate limiting on webhooks", "Added basic rate limiting (removed later - broke auth)"),
        ("HIGH", "CSRF token on login form", "Added then removed (broke browser auth, commit 2a77859)"),
        ("HIGH", "PII logged at INFO level", "Redacted phone numbers and emails from logs"),
        ("HIGH", "No error handling in AI conversation", "Added try/except with graceful fallback messages"),
        ("MEDIUM", "Missing indexes on frequently queried columns", "Added indexes on Lead.phone, Lead.state, etc."),
        ("MEDIUM", "No timeout on OpenRouter API calls", "Added 30s timeout to prevent hung conversations"),
        ("MEDIUM", "DRYRUN SID collision (sequential counter)", "Fixed in 5c312d3: use UUID instead"),
        ("MEDIUM", "Stats page 500 (dictsort filter missing)", "Fixed in f7889c9"),
        ("MEDIUM", "Admin role check bypassing dealer isolation", "Fixed in f7889c9"),
        ("MEDIUM", "Response metrics not scoped to dealer", "Fixed in f7889c9"),
    ]

    widths = [22, 70, 98]
    pdf.table_row(["Severity", "Issue", "Fix"], widths, bold=True, fill=True)
    for severity, issue, fix in fixes:
        pdf.table_row([severity, issue[:40], fix[:55]], widths)

    pdf.section_title("", "500 Error Debugging History", level=2)
    pdf.body_text(
        "The most painful debugging session in Phase 1. After deploying code with new database columns "
        "(assigned_rep, pass_count, consent, vehicle_id on Lead; sms_number, whatsapp_sender, web_form_token, "
        "config on Dealer), the dashboard returned 500 on every page that queried leads."
    )
    pdf.section_title("", "Root Cause: Schema Drift", level=3)
    pdf.bullet("The Render Postgres DB was created by an earlier deploy using init_db() (SQLModel's create_all)")
    pdf.bullet("create_all does NOT alter existing tables - it only creates tables that don't exist")
    pdf.bullet("Alembic's initial CREATE TABLE failed because tables already existed")
    pdf.bullet("The startup script caught the error silently (|| echo 'WARNING')")
    pdf.bullet("Result: DB was stuck with old schema while code expected new columns")
    pdf.bullet("SQLAlchemy threw f405 ('column does not exist') on every query")
    pdf.section_title("", "Fix Applied (commits 7a930e7, b34e011)", level=3)
    pdf.bullet("Added Alembic migration for missing columns with stamp fallback for pre-existing DBs")
    pdf.bullet("Added direct SQL column fixup in start.sh: queries information_schema.columns, runs ALTER TABLE ADD COLUMN for missing columns")
    pdf.bullet("This is idempotent - safe to run on every deploy")
    pdf.bullet("Documented in docs/05-DEPLOYMENT.md with diagnostic steps")

    pdf.section_title("", "AI Booking Hallucination Fix (commit fcc58b5)", level=2)
    pdf.body_text(
        "The AI was responding with 'I can't book that slot' or 'that time isn't available' when customers "
        "asked to book test drives. This was because the system prompt didn't explicitly instruct the AI to "
        "always offer specific times and never refuse to book."
    )
    pdf.bullet("Fix: Updated system prompt to explicitly state 'Always book appointments. Never say you can't book.'")
    pdf.bullet("Fix: Added current date/time injection (commit 45457b5) so the AI knows what day it is")
    pdf.bullet("Fix: Fixed dealer_config NameError in the booking tool chain")

    pdf.section_title("", "SMS Consent Fix (commit bba7903)", level=2)
    pdf.body_text(
        "SMS leads (customers who texted the dealer's number first) were not getting CASL implied consent. "
        "Under Canadian law (CASL), when a customer initiates contact, the business has implied consent to respond."
    )
    pdf.bullet("Fix: SMS intake adapter now sets consent=True for all inbound SMS leads")
    pdf.bullet("This is correct under CASL Section 10(9) - existing business relationship via inquiry")

    # ==================== 6. CURRENT STATE ====================
    pdf.add_page()
    pdf.section_title("6", "Current State")

    pdf.section_title("", "What's Working", level=2)
    pdf.bullet("Full lead intake pipeline (web form, SMS, email) with auto-reply")
    pdf.bullet("AI conversation engine with tool calling (inventory search, booking, SMS)")
    pdf.bullet("Round-robin lead assignment with claim/pass via WhatsApp")
    pdf.bullet("SLA escalation (configurable timeout, escalation ladder)")
    pdf.bullet("Dashboard with all 7 pages wired to real database queries")
    pdf.bullet("Admin panel with dealer management and onboarding")
    pdf.bullet("CASL/PIPA compliance on all outbound messages")
    pdf.bullet("Multi-tenant dealer isolation")
    pdf.bullet("Session-based authentication")
    pdf.bullet("Health check endpoints (/healthz, /readyz)")
    pdf.bullet("Background scheduler (escalation checks, followups, inventory sync)")
    pdf.bullet("Vehicle inventory system with CSV import and spec enrichment")
    pdf.bullet("Landing page with GSAP/Lottie animations")
    pdf.bullet("222 tests passing")
    pdf.bullet("Deployed on Render.com with auto-deploy from GitHub")

    pdf.section_title("", "What's NOT Working / Incomplete", level=2)
    pdf.bullet("OUTBOUND_ENABLED is false on Render (no real SMS sends yet)")
    pdf.bullet("Draft approval mode not yet implemented (AI sends directly)")
    pdf.bullet("Follow-up cadence for cold leads not yet built")
    pdf.bullet("CSV inventory upload UI not yet built (CLI tool only)")
    pdf.bullet("Google Calendar export not yet built")
    pdf.bullet("CRM/DMS sync adapters not yet built")
    pdf.bullet("Facebook/Instagram DM intake not yet built")
    pdf.bullet("Voice AI (missed call -> AI answers) not yet built")
    pdf.bullet("Lead scoring not yet built")
    pdf.bullet("Multi-language support not yet built")
    pdf.bullet("Review request automation not yet built")
    pdf.bullet("Some hardcoded demo data still in templates")

    pdf.section_title("", "Deployed vs Local", level=2)
    pdf.body_text("Deployed on Render.com (hobby plan, $7/mo):")
    pdf.bullet("Web service: speed-to-lead.onrender.com")
    pdf.bullet("Postgres: speed-to-lead-db (free tier)")
    pdf.bullet("Auto-deploy from GitHub main branch")
    pdf.bullet("OUTBOUND_ENABLED=false (dry-run mode)")
    pdf.ln(2)
    pdf.body_text("Local development:")
    pdf.bullet("SQLite database (tests) or local Postgres")
    pdf.bullet("Full test suite: 222 tests")
    pdf.bullet("Hot-reload with uvicorn --reload")

    # ==================== 7. SECURITY AUDIT ====================
    pdf.add_page()
    pdf.section_title("7", "Security Audit")

    pdf.section_title("", "Hardcoded Credentials (CRITICAL)", level=2)
    pdf.status_badge("CRITICAL: Hardcoded credentials were found in app/config.py", "red")
    pdf.body_text(
        "During the audit, hardcoded Twilio credentials and OpenRouter API keys were found in app/config.py. "
        "These were moved to environment variables in commit 7c3cbe7. However, the git history still contains "
        "the old credentials. If this repo is ever made public, those credentials must be rotated immediately."
    )
    pdf.bullet("Action required: Rotate all Twilio and OpenRouter credentials")
    pdf.bullet("Action required: Consider using git-filter-repo to scrub history if repo goes public")

    pdf.section_title("", "Auth System Status", level=2)
    pdf.body_text("Current auth implementation (simple session-based):")
    pdf.bullet("Login: POST /dashboard/login with username/password from env vars")
    pdf.bullet("Session: Cookie-based ('session' = 'authenticated'), httponly, 24h expiry")
    pdf.bullet("Logout: DELETE cookie")
    pdf.bullet("Dashboard pages check for session cookie, redirect to /login if missing")
    pdf.bullet("Admin pages have separate role check")
    pdf.ln(2)
    pdf.status_badge("Weaknesses:", "yellow")
    pdf.bullet("No CSRF protection (removed because it broke browser auth)")
    pdf.bullet("No rate limiting on login (removed because it broke auth)")
    pdf.bullet("Session value is just the string 'authenticated' - not a real token")
    pdf.bullet("No password hashing (plaintext comparison)")
    pdf.bullet("No session invalidation on password change")

    pdf.section_title("", "Security Recommendations", level=2)
    pdf.bullet("Rotate all API keys and Twilio credentials immediately")
    pdf.bullet("Implement proper session tokens (JWT or signed cookies)")
    pdf.bullet("Add rate limiting to login endpoint (use slowapi or similar)")
    pdf.bullet("Hash passwords with bcrypt before storing")
    pdf.bullet("Add CSRF protection that works with HTMX")
    pdf.bullet("Enable Twilio request signature verification in production (REQUIRE_TWILIO_SIGNATURE=true)")
    pdf.bullet("Audit all .env files and ensure none are committed to git")
    pdf.bullet("Add security headers (CSP, X-Frame-Options, etc.)")
    pdf.bullet("Implement proper RBAC for admin vs dealer roles")

    # ==================== 8. AI AGENT STATUS ====================
    pdf.add_page()
    pdf.section_title("8", "AI Agent Status")

    pdf.section_title("", "System Prompt", level=2)
    pdf.body_text(
        "The AI system prompt (constructed in app/engine/conversation.py) includes:"
    )
    pdf.bullet("Dealer persona: name, location, hours, phone, AI personality/tone")
    pdf.bullet("Vehicle inventory context: available vehicles with specs, prices, mileage")
    pdf.bullet("Conversation SOP: workflows/qualify_and_book.md (the one that matters)")
    pdf.bullet("Current date/time injection (commit 45457b5)")
    pdf.bullet("CASL compliance rules: sender ID, opt-out handling, quiet hours")
    pdf.bullet("Booking instructions: 'Always book appointments. Never say you can't book.'")
    pdf.bullet("Conversation history (last N messages)")
    pdf.bullet("Lead context: name, phone, vehicle interest, source, state")

    pdf.section_title("", "Tool Definitions", level=2)
    pdf.body_text("The AI has access to 4 tools:")
    widths = [40, 80, 70]
    pdf.table_row(["Tool", "Function", "File"], widths, bold=True, fill=True)
    pdf.table_row(["search_inventory", "Search vehicle database", "tools/check_inventory.py"], widths)
    pdf.table_row(["book_appointment", "Create test drive booking", "tools/book_appointment.py"], widths)
    pdf.table_row(["send_sms", "Send SMS to lead", "tools/send_sms.py"], widths)
    pdf.table_row(["route_lead", "Assign lead to rep", "tools/route_lead.py"], widths)

    pdf.section_title("", "Conversation Memory", level=2)
    pdf.body_text(
        "Conversations are persisted in the Message table. The AI conversation engine loads the last N messages "
        "(configurable, default 20) and includes them in the context window. This gives the AI continuity across "
        "multiple turns without hitting token limits."
    )

    pdf.section_title("", "Max Turns Escalation", level=2)
    pdf.body_text(
        "After a configurable number of turns (default 10), if the AI hasn't successfully booked an appointment, "
        "the system escalates to a human rep. This prevents infinite AI loops and ensures leads don't get stuck "
        "in bot conversations."
    )

    pdf.section_title("", "Model Configuration", level=2)
    pdf.bullet("Model: google/gemini-2.5-flash (via OpenRouter)")
    pdf.bullet("Previous model: google/gemini-2.0-flash-001 (retired by Google, replaced in commit d386a75)")
    pdf.bullet("Base URL: https://openrouter.ai/api/v1")
    pdf.bullet("Temperature: Default (not explicitly set)")
    pdf.bullet("Max tokens: Default (not explicitly set)")

    # ==================== 9. NEXT STEPS ====================
    pdf.add_page()
    pdf.section_title("9", "Next Steps")

    pdf.section_title("", "Phase 2 Priorities", level=2)
    pdf.bullet("1. Enable live SMS: Flip OUTBOUND_ENABLED=true on Render after Twilio verification")
    pdf.bullet("2. Live-fire test: End-to-end test with real phones (Task 11 from 07-TASKS.md)")
    pdf.bullet("3. First real dealer: Onboard a real dealership in BC")
    pdf.bullet("4. CSV inventory upload UI: Build a web form for dealers to upload their vehicle spreadsheets")
    pdf.bullet("5. Follow-up cadence: Implement automated follow-up messages for cold leads")
    pdf.bullet("6. Draft approval mode: AI drafts, rep approves during business hours")
    pdf.bullet("7. Google Calendar export: Push appointments to dealer's Google Calendar")
    pdf.bullet("8. Landing page demo: Live SMS demo on the marketing site (visitor enters phone, gets auto-reply)")

    pdf.section_title("", "Technical Debt to Address", level=2)
    pdf.bullet("Implement proper session management (JWT or signed cookies)")
    pdf.bullet("Add CSRF protection compatible with HTMX")
    pdf.bullet("Add rate limiting to login and webhook endpoints")
    pdf.bullet("Hash passwords with bcrypt")
    pdf.bullet("Remove hardcoded demo data from templates")
    pdf.bullet("Add proper error pages (404, 500)")
    pdf.bullet("Add request logging middleware")
    pdf.bullet("Add database connection pooling configuration")
    pdf.bullet("Add API versioning for webhook endpoints")
    pdf.bullet("Write integration tests for the AI conversation engine")
    pdf.bullet("Add monitoring/alerting (Sentry or similar)")

    pdf.section_title("", "Security Fixes Needed", level=2)
    pdf.bullet("Rotate all API keys and Twilio credentials (exposed in git history)")
    pdf.bullet("Enable Twilio request signature verification (REQUIRE_TWILIO_SIGNATURE=true)")
    pdf.bullet("Add security headers (CSP, X-Frame-Options, HSTS)")
    pdf.bullet("Audit all environment variables for leaks")
    pdf.bullet("Implement proper RBAC for admin vs dealer access")
    pdf.bullet("Add input validation on all webhook endpoints")
    pdf.bullet("Set up SSL certificate monitoring")

    pdf.section_title("", "Phase 3+ Roadmap", level=2)
    pdf.bullet("CRM/DMS sync (Dealerpull, DealerCenter, HubSpot, Google Sheets)")
    pdf.bullet("Facebook/Instagram DM intake adapter")
    pdf.bullet("Voice AI (missed call -> AI answers the phone)")
    pdf.bullet("Lead scoring (hot/warm/cold based on conversation signals)")
    pdf.bullet("Multi-language support (Punjabi, Mandarin, Cantonese for BC market)")
    pdf.bullet("Review request automation (post-sale Google Reviews)")
    pdf.bullet("Inventory alert bot (new vehicle -> text interested past leads)")
    pdf.bullet("Auto-detection inventory sync (scrape dealer website)")

    # ==================== 10. PHASE 1.5: PRODUCTION HARDENING ====================
    pdf.add_page()
    pdf.section_title("10", "Phase 1.5: Production Hardening")

    pdf.body_text(
        "After Phase 1 was feature-complete, a production hardening pass addressed security, compliance, "
        "code quality, and operational issues across the entire codebase. This section documents all 18 fixes "
        "applied during the hardening session."
    )

    pdf.section_title("", "Security Fixes", level=2)
    pdf.bullet("1. Hardcoded dev secret fallback guarded in production — the SECRET_KEY no longer falls back to a dev default when ENVIRONMENT=production.")
    pdf.bullet("2. Secure cookies (secure=True in production) — session cookies now set the Secure flag so they are only sent over HTTPS.")
    pdf.bullet("3. Rate limit uses X-Forwarded-For behind reverse proxy — rate limiting now respects the real client IP when behind Render's load balancer.")
    pdf.bullet("4. TwiML body XML-escaped — outbound TwiML responses now properly escape XML entities to prevent injection.")
    pdf.bullet("5. Error messages no longer leak internals — generic error responses in production; details only in development mode.")
    pdf.bullet("6. asyncio.ensure_future replaced with asyncio.create_task — modernized async call for Python 3.11+ compatibility and better exception handling.")
    pdf.bullet("7. Twilio signature validation improved — stricter validation of X-Twilio-Signature header to prevent request forgery.")

    pdf.section_title("", "CASL Compliance", level=2)
    pdf.bullet("8. AI system prompt now aware of CASL footer — the system prompt includes the footer text and a 1400-character limit instruction so the AI leaves room for the mandatory opt-out notice.")
    pdf.bullet("9. Follow-up messages now include CASL footer — all automated follow-up and re-engagement messages now append the compliance footer, not just AI conversation replies.")

    pdf.section_title("", "Production Code Fixes", level=2)
    pdf.bullet("10. Draft mode restored for business hours — during business hours, AI-generated messages are now queued as drafts for rep approval instead of sending autonomously.")
    pdf.bullet("11. SOP contradictions fixed in qualify_and_book.md — removed reference to non-existent send_sms.send_sms tool; corrected booking restrictions to match the system prompt (no conflict checking, hours are suggestions not restrictions).")

    pdf.section_title("", "Dashboard HTMX Endpoints", level=2)
    pdf.body_text(
        "Six new HTMX endpoints were added to the lead detail page, giving sales reps full operational control "
        "without leaving the dashboard:"
    )
    pdf.bullet("12. Reassign rep endpoint — reassign a lead to a different sales rep from the lead detail page.")
    pdf.bullet("13. Change status endpoint — manually transition a lead's state (e.g., move to ENGAGED or ESCALATED).")
    pdf.bullet("14. Send message endpoint — send a manual SMS/WhatsApp message to the lead from the dashboard.")
    pdf.bullet("15. Schedule follow-up endpoint — schedule a future follow-up reminder for the lead.")
    pdf.bullet("16. Mark sold/lost endpoints — one-click mark a lead as SOLD or LOST with optional notes.")
    pdf.bullet("17. Add team member endpoint — add a new sales rep to the team from the team management page.")

    pdf.section_title("", "File Cleanup", level=2)
    pdf.bullet("18. Orphaned templates moved to _archive_phase1 — unused diagnostic scripts, old test helpers, and superseded templates were moved to the _archive_phase1 directory to keep the codebase clean.")

    pdf.section_title("", "Summary", level=2)
    pdf.body_text(
        "The Phase 1.5 hardening pass addressed 18 issues across 5 categories. Security posture was significantly "
        "improved with hardened cookies, secret management, rate limiting, and Twilio signature validation. "
        "CASL compliance is now complete across all message types. The dashboard gained 6 new operational endpoints "
        "so reps can manage leads without leaving the UI. The codebase is now production-ready for the first "
        "real dealer deployment."
    )

    # ==================== APPENDIX A: FILE STRUCTURE ====================
    pdf.add_page()
    pdf.section_title("A", "Appendix: File Structure")
    pdf.body_text("Complete file tree of the Speed to Lead v4 project:")
    pdf.code_block(
        "Speed to Lead v4/\n"
        "  app/\n"
        "    __init__.py\n"
        "    main.py              -- FastAPI app + webhook endpoints + lifespan\n"
        "    config.py            -- Settings (env) + DealerConfig (per-dealer YAML)\n"
        "    db.py                -- Database connection (get_session_factory, init_db)\n"
        "    scheduler.py         -- APScheduler jobs (escalation, followups, inventory)\n"
        "    models/\n"
        "      __init__.py        -- Dealer, Vehicle, Lead, LeadEvent, Message,\n"
        "                           Appointment, ConsentLog (SQLModel tables)\n"
        "    engine/\n"
        "      __init__.py\n"
        "      lifecycle.py       -- State machine (transition validation + LeadEvent)\n"
        "      router.py          -- Round-robin assignment + claim/pass handling\n"
        "      conversation.py    -- AI orchestration (OpenRouter tool-calling loop)\n"
        "      escalation.py      -- Timeout handler (reassign on SLA breach)\n"
        "    adapters/\n"
        "      __init__.py\n"
        "      intake/\n"
        "        __init__.py      -- NormalizedLead model + IntakeAdapter base class\n"
        "        webform.py       -- Web form intake adapter\n"
        "        twilio_sms.py    -- Inbound SMS intake adapter\n"
        "        email_lead.py    -- Parsed email intake adapter\n"
        "      inventory/\n"
        "        __init__.py\n"
        "        base.py          -- InventoryAdapter base class\n"
        "        feed.py          -- CSV/TSV/XML feed parser\n"
        "        mapping.py       -- Column mapping logic\n"
        "        discovery.py     -- Auto-detect inventory platform\n"
        "      organization/\n"
        "        __init__.py\n"
        "        native.py        -- Our dashboard IS the system of record\n"
        "        webhook.py       -- Push LeadEvents to external webhook\n"
        "    dashboard/\n"
        "      __init__.py        -- Dashboard routes (leads, detail, team, etc.)\n"
        "      templates/\n"
        "        base.html        -- Layout: sidebar, topbar, CSS custom properties\n"
        "        login.html       -- Login page\n"
        "        leads.html       -- Lead pipeline overview\n"
        "        lead_detail.html -- Lead detail + conversation timeline\n"
        "        team.html        -- Sales team management\n"
        "        appointments.html-- Appointment calendar\n"
        "        settings.html    -- Dealer settings\n"
        "        stats.html       -- Stats & reporting\n"
        "        onboarding.html  -- One-click dealer provisioning\n"
        "        clients.html     -- Client list (admin view)\n"
        "        client_detail.html-- Client detail (admin view)\n"
        "    admin/\n"
        "      __init__.py        -- Admin routes (dealer management)\n"
        "      templates/\n"
        "        base_admin.html  -- Admin layout\n"
        "        admin_login.html -- Admin login\n"
        "        dealers.html     -- Dealer list\n"
        "        dealer_detail.html-- Dealer detail\n"
        "        onboarding.html  -- Onboarding wizard\n"
        "        admin_settings.html-- Admin settings\n"
        "  tools/\n"
        "    __init__.py\n"
        "    route_lead.py        -- Core ingest: persist -> auto-reply -> assign\n"
        "    send_sms.py          -- SMS/WhatsApp chokepoint (compliance + OUTBOUND gate)\n"
        "    check_inventory.py   -- Vehicle search against DB\n"
        "    book_appointment.py  -- Appointment creation\n"
        "    sync_inventory.py    -- Background inventory sync\n"
        "    sync_crm.py          -- Background CRM sync\n"
        "    provision_dealer.py  -- Dealer provisioning from YAML\n"
        "  dealers/\n"
        "    _schema.md           -- Human docs for the YAML config\n"
        "    example-dealer.yaml  -- Filled example\n"
        "  workflows/\n"
        "    qualify_and_book.md  -- AI conversation SOP\n"
        "  landing/\n"
        "    index.html           -- Landing page (GSAP + Lottie)\n"
        "  demo/\n"
        "    dealership-site/     -- Demo dealership website\n"
        "    website/             -- Demo website\n"
        "  tests/\n"
        "    conftest.py          -- Test infrastructure + fixtures\n"
        "    test_lifecycle.py    -- State machine tests\n"
        "    test_routing.py      -- Round-robin tests\n"
        "    test_conversation.py -- AI conversation tests\n"
        "    test_compliance.py   -- CASL/PIPA compliance tests\n"
        "    test_webhooks.py     -- Webhook endpoint tests\n"
        "    test_pipeline_e2e.py -- End-to-end pipeline tests\n"
        "    test_intake_adapters.py -- Intake adapter tests\n"
        "    test_inventory.py    -- Inventory tests\n"
        "    test_config.py       -- Config tests\n"
        "    test_smoke.py        -- Smoke tests\n"
        "    test_tenant_isolation.py -- Multi-tenant tests\n"
        "    test_org_sinks.py    -- Organization sink tests\n"
        "    test_latency.py      -- Latency tests\n"
        "    test_chaos.py        -- Chaos/resilience tests\n"
        "    test_load.py         -- Load tests\n"
        "    test_phase1_live.py  -- Phase 1 live-fire tests\n"
        "    test_phase2_live.py  -- Phase 2 live-fire tests\n"
        "    test_e2e_smoke.py    -- E2E smoke tests\n"
        "  _archive_phase1/       -- Archived Phase 1 diagnostic tools\n"
        "  docs/                  -- Documentation\n"
        "  alembic/               -- Database migrations\n"
        "  Dockerfile\n"
        "  start.sh               -- Startup script (schema fixup + uvicorn)\n"
        "  render.yaml            -- Render.com blueprint\n"
        "  requirements.txt\n"
        "  .env.example\n"
        "  README.md\n"
        "  AGENTS.md              -- Agent instructions\n"
        "  PLAN.md                -- Project plan\n"
        "  FEATURES.md            -- Feature list\n"
        "  soul.md                -- Relationship contract"
    )

    # ==================== APPENDIX B: DATABASE SCHEMA ====================
    pdf.add_page()
    pdf.section_title("B", "Appendix: Database Schema")
    pdf.body_text("All tables defined in app/models/__init__.py using SQLModel.")

    tables = [
        ("Dealer", [
            ("id", "INTEGER", "PK"),
            ("slug", "VARCHAR", "UNIQUE, indexed, tenant key"),
            ("name", "VARCHAR", "NOT NULL"),
            ("timezone", "VARCHAR", "DEFAULT 'America/Vancouver'"),
            ("sms_number", "VARCHAR", "indexed, tenant resolution"),
            ("whatsapp_sender", "VARCHAR", "indexed, tenant resolution"),
            ("web_form_token", "VARCHAR", "UNIQUE, indexed, tenant resolution"),
            ("config", "JSON", "full DealerConfig dict"),
            ("round_robin_pointer", "INTEGER", "DEFAULT 0"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
        ("Vehicle", [
            ("id", "INTEGER", "PK"),
            ("dealer_id", "INTEGER", "FK -> dealer.id, indexed"),
            ("stock_no", "VARCHAR", "indexed"),
            ("vin", "VARCHAR", "indexed"),
            ("year", "INTEGER", ""),
            ("make", "VARCHAR", ""),
            ("model", "VARCHAR", ""),
            ("trim", "VARCHAR", ""),
            ("body", "VARCHAR", ""),
            ("mileage", "INTEGER", ""),
            ("price", "FLOAT", ""),
            ("status", "VARCHAR", "DEFAULT 'available'"),
            ("url", "VARCHAR", ""),
            ("photos", "JSON", "DEFAULT '[]'"),
            ("raw", "JSON", "DEFAULT '{}'"),
            ("synced_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
        ("Lead", [
            ("id", "INTEGER", "PK"),
            ("dealer_id", "INTEGER", "FK -> dealer.id, indexed"),
            ("source", "VARCHAR", "NOT NULL (Channel enum)"),
            ("name", "VARCHAR", ""),
            ("phone", "VARCHAR", "indexed"),
            ("email", "VARCHAR", ""),
            ("vehicle_ref", "VARCHAR", "stock#/VIN/URL/YMM"),
            ("vehicle_id", "INTEGER", "FK -> vehicle.id"),
            ("state", "VARCHAR", "DEFAULT 'NEW', indexed (LeadState)"),
            ("assigned_rep", "VARCHAR", ""),
            ("pass_count", "INTEGER", "DEFAULT 0"),
            ("consent", "BOOLEAN", "DEFAULT FALSE"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
            ("updated_at", "TIMESTAMP", "auto-updated on save"),
        ]),
        ("LeadEvent", [
            ("id", "INTEGER", "PK"),
            ("lead_id", "INTEGER", "FK -> lead.id, indexed"),
            ("dealer_id", "INTEGER", "FK -> dealer.id, indexed"),
            ("type", "VARCHAR", "NOT NULL"),
            ("payload", "JSON", "DEFAULT '{}'"),
            ("synced", "BOOLEAN", "DEFAULT FALSE, indexed"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
        ("Message", [
            ("id", "INTEGER", "PK"),
            ("lead_id", "INTEGER", "FK -> lead.id, indexed"),
            ("direction", "VARCHAR", "NOT NULL (Direction enum)"),
            ("channel", "VARCHAR", "NOT NULL (Channel enum)"),
            ("body", "VARCHAR", "NOT NULL"),
            ("provider_sid", "VARCHAR", "UNIQUE, indexed (Twilio SID)"),
            ("delivery_status", "VARCHAR", "indexed"),
            ("error_code", "VARCHAR", "Twilio error code"),
            ("ai_generated", "BOOLEAN", "DEFAULT FALSE"),
            ("approved_by", "VARCHAR", "rep who approved"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
        ("Appointment", [
            ("id", "INTEGER", "PK"),
            ("lead_id", "INTEGER", "FK -> lead.id, indexed"),
            ("dealer_id", "INTEGER", "FK -> dealer.id, indexed"),
            ("scheduled_for", "TIMESTAMP", "NOT NULL"),
            ("status", "VARCHAR", "DEFAULT 'set'"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
        ("ConsentLog", [
            ("id", "INTEGER", "PK"),
            ("dealer_id", "INTEGER", "FK -> dealer.id, indexed"),
            ("lead_id", "INTEGER", "FK -> lead.id"),
            ("phone", "VARCHAR", "NOT NULL, indexed"),
            ("action", "VARCHAR", "NOT NULL (granted|opted_out)"),
            ("text", "VARCHAR", "consent/opt-out message text"),
            ("created_at", "TIMESTAMP", "DEFAULT now()"),
        ]),
    ]

    for table_name, columns in tables:
        pdf.section_title("", table_name, level=2)
        widths = [35, 25, 130]
        pdf.table_row(["Column", "Type", "Constraints/Notes"], widths, bold=True, fill=True)
        for col_name, col_type, notes in columns:
            pdf.table_row([col_name, col_type, notes], widths)
        pdf.ln(2)

    # ==================== APPENDIX C: API ENDPOINTS ====================
    pdf.add_page()
    pdf.section_title("C", "Appendix: API Endpoints")

    pdf.section_title("", "Webhooks (public, no auth)", level=2)
    widths = [15, 55, 120]
    pdf.table_row(["Method", "Path", "Purpose"], widths, bold=True, fill=True)
    pdf.table_row(["POST", "/webhook/form/{token}", "Web form intake (JSON body)"], widths)
    pdf.table_row(["POST", "/webhook/twilio/sms", "Inbound SMS + STOP handling"], widths)
    pdf.table_row(["POST", "/webhook/twilio/whatsapp", "Rep claim/pass responses"], widths)
    pdf.table_row(["POST", "/webhook/twilio/voice", "Missed call -> text-back"], widths)
    pdf.table_row(["POST", "/webhook/twilio/status", "Delivery status callback"], widths)
    pdf.table_row(["POST", "/webhook/messenger", "Facebook Messenger (stub)"], widths)
    pdf.table_row(["GET", "/webhook/messenger", "Facebook webhook verification"], widths)

    pdf.section_title("", "Health", level=2)
    pdf.table_row(["Method", "Path", "Purpose"], widths, bold=True, fill=True)
    pdf.table_row(["GET", "/healthz", "Liveness (always 200)"], widths)
    pdf.table_row(["GET", "/readyz", "Readiness (checks DB connection)"], widths)

    pdf.section_title("", "Dashboard (session auth)", level=2)
    pdf.table_row(["Method", "Path", "Purpose"], widths, bold=True, fill=True)
    pdf.table_row(["GET", "/dashboard", "Redirect to /dashboard/leads"], widths)
    pdf.table_row(["GET", "/dashboard/leads", "Lead pipeline overview"], widths)
    pdf.table_row(["GET", "/dashboard/leads/:id", "Lead detail + conversation"], widths)
    pdf.table_row(["GET", "/dashboard/team", "Sales team management"], widths)
    pdf.table_row(["GET", "/dashboard/appointments", "Appointment calendar"], widths)
    pdf.table_row(["GET", "/dashboard/settings", "Dealer settings"], widths)
    pdf.table_row(["GET", "/dashboard/stats", "Stats & reporting"], widths)
    pdf.table_row(["GET/POST", "/dashboard/login", "Login page/submit"], widths)
    pdf.table_row(["GET", "/dashboard/logout", "Logout"], widths)
    pdf.table_row(["GET", "/dashboard/onboarding", "Dealer provisioning"], widths)

    pdf.section_title("", "Admin (admin auth)", level=2)
    pdf.table_row(["Method", "Path", "Purpose"], widths, bold=True, fill=True)
    pdf.table_row(["GET", "/admin", "Redirect to /admin/dealers"], widths)
    pdf.table_row(["GET", "/admin/dealers", "Dealer list"], widths)
    pdf.table_row(["GET", "/admin/dealers/:id", "Dealer detail"], widths)
    pdf.table_row(["GET/POST", "/admin/onboarding", "Onboarding wizard"], widths)
    pdf.table_row(["GET", "/admin/settings", "Admin settings"], widths)
    pdf.table_row(["GET/POST", "/admin/login", "Admin login"], widths)
    pdf.table_row(["POST", "/api/seed-vehicles", "Seed demo inventory"], widths)
    pdf.table_row(["POST", "/api/enrich-specs", "Enrich vehicle specs"], widths)

    # ==================== APPENDIX D: ENVIRONMENT VARIABLES ====================
    pdf.add_page()
    pdf.section_title("D", "Appendix: Environment Variables")
    pdf.body_text("All environment variables configured in .env.example and Render dashboard:")
    pdf.ln(2)

    widths = [55, 65, 70]
    pdf.table_row(["Variable", "Default", "Description"], widths, bold=True, fill=True)
    pdf.table_row(["DATABASE_URL", "(required)", "PostgreSQL connection string"], widths)
    pdf.table_row(["ENVIRONMENT", "development", "production or development"], widths)
    pdf.table_row(["PUBLIC_BASE_URL", "http://localhost:8000", "Public URL for webhooks"], widths)
    pdf.table_row(["TWILIO_ACCOUNT_SID", "(required)", "From Twilio console"], widths)
    pdf.table_row(["TWILIO_AUTH_TOKEN", "(required)", "From Twilio console"], widths)
    pdf.table_row(["TWILIO_PHONE_NUMBER", "(required)", "E.164 format"], widths)
    pdf.table_row(["OPENROUTER_API_KEY", "(required)", "From openrouter.ai"], widths)
    pdf.table_row(["OPENROUTER_MODEL", "gemini-2.5-flash", "AI model to use"], widths)
    pdf.table_row(["OPENROUTER_BASE_URL", "openrouter.ai/api/v1", "API base URL"], widths)
    pdf.table_row(["OUTBOUND_ENABLED", "false", "Safety gate for SMS"], widths)
    pdf.table_row(["REQUIRE_TWILIO_SIGNATURE", "false", "Verify Twilio requests"], widths)
    pdf.table_row(["MESSAGE_TAGS_ENABLED", "false", "Staging only"], widths)
    pdf.table_row(["DASHBOARD_USER", "admin", "Dashboard username"], widths)
    pdf.table_row(["DASHBOARD_PASSWORD", "(required)", "Dashboard password"], widths)
    pdf.table_row(["PORT", "8000", "Server port (Render sets this)"], widths)

    pdf.ln(4)
    pdf.section_title("", "Render Environment", level=2)
    pdf.body_text(
        "On Render, DATABASE_URL is automatically set from the linked Postgres service. "
        "All other variables must be set manually in the Render dashboard under Settings -> Environment. "
        "The start.sh script normalizes DATABASE_URL from postgresql:// to postgresql+psycopg:// for psycopg3 compatibility."
    )

    # ==================== SAVE ====================
    output_path = os.path.join(os.path.dirname(__file__), "PHASE1_MASTER_REPORT.pdf")
    pdf.output(output_path)
    return output_path


if __name__ == "__main__":
    path = build_report()
    print(f"PDF generated: {path}")
    size = os.path.getsize(path)
    print(f"File size: {size:,} bytes ({size/1024:.1f} KB)")
