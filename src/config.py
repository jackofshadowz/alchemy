import os
import sys
import json
import srt_equalizer

from termcolor import colored

ROOT_DIR = os.path.dirname(sys.path[0])

_config = None


def _load_config() -> dict:
    global _config
    if _config is None:
        with open(os.path.join(ROOT_DIR, "config.json"), "r") as file:
            _config = json.load(file)
    return _config


def reload_config() -> dict:
    global _config
    _config = None
    return _load_config()


def assert_folder_structure() -> None:
    if not os.path.exists(os.path.join(ROOT_DIR, ".mp")):
        if get_verbose():
            print(colored(f"=> Creating .mp folder at {os.path.join(ROOT_DIR, '.mp')}", "green"))
        os.makedirs(os.path.join(ROOT_DIR, ".mp"))


def get_first_time_running() -> bool:
    return not os.path.exists(os.path.join(ROOT_DIR, ".mp"))


# --- General ---

def get_verbose() -> bool:
    return _load_config().get("verbose", True)


def get_headless() -> bool:
    return _load_config().get("headless", False)


def get_threads() -> int:
    return _load_config().get("threads", 2)


# --- LLM ---

def get_llm_config() -> dict:
    cfg = _load_config()
    llm = cfg.get("llm", {})
    provider_name = llm.get("provider", "groq")
    providers = llm.get("providers", {})
    provider = providers.get(provider_name, {})
    return {
        "provider": provider_name,
        "api_key": provider.get("api_key", ""),
        "base_url": provider.get("base_url", ""),
        "model": provider.get("model", ""),
    }


# --- TTS ---

def get_tts_config() -> dict:
    cfg = _load_config()
    tts = cfg.get("tts", {})
    return {
        "voice": tts.get("voice", "af_heart"),
        "speed": tts.get("speed", 1.0),
    }


# --- Image Generation ---

def get_image_gen_api_base_url() -> str:
    return _load_config().get("image_generation", {}).get(
        "api_base_url", "https://generativelanguage.googleapis.com/v1beta"
    )


def get_image_gen_api_key() -> str:
    configured = _load_config().get("image_generation", {}).get("api_key", "")
    return configured or os.environ.get("GEMINI_API_KEY", "")


def get_image_gen_model() -> str:
    return _load_config().get("image_generation", {}).get(
        "model", "gemini-2.0-flash-preview-image-generation"
    )


def get_image_gen_aspect_ratio() -> str:
    return _load_config().get("image_generation", {}).get("aspect_ratio", "9:16")


# --- YouTube ---

def get_is_for_kids() -> bool:
    return _load_config().get("youtube", {}).get("is_for_kids", False)


def get_zip_url() -> str:
    return _load_config().get("youtube", {}).get("zip_url", "")


def get_font() -> str:
    return _load_config().get("youtube", {}).get("font", "bold_font.ttf")


def get_fonts_dir() -> str:
    return os.path.join(ROOT_DIR, "fonts")


def get_imagemagick_path() -> str:
    return _load_config().get("youtube", {}).get("imagemagick_path", "/usr/bin/convert")


def get_script_sentence_length() -> int:
    return _load_config().get("youtube", {}).get("script_sentence_length", 4)


# --- Twitter ---

def get_twitter_language() -> str:
    return _load_config().get("twitter_language", "English")


# --- Outreach ---

def get_google_maps_scraper_zip_url() -> str:
    return _load_config().get("outreach", {}).get("google_maps_scraper", "")


def get_google_maps_scraper_niche() -> str:
    return _load_config().get("outreach", {}).get("google_maps_scraper_niche", "")


def get_scraper_timeout() -> int:
    return _load_config().get("outreach", {}).get("scraper_timeout", 300) or 300


def get_outreach_message_subject() -> str:
    return _load_config().get("outreach", {}).get("message_subject", "I have a question...")


def get_outreach_message_body_file() -> str:
    return _load_config().get("outreach", {}).get("message_body_file", "outreach_message.html")


# --- Email ---

def get_email_credentials() -> dict:
    return _load_config().get("email", {})


# --- Subtitles ---

def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
    srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)
