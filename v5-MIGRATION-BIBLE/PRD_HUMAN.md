# Speed to Lead v5 — PRD (Human)

> **For:** Manav — the founder, builder, closer
> **Purpose:** One document that answers "what does the world actually need from this system?"
> **Status:** LIVE — this is the north star. If it conflicts with anything else, this wins.
> **Version:** 1.0 — written June 20, 2026

---

## The One-Sentence Reason This Exists

**Dealerships lose sales every single day because no one answers the phone, texts, or web form fast enough.** Speed to Lead v5 plugs that gap. First response in under 60 seconds. A real conversation that books the test drive. No lead slips through because the customer used the wrong channel.

---

## What the World Actually Expects

This is not a feature list. This is what real dealers and real customers need. Every decision in the system either serves this or is noise.

### 1. Speed — The Non-Negotiable

If a customer texts, calls, submits a web form, or emails: they get a response in under 60 seconds. Period. If they called at 2am and left a voicemail — the SMS follow-up reaches them within a minute of the missed call. If they emailed at 3am — the AI response is waiting when they wake up.

**The edge case that breaks systems:** A customer calls, nobody picks up, nobody texts. The system registered the missed call but never followed up. That's a fall-through that destroys trust.

**What "good" looks like:** A customer on AutoTrader clicks "Email Dealer" at 10pm. The lead comes in via IMAP. The AI responds within 60 seconds acknowledging their interest and asking about timing. The customer wakes up to a conversation, not silence.

### 2. The AI Sounds Human, Not Like a Bot

The AI knows the dealer's actual inventory. It doesn't invent cars. It knows the real price, mileage, and features. It doesn't sound like a call centre script. The tone matches the dealer — some dealers are formal, some are "hey what's up."

**The edge case that breaks systems:** The AI confidently books a test drive for a car that was sold last week because it's reading stale inventory. Or it says "let me check with my manager" when the dealer's policy is to give the price immediately. These feel like lies to the customer.

**The edge case that breaks systems:** A customer says "I need a truck under $30k." The AI only knows about sedans in that range and says "we don't have anything." But the dealer has 3 trucks sitting on the lot at $28k — just not uploaded to the system yet. The inventory sync gap creates a false "no" that costs a sale.

**What "good" looks like:** Customer says "looking for a 2022 Honda Civic under $20k." AI immediately says "We have a 2022 Civic Sport in silver on the lot at $18,900 — 48,000km, clean CarProof. Want to come take a look?" The specificity builds trust. The customer feels heard.

### 3. Appointments Booked Without Human Back-and-Forth

The AI offers specific time slots. "Tuesday at 2pm or Wednesday at 10am?" The customer picks one. It's on the rep's calendar. No "let me check availability and get back to you."

**The edge case that breaks systems:** AI books a test drive at 9pm on a Tuesday when the dealer closes at 6pm. The customer shows up to a locked lot. This is the single most damaging failure mode for the product — the AI created a real-world commitment that the business can't honour.

**The edge case that breaks systems:** Two customers book the same 2pm slot for the same rep. The system didn't check overlap. Rep shows up to two customers expecting a test drive at the same time.

**What "good" looks like:** The AI checks the dealer's operating hours before offering time slots. The booking system checks for rep availability. The rep sees the appointment in their dashboard with the customer's name, car, phone number, and full conversation history. No time wasted hunting for context.

### 4. Customer Control Is Enforced in Code, Not in Policy

STOP means stop — instant unsubscribe, no more messages. START means start again. Quiet hours (9pm-8am, dealer's timezone) are enforced on every outbound message. Not a checkbox. Not a "we'll try." Code-level enforcement.

**The edge case that breaks systems:** A customer texts STOP at 10pm. The system registers it, but while processing another subsystem sends the quiet-hours queued message at 2am because it didn't check the unsubscribe status. Customer gets a message they explicitly opted out of. That's a regulatory violation in Canada.

**The edge case that breaks systems:** Customer texts "stop sending me stuff" — the system doesn't parse it as an opt-out because it's not exactly "STOP." In Canadian CASL law, unsubscribe must work from any reasonable expression of intent.

**What "good" looks like:** Customer texts STOP. The code blocks all outbound. If the dealer tries to manually text them, the dashboard shows "This customer has unsubscribed." The audit log has a timestamped entry: "2026-06-20 14:32:01 — customer@example.com — UNSUBSCRIBE — Source: SMS"

### 5. Privacy Is Not an Afterthought

The system stores the minimum: name, phone, vehicle interest. Every consent event is logged with a timestamp. 7-year retention policy for CASL audit. Data is visible only to the dealer. Deletion on request works — and is logged.

**The edge case that breaks systems:** A customer's data is still in the system 8 years later because there's no automated cleanup. If PIPA-BC investigates, "we forgot" is not a defence.

**The edge case that breaks systems:** A customer requests "delete all my data." The system deletes the contact record but leaves orphaned message history with their phone number and full conversation. The "deleted" data is still recoverable.

**What "good" looks like:** Customer requests deletion. Dashboard shows "Requested deletion on 2026-06-20." Data is hard-deleted within 72 hours. The only remaining record is a compliance log: "DELETED — None — 2026-06-20 — Request 482."

### 6. The Customer Is Not a New Person Every Time They Reach Out

Same person texts Monday, fills a web form Wednesday, calls Friday: one thread, one history. The rep opens the lead and sees everything — "They asked about the Civic on Monday, web-formed about the Civic on Wednesday, called today." The customer feels like the dealership knows them.

**The edge case that breaks systems:** Same person uses two different phone numbers (work and personal). The system creates two separate leads. Reps reach out to both numbers independently. Customer gets two messages from the same dealership. Feels disorganized and annoying.

**The edge case that breaks systems:** A person inquires about a Civic 6 months ago, then inquires again about a different car. The system links both inquiries. The rep sees "came back — last time was interested in Civic, now asking about SUV." That's good dedup. But only if the system handles re-engagement correctly without treating a 6-month-old lead as "current."

**What "good" looks like:** Customer texts "hi I'm back, that car I was looking at last month — is it still available?" The AI says "Welcome back John! The 2022 Civic Sport is still on the lot. Want to come in this week?" The customer is impressed the dealership remembered them.

---

## The Dealer's Experience

### What the Dealer Sees on Day 1

- A dashboard that looks like a real product, not a weekend project
- Their leads organized by status — new, warm, appointment set, sold, lost
- Each lead card shows: customer name, car they're interested in, status, time since last contact
- Click a lead → full conversation history, AI summary, booking controls
- Customize rep names and which channels they handle

### What the Dealer Does NOT Have to Do

- No IT setup. No webhooks. No API keys to configure.
- No training the AI. It works with the inventory they upload.
- No reading manuals. The dashboard is self-explanatory.
- No adding extra phone numbers they didn't already have.
- No "setting up" each new lead source. AutoTrader, CarGurus, Kijiji, web forms all just work.

### What the Dealer Cares About Most

In order:

1. **"Did anyone reach out to my customer?"** — Speed to lead is the #1 KPI. If the system doesn't respond fast, it's dead.
2. **"Is the AI saying the right things?"** — If the AI sounds like a robot or gives wrong info, the dealer turns it off.
3. **"Did we book the test drive?"** — Appointments booked = tangible value. Everything else is overhead.
4. **"Can I see what happened?"** — Conversation history, lead timeline, who did what when.
5. **"Does this save me time or add more work?"** — If the system creates more notifications than it solves, the dealer ignores it.

---

## Boundaries — What This System Does NOT Do

| Not in scope | Why |
|---|---|
| **AI phone calls** | Voice AI is a different product. We detect missed calls and trigger SMS. That's enough. |
| **Facebook/Instagram DMs** | CASL compliance is murky. No dealer has asked. Add when they do. |
| **CRM sync** | Salesforce/HubSpot stubs exist. Not needed for first dealer. |
| **Multi-location** | One config file = one dealership. Multi-location is a future problem. |
| **Reseller portal** | You ARE the reseller. Portal comes at 10+ dealers. |
| **v6** | v5 goes to market. The only path to v6 is an exclusive customer feature request. |

---

## The Hard Truths (Read These. Seriously.)

### 1. No One Cares About the Tech

A dealer does not care that the system uses DeepSeek V4 Flash, PostgreSQL, or Telegram bot API. They care that when a customer texts at 10pm, the AI responds immediately and sounds competent. Every technical decision must pass this test: "does the customer or dealer experience this benefit?"

### 2. Wrong Information Is Worse Than No Information

An AI that books a test drive for a sold car, offers a time outside business hours, or confuses a customer's name does MORE damage than no AI at all. Every "hallucination" in the AI pipeline erodes trust. The system must be conservative. If the AI doesn't know the answer, it should say "Let me connect you with a sales rep who can help."

### 3. The Test Mode / Production Mode Split Is Invisible to the Customer

There is no "well it's just a test" in the customer's experience. If the system touches a real customer — even in "test" mode — it must work correctly. A test-mode WhatsApp handler that runs in production is not "just scaffolding." It's a bug that loses real sales. (This is Pitfall 10 and it's why Phase 0 exists.)

### 4. The Dealer Is Not You

You understand webhooks, API keys, and async architectures. A dealer in Surrey running a lot with 3 employees does not. If onboarding requires more than 5 minutes of their time, they won't do it. If something breaks and they can't fix it in 30 seconds, they'll call you frustrated.

### 5. Not All Leads Are Equal

A text from someone who found the dealer on Google and says "I want the grey Civic" is different from an AutoTrader email lead with no phone number. The system must treat them differently — not because of technical constraints, but because the rep's time is valuable and should go where it's most likely to close.

### 6. The Rep Needs to Trust the AI to Use It

If a rep sees that the AI has been booking appointments that don't make sense, or sending wrong information, they'll stop using the system entirely. A rep turning it off is worse than never having implemented it — it means you spent time building something that doesn't get used. Every interaction must build the rep's confidence that the AI is competent.

---

## How to Read This Document

**For you (Manav):** This is your reality check. When a phase is done, ask "does this serve what the world actually expects?" If the answer is no, something is off.

**For the execution agents:** This lives alongside PRD_AGENT.md. PRD_HUMAN.md is the business-level "why." PRD_AGENT.md is the technical "how." Agents should read this first to understand intent, then PRD_AGENT.md for the technical constraints. When the two conflict, this document wins.

---

## Document Relationships

| Document | Audience | Purpose |
|---|---|---|
| `PRD_HUMAN.md` | Manav + agents (context) | "What the world expects" — the north star |
| `PRD_AGENT.md` | Execution agents only | "Keep the code aligned with reality" — autonomy framework |
| `VISION.md` | Agents only | System context, 6 promises, decisions that supersede old PRDs |
| `ARCHITECTURE.md` | Agents only | Channel architecture, role model, UI spec |
| `REFACTORING_GUIDE.md` | Agents only | Phase-by-phase execution instructions |
| `RE-ALIGNMENT_PROMPT.md` | Agents only | Run after every phase — checks work against these docs |

---

*This document is live. Update it when you discover a new "what the world expects" truth. Don't let it go stale.*
