# Speed to Lead v5 — PRD (Agent)

> **For:** Execution agents on the new PC
> **Source of truth precedence:** PRD_HUMAN.md > PRD_AGENT.md > VISION.md > ARCHITECTURE.md > REFACTORING_GUIDE.md > CODEBASE_AUDIT.md
> **Purpose:** Keep your work anchored to real-world user experience. The bible is guidance, not shackles.
> **Version:** 1.0 — June 20, 2026
> **Critical rule:** You have AUTONOMY to override the bible when it would produce a bad user experience. Read Section 3.

---

## 1. The Three Layers of Truth

When VISION.md, ARCHITECTURE.md, and REFACTORING_GUIDE.md say one thing, but a real dealer or customer would experience the opposite — the user experience wins. Here's the priority:

```
PRD_HUMAN.md (what the world expects)
         ↓
PRD_AGENT.md (how to stay anchored to reality)
         ↓
VISION.md + ARCHITECTURE.md (system design intent)
         ↓
REFACTORING_GUIDE.md (phase-by-phase instructions)
         ↓
CODEBASE_AUDIT.md (current state snapshot)
```

**This means:** If REFACTORING_GUIDE.md tells you to do X but X would produce a bad customer experience, you STOP doing X and ask: "What's the right thing that serves the user?"

**This is NOT optional.** If you catch a bug in the bible — a wrong assumption, a stale design decision, a constraint that would hurt a user — you fix it. The bible is not sacred. The user experience is.

---

## 2. The 8 Real-World Tests (Run These Against Every Task)

Before and after every task, ask these questions. If any answer is "no" or "I'm not sure" — DO NOT proceed until it's resolved.

### Test 1: Would This Work If the System Goes Down?
Your code handles the happy path? Good. What happens when:
- Twilio is down (connection timeout, 503, invalid response)?
- PostgreSQL connection pool is exhausted?
- DeepSeek API returns a 500 or rate-limit?
- Telegram bot API is unreachable?
- Email provider (IMAP/Mailgun) is unavailable?

**If you didn't handle at least one of these gracefully, your task is incomplete.**

### Test 2: Would This Confuse a Non-Technical Dealer?
A dealer in Surrey with 3 employees is going to use this system. They don't know what a webhook is. They don't understand async. They don't care about your architecture.

- If they see an error, does it tell them what to do? Or does it say "500 Internal Server Error"?
- If they need to configure something, is it a button on a dashboard? Or do they need to edit a YAML file?
- If the system acts unexpectedly, is there a log they can send you? Or does it silently fail?

**If a dealer would need to call you to understand what happened, you shipped a support ticket, not a product.**

### Test 3: Would This Lose a Sale?
Be brutal here. Ask:
- Could this change cause a lead to go unanswered for more than 60 seconds?
- Could this change cause a wrong response to a customer (wrong car, wrong price, wrong time)?
- Could this change cause a duplicate outreach to the same customer?
- Could this change prevent a rep from seeing a lead they need to act on?

**If the answer to any is "yes" or "maybe" — stop and fix it.**

### Test 4: Does This Violate Canadian Law?
You need to know three things:
1. **CASL (Canada's Anti-Spam Law)** — Every commercial message needs consent. Unsubscribe must be instant. Every message must identify the sender. Record-keeping: 3 years from the date the consent was obtained.
2. **PIPA-BC (BC's private sector privacy law)** — Only collect what you need. Tell people what you're collecting and why. Let them access their data. Delete it on request.
3. **PIPEDA (federal)** — Applies if the dealer does inter-provincial business. Similar rules to PIPA-BC but federal.

**If you change anything related to consent, unsubscribe, data retention, or message content — check these laws first.**

### Test 5: Is This Making the Rep's Job Easier or Harder?
Every feature should reduce cognitive load, not add to it. Ask:
- Does this reduce the number of clicks to do a common action?
- Does this add information the rep needs, or noise they have to filter?
- Does this automate something the rep used to do manually?
- Or does this create a new notification the rep has to acknowledge and dismiss?

**If it adds friction, don't build it. If it replaces friction, build it.**

### Test 6: What Happens at 3am?
Systems fail when nobody's watching. Ask:
- If a lead comes in at 3am, does the AI respond?
- If the AI fails to respond, does the lead enter a queue that someone will see in the morning?
- If a cron job crashes at 3am, does the error get logged? Does it recover on the next tick?
- If a customer texts at 3am and the AI responds, does the system respect quiet hours? (Wait — AI responses during quiet hours are fine. Dealer notifications at 3am are not.)

**The system must be robust when no human is watching.**

### Test 7: Have You Read the Actual File You're Changing?
The Zero-Rework Doctrine says: before writing ANY line of code, read the source file you're about to change. This is not optional.

- Read the function you're modifying
- Read all imports the function uses
- Read the config fields it references
- Read existing tests that cover it

**If you write code without reading the file first, you're guessing. Guessing creates bugs.**

### Test 8: Does This Pass the "One Tab Open" Test?
A rep should be able to do their job with one browser tab open. No popups. No "open this link to see the lead." No "open a new tab to respond." The dashboard is the single source of truth.

- Can the rep see all their leads on one screen?
- Can the rep take action on a lead without navigating away?
- If they need to switch to Telegram to see a notification, does the dashboard still show everything they need?

**If the answer to any is "no" — either fix it or document the trade-off.**

---

## 3. The Autonomy Clause (Read This Carefully)

You are NOT a blind instruction follower. You have the authority (and obligation) to identify when the bible is wrong and correct course.

### When to Override the Bible

You may override REFACTORING_GUIDE.md, VISION.md, or ARCHITECTURE.md when:

1. **The instruction would produce a bad user experience** — e.g., a design choice that looks clean on paper but would confuse a real dealer
2. **The instruction makes an assumption that's no longer true** — e.g., the codebase has evolved since the doc was written
3. **The instruction conflicts with PRD_HUMAN.md** — PRD_HUMAN.md wins every time
4. **The instruction is based on a stale dependency or API** — e.g., recommending a function that no longer exists
5. **The instruction would violate CASL, PIPA-BC, or PIPEDA** — the law overrides all design documents

### When to NOT Override the Bible

Do NOT override when:

1. **You're guessing that the bible is wrong** — verify first. Read the file. Run the test. Confirm the assumption.
2. **You prefer a different code style** — follow the existing codebase conventions. Style preferences are not justification.
3. **You want to add a feature that's not in scope** — the 12-phase plan is the plan. If you want to add something outside it, discuss with Manav.
4. **You think the approach is "too hard"** — difficulty is not a valid reason to skip. If something is genuinely impossible, document why.

### How to Override

If you override the bible, you MUST:

1. **Document it in PHASE_LOG.md** — what you changed, why, what the bible said vs what you did
2. **Update the relevant bible document** — strike through the old instruction and add the corrected version so future agents don't repeat the wrong approach
3. **Run the full test suite** — confirm your change doesn't break anything
4. **Flag it for Manav** — note in the phase log entry that you made a judgement call

---

## 4. The Edge Cases You Must Always Check

These are not in the pitfall catalog. These are deeper. Every task needs to pass through these questions.

### Can the AI hallucinate here?
If you're working on the conversation engine, message templating, or any AI-generated output:
- Could the AI invent a car that doesn't exist?
- Could the AI offer a time slot outside business hours?
- Could the AI promise something the dealer can't deliver (price match, trade-in guarantee, etc.)?
- Does the system have a "I don't know, let me connect you with a rep" fallback?

### Can the data get into a bad state?
If you're working on data persistence:
- Could a partial transaction leave orphaned data?
- Could a race condition create duplicate leads?
- Could a failed API call leave a lead in a stuck state?
- Could two operations on the same lead at the same time produce a wrong result?

### Can a silent failure happen?
Silent failures are the most dangerous. They look like success but aren't.
- Did you log errors that would help debug this?
- Does the error propagate up to something that would catch it?
- Is there a monitoring path for this operation?

### Can a non-technical user recover from this?
If something goes wrong:
- Will the dashboard show an error?
- Will the rep know what to do next?
- Will the system retry automatically?

---

## 5. Verifying Work After Every Phase

After every phase, run the RE-ALIGNMENT_PROMPT. This is not optional. The prompt walks you through:
1. Reading PRD_HUMAN.md
2. Testing each task against the 8 real-world tests (above)
3. Checking for bible conflicts you should have overridden but didn't
4. Looking for wrong assumptions or stale rules in the bible that need updating
5. Verifying that a real dealer using your code would have a good experience

**If RE-ALIGNMENT_PROMPT finds anything concerning, fix it before starting the next phase.**

---

## 6. The Golden Rule

> **The bible is the plan. The world is the judge.**
> 
> Every phase produces code that a real dealer will use with real customers. If the code works but the experience is bad, the code is wrong. Fix the code, not the customer.

---

*This document lives alongside PRD_HUMAN.md. Read PRD_HUMAN.md first to understand intent, then this document for the autonomy framework. If the two documents ever conflict, PRD_HUMAN.md wins.*
