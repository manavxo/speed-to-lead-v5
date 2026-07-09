# Engine Test Report -- June 04, 2026

## Run info
- Model (chat): DeepSeek V4 Flash
- Model (tool turns): GPT-4o-mini (via OpenRouter)
- OUTBOUND_ENABLED: false
- Frozen time: Thursday 2026-06-04 10:00 AM PDT

## Hard checks (deterministic)
| ID | Scenario | Check | Result |
|----|----------|-------|--------|
| D1 | S1 | check_inventory fired | [PASS] |
| D1 | S3 | check_inventory fired on specific car query | [PASS] |
| D2 | S1 | No hallucinated vehicles | [PASS] |
| D2 | S2 | No hallucinated vehicle | [PASS] |
| D2 | S3 | Specs match seeded data | [PASS] |
| D3 | S1 | <=3 vehicles listed | [PASS] |
| D4 | S4 | Appointment booked + lead APPT_SET | [PASS] |
| D5 | S4 | Rep notification chain verified | [PASS] |
| D6 | All | No tool-call markers in ANY reply | [PASS] |
| D7 | S7 | CASL footer appears exactly once | [PASS] |
| D8 | S4 | Booking claim matches tool result | [PASS] |
| S10-no-other-urls | S10 | No other URLs | [PASS] |
| S10-website | S10 | Configured website URL in reply | [PASS] |
| S11-book-first | S11 | First customer books slot | [FAIL] |
| S11-double-book | S11 | Second customer offered alternative | [FAIL] |
| S11-out-of-hours | S11 | Counter-offers within hours | [PASS] |
| S12-reasonable | S12 | Reasonable opt-out honored | [FAIL] |
| S12-start | S12 | START leads to ENGAGED | [PASS] |
| S12-stop | S12 | STOP leads to OPTED_OUT | [FAIL] |
| S13-quiet-hours | S13 | Engine stops outbound in quiet hours | [FAIL] |
| S5-honesty | S5 | check_availability called + slot grounding | [PASS] |
| S6-dedup | S6 | No re-greeting on return | [PASS] |
| S9-concise-T1 | S9 | Reply <=3 sentences (Turn 1) | [PASS] |
| S9-concise-T2 | S9 | Reply <=3 sentences (Turn 2) | [PASS] |
| S9-concise-T3 | S9 | Reply <=3 sentences (Turn 3) | [FAIL] |
| S9-concise-T4 | S9 | Reply <=3 sentences (Turn 4) | [FAIL] |
| S9-emoji-T1 | S9 | <=2 emojis (Turn 1) | [FAIL] |
| S9-emoji-T2 | S9 | <=2 emojis (Turn 2) | [PASS] |
| S9-emoji-T3 | S9 | <=2 emojis (Turn 3) | [PASS] |
| S9-emoji-T4 | S9 | <=2 emojis (Turn 4) | [PASS] |

## Failures -- detail
### S9-emoji-T1 (S9) -- <=2 emojis (Turn 1)
```
Expected: <=2 emojis
  Actual: 3 emojis: Hello! At Premier Auto Group, we currently have some great options in stock:

🚙 **2023 Hyundai Tucson Preferred** — $29,900 (AWD, perfect for all seasons)  
🚙 **2023 Mazda CX-5 GX** — $31,200 (stylish
```

### S9-concise-T3 (S9) -- Reply <=3 sentences (Turn 3)
```
Expected: <=3 sentences
  Actual: 4 sentences: Great choice! 🚗 Here's what we've got:

**2023 Mazda CX-5 GX** — **$31,200** | 14,500 km | Soul Red Crystal

It's got the 2.5L engine with **AWD** — perfect for Burnaby winters — and that premium feel
```

### S9-concise-T4 (S9) -- Reply <=3 sentences (Turn 4)
```
Expected: <=3 sentences
  Actual: 5 sentences: We've got a **2023 Toyota RAV4 LE** in Magnetic Gray — $32,000 with just 19,500 km 🚙

It comes with a **2.5L engine and AWD** — great for confident driving in all weather. Reliable, practical, and sup
```

### S11-book-first (S11) -- First customer books slot
```
Expected: Should succeed
  Actual: Cannot book appointment in the past: 2026-06-26T17:00:00+00:00. Current time: 2026-07-09T05:44:54.353179+00:00
```

### S11-double-book (S11) -- Second customer offered alternative
```
Expected: Should note slot unavailable
  Actual: Text: It looks like we don't have availability for Friday, June 26, but I do have openings this Friday, July 10, at 10 AM and several other times throughout the day. Would either of those work for you? 🚗
```

### S12-stop (S12) -- STOP leads to OPTED_OUT
```
Expected: Should be OPTED_OUT
  Actual: State: ENGAGED
```

### S12-reasonable (S12) -- Reasonable opt-out honored
```
Expected: Should be OPTED_OUT
  Actual: State: ENGAGED
```

### S13-quiet-hours (S13) -- Engine stops outbound in quiet hours
```
Expected: mode should be 'quiet_hours'
  Actual: mode=send, text=Unfortunately, we don't have any availability tomorrow. Would you like me to connect you with our team to find a time that works for you?
```

## Transcripts
### S1

**Customer:** Hi, what SUVs do you have under $35k?
**AI:** Here are our top SUVs under $35k 🚙

• 2023 Hyundai Tucson Preferred — $29,900 (AWD, great for all-weather driving)  
• 2023 Mazda CX-5 GX — $31,200 (sporty design, fun to drive)  
• 2024 Kia Sportage EX — $34,900 (spacious interior, packed with tech)  

Which one catches your eye? I'd love to help you set up a test drive!
  *(tools: check_inventory)*

### S10

**Customer:** Do you have a website I can look at?
**AI:** Hi there! You can check us out at **https://www.premierautogroup.com** 🚗

Feel free to browse our inventory online. If anything catches your eye, just let me know and I can set up a time for you to come check it out in person! Any particular type of vehicle you're looking for?

### S11-1

**Customer:** Can I come by at 8pm tonight?
**AI:** We're closed at 8 PM tonight, but I have openings tomorrow at 9 AM or 10 AM. Would either of those work for you? 🚗
  *(tools: check_availability)*

### S11-2

**Customer:** I'd like to book Friday June 26 at 10am
**AI:** It looks like we don't have availability for Friday, June 26, but I do have openings this Friday, July 10, at 10 AM and several other times throughout the day. Would either of those work for you? 🚗
  *(tools: check_availability)*

### S12

**Customer:** STOP
**AI:** No problem at all! If you ever have any questions about our inventory or want to come by for a test drive, feel free to reach out anytime. Have a great day! 😊

**Customer:** START
**AI:** Hi there! Welcome to Premier Auto Group in Burnaby 👋

What kind of vehicle are you looking for today? Whether it's a compact sedan, a family SUV, or a sporty coupe, I'd love to help you find the perfect match! 🚗

**Customer:** please stop texting me
**AI:** Of course, I'll stop texting you. Sorry for any inconvenience — have a great day! 👍

### S13

**Customer:** Are you open tomorrow?
**AI:** Unfortunately, we don't have any availability tomorrow. Would you like me to connect you with our team to find a time that works for you?
  *(tools: check_availability)*

### S2

**Customer:** Do you have a 2024 Ferrari 488?
**AI:** I don't see a 2024 Ferrari 488 in our current inventory — those are pretty rare finds! Our stock is more focused on everyday luxury and reliable daily drivers. 🚗

What drew you to the Ferrari? If you're looking for something sporty and luxurious, I've got a few options that might surprise you. What's your budget range?
  *(tools: check_inventory)*

### S3

**Customer:** Tell me about the Hyundai Tucson -- what engine and color?
**AI:** The 2023 Hyundai Tucson Preferred features a 2.5L I4 engine with an automatic transmission and AWD for great handling. It's available in a sleek Phantom Black color and is priced at $29,900. 

Would you like to come in for a test drive? 🚗
  *(tools: check_inventory, check_inventory)*

### S4

**Customer:** I want to test drive the Tucson, can I come by?
**AI:** We have a 2023 Hyundai Tucson available for a test drive at $29,900! 🚙

You can come in tomorrow, Thursday, July 9th. We have slots at 9 AM, 10 AM, or 11 AM. Which time works best for you?
  *(tools: check_inventory, check_availability)*

**Customer:** What times are open?
**AI:** We have several slots open for appointments:

**Thursday, July 9:**
- 9:00 AM
- 10:00 AM
- 11:00 AM
- 12:00 PM
- 1:00 PM
- 2:00 PM
- 3:00 PM
- 4:00 PM
- 5:00 PM
- 6:00 PM

**Friday, July 10:**
- 9:00 AM
- 10:00 AM
- 11:00 AM
- 12:00 PM
- 1:00 PM
- 2:00 PM
- 3:00 PM
- 4:00 PM
- 5:00 PM
- 6:00 PM

Which time works best for you? 🚗
  *(tools: check_availability)*

**Customer:** 10:00 AM works for me, please book it
**AI:** You're all set! We'll see you Thursday, July 9th at 10:00 AM at Premier Auto Group, located at 4567 Kingsway, Burnaby. Bring your driver's license, and I look forward to meeting you! 🚗
  *(tools: check_availability, book_appointment)*

### S5

  *Analysis: 20 real slots. AI offered times in S4 turn 2.*

### S6

**Customer:** Hi, what SUVs do you have?
**AI:** Here are some of our top SUVs available right now 🚙:

• 2023 Hyundai Tucson Preferred — $29,900 (great value with AWD)

• 2023 Mazda CX-5 GX — $31,200 (smooth ride and premium interior)

• 2024 Kia Sportage EX — $34,900 (modern styling and spacious)

Which one catches your eye? I can help set up a test drive!
  *(tools: check_inventory)*

**Customer:** I'm back, still looking at SUVs
**AI:** Glad you're back! Here are the SUVs catching the most attention right now 🚙

• **2023 Hyundai Tucson Preferred** — $29,900 (AWD, loaded with tech, great value)
• **2023 Toyota RAV4 LE** — $32,000 (rock-solid reliability, holds value)
• **2023 Mazda CX-5 GX** — $31,200 (premium interior, fun to drive)

Any of these catch your eye? If you're still narrowing things down, what's most important to you — budget, fuel economy, or cargo space?
  *(tools: check_inventory)*

### S7

**Customer:** (inbound not captured by _process_and_send_sync wrapper)

**Customer:** (inbound not captured by _process_and_send_sync wrapper)

### S8

**Customer:** I'm just looking, not ready to buy.
**AI:** Hi there! Welcome to Premier Auto Group 👋

No pressure at all — happy to help you browse. What kind of vehicle are you curious about? Looking for an SUV, sedan, truck, or something else? I can point out a few that catch the eye 🚗

**Customer:** what's your best price?
**AI:** Hi there! Welcome to Premier Auto Group 🚗

Could you let me know which vehicle you're interested in? That way I can check our inventory and give you the details. Are you looking at a specific model or type of car?

### S9

**Customer:** Hi, what do you have in stock?
**AI:** Hello! At Premier Auto Group, we currently have some great options in stock:

🚙 **2023 Hyundai Tucson Preferred** — $29,900 (AWD, perfect for all seasons)  
🚙 **2023 Mazda CX-5 GX** — $31,200 (stylish design, smooth ride)  
🚙 **2022 Honda Civic Sport** — $25,800 (reliable and fuel-efficient)  

Which one catches your eye? I can arrange a test drive for you!
  *(tools: check_inventory)*

**Customer:** Tell me more about the Tucson
**AI:** Great choice! Here's what we've got:

**2023 Hyundai Tucson Preferred** — $29,900 🚙
- **2.5L engine + AWD** — plenty of power for highway merging and confident grip in rainy BC weather
- **Only 18,500 km** — practically new, with plenty of factory warranty left
- Finished in **Phantom Black** — sleek, timeless look

It's a fantastic value — loaded with tech, super smooth ride, and one of the roomiest interiors in its class. Want to come take it for a spin this week to see how it feels behind the wheel? 😊
  *(tools: check_inventory)*

**Customer:** What about the CX-5?
**AI:** Great choice! 🚗 Here's what we've got:

**2023 Mazda CX-5 GX** — **$31,200** | 14,500 km | Soul Red Crystal

It's got the 2.5L engine with **AWD** — perfect for Burnaby winters — and that premium feel Mazda's known for inside and out. A real head-turner on the lot!

Would you like to come take it for a spin this week?
  *(tools: check_inventory)*

**Customer:** Can I see the RAV4 too?
**AI:** We've got a **2023 Toyota RAV4 LE** in Magnetic Gray — $32,000 with just 19,500 km 🚙

It comes with a **2.5L engine and AWD** — great for confident driving in all weather. Reliable, practical, and super popular.

Want to come check it out alongside the other one you're looking at? I can set up a time for you to see both!
  *(tools: check_inventory)*

## Judgment flags (for human review)

Review the transcripts above for:
- **Curation quality (S1):** Did the AI list 2-3 curated picks with benefit hooks and a question, or dump a spec sheet?
- **Tone:** Warm and human, or robotic/pushy?
- **Objection grace (S8):** Did it stay no-pressure and leave a next step open?
- **Cross-sell / qualifying intelligence:** Did it suggest alternatives naturally?
- **Booking flow (S4):** Smooth progression from interest to availability to booking?

*Report generated by scripts/engine_test_harness.py*
