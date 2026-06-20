# Speed to Lead v5 — Re-Alignment Prompt

> **Run this AFTER EVERY PHASE. Do not start the next phase until this is complete.**
> **Purpose:** Catch misalignment between what the bible says and what the world actually needs.
> **Your role:** You are the agent who just completed work on the new PC. The bible exists. So does your autonomy. Use it.

---

## Pre-Check

Before running the alignment, write down:
- **Phase completed:** (e.g. "Phase 0: Cleanup" or "Phase 1: Critical Bugs")
- **Tasks in this phase:** (list each task with file/line references)
- **Bible doc used:** (REFACTORING_GUIDE.md, VISION.md, etc.)

---

## Step 1: Read PRD_HUMAN.md

Open `../PRD_HUMAN.md` (or wherever it lives in the migration bible folder).

Ask yourself three questions:

**Q1:** Did this phase serve any of the "6 things the world expects"? (Speed, Human-like AI, Appointment booking, Customer control, Privacy, Cross-channel continuity)

- If yes → write down which one(s) and how
- If no → does it serve infrastructure that enables one of those? (e.g., "fixed daily digest crash" → enables speed because the rep sees missed leads)
- If neither → why does this task exist? Is it valid cleanup (Phase 0) or is it scope creep?

**Q2:** Does any edge case from PRD_HUMAN.md apply to this phase's tasks?

For example: "The edge case that breaks systems: AI books a test drive at 9pm when the dealer closes at 6pm"
- Did your phase introduce anything that could cause this?
- If yes → document it. Even if it's a future-phase concern, flag it now.

**Q3:** Is there anything in PRD_HUMAN.md that suggests this phase's work is misdirected?

- If the code you wrote works against a real-world need → good.
- If the code you wrote optimizes for something no customer or dealer would care about → that's a problem.

---

## Step 2: Run the 8 Real-World Tests

For every task in this phase, ask these 8 questions. Be specific.

| # | Test | Your Answer | Evidence |
|---|------|------------|----------|
| 1 | Would this work if the system goes down? | ✅ / ⚠️ / ❌ | (e.g., "Added try/except for Twilio timeout") |
| 2 | Would this confuse a non-technical dealer? | ✅ / ⚠️ / ❌ | (e.g., "Error message says 'Lead not found' instead of '500'") |
| 3 | Would this lose a sale? | ✅ / ⚠️ / ❌ | (e.g., "Fixed consent=False — was preventing CASL-compliant outreach") |
| 4 | Does this violate Canadian law? | ✅ / ⚠️ / ❌ | (e.g., "consent=False → True corrects implied consent under CASL") |
| 5 | Is this making the rep's job easier or harder? | ✅ / ⚠️ / ❌ | (e.g., "Removed WhatsApp test handler — less clutter in main.py") |
| 6 | What happens at 3am? | ✅ / ⚠️ / ❌ | (e.g., "Daily digest won't crash now — dealer variable fixed") |
| 7 | Have you read the actual file you're changing? | ✅ / ⚠️ / ❌ | (e.g., "Verified function signature before writing test") |
| 8 | Does this pass the "one tab open" test? | ✅ / ⚠️ / ❌ | (e.g., "This phase didn't touch dashboard — N/A") |

**If any answer is ⚠️ or ❌:** stop and fix it before proceeding. Document what you changed and why.

---

## Step 3: Audit the Bible for Stale or Wrong Rules

You just executed a phase using the bible as your guide. Now check: was the bible right?

Read through the relevant sections of:
- `VISION.md`
- `REFACTORING_GUIDE.md` (for your current phase)
- `ARCHITECTURE.md`

Ask:

**Q1:** Did any instruction in the bible assume something that's no longer true?
- Example: "Remove WhatsApp test handler from app/main.py" — but the actual code has already been partially refactored and the function is in a different file.
- **If yes:** Document the discrepancy. Fix the bible. Strike through the stale instruction and add corrected text.

**Q2:** Did any instruction in the bible tell you to do something that would produce a bad user experience?
- Example: "Remove all WhatsApp dealer notification code" — but a specific dealer has WhatsApp as their primary communication channel and removing it without fallback would strand them.
- **If yes:** Override it (per the autonomy clause in PRD_AGENT.md). Document the override in PHASE_LOG.md. Update the bible.

**Q3:** Are there any rules or expectations in the bible that this phase bypassed?
- Example: The bible says "TDD is mandatory — RED before GREEN" but you wrote the fix first and then the test.
- **If yes:** This is a violation. Go back and write the RED test. If the code is already written, revert it, write the failing test, then re-apply the fix.

**Q4:** Did the bible miss a critical edge case that your code now handles?
- Example: The bible says "Fix phone masking" but doesn't mention what happens if the phone has already been used in a dedup check before the fix.
- **If yes:** Update the bible with your discovery. This is the self-improvement loop.

---

## Step 4: The Decker Test (Walk Through a Real Scenario)

Put yourself in the shoes of a real person. Pick one:

**Scenario A — Customer:** You're shopping for a used car. You find a listing on AutoTrader. You click "Email Dealer" at 10pm with the message "Interested in the 2022 Civic — still available?"

Walk through what happens:
1. Email arrives → system parses it → does it extract the phone number from the email body?
2. Yes → SMS sent within 60 seconds → does it work?
3. You receive the SMS at 10:01pm → you reply "Yeah still looking, what's the price?"
4. AI responds with the price and asks about timing → does it offer valid time slots?
5. You pick one → appointment booked → rep gets Telegram notification → does the rep see the right info?

Now check your phase's work against this scenario:
- **If your phase touches email parsing (1.4, 1.5):** Does the phone get stored unmasked? Is consent properly recorded?
- **If your phase touches the conversation engine (1.2):** Does the state transition log properly?
- **If your phase touches scheduled jobs (1.1):** Does the daily digest go through without crashing?

**Scenario B — Dealer:** You run a lot with 3 reps. You wake up and check the dashboard. A lead came in at 2am. The AI handled it. You see the lead with the full conversation.

Walk through:
1. You open the dashboard → leads page loads fast → you see the new lead
2. Click the lead → full conversation history, AI summary, the appointment that was booked
3. You see a Telegram notification: 🟢 HOT LEAD — lead name, car, appointment time
4. You mark it as claimed → the system knows this is your lead now

Check your phase's work:
- **If your phase touches the daily digest (1.1):** Is the digest working? Does it show leads from the night before?
- **If your phase touches state management (1.2, 1.3):** Is the lead in the right state when the rep sees it?

---

## Step 5: The Autonomy Audit

Be honest here. This is the most important step.

**Q1:** During this phase, did you encounter a situation where the bible's instruction was wrong, but you followed it anyway because "that's what the doc says"?

- If yes → this is a problem. Document what happened and why you didn't override. Next time, YOU override. The bible is not sacred. PRD_AGENT.md gives you this authority.

**Q2:** During this phase, did you encounter a situation where following the bible would have produced a bad user experience, but you overrode it?

- If yes → document the override in the phase log. This is a win. You exercised your autonomy correctly.

**Q3:** During this phase, did you discover a rule or expectation in the bible that is stale, wrong, or harmful?

- If yes → update the bible. Strike through the stale content and add corrected text. Future agents shouldn't repeat your discovery.

**Q4:** Is there anything in your phase's work that, if you're honest, would make a dealer say "what the hell?"

- If yes → fix it. Right now. Not "in a future phase."

---

## Step 6: Final Verdict

Write a one-paragraph summary:

```
PHASE X VERDICT:
[Phase name] — ALIGNED / MISALIGNED / NEEDS FIX

Key alignment wins:
- [What went right]
- [What went right]

Key concerns:
- [What needs attention]
- [What needs attention]

Changes made to bible documents:
- [Doc name]: [change summary]

Autonomy exercised:
- [Yes/No] — [what happened]

Ready for next phase: YES / NO (if NO, explain why)
```

---

## Step 7: Update PHASE_LOG.md

Add the verdict to the phase log entry. The verdict block should be at the bottom of the phase entry so future agents can see:

```
### Re-Alignment (run after phase completion)
| Check | Result | Notes |
|-------|--------|-------|
| 8 Real-World Tests | ✅ PASS | Tasks 1.1-1.5 all pass Tests 1-8 |
| Bible Audit | ⚠️ WARN | REFACTORING_GUIDE.md had stale line number for 1.4 — updated |
| Decker Test | ✅ PASS | Scenario A and B both work correctly |
| Autonomy Audit | ✅ CLEAN | No overrides needed — bible was correct for this phase |
| **Verdict** | **ALIGNED** | Ready for Phase 2 |
```

---

## When to Skip This

Never. This prompt runs after EVERY phase. Even Phase 0 (Cleanup).

The phases it will catch most:
- Phase 1 (Critical Bugs) — were the bugs really bugs? Or did you work around a design flaw?
- Phase 2 (Database) — did you add a column that should have been there? Or create tech debt?
- Phase 4 (Transport) — are you sure Telegram-only is right for THIS dealer? What if they hate Telegram?
- Phase 9-12 (Email, Roles, UI, Demo) — these touch real users. Alignment is critical here.

**Every phase. No exceptions.**
