# Repository Guidelines

## Project Structure & Module Organization
- `src/` contains the application code. Use `src/main.py` as the interactive entrypoint.
- `src/classes/` holds provider-specific components (`YouTube.py`, `Twitter.py`, `Tts.py`, `AFM.py`, `Outreach.py`).
- Shared utilities and configuration live in `src/config.py`, `src/utils.py`, `src/cache.py`, and `src/constants.py`.
- `modal_services/` contains Modal deployment definitions for cloud compute (TTS, STT).
- `scripts/` contains helper workflows such as setup and upload helpers.
- `docs/` contains feature documentation; `assets/` and `fonts/` contain static resources.

## Build, Test, and Development Commands
- `cp config.example.json config.json`: create config from template, then fill in API keys.
- `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`: install deps.
- `playwright install firefox`: install Playwright browser binaries.
- `modal deploy modal_services/tts.py && modal deploy modal_services/stt.py`: deploy cloud TTS/STT.
- `python src/main.py`: start the CLI app.

## Coding Style & Naming Conventions
- Target Python 3.12+ (no upper bound).
- Use 4-space indentation and follow existing Python conventions:
  - `snake_case` for functions/variables
  - `PascalCase` for classes
  - `UPPER_SNAKE_CASE` for constants
- Keep new business logic in focused modules under `src/`; keep provider/integration code in `src/classes/`.
- Prefer small, explicit functions and preserve existing CLI-first behavior.

## Testing Guidelines
- There is currently no enforced automated test suite or coverage threshold.
- Minimum validation for changes:
  - Syntax check: `python -c "import ast; ast.parse(open('file.py').read())"`
  - Smoke-test impacted flows via `python src/main.py`
- When adding tests, place them in a top-level `tests/` directory with names like `test_<module>.py`.

## Commit & Pull Request Guidelines
- Follow the existing commit style: imperative summaries like `Fix ...`, `Update ...`.
- Open PRs against `main`.
- Link each PR to an issue, keep scope to one feature/fix, and use a clear title + description.

## Security & Configuration Tips
- Treat `config.json` as environment-specific; do not commit real API keys or private profile paths.
- Start from `config.example.json` and prefer environment variables where supported (e.g., `GEMINI_API_KEY`).
