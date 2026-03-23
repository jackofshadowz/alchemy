# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Alchemy is a Python CLI tool that automates four online content workflows. Forked from MoneyPrinterV2 and modernized with cloud inference, Modal compute, and Playwright browser automation.

1. **YouTube Shorts** — generate video (LLM script → cloud TTS → images → MoviePy composite) and upload via Playwright
2. **Twitter/X Bot** — generate and post tweets via Playwright
3. **Affiliate Marketing** — scrape Amazon product info, generate pitch, share on Twitter
4. **Local Business Outreach** — scrape Google Maps (Go binary), extract emails, send cold outreach via SMTP

There is no web UI, no REST API, no test suite, no CI, and no linting config.

## Running the Application

```bash
# First-time setup
cp config.example.json config.json   # then fill in API keys
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install firefox

# Deploy Modal services (one-time)
modal deploy modal_services/tts.py
modal deploy modal_services/stt.py

# Run
python src/main.py
```

The app **must** be run from the project root. `python src/main.py` adds `src/` to `sys.path`, so all imports use bare module names (e.g., `from config import *`, not `from src.config import *`).

## Architecture

### Entry Points
- `src/main.py` — interactive menu loop (primary)
- `src/cron.py` — headless runner invoked by the scheduler as a subprocess: `python src/cron.py <platform> <account_uuid>`

### Provider Pattern

| Category | Config location | Options |
|---|---|---|
| LLM | `llm.provider` + `llm.providers.*` | inference.net, groq, openrouter, deepseek, moonshot (all OpenAI-compatible) |
| Image gen | `image_generation.*` | Gemini API |
| TTS | Modal service | Kokoro TTS (deployed on Modal) |
| STT | Modal service | Whisper large-v3 (deployed on Modal) |

All LLM providers use the `openai` Python SDK with different `base_url`/`api_key`/`model` values.

### Key Modules
- **`src/llm_provider.py`** — unified `generate_text(prompt)` using the OpenAI SDK, multi-provider via config
- **`src/config.py`** — loads `config.json` once (cached), provides getter functions. `ROOT_DIR` = project root
- **`src/cache.py`** — JSON file persistence in `.mp/` directory (accounts, videos, posts, products)
- **`src/constants.py`** — menu strings, browser selectors (YouTube Studio, X.com, Amazon)
- **`src/classes/YouTube.py`** — full pipeline: topic → script → metadata → image prompts → images → TTS → subtitles → MoviePy combine → Playwright upload
- **`src/classes/Twitter.py`** — Playwright automation against x.com
- **`src/classes/AFM.py`** — Amazon scraping + LLM pitch generation
- **`src/classes/Outreach.py`** — Google Maps scraper (requires Go) + email sending via yagmail
- **`src/classes/Tts.py`** — thin Modal client for Kokoro TTS
- **`modal_services/tts.py`** — Kokoro TTS deployed on Modal (T4 GPU)
- **`modal_services/stt.py`** — Whisper large-v3 deployed on Modal (T4 GPU)

### Data Storage
All persistent state lives in `.mp/` at the project root as JSON files (`youtube.json`, `twitter.json`, `afm.json`). This directory also serves as scratch space for temporary WAV, PNG, SRT, and MP4 files — non-JSON files are cleaned on each run by `rem_temp_files()`.

### Browser Automation
Playwright uses persistent Firefox contexts (pre-authenticated). The profile path is stored per-account in the cache JSON as `browser_profile`.

### CRON Scheduling
Uses Python's `schedule` library (in-process, not OS cron). The scheduled job spawns `subprocess.run(["python", "src/cron.py", platform, account_id])`.

## Configuration

All config lives in `config.json` at the project root. See `config.example.json` for the full template. Key external dependencies:
- **LLM API key** — at least one provider in `llm.providers` must have a valid API key
- **Modal** — `modal token set` for TTS/STT services
- **ImageMagick** — required for MoviePy subtitle rendering (`youtube.imagemagick_path`)
- **Gemini API key** — for image generation (`image_generation.api_key`)
- **Playwright Firefox** — `playwright install firefox`
- **Go** — only needed for Outreach (Google Maps scraper)
