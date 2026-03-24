"""Alchemy — automated content creation platform."""

import sys
import os
import schedule
import subprocess

from art import print_banner
from cache import get_accounts, add_account, remove_account, get_products, add_product
from utils import rem_temp_files, fetch_songs
from config import (
    ROOT_DIR, assert_folder_structure, get_first_time_running,
    get_verbose, get_headless,
)
from status import info, success, warning, error, question
from constants import (
    MAIN_MENU, YOUTUBE_MENU, TWITTER_MENU, SCHEDULE_OPTIONS,
)
from uuid import uuid4
from classes.Tts import TTS
from termcolor import colored
from classes.Twitter import Twitter
from classes.YouTube import YouTube
from prettytable import PrettyTable
from classes.Outreach import Outreach
from classes.AFM import AffiliateMarketing
from llm_provider import init_provider, get_active_model, get_active_provider


def show_menu(title: str, options: list) -> int:
    """Display a numbered menu and return the user's choice (1-indexed)."""
    info(f"\n{'=' * 12} {title} {'=' * 12}", False)
    for i, opt in enumerate(options, 1):
        print(colored(f" {i}. {opt}", "cyan"))
    info("=" * (26 + len(title)), False)

    while True:
        raw = input("\nSelect an option: ").strip()
        try:
            choice = int(raw)
            if 1 <= choice <= len(options):
                return choice
        except ValueError:
            pass
        print("Invalid input. Try again.")


def pick_account(platform: str) -> dict | None:
    """Show account table, let user pick or delete. Returns selected account or None."""
    accounts = get_accounts(platform)

    if not accounts:
        warning("No accounts found. Create one now?")
        if question("Yes/No: ").strip().lower() != "yes":
            return None
        return create_account(platform)

    table = PrettyTable()
    if platform == "youtube":
        table.field_names = ["#", "ID", "Nickname", "Niche"]
        for i, a in enumerate(accounts, 1):
            table.add_row([i, colored(a["id"][:8], "cyan"), colored(a["nickname"], "blue"), colored(a["niche"], "green")])
    else:
        table.field_names = ["#", "ID", "Nickname", "Topic"]
        for i, a in enumerate(accounts, 1):
            table.add_row([i, colored(a["id"][:8], "cyan"), colored(a["nickname"], "blue"), colored(a.get("topic", ""), "green")])

    print(table)
    info("Type 'd' to delete an account.", False)

    raw = question("Select account (or 'd'): ").strip()

    if raw.lower() == "d":
        idx = question("Account # to delete: ").strip()
        try:
            acct = accounts[int(idx) - 1]
            if question(f"Delete '{acct['nickname']}'? (Yes/No): ").strip().lower() == "yes":
                remove_account(platform, acct["id"])
                success("Deleted.")
        except (IndexError, ValueError):
            error("Invalid selection.")
        return None

    try:
        return accounts[int(raw) - 1]
    except (IndexError, ValueError):
        error("Invalid selection.")
        return None


def create_account(platform: str) -> dict | None:
    """Interactively create a new account."""
    uid = str(uuid4())
    success(f"Generated ID: {uid[:8]}")

    nickname = question("Nickname: ")
    profile = question("Browser profile path: ")

    if platform == "youtube":
        niche = question("Niche: ")
        language = question("Language: ")
        account = {
            "id": uid, "nickname": nickname, "browser_profile": profile,
            "niche": niche, "language": language, "videos": [],
        }
    else:
        topic = question("Topic: ")
        account = {
            "id": uid, "nickname": nickname, "browser_profile": profile,
            "topic": topic, "posts": [],
        }

    add_account(platform, account)
    success("Account created.")
    return account


def get_profile(account: dict) -> str:
    """Get browser profile path from account, supporting both old and new key names."""
    return account.get("browser_profile", account.get("firefox_profile", ""))


# ─── Feature Handlers ───

def handle_youtube():
    info("Starting YouTube Shorts Automater...")
    account = pick_account("youtube")
    if not account:
        return

    yt = YouTube(
        account["id"], account["nickname"], get_profile(account),
        account["niche"], account["language"],
    )

    while True:
        choice = show_menu("YOUTUBE", YOUTUBE_MENU)

        if choice == 1:
            tts = TTS()
            yt.generate_video(tts)
            if question("Upload to YouTube? (Yes/No): ").strip().lower() == "yes":
                yt.upload_video()

        elif choice == 2:
            videos = yt.get_videos()
            if videos:
                t = PrettyTable(["#", "Date", "Title"])
                for i, v in enumerate(videos, 1):
                    t.add_row([i, colored(v["date"], "blue"), colored(v["title"][:60], "green")])
                print(t)
            else:
                warning("No videos found.")

        elif choice == 3:
            sched_choice = show_menu("SCHEDULE", SCHEDULE_OPTIONS)
            if sched_choice == 4:
                continue
            cmd = ["python", os.path.join(ROOT_DIR, "src", "cron.py"), "youtube", account["id"]]
            job = lambda: subprocess.run(cmd)
            if sched_choice == 1:
                schedule.every(1).day.do(job)
            elif sched_choice == 2:
                schedule.every().day.at("10:00").do(job)
                schedule.every().day.at("16:00").do(job)
            elif sched_choice == 3:
                schedule.every().day.at("08:00").do(job)
                schedule.every().day.at("12:00").do(job)
                schedule.every().day.at("18:00").do(job)
            success("CRON job set.")

        elif choice == 4:
            break


def handle_twitter():
    info("Starting Twitter Bot...")
    account = pick_account("twitter")
    if not account:
        return

    tw = Twitter(account["id"], account["nickname"], get_profile(account), account["topic"])

    while True:
        choice = show_menu("TWITTER", TWITTER_MENU)

        if choice == 1:
            tw.post()

        elif choice == 2:
            posts = tw.get_posts()
            if posts:
                t = PrettyTable(["#", "Date", "Content"])
                for i, p in enumerate(posts, 1):
                    t.add_row([i, colored(p["date"], "blue"), colored(p["content"][:60], "green")])
                print(t)
            else:
                warning("No posts found.")

        elif choice == 3:
            sched_choice = show_menu("SCHEDULE", SCHEDULE_OPTIONS)
            if sched_choice == 4:
                continue
            cmd = ["python", os.path.join(ROOT_DIR, "src", "cron.py"), "twitter", account["id"]]
            job = lambda: subprocess.run(cmd)
            if sched_choice == 1:
                schedule.every(1).day.do(job)
            elif sched_choice == 2:
                schedule.every().day.at("10:00").do(job)
                schedule.every().day.at("16:00").do(job)
            elif sched_choice == 3:
                schedule.every().day.at("08:00").do(job)
                schedule.every().day.at("12:00").do(job)
                schedule.every().day.at("18:00").do(job)
            success("CRON job set.")

        elif choice == 4:
            break


def handle_affiliate():
    info("Starting Affiliate Marketing...")
    products = get_products()

    if not products:
        warning("No products found. Create one now?")
        if question("Yes/No: ").strip().lower() != "yes":
            return

        link = question("Affiliate link: ")
        tw_uuid = question("Twitter Account UUID: ")

        tw_accounts = get_accounts("twitter")
        account = next((a for a in tw_accounts if a["id"] == tw_uuid), None)
        if not account:
            error("Twitter account not found.")
            return

        add_product({"id": str(uuid4()), "affiliate_link": link, "twitter_uuid": tw_uuid})

        afm = AffiliateMarketing(link, get_profile(account), account["id"], account["nickname"], account["topic"])
        afm.generate_pitch()
        afm.share_pitch("twitter")
    else:
        t = PrettyTable(["#", "Affiliate Link", "Twitter UUID"])
        for i, p in enumerate(products, 1):
            t.add_row([i, colored(p["affiliate_link"], "cyan"), colored(p["twitter_uuid"][:8], "blue")])
        print(t)

        raw = question("Select product: ").strip()
        try:
            product = products[int(raw) - 1]
        except (IndexError, ValueError):
            error("Invalid selection.")
            return

        account = next((a for a in get_accounts("twitter") if a["id"] == product["twitter_uuid"]), None)
        if not account:
            error("Associated Twitter account not found.")
            return

        afm = AffiliateMarketing(
            product["affiliate_link"], get_profile(account),
            account["id"], account["nickname"], account["topic"],
        )
        afm.generate_pitch()
        afm.share_pitch("twitter")


def handle_outreach():
    info("Starting Outreach...")
    Outreach().start()


# ─── Main Loop ───

HANDLERS = {
    1: handle_youtube,
    2: handle_twitter,
    3: handle_affiliate,
    4: handle_outreach,
}


def main_loop():
    choice = show_menu("ALCHEMY", MAIN_MENU)
    if choice == 5:
        if get_verbose():
            info("Quitting...")
        sys.exit(0)
    handler = HANDLERS.get(choice)
    if handler:
        handler()
    else:
        error("Invalid option.")


if __name__ == "__main__":
    print_banner()

    if get_first_time_running():
        print(colored("Welcome to Alchemy. Let's get you set up.", "yellow"))

    assert_folder_structure()
    rem_temp_files()
    fetch_songs()

    try:
        init_provider()
        success(f"LLM: {get_active_provider()} / {get_active_model()}")
    except Exception as e:
        error(f"Failed to initialize LLM: {e}")
        info("Check config.json — set llm.provider and the API key.")
        sys.exit(1)

    while True:
        main_loop()
