# CASL & PIPA Compliance — Dealer Rady

Canadian SMS / messaging / data privacy law relevant to a small BC used-car dealer running an AI instant-response product.

---

## CASL (Canada's Anti-Spam Legislation) — what it is

**Source:** Innovation, Science and Economic Development Canada — CASL Performance Measurement Report 2023-24
**URL:** https://ised-isde.canada.ca/site/canada-anti-spam-legislation/en/canadas-anti-spam-legislation-resources/performance-measurement-reports/canadas-anti-spam-legislation-performance-measurement-report-2023-24
**Year:** 2023-24 (published Apr 2, 2025)
**Sample:** national — all commercial electronic message enforcement
**Quote:** "In 2023–24, 693 breaches were reported to the OPC [Office of the Privacy Commissioner], affecting approximately 25 million Canadian accounts."
**URL:** https://ised-isde.canada.ca/site/canada-anti-spam-legislation/en/canadas-anti-spam-legislation

**Mechanism (per Prospeo 2026 compliance summary):**
- "CASL demands verified data before you hit send. ... Penalties up to $10M per violation for organizations, $1M for individuals. Cross-border reach. If the recipient accesses the message in Canada, CASL applies - even if you're sending from Dallas."
- URL: https://prospeo.io/s/casl-email-compliance
- Requires express or implied consent, sender identification, working unsubscribe mechanism.

---

## CRTC enforcement volume (2025)

**Source:** Prospeo / CASL compliance article (citing CRTC enforcement data)
**URL:** https://prospeo.io/s/casl-email-compliance
**Year:** 2025 (April 1 – September 30, 2025)
**Sample:** national CRTC enforcement actions
**Quote:** "Between April 1 and September 30, 2025, the CRTC issued 153 Notices to Produce, 123 Warning Letters, and 5 Preservation Demands. A Notice to Produce means handing over consent records, email logs, and internal documentation - weeks of operational disruption regardless of whether a fine follows."
**URL:** https://prospeo.io/s/casl-email-compliance

- 153 Notices to Produce, 123 Warning Letters, 5 Preservation Demands (H1 2025–26 fiscal year).
- 2023-24 OPC: 693 breaches reported, ~25M accounts affected.
- Ebury Botnet takedown: warning letters to 80 web hosting companies for 35M+ spam messages/day (not dealer-specific but shows CRTC activity level).

---

## Real CASL penalty case (illustrative, not dealer)

**Source:** Prospeo article (citing CRTC announcement, October 2023)
**URL:** https://prospeo.io/s/casl-email-compliance
**Year:** 2023
**Sample:** 1 SMS phishing case
**Quote:** "In October 2023, the CRTC hit Quebec resident Sami Medouni with a $40,000 penalty for sending over 31,000 phishing texts using six fraudulently obtained phone numbers."
**URL:** https://prospeo.io/s/casl-email-compliance

- Useful precedent: even a $40K penalty for a single SMS-spam individual is on the books. For businesses the statutory max is $10M per violation.
- CASL also has a private right of action (PRA) that has been suspended/limited by regulation but historically allowed individuals to sue for up to $200/contravention, $1M/day.

---

## [Pending] Dealer-specific CASL enforcement cases

**NOT FOUND in 8-min search.** Searches for "auto dealer" / "car dealer" + CASL fine returned general CASL law content, not specific dealer enforcement actions. The CRTC publishes an enforcement actions page at https://crtc.gc.ca/eng/com500/tel500.htm (404'd during this search — may have moved to https://crtc.gc.ca/canadian-anti-spam-legislation/en/casl-actions). To be verified post-hoc.

---

## PIPA (BC) — Personal Information Protection Act (BC)

**Source:** BC Laws — Personal Information Protection Act, SBC 2003, c 63
**URL:** https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/03063_01
**Year:** SBC 2003 (amended 2024)
**Sample:** statute (province-wide)
**Quote:** "The purpose of this Act is to govern the collection, use and disclosure of personal information by organizations in a manner that recognizes both the right of individuals to protect their personal information..."
**URL:** https://www.bclaws.gov.bc.ca/civix/document/id/complete/statreg/03063_01

- Overseen by the Office of the Information and Privacy Commissioner (OIPC) for BC.
- Powers include audits, investigations, and enforcement orders.

---

## PIPA BC — penalty regime (Clym compliance summary)

**Source:** Clym compliance guide (BC PIPA)
**URL:** https://www.clym.io/regulations/british-columbia-personal-information-protection-act-bc-pipa
**Year:** 2026
**Sample:** summary of PIPA BC penalty provisions
**Quote:** "Overseen by the Office of the Information and Privacy Commissioner (OIPC). Powers include audits, investigations, and enforcement orders. Penalties: Fines of [up to $10K for individuals, $100K+ for organizations per offence — to verify post-hoc]."
**URL:** https://www.clym.io/regulations/british-columbia-personal-information-protection-act-bc-pipa

- BC PIPA has both administrative (commissioner orders) and quasi-criminal penalty routes.
- OIPC can compel breach notification, audits, and issue binding orders.
- OIPC orders: https://www.oipc.bc.ca/orders/ (URL 404'd during this search — actual current URL appears to be https://www.oipc.bc.ca/rulings/orders/ — to verify).

---

## PIPA / OIPC — auto-dealer-specific enforcement orders

**NOT FOUND in 8-min search.** No specific auto-dealer PIPA enforcement orders surfaced. OIPC publishes all orders on the OIPC site, but a targeted search for "motor dealer" / "car dealer" + OIPC order did not return a clean hit. Likely because the small BC used-car dealer segment rarely triggers OIPC investigations (the OIPC's volume is dominated by larger private-sector breaches — health, insurance, retail, etc.). The risk for Dealer Rady dealers is still real because each dealer handles buyer personal info (name, phone, driver's licence, credit application data, financing).

---

## BC PIPA Guide (OIPC official)

**Source:** OIPC BC — A Guide to B.C.'s Personal Information Protection Act
**URL:** https://www.oipc.bc.ca/guidance-documents/1438 (PDF)
**Year:** current
**Sample:** official OIPC guidance
**Quote:** "PIPA requires you to have procedures in place to receive and respond to complaints or inquiries about your organization's handling of personal information (section 5)."
**URL:** https://www.oipc.bc.ca/guidance-documents/1438

---

## Implication for Dealer Rady (synthesis)

- **CASL — hard ceiling on SMS outreach:** A small BC used-car dealer using a generic "blast" list is a perfect CASL defendant. Dealer Rady's instant-response tool ONLY responds to inbound web leads / phone-ups / form fills, which is **consent-by-inquiry** territory — much safer than cold outbound. Sales pitch should lean on "CASL-safe by design."
- **CASL penalty risk per dealer:** up to $10M per violation (organizations) — even a single 1,000-message blast can theoretically expose a dealer to multi-million-dollar exposure if no consent.
- **PIPA — buyer PII handling:** Every Dealer Rady dealer will collect name, phone, email, driver's licence, trade-in VIN, sometimes credit-app data. They are a "PIPA organization." Need: privacy policy, retention policy, breach response procedure. Dealer Rady should ship a "PIPA-ready" template.
- **Differentiator:** Most competing AI BDC tools are designed for franchised dealers (large compliance teams). A "CASL-safe + PIPA-ready by default" pitch is a strong wedge for the small-dealer market.

---
