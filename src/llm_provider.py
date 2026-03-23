from openai import OpenAI
from config import get_llm_config

_client: OpenAI | None = None
_model: str | None = None
_provider: str | None = None

PROVIDERS = {
    "inference_net",
    "groq",
    "openrouter",
    "deepseek",
    "moonshot",
}


def init_provider(provider: str = None, api_key: str = None,
                  base_url: str = None, model: str = None) -> None:
    global _client, _model, _provider
    cfg = get_llm_config()
    _provider = provider or cfg["provider"]
    _model = model or cfg["model"]
    _client = OpenAI(
        api_key=api_key or cfg["api_key"],
        base_url=base_url or cfg["base_url"],
    )


def get_active_model() -> str | None:
    return _model


def get_active_provider() -> str | None:
    return _provider


def generate_text(prompt: str, model_name: str = None) -> str:
    if _client is None:
        init_provider()

    response = _client.chat.completions.create(
        model=model_name or _model,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content.strip()
