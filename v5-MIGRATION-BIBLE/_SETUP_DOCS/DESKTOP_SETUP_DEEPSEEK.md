# Hermes Agent — Desktop Setup Guide
## DeepSeek V4 + Token-Efficient Configuration

Generated: 2026-06-19

---

## Hardware Context
- CPU: Ryzen 7 3700X (8C/16T)
- RAM: 32 GB DDR4
- GPU: GTX 1660 Super (6 GB VRAM)
- MiMo Code already installed for local coding

## What This Setup Gives You
- **Model:** DeepSeek V4 Flash (1M context window, excellent code quality)
- **Cost:** ~$0.14/M input, $0.28/M output (vs $5-15/day on OpenRouter)
- **Compression:** Aggressive context compression (triggers at 40%, targets 15%)
- **Subagents:** Also use DeepSeek (no OpenRouter bleed)
- **Auxiliary tasks:** Compression + title gen on DeepSeek (cheap)
- **OpenRouter:** Kept as fallback only (key stays in .env)

## Step 1: Install Hermes (if not already installed)

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

## Step 2: Get DeepSeek API Key

1. Go to https://platform.deepseek.com
2. Sign up (no card needed, they give free credits)
3. Top up $10 CAD if you want zero-worry buffer
4. Go to API Keys → Create new key
5. Copy the key

## Step 3: Add API Key

Option A — Interactive:
```bash
hermes auth add deepseek
```

Option B — Direct edit:
```bash
# Edit the .env file
notepad "%LOCALAPPDATA%\hermes\.env"
```
Add this line:
```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

Option C — CLI one-liner:
```bash
hermes config env-path
# Then edit that file and add: DEEPSEEK_API_KEY=your_key_here
```

## Step 4: Apply Config Settings

Run these commands in order:

```bash
# Primary model
hermes config set model.provider deepseek
hermes config set model.default deepseek-v4-flash
hermes config set model.base_url https://api.deepseek.com

# Compression (token savings)
hermes config set compression.enabled true
hermes config set compression.threshold 0.4
hermes config set compression.target_ratio 0.15
hermes config set compression.protect_last_n 15
hermes config set compression.hygiene_hard_message_limit 300

# Auxiliary tasks on DeepSeek (no OpenRouter bleed)
hermes config set auxiliary.compression.provider deepseek
hermes config set auxiliary.compression.model deepseek-v4-flash
hermes config set auxiliary.title_generation.provider deepseek
hermes config set auxiliary.title_generation.model deepseek-v4-flash

# Subagents on DeepSeek
hermes config set delegation.provider deepseek
hermes config set delegation.model deepseek-v4-flash
```

## Step 5: Verify

```bash
hermes doctor
hermes config
```

Then start a session:
```bash
hermes
```

Run `/usage` in-session to confirm DeepSeek is the active provider.

## Step 6: Install Headroom (context compression layer)

Headroom should already be installed if you copied config from laptop.
If not:
```bash
pip install headroom-cli
```

Verify MCP server is configured:
```bash
hermes mcp list
```
Should show `headroom` as a configured server.

## Cost Estimate

With $10 CAD (~$7.30 USD) on DeepSeek:
- ~50+ full refactoring sessions (each ~500K input, ~100K output)
- With cache hits on repeated context: even more
- Compression reduces tokens by ~40-60% on top of that

## What Stays on OpenRouter
- Vision tasks (Claude Opus for image analysis) — rarely used
- Nothing else. Everything else is DeepSeek.

## If Something Breaks

Restore from backup:
```bash
# Config backup was created at:
dir "%LOCALAPPDATA%\hermes\config.yaml.bak.*"
```

Or reset to OpenRouter temporarily:
```bash
hermes config set model.provider openrouter
hermes config set model.default xiaomi/mimo-v2.5-pro
```

---

## For Speed to Lead v5 Refactoring Specifically

Use Hermes with DeepSeek as the orchestrator. MiMo Code on desktop handles
individual file implementation. The workflow:

1. Hermes (DeepSeek) → plans the phase, reviews architecture
2. MiMo Code (desktop) → implements individual files
3. Hermes (DeepSeek) → reviews PR, runs tests, tracks progress

This gives you the best of both: cheap orchestration + fast local coding.
