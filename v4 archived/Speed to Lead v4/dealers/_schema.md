# Dealer Config Schema

One dealership = one validated YAML file in this folder. It is the **only** thing needed to onboard a
client — every runtime behavior reads from it (validated by `DealerConfig` in `app/config.py`).

Onboard with:

```bash
python tools/provision_dealer.py dealers/<slug>.yaml
```

The three blocks that absorb per-client variation are **`channels`** (Axis 3 — lead sources),
**`inventory`** (Axis 1 — website/inventory), and **`lead_org`** (Axis 2 — system of record).

---

## `dealer`
| Field | Required | Notes |
|---|---|---|
| `slug` | ✅ | Tenant key, kebab-case, unique. |
| `name` | ✅ | Display name; used in messages + consent text. |
| `timezone` | | IANA tz; BC = `America/Vancouver`. All decisions/quiet-hours use this. |
| `hours` | | Per-day `"HH:MM-HH:MM"` or `"closed"`. **Drives the hybrid AI-autonomy switch.** |
| `location_address`, `maps_url`, `main_phone` | | Used by the AI to answer "where/are you open?" |

## `channels` — AXIS 3 (channels they use to generate leads)
| Field | Notes |
|---|---|
| `sms_number` | Canadian Twilio number; lead-facing SMS conversations. |
| `whatsapp_sender` | Twilio WhatsApp sender; rep-facing round-robin/claim pings. |
| `lead_email_inbox` | Address that Cars.com / CarGurus / AutoTrader.ca / Kijiji lead emails forward to. |
| `facebook_page_id` | Optional; Messenger via Twilio Conversations. |
| `web_form_token` | Identifies the dealer at `POST /webhook/form/{token}` for the embeddable form. |

Tenants are resolved on each inbound webhook by matching one of these destinations.

## `sales_team`
List of reps in the round-robin pool. Each: `{ name, whatsapp, active }`. `whatsapp` **must** be a
WhatsApp-enabled number. An empty team is allowed (AI-only) but `provision_dealer` will warn.

## `routing`
| Field | Notes |
|---|---|
| `strategy` | `round_robin` (default), `by_source`, or `single_pool`. |
| `claim_timeout_min` | SLA: reassign if a rep doesn't claim within this many minutes. |
| `escalation` | Ordered actions when unclaimed, e.g. `[reassign, notify_manager]`. |
| `manager_phone` | Where the final escalation lands. |

## `ai`
| Field | Notes |
|---|---|
| `persona` | Tone/voice for the assistant. |
| `goal` | Conversation objective (default `book_appointment`). |
| `guardrails` | Booleans, e.g. `no_price_negotiation`, `no_financing_promises`. |

## `followups`
| Field | Notes |
|---|---|
| `cadence_min` | Minutes after going cold to send each follow-up. Default `[60, 1440, 4320, 10080]`. |

## `inventory` — AXIS 1 (how they maintain their website)
| Field | Notes |
|---|---|
| `source` | `auto` (run discovery probe) · `feed` · `dms` · `structured_data` · `website_scrape` · `manual` · `none`. |
| `url` | Website / feed / API URL. Probed when `source: auto`. |
| `platform` | Optional hint to skip detection: `dealerpull`, `dealercenter`, `autosync`, … |
| `refresh_min` | How often to re-sync inventory into the `vehicles` table. |
| `field_map` | `auto` (known map or LLM-assisted) or explicit `{their_column: canonical_field}` overrides. |

## `lead_org` — AXIS 2 (how they organize/track their leads)
| Field | Notes |
|---|---|
| `mode` | `native` (our dashboard is the record) · `crm_sync` · `sheet` · `webhook` · `email_digest`. |
| `target` | CRM/DMS name, Google Sheet ID, or webhook URL — depends on `mode`. |
| `credentials_ref` | Name of the secret in `.env`/host vault holding the API key/token. **Never inline a secret here.** |

## `compliance` — Canada / BC
| Field | Notes |
|---|---|
| `region` | `CA-BC`. Drives CASL + PIPA BC behavior. |
| `consent_text` | Shown/sent at opt-in; identifies the sender (CASL). `{dealer.name}` is interpolated. |
| `opt_out_keywords` | Inbound keywords that immediately opt a lead out. Include `STOP` and `ARRET`. |
| `quiet_hours` | `"HH:MM-HH:MM"` window with no outbound sends (dealer timezone). |
