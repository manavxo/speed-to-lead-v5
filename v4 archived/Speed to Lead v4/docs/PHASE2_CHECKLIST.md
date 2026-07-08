---
title: "Speed to Lead v4 — Phase 2 Client-Side Testing Checklist"
subtitle: "Dashboard Features & Client Service Verification"
date: "June 8, 2026"
---

# SPEED TO LEAD v4 — PHASE 2 CHECKLIST
## Client-Side Features & Service Delivery Verification

**Date:** June 8, 2026  
**Live URL:** https://speed-to-lead-8tfi.onrender.com  
**Test Credentials:** dealer=premier-auto, user=admin, pw=Sunday@123  
**Test Command:** `pytest -q --tb=short`  
**Current Status:** Phase 1 complete (222 tests, 317 leads, Twilio ON)

---

## SECTION 1: DEALERSHIP OWNER / GENERAL MANAGER

These features serve the person who pays for the product. They need to see ROI, manage their team, and trust the system.

### 1.1 Login & Authentication
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 1 | Secure login with dealer slug | POST /dashboard/login with valid slug+user+pw → 302 to /dashboard/leads, session cookie set | [ ] |
| 2 | Invalid credentials rejected | POST with wrong password → 401 + "Invalid credentials" message | [ ] |
| 3 | Unknown dealer slug rejected | POST with nonexistent slug → 401 + "Unknown dealer slug" | [ ] |
| 4 | Rate limiting on brute force | 5 failed logins from same IP → 429 + "Too many attempts" for 15 min | [ ] |
| 5 | Session expiry (24h) | Login, wait or tamper with cookie timestamp → redirect to /login | [ ] |
| 6 | Logout clears session | GET /dashboard/logout → cookie deleted, redirect to /login | [ ] |
| 7 | Unauthenticated access blocked | GET /dashboard/leads without cookie → 303 redirect to /login | [ ] |
| 8 | Cross-dealer data isolation | Login as premier-auto → cannot view leads from another dealer by ID | [ ] |

### 1.2 Lead Pipeline Overview
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 9 | Lead table renders with real data | GET /dashboard/leads → HTML contains lead names, phones, statuses from DB | [ ] |
| 10 | Stats cards show correct counts | total_leads, active_leads, appt_leads, sold_leads match DB queries | [ ] |
| 11 | Status badges display correctly | Each lead row shows colored badge (NEW=green, ASSIGNED=yellow, LOST=red, etc.) | [ ] |
| 12 | Health indicators compute correctly | Hot (APPT_SET), Warm (<48h), Cold (<72h), Dead (>72h) — verify each color | [ ] |
| 13 | Click lead row → detail page | Click any row → navigates to /dashboard/leads/{id} with correct lead data | [ ] |
| 14 | "No leads found" empty state | Dealer with zero leads → shows "No leads found." message, not a crash | [ ] |
| 15 | Lead timestamps render correctly | created_at shows as "Jun 08, 2026 02:30 PM" format, not raw ISO | [ ] |

### 1.3 Needs Attention Widget
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 16 | Unclaimed leads flagged | Lead in ASSIGNED state > 2h → appears with red "Unclaimed for Xh" card | [ ] |
| 17 | Going-cold leads flagged | Lead in ENGAGED state > 48h → appears with yellow "No activity for X days" card | [ ] |
| 18 | Today's appointments shown | Appointment scheduled for today → appears with blue calendar card | [ ] |
| 19 | Failed deliveries flagged | Message with delivery_status=failed → appears with red X-circle card | [ ] |
| 20 | Cards sorted by urgency | High urgency (unclaimed, failed) appears before medium (cold, appointments) | [ ] |
| 21 | "All clear" state when empty | No attention items → green checkmark + "All clear — no items need attention" | [ ] |
| 22 | Click card → lead detail | Clicking any attention card navigates to that lead's detail page | [ ] |

### 1.4 Lead Detail & Timeline
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 23 | Lead info card displays | Name, phone, email, source, status, assigned rep all rendered | [ ] |
| 24 | Unified timeline merges events + messages | Events (state changes) and messages appear chronologically in one view | [ ] |
| 25 | Message direction indicators | Inbound messages show differently from outbound (icons/colors) | [ ] |
| 26 | Message channel shown | Each message shows SMS, WhatsApp, or Email channel badge | [ ] |
| 27 | AI-generated messages flagged | Messages with ai_generated=true show an AI indicator | [ ] |
| 28 | Delivery status visible | Each message shows delivery status (delivered, failed, sent) | [ ] |
| 29 | Appointments section | Booked appointments show with date, time, status (set/confirmed/showed/no_show) | [ ] |
| 30 | Reassign lead (HTMX) | POST /leads/{id}/reassign with rep name → lead.assigned_rep updated, toast shown | [ ] |
| 31 | Update status (HTMX) | POST /leads/{id}/status with new state → lifecycle transition fires, event logged | [ ] |
| 32 | Send message (HTMX) | POST /leads/{id}/messages with text → Message record created, SMS sent (or DRYRUN) | [ ] |
| 33 | Mark sold (HTMX) | POST /leads/{id}/mark-sold → state=SOLD, redirect to leads list | [ ] |
| 34 | Mark lost (HTMX) | POST /leads/{id}/mark-lost → state=LOST, redirect to leads list | [ ] |
| 35 | Schedule follow-up | POST /leads/{id}/follow-up with datetime → LeadEvent created with scheduled_for | [ ] |

### 1.5 Stats & Analytics
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 36 | Date range filter works | ?days=7, ?days=30, ?days=90 → stats reflect only leads in that window | [ ] |
| 37 | Top stats cards correct | Total Leads, Active Leads, Conversion Rate, Appointments match DB counts | [ ] |
| 38 | Avg response time computed | Response metrics show human-readable time (e.g., "45s" or "3m 12s") | [ ] |
| 39 | Response time color coding | <60s=green, 60-300s=yellow, >300s=red — verify CSS classes applied | [ ] |
| 40 | % Within 5 Minutes correct | Percentage matches (leads responded in <5min / total responded) * 100 | [ ] |
| 41 | Conversion funnel renders | 8 pipeline stages (NEW→SOLD) shown as horizontal bars with counts and percentages | [ ] |
| 42 | Funnel narrows correctly | NEW count >= AUTO_REPLIED >= ASSIGNED >= ... >= SOLD (or shows zeros) | [ ] |
| 43 | Source breakdown table | Leads grouped by source (webform, sms, email) with total, conversion%, appt% | [ ] |
| 44 | Source percentage bars render | Visual bars show relative volume and conversion rate per source | [ ] |
| 45 | Rep performance leaderboard | Per-rep table: assigned, engaged, appt_set, sold, lost, conversion% | [ ] |
| 46 | Leaderboard sorted by sold | Rep with most sales appears first, gold/silver/bronze rank indicators | [ ] |

### 1.6 Appointments Calendar
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 47 | Appointments list renders | GET /dashboard/appointments → shows all appointments with lead names | [ ] |
| 48 | Today/week counts correct | today_count and week_count match actual appointments in those windows | [ ] |
| 49 | Show rate computed | showed_count and no_show_pct calculated from completed appointments | [ ] |
| 50 | Status filter works | ?status=set, ?status=showed, ?status=no_show → list filters correctly | [ ] |
| 51 | Appointment detail links | Each appointment links to the associated lead's detail page | [ ] |

### 1.7 Settings & Configuration
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 52 | Dealer info displayed | Dealer name, phone, address, AI persona loaded from dealer config | [ ] |
| 53 | Settings form renders | GET /dashboard/settings → form fields populated with current values | [ ] |
| 54 | Settings save (if wired) | POST /dashboard/settings → config updated in DB, toast confirmation | [ ] |

---

## SECTION 2: SALES TEAM / SALES REPS

These features serve the people on the floor who handle leads daily.

### 2.1 Team Management
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 55 | Team roster displays | GET /dashboard/team → shows all configured reps with names and phones | [ ] |
| 56 | Add team member | POST /team with name+phone → rep added to dealer config, toast shown | [ ] |
| 57 | Rep performance table | Each rep shows: assigned, engaged, appt_set, sold, lost, conversion% | [ ] |
| 58 | Reps without leads still show | Configured reps with zero leads appear in roster (not missing) | [ ] |
| 59 | Active rep count correct | Header shows count of unique reps (configured + those with leads) | [ ] |
| 60 | Leads today count | "Leads Today" stat shows leads created since midnight UTC | [ ] |
| 61 | Overall conversion rate | total_sold / total_assigned * 100 displayed as percentage | [ ] |

### 2.2 Lead Assignment & Routing
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 62 | Round-robin assigns evenly | 3 reps, 6 leads → each rep gets 2 (verify via DB query) | [ ] |
| 63 | WhatsApp claim ping sent | New lead → Twilio WhatsApp message sent to assigned rep with "1 to claim, 2 to pass" | [ ] |
| 64 | Claim via reply "1" | Rep replies "1" → lead state transitions to CLAIMED, assigned_rep confirmed | [ ] |
| 65 | Pass via reply "2" | Rep replies "2" → lead reassigned to next rep in rotation | [ ] |
| 66 | SLA timeout escalation | No claim within 5 min → lead moves to next rep, then to manager | [ ] |
| 67 | Inactive reps skipped | Rep marked inactive → not included in round-robin rotation | [ ] |

### 2.3 Lead Interaction from Dashboard
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 68 | Send SMS from lead detail | Type message, click send → outbound Message created, Twilio called (or DRYRUN) | [ ] |
| 69 | Message appears in timeline | After sending, message appears in the unified timeline with direction=outbound | [ ] |
| 70 | Reassign to another rep | Select different rep from dropdown → lead.assigned_rep updated, event logged | [ ] |
| 71 | Status change via dashboard | Change status dropdown → lifecycle transition fires, state_change event created | [ ] |

---

## SECTION 3: THE CUSTOMER EXPERIENCE

These features are what the car buyer experiences. They're the product.

### 3.1 Auto-Reply System
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 72 | Instant auto-reply on SMS | Customer texts Twilio number → auto-reply SMS within 60s mentioning their vehicle | [ ] |
| 73 | Auto-reply mentions dealer name | Reply includes the dealership's name from config | [ ] |
| 74 | Auto-reply mentions vehicle | Reply references the specific vehicle the customer asked about | [ ] |
| 75 | Auto-reply asks one clear question | Reply ends with a question that moves toward a visit (not open-ended) | [ ] |
| 76 | Lead appears in dashboard | After auto-reply, lead shows in /dashboard/leads with state=AUTO_REPLIED | [ ] |

### 3.2 AI Qualification & Booking
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 77 | AI qualifies timeline | Customer says "looking to buy this week" → AI recognizes urgency | [ ] |
| 78 | AI qualifies trade-in | Customer mentions trade-in → AI asks about vehicle details | [ ] |
| 79 | AI qualifies financing | Customer asks about payments → AI acknowledges without making promises | [ ] |
| 80 | AI books appointment | Customer agrees to time → Appointment created in DB, state=APPT_SET | [ ] |
| 81 | AI offers specific slots | AI suggests "Tuesday at 2pm or Wednesday at 10am" not "when works for you" | [ ] |
| 82 | AI respects guardrails | Customer asks about price negotiation → AI deflects to "I'll have a rep discuss that" | [ ] |
| 83 | AI uses real inventory only | AI mentions a car → that car exists in the Vehicle table with matching details | [ ] |

### 3.3 After-Hours Mode
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 84 | After-hours detection | System correctly identifies business hours vs after-hours from dealer config | [ ] |
| 85 | AI runs autonomously after hours | After-hours lead → AI handles full conversation without rep intervention | [ ] |
| 86 | Morning summary generated | Leads handled after hours → summary available for reps at start of business | [ ] |

### 3.4 Compliance (CASL + PIPA BC)
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 87 | Opt-out honored immediately | Customer texts "STOP" → confirmation sent, no further messages | [ ] |
| 88 | Opt-out logged | STOP → ConsentLog entry created with timestamp and keyword | [ ] |
| 89 | Opted-out customer ignored | Opted-out customer texts again → no response sent | [ ] |
| 90 | Quiet hours respected | Messages not sent during quiet hours (configurable, default 9PM-8AM) | [ ] |
| 91 | Sender identification | Every outbound SMS includes dealer name + opt-out instructions | [ ] |
| 92 | Consent capture | New lead → consent recorded in ConsentLog table | [ ] |

---

## SECTION 4: SYSTEM HEALTH & RELIABILITY

### 4.1 Infrastructure
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 93 | Health endpoint live | GET /healthz → 200 {"status":"ok","db":"ok"} | [ ] |
| 94 | Readiness endpoint live | GET /readyz → 200 {"status":"ready"} | [ ] |
| 95 | No JS console errors | browser_console() on each dashboard page → zero uncaught errors | [ ] |
| 96 | Dark theme renders correctly | Background #0a0a0f, surface #12121a, accent #6366f1 on all pages | [ ] |
| 97 | Responsive on mobile | Sidebar collapses, content stacks vertically on narrow viewport | [ ] |
| 98 | HTMX partial updates work | Filter dropdowns, search input → table updates without full page reload | [ ] |
| 99 | Sidebar navigation correct | Leads, Team, Settings, Stats, Appointments all link to correct routes | [ ] |
| 100 | Active page highlighted in sidebar | Current page's nav item has distinct visual indicator | [ ] |

### 4.2 Data Integrity
| # | Client Feature | Technical Test | Pass/Fail |
|---|---------------|----------------|-----------|
| 101 | LeadEvent append-only | State changes create LeadEvent records, never modify existing ones | [ ] |
| 102 | Message records complete | Every SMS (inbound + outbound) has a Message record with direction, channel, body | [ ] |
| 103 | Appointment records linked | Each appointment has a valid lead_id foreign key | [ ] |
| 104 | Dealer isolation verified | Query leads for dealer A → zero results from dealer B | [ ] |

---

## TESTING PROTOCOL

### Phase 2 Execution Order
1. **Automated tests first:** `pytest -q --tb=short` — all 222+ tests must pass
2. **Browser walkthrough:** Login → click every page → check console for errors
3. **HTMX interaction test:** Click every button, fill every form, verify toast messages
4. **Data verification:** Compare dashboard numbers against direct DB queries
5. **Mobile viewport test:** Resize browser to 375px width, verify layout adapts

### Browser Verification Commands
```
# Navigate and snapshot
browser_navigate(url="https://speed-to-lead-8tfi.onrender.com/dashboard/login")
browser_snapshot(full=True)

# Login flow
browser_type(ref="@eX", text="premier-auto")  # dealer slug
browser_type(ref="@eX", text="admin")          # username
browser_type(ref="@eX", text="Sunday@123")     # password
browser_click(ref="@eX")                        # submit

# Check each page
browser_navigate(url=".../dashboard/leads")
browser_navigate(url=".../dashboard/team")
browser_navigate(url=".../dashboard/stats")
browser_navigate(url=".../dashboard/appointments")
browser_navigate(url=".../dashboard/settings")

# Check console on each page
browser_console()
```

### Success Criteria
- All 104 checklist items pass
- Zero JavaScript console errors on any page
- All HTMX interactions return 200 + show toast confirmation
- Dashboard numbers match direct DB queries
- Dark theme renders consistently across all pages
- No broken links or 404s in navigation

---

## NOTES
- Items marked [BUILT] in FEATURES.md are verified in this checklist
- Items marked [PLAN] are the ones we're testing — they should be wired up
- Items marked [FUTURE] are out of scope for Phase 2
- Twilio is ON — real SMS will send during live-fire tests (items 72-76, 87-88)
- Use OUTBOUND_ENABLED=false for dashboard-only testing to avoid burning credits

---

*Generated: June 8, 2026 | Speed to Lead v4 | Phase 2 Client-Side Verification*
