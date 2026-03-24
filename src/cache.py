"""Alchemy — JSON-based local data persistence."""

import os
import json
from typing import List
from config import ROOT_DIR

CACHE_DIR = os.path.join(ROOT_DIR, ".mp")


def _cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, f"{name}.json")


def _read(name: str) -> dict:
    path = _cache_path(name)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _write(name: str, data: dict) -> None:
    path = _cache_path(name)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# ─── Accounts (YouTube, Twitter) ───

def get_accounts(platform: str) -> List[dict]:
    data = _read(platform)
    return data.get("accounts", [])


def add_account(platform: str, account: dict) -> None:
    data = _read(platform)
    accounts = data.get("accounts", [])
    accounts.append(account)
    _write(platform, {"accounts": accounts})


def remove_account(platform: str, account_id: str) -> None:
    data = _read(platform)
    accounts = [a for a in data.get("accounts", []) if a["id"] != account_id]
    _write(platform, {"accounts": accounts})


# ─── Products (Affiliate Marketing) ───

def get_products() -> List[dict]:
    data = _read("afm")
    return data.get("products", [])


def add_product(product: dict) -> None:
    data = _read("afm")
    products = data.get("products", [])
    products.append(product)
    _write("afm", {"products": products})


# ─── Path helpers ───

def get_youtube_cache_path() -> str:
    return _cache_path("youtube")


def get_twitter_cache_path() -> str:
    return _cache_path("twitter")


def get_afm_cache_path() -> str:
    return _cache_path("afm")


def get_results_cache_path() -> str:
    return os.path.join(CACHE_DIR, "scraper_results.csv")
