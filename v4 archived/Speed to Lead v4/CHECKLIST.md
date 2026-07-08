# Speed to Lead v4 — Manager Simulation Checklist

> This checklist is for you (Manav) to manually verify every client-facing feature on the live system.  
> Check off each item as you confirm it works. If anything fails, note it and we'll fix it.

---

## Reference URLs

| What | URL |
|------|-----|
| Dealership Website | https://premier-auto-group.vercel.app |
| Backend (Render) | https://speed-to-lead-8tfi.onrender.com |
| Dashboard Login | https://speed-to-lead-8tfi.onrender.com/dashboard/login |
| Dealer ID | `premier-auto` |
| Username | `admin` |
| Password | `Sunday@123` |

---

## 1. CUSTOMER EXPERIENCE

These are things the customer sees or does. Test them yourself as if you were a car buyer.

### 1.1 Website Contact Form

- [ ] Go to https://premier-auto-group.vercel.app
- [ ] Find the contact form (look for "Contact Us" or a lead capture form)
- [ ] Fill in: Name = "Test Customer", Phone = your real cell number, Email = your real email
- [ ] Select a vehicle (e.g. RAV4 XLE)
- [ ] Type a message: "I'm interested in the RAV4, when can I come see it?"
- [ ] Submit the form
- [ ] Confirm: The form says "Thank you" or shows a success message (not an error)
- [ ] **You should receive an SMS auto-reply within 60 seconds on your cell phone**
- [ ] The SMS should mention "Premier Auto Group" and sound like a friendly sales rep
- [ ] The SMS should include an opt-out footer ("Reply STOP to opt out")

### 1.2 SMS Conversation (Customer Side)

- [ ] Reply to the auto-reply SMS with: "What SUVs do you have under $30k?"
- [ ] Wait 30-60 seconds for a reply
- [ ] The reply should list 1-3 actual vehicles from the inventory (not made-up cars)
- [ ] Prices and details should match what's on the dealership website
- [ ] Reply: "I like the Tucson. Can I test drive it this Saturday at 2pm?"
- [ ] Wait for a reply — the AI should either:
  - Book the appointment immediately ("You're all set! We'll see you Saturday at 2pm..."), OR
  - Offer two specific time options
- [ ] Reply: "What's the best price you can give me on it?"
- [ ] The AI should NOT negotiate or quote a discount — it should defer to "the team will discuss pricing when you come in"
- [ ] Reply: "Can I talk to a real person?"
- [ ] The AI should provide the dealership phone number and offer a callback

### 1.3 Opt-Out / Compliance

- [ ] Reply "STOP" to any SMS from the system
- [ ] You should receive: "You have been unsubscribed. Reply START to resubscribe."
- [ ] No further SMS should be sent to your number (unless you reply START)
- [ ] Reply "START" to re-subscribe
- [ ] You should receive: "You've been resubscribed. Reply STOP to opt out again."

---

## 2. SALES REP EXPERIENCE

These are things the sales rep sees and does on the dashboard.

### 2.1 Lead Notification (WhatsApp)

- [ ] When a new lead comes in, the assigned rep should receive a WhatsApp message
- [ ] The message should say: "New lead assigned to you: [Name] ([Phone]). Reply 1 to claim, 2 to pass."
- [ ] Reply "1" to claim the lead
- [ ] The lead's status in the dashboard should change from ASSIGNED to CLAIMED

### 2.2 Dashboard Login

- [ ] Go to https://speed-to-lead-8tfi.onrender.com/dashboard/login
- [ ] Enter: Dealer ID = `premier-auto`, Username = `admin`, Password = `Sunday@123`
- [ ] Click "Sign In"
- [ ] You should see the Leads page with the sidebar showing: Leads, Appointments, Team, Settings, Stats

### 2.3 Leads List

- [ ] The stats bar at the top shows: TODAY'S LEADS, ACTIVE, APPTS SET, SOLD, AVG RESPONSE
- [ ] Numbers look reasonable (not all zeros if you've submitted test leads)
- [ ] The "Needs Attention" section shows stale leads (unclaimed for 24+ hours) — highlighted in yellow/red
- [ ] The lead table shows columns: NAME, PHONE, SOURCE, VEHICLE, STATUS, HEALTH, REP, RESPONSE TIME
- [ ] Each lead row has a colored health indicator (🟢 HOT, 🟡 WARM, 🔴 COLD)
- [ ] The STATUS filter dropdown works — select "Auto-Replied" and only AUTO_REPLIED leads show
- [ ] The DATE filter works — select "Today" and only today's leads show
- [ ] The SEARCH box works — type a lead name and the list filters

### 2.4 Lead Detail Page

- [ ] Click on any lead row to open the lead detail page
- [ ] The page shows: Lead name, Phone (masked), Source, Assigned Rep, Consent status, Created date
- [ ] Quick-contact buttons work:
  - [ ] 📞 opens a phone call (tel: link)
  - [ ] 💬 opens an SMS (sms: link)
  - [ ] 📋 copies the phone number to clipboard
  - [ ] ✉️ opens email (mailto: link) — only if email is available
- [ ] The Conversation section shows the message history
- [ ] The state timeline shows all transitions (e.g. "NEW → AUTO_REPLIED")
- [ ] You can type a message in the textbox and click Send (it should appear in the conversation)

### 2.5 Quick Activity Notes

- [ ] On a lead detail page, click "📞 No Answer" — a green toast should confirm "Activity logged"
- [ ] Click "🎙️ Voicemail" — same confirmation
- [ ] Click "💬 Texted" — same confirmation
- [ ] Click "🗣️ Spoke" — same confirmation
- [ ] Click "✅ Confirmed" — same confirmation
- [ ] Click "💰 Offer" — same confirmation
- [ ] Each activity log should appear in the conversation timeline

### 2.6 Rep Assignment & Status Change

- [ ] On a lead detail page, use the "Reassign Rep" dropdown to select a rep (Alex, Jordan, Mike, Lisa)
- [ ] The assigned rep should update on the page
- [ ] Use the "Status" dropdown to change the lead status
- [ ] The status badge should update immediately
- [ ] Use the "Schedule Follow-up" date picker and click "Set Reminder"
- [ ] A confirmation should appear

### 2.7 Mark as Sold / Lost

- [ ] On a lead detail page, click "Mark as Sold"
- [ ] The lead status should change to SOLD
- [ ] Go back to the leads list — the SOLD count in the stats bar should increase by 1
- [ ] On another lead, click "Mark as Lost"
- [ ] The lead status should change to LOST

---

## 3. OWNER / MANAGER EXPERIENCE

These are things the dealership owner sees and configures.

### 3.1 Appointments Page

- [ ] Click "Appointments" in the sidebar
- [ ] The stats show: TODAY, THIS WEEK, SHOWED, NO-SHOW RATE
- [ ] The appointment table shows: LEAD, VEHICLE INTEREST, SCHEDULED, REP, STATUS
- [ ] Filter tabs work: All, Set, Confirmed, Showed, No-Show, Cancelled
- [ ] If you booked a test appointment via SMS earlier, it should appear here

### 3.2 Team Management Page

- [ ] Click "Team" in the sidebar
- [ ] Stats show: ACTIVE REPS, OVERALL CONVERSION, LEADS TODAY, TOTAL LEADS
- [ ] The Rep Performance Leaderboard shows columns: RANK, REP, ASSIGNED, ENGAGED, APPTS, SOLD, LOST, CONV%, TODAY, AVG RESPONSE
- [ ] Click column headers to sort (the table should re-sort)
- [ ] Click "Add Team Member" — a form should appear (or navigate to add-rep page)
- [ ] Each rep row shows their stats

### 3.3 Stats & Analytics Page

- [ ] Click "Stats" in the sidebar
- [ ] Summary cards show: TOTAL LEADS, ACTIVE LEADS, CONVERSION RATE, APPOINTMENTS, AVG RESPONSE TIME, % WITHIN 5 MINUTES, LEADS WITH RESPONSE
- [ ] "Leads by Source" chart shows webform and/or sms counts
- [ ] "Conversion Funnel" shows all stages: New → Auto Replied → Assigned → Claimed → Engaged → Appt Set → Showed → Sold
- [ ] "Source / Channel Breakdown" table shows per-source stats
- [ ] "Per-Rep Performance" table shows per-rep stats
- [ ] The time range filter (7/30/90/180 days, 1 year) works — numbers change when you select a different range

### 3.4 Settings — Business Info

- [ ] Click "Settings" in the sidebar (default tab: Business Info)
- [ ] Business Name shows "Premier Auto Group"
- [ ] Phone Number shows the Twilio number
- [ ] Timezone is set correctly
- [ ] Business hours are set for each day (Mon-Sat open, Sun closed)
- [ ] Edit the business name, click "Save Business Info"
- [ ] Refresh the page — the name should persist

### 3.5 Settings — AI Personality

- [ ] Click the "AI Personality" tab
- [ ] Temperature and Top P sliders are visible and adjustable
- [ ] Core values textbox shows the persona description
- [ ] Guardrails checkboxes are present (No price negotiation, No financing promises, etc.)
- [ ] Toggle a checkbox, click "Save AI Personality"
- [ ] Refresh — the setting should persist

### 3.6 Settings — Channels

- [ ] Click the "Channels" tab
- [ ] Toggle switches are present for: Web Form, SMS, Email, Facebook, Instagram
- [ ] Toggle one, click "Save Channel Settings"
- [ ] Refresh — the setting should persist

### 3.7 Settings — Compliance

- [ ] Click the "Compliance" tab
- [ ] Opt-out keywords are listed: stop, unsubscribe, remove, opt out, do not contact
- [ ] Click "×" on a keyword to remove it
- [ ] Type a new keyword in the textbox, click "Add"
- [ ] Quiet Hours Start and End times are shown (9:00 PM — 8:00 AM)
- [ ] Click "Save Compliance Settings"
- [ ] Refresh — changes should persist

---

## 4. CROSS-CUTTING CHECKS

### 4.1 Mobile Responsiveness

- [ ] Open the dashboard on your phone browser
- [ ] The sidebar collapses or is accessible via a menu button
- [ ] The leads table is readable (not cut off)
- [ ] Lead detail page works (scroll, click buttons)
- [ ] Quick-contact buttons (tel:, sms:) work from mobile

### 4.2 Error Handling

- [ ] Go to https://speed-to-lead-8tfi.onrender.com/healthz — should return `{"ok": true}`
- [ ] Go to https://speed-to-lead-8tfi.onrender.com/readyz — should return `{"ok": true, "db": "connected"}`
- [ ] Try logging in with wrong password — should show error, not crash
- [ ] Try accessing /dashboard/leads without logging in — should redirect to login

---

## Troubleshooting

**If the AI doesn't reply to SMS:**
- Check that OUTBOUND_ENABLED is false (dry-run mode) — the auto-reply is generated by the system, not Twilio
- The auto-reply is generated server-side when the webform is submitted, so it doesn't depend on Twilio for the first message

**If the dashboard shows no leads:**
- Make sure you're logged in as `premier-auto` (not a different dealer)
- Change the date filter to "All Time"

**If appointments don't appear:**
- The AI must have successfully called the book_appointment tool during the SMS conversation
- Check the lead detail page — the state should be APPT_SET if an appointment was booked

---

*Generated: June 9, 2026 | Speed to Lead v4 Phase 2E*
