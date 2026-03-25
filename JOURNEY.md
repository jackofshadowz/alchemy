# Alchemy — Development Journey

## Origins (March 23, 2026)

Alchemy started as a fork of [MoneyPrinterV2](https://github.com/FujiwaraChoki/MoneyPrinterV2), a Python CLI tool for automating content creation. The original tool used local inference (Ollama), local TTS (KittenTTS), Selenium for browser automation, and was locked to Python <3.13.

We gutted it and rebuilt it cloud-native.

## The Rewrite

**What changed:**
- Ollama (local LLM) → Multi-provider cloud LLM (Groq, DeepSeek, Moonshot, Qwen) via OpenAI SDK
- KittenTTS (local, Python-locked) → Kokoro TTS on Modal (5 voice rotation)
- Local Whisper → Whisper large-v3 on Modal
- Selenium → Playwright
- Static images → Helios 14B video generation on Modal H100
- AGPL-3.0 → BSL 1.1 (clean-room rewrite of all files)

**Every file is original work.** No code remains from MoneyPrinterV2.

## The Video Pipeline Evolution

### Version 1: Static Images + Ken Burns
- Gemini API for image generation (immediately hit free tier rate limits)
- Switched to Qwen Image 2.0 Pro via DashScope
- Ken Burns zoom/pan on static images
- MoviePy for composition
- **Problem:** No audio (MoviePy's audio embedding was broken)

### Version 2: Fixed Audio via ffmpeg
- Discovered MoviePy can't reliably embed audio into MP4
- Switched to ffmpeg for all audio muxing
- Voice + background music mixed via ffmpeg filter_complex
- **Problem:** Scripts sounded like AI, not like real motivational content

### Version 3: Curated Script Library
- Studied 18 SoundCloud motivational speeches (Eric Thomas, Les Brown, Greg Plitt)
- Identified the 5-act emotional arc: wound → anger → reframe → escalation → resolution
- Wrote 14 original scripts using ET/Les Brown cadence and rhetorical techniques
- Anaphora, antithesis, second-person direct address, visceral details
- **Problem:** Images didn't match the script, no visual arc

### Version 4: Helios Video Generation
- Deployed Helios 14B Distilled on Modal H100
- Text-to-video: ~17-20s per clip on warm container
- Replaced static images with actual AI-generated video clips
- 20 rapid-fire clips at ~1.2s each (montage style)
- **Problem:** AI artifacts (garbled text, extra hands, uncanny faces)

### Version 5: Curated Visuals Library
- 60+ hand-crafted cinematic prompts across 7 categories
- Written through the lens of Deakins, Lubezki, Richardson, Storaro, Scorsese, Coppola
- Mixed with raw iPhone/social media energy
- Emotional arc: hooks → struggle → grind → transition → luxury → triumph → outro
- **Problem:** Still some artifacts, needed extensive rules

### Version 6: The Rules (Current)
Extensive prompt engineering rules accumulated from testing:

**What AI video does well:** supercars (specific models), ground-level tracking shots, silhouettes, driver's seat POV, simple-background face close-ups, wide landscapes, gym equipment, suit details, coffee close-ups

**What AI video butchers:** front-facing faces in busy scenes, hands/fingers, text/signage, car logos/license plates, dashboard screens, rear-view mirrors, watches, phones, feet close-ups, helicopters in flight

**Content rules:** no alcohol, no shirtless men, couples must be man+woman from behind/silhouette only, gym scenes solo only, no specific city names, cars always driving forward

## Tech Stack

| Component | Service | Cost |
|-----------|---------|------|
| LLM | Qwen (qwen-max-latest) via DashScope | Free tier |
| TTS | Kokoro TTS on Modal T4 | ~$0.01/video |
| Video Gen | Helios 14B on Modal H100 | ~$0.35/video |
| Images | Qwen Image 2.0 Pro (backup) | Free tier |
| Audio Mix | ffmpeg (local) | Free |
| Composition | ffmpeg (local) | Free |

**Total cost per video:** ~$0.40
**Modal credits remaining:** ~$4,100
**Videos possible:** ~10,000

## Voice Library

5-voice rotation for variety:
- `am_adam` — Deep, authoritative American
- `am_michael` — Warm narrator American
- `am_eric` — Sharp, clear American
- `bm_george` — Distinguished British
- `bm_lewis` — Textured British

## What's Next

1. Speaker-style scripts (ET, Goggins, Les Brown, Peterson) with matched voices
2. Sentence-matched imagery (visuals that represent what's being said)
3. Mashup format (multiple voices on one script)
4. Format menu system
5. Batch generation (10 videos at once)
6. Subtitle burn-in
7. Frontier model evaluation for quality upgrade
