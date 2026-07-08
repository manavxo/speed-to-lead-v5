# Speed to Lead v4 — Feature List

> The complete feature set we sell to dealerships. Each feature is either built, planned, or a future add-on.
> Status: [BUILT] = exists in v3, [PLAN] = building in v4, [FUTURE] = v4.1+

---

## CORE FEATURES (the product)

### 1. Instant Auto-Reply [BUILT]
Every lead gets a personalized SMS reply within seconds — mentioning the exact car they asked about, the dealer's name, and one clear question that moves toward a visit. 24/7, 365.
- **What the dealer sees:** "Every lead gets answered in under 60 seconds."
- **What the customer experiences:** A warm, specific text that feels like a real person.

### 2. Round-Robin Lead Routing [BUILT]
Leads are distributed evenly across the sales team. No more "I thought you were handling that." Each rep gets a WhatsApp ping: "New lead assigned — reply 1 to claim, 2 to pass."
- **What the dealer sees:** Fair distribution, zero leads lost, clear ownership.
- **What the salesperson experiences:** A WhatsApp message they can claim with one tap.

### 3. SLA Escalation [BUILT]
If a rep doesn't claim within the set window (configurable, default 5 min), the lead automatically moves to the next rep, then to the manager. No lead ever falls through the cracks.
- **What the dealer sees:** "We guarantee every lead is owned by a human within minutes."
- **Configurable:** Timeout duration, escalation ladder, manager notification.

### 4. AI Qualification & Booking [BUILT]
The AI assistant qualifies the lead (timeline, trade-in, financing needs) and drives toward booking a test drive or visit. It offers specific time slots, not open-ended questions.
- **What the dealer sees:** "Leads come in pre-qualified with a booked appointment."
- **Guardrails:** No price negotiation, no financing promises — those go to the rep.

### 5. After-Hours Autonomous Mode [BUILT]
During business hours: AI drafts replies, rep approves. After hours: AI runs the full conversation autonomously — qualifies, answers questions, books the appointment. Rep gets a summary in the morning.
- **What the dealer sees:** "You never lose a lead at 2am on a Sunday again."
- **This is the #1 selling point for small dealerships.**

### 6. Real Inventory Grounding [BUILT]
The AI only talks about cars that actually exist on the lot. It reads from a synced inventory database — never invents a price, a model, or availability. If a car is sold, it says so and offers alternatives.
- **What the dealer sees:** "The assistant always talks about real cars at real prices."
- **Trust builder:** Eliminates the #1 fear about AI ("it'll make stuff up").

### 7. Multi-Channel Lead Intake [BUILT + EXPANDING]
Leads come in from: website forms, SMS, missed calls (text-back), listing site emails (AutoTrader.ca, Kijiji, Cars.com, CarGurus), Facebook Messenger, Instagram DMs.
- **What the dealer sees:** "We plug into wherever your leads already come from."
- **Floor:** If they have nothing, we provide a hosted web form.
- **Non-invasive capture:** We never ask for backend access. Two things the dealer does:
  1. **Email forwarding rule** — Forward notification emails from AutoTrader/CarGurus/Kijiji/website to our parsing address. 2-minute setup in their email client.
  2. **Phone number swap** — We give them a Twilio number for their listings. Captures calls, enables missed-call text-back.
- **Optional (Phase 2):** Facebook/Instagram webhook integration for Messenger and DM leads.
- **Provisions for future change:** The intake adapter pattern is pluggable — adding a new source is one adapter file, zero core changes. If a dealer has a non-standard lead source, we build a custom adapter.

### 8. Compliance Built-In (CASL + PIPA BC) [BUILT]
Every message respects Canadian texting law. Consent capture, sender identification, instant opt-out (STOP/ARRET), quiet hours, audit trail.
- **What the dealer sees:** "You're fully compliant. We handle the legal stuff."
- **Risk mitigation:** This protects the dealer from real legal exposure.

---

## DASHBOARD FEATURES (the management layer)

### 9. Lead Dashboard [PLAN]
A clean, dark-mode dashboard showing all leads, their status, conversation history, and assigned rep. Filter by status, date, source. Click into any lead to see the full timeline.
- **What the dealer sees:** "One place to see everything that's happening."

### 10. Salesperson Management [PLAN]
Add/remove reps, toggle active status, set round-robin weights (give top performers more leads), view per-rep stats (claims, response time, conversion).
- **What the dealer sees:** "Manage your team from one place."

### 11. Appointment Calendar [PLAN]
View all booked appointments, filter by rep, see no-shows and cancellations. Export to Google Calendar.
- **What the dealer sees:** "Your test drive schedule, always up to date."

### 12. Stats & Reporting [PLAN]
Leads per week, average response time, conversion funnel (lead → contacted → qualified → booked → showed → sold), per-rep performance, lead source breakdown.
- **What the dealer sees:** "Data that proves the system is working."

### 13. AI Conversation Review [PLAN]
Read every AI conversation. Approve or edit AI-drafted messages before they send (business-hours mode). See what the AI said and how the customer responded.
- **What the dealer sees:** "Full transparency. You see everything the AI says."

---

## ONBOARDING FEATURES (how dealers get started)

### 14. One-Click Dealer Provisioning [PLAN]
Fill in a simple form (business info, hours, team, inventory source) → system sets everything up automatically. No YAML files, no terminal commands.
- **What Manav does:** Collects info from the dealer, enters it in a form, clicks "Go Live."
- **What the dealer sees:** "We were up and running in 15 minutes."

### 14b. Dealer Persona Profile [NEW — BUILD THIS]
During onboarding, collect the dealership's personality: values, tone, what makes them different, how they talk. This becomes a persona block injected into the AI's system prompt so it sounds like it actually works at THAT dealership.
- **What the dealer sees:** "The AI sounds like one of our people."
- **Why it matters:** Every competitor uses the same robot voice. This makes the AI feel like part of the team.

### 15. Inventory CSV Upload [PLAN]
Dealer uploads a spreadsheet of their vehicles. System imports, normalizes, and makes them available to the AI. No technical setup required.
- **Floor:** This works for every dealer, even ones with no website.

### 16. Auto-Detection Inventory Sync [FUTURE]
Give us your website URL — we detect your inventory platform, pull the car list automatically, and keep it synced. Supports schema.org JSON-LD, common DMS feeds, and LLM-assisted HTML scraping.
- **What the dealer sees:** "Just give us your website. We handle the rest."

---

## COMMUNICATION FEATURES

### 17. WhatsApp Claim Pings [BUILT]
Reps receive lead assignments on WhatsApp — the app they already use. Reply "1" to claim, "2" to pass. No new app to install.
- **What the salesperson experiences:** "I just reply 1 and the lead is mine."

### 18. Follow-Up Cadence [PLAN]
If a lead goes cold, the system sends gentle follow-ups on a configurable schedule (e.g., 1 hour, 1 day, 3 days, 1 week). Stops when the lead responds or opts out.
- **What the dealer sees:** "We never let a warm lead go cold."

### 19. Missed-Call Text-Back [BUILT]
Someone calls the dealership and nobody answers? They automatically get a text: "Hi! We missed your call. Text us here and we'll get back to you right away."
- **What the dealer sees:** "Every missed call becomes a conversation."

### 20. Draft Approval Mode [PLAN]
During business hours, the AI drafts replies but the assigned rep approves or edits before sending. One-tap approval. Keeps a human in the loop.
- **What the dealer sees:** "AI does the work, your team has the final say."

---

## INTEGRATION FEATURES

### 21. CRM / DMS Sync [FUTURE]
Push leads and events to the dealer's existing system: Dealerpull, DealerCenter, AutoSync, HubSpot, Google Sheets, or any webhook endpoint.
- **What the dealer sees:** "Leads flow into whatever system you already use."
- **Floor:** Our own dashboard IS the system of record (native mode).

### 22. Multi-Tenant Architecture [BUILT]
One deployment serves multiple dealerships. Each dealer's data is completely isolated. Add a new dealer without touching the code.
- **For Manav:** One server, many clients. Margins improve with scale.

---

## FEATURES TO ADD (ideas for v4+)

### 23. Live Demo on Landing Page [NEW — BUILD THIS]
A visitor enters their phone number on the marketing site. They receive a real SMS auto-reply within seconds — the exact experience a dealership lead would have. This is the close.
- **Impact:** "I just experienced the product. I want it."

### 24. Voice AI (Missed Call → AI Answers) [FUTURE]
Instead of just texting back, the AI actually answers the phone, qualifies the caller, and books an appointment. Uses Twilio Voice + Claude.
- **What the dealer sees:** "Our phone is answered 24/7 by AI."
- **Premium add-on:** $200-500/mo additional.

### 25. Lead Scoring [FUTURE]
AI assigns a score (hot/warm/cold) based on conversation signals: urgency, budget mentions, trade-in interest, timeline. Hot leads get prioritized.
- **What the dealer sees:** "Know who to call first."

### 26. Multi-Language Support [FUTURE]
AI responds in the customer's language. BC has a large Punjabi, Mandarin, and Cantonese-speaking population. This is a real differentiator.
- **What the dealer sees:** "We serve every customer in their language."

### 27. Review Request Automation [FUTURE]
After a sale, automatically send a review request to the customer's phone with a link to Google Reviews.
- **What the dealer sees:** "More 5-star reviews, automatically."

### 28. Inventory Alert Bot [FUTURE]
When a new vehicle is added to inventory, automatically text past leads who asked about similar vehicles. "Hey, we just got a 2023 RAV4 in — want to come see it?"
- **What the dealer sees:** "New inventory automatically finds interested buyers."

---

## WHAT WE'RE SELLING — THE PITCH

**For $299-499/month, a dealership gets:**
- Every lead answered in seconds, 24/7
- AI that qualifies and books appointments
- Round-robin routing to their sales team
- After-hours coverage (the biggest gap)
- Full compliance with Canadian law
- A dashboard to see everything
- Setup in 15 minutes

**The ROI story:**
- Average used car profit: $2,000-3,000
- If the system saves even ONE deal per month, it pays for itself 5-10x
- Small dealers lose 2-5 deals per month to slow response times
- The math is obvious

**The competitive advantage:**
- No BDC team needed ($3,000-5,000/month saved)
- Works after hours (competitors don't)
- Setup in 15 minutes, not 3 months
- Built for Canadian compliance (CASL/PIPA)
- Works with whatever they already have (no system change required)

---

*This list is the product. Everything we build serves one of these features. If a feature doesn't serve the pitch, cut it.*
