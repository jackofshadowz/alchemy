import re
import sys
import time
import os
import json

from cache import *
from config import *
from status import *
from llm_provider import generate_text
from typing import List, Optional
from datetime import datetime
from termcolor import colored

from playwright.sync_api import sync_playwright


class Twitter:
    """
    Class for the Bot, that grows a Twitter account.
    """

    def __init__(
        self, account_uuid: str, account_nickname: str, browser_profile_path: str, topic: str
    ) -> None:
        self.account_uuid: str = account_uuid
        self.account_nickname: str = account_nickname
        self.browser_profile_path: str = browser_profile_path
        self.topic: str = topic

        # Initialize Playwright with persistent context
        self._pw = sync_playwright().start()
        self.browser = self._pw.firefox.launch_persistent_context(
            user_data_dir=browser_profile_path,
            headless=get_headless(),
        )
        self.page = self.browser.new_page()

    def __del__(self):
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass

    def post(self, text: Optional[str] = None) -> None:
        self.page.goto("https://x.com/compose/post")

        post_content: str = text if text is not None else self.generate_post()
        now: datetime = datetime.now()

        print(colored(" => Posting to Twitter:", "blue"), post_content[:30] + "...")
        body = post_content

        text_box = None
        text_box_selectors = [
            "div[data-testid='tweetTextarea_0'] div[role='textbox']",
            "xpath=//div[@data-testid='tweetTextarea_0']//div[@role='textbox']",
            "div[role='textbox']",
        ]

        for selector in text_box_selectors:
            try:
                locator = self.page.locator(selector)
                locator.wait_for(state="visible", timeout=10000)
                locator.click()
                locator.fill(body)
                text_box = locator
                break
            except Exception:
                continue

        if text_box is None:
            raise RuntimeError(
                "Could not find tweet text box. Ensure you are logged into X in this browser profile."
            )

        post_button = None
        post_button_selectors = [
            "button[data-testid='tweetButtonInline']",
            "button[data-testid='tweetButton']",
            "xpath=//span[text()='Post']/ancestor::button",
        ]

        for selector in post_button_selectors:
            try:
                locator = self.page.locator(selector)
                locator.wait_for(state="visible", timeout=5000)
                locator.click()
                post_button = locator
                break
            except Exception:
                continue

        if post_button is None:
            raise RuntimeError("Could not find the Post button on X compose screen.")

        if get_verbose():
            print(colored(" => Posted to Twitter.", "blue"))
        self.page.wait_for_timeout(2000)

        self.add_post({"content": body, "date": now.strftime("%m/%d/%Y, %H:%M:%S")})

        success("Posted to Twitter successfully!")

    def get_posts(self) -> List[dict]:
        if not os.path.exists(get_twitter_cache_path()):
            with open(get_twitter_cache_path(), "w") as file:
                json.dump({"accounts": []}, file, indent=4)

        with open(get_twitter_cache_path(), "r") as file:
            parsed = json.load(file)

            accounts = parsed["accounts"]
            for account in accounts:
                if account["id"] == self.account_uuid:
                    posts = account["posts"]

                    if posts is None:
                        return []

                    return posts

        return []

    def add_post(self, post: dict) -> None:
        posts = self.get_posts()
        posts.append(post)

        with open(get_twitter_cache_path(), "r") as file:
            previous_json = json.loads(file.read())

            accounts = previous_json["accounts"]
            for account in accounts:
                if account["id"] == self.account_uuid:
                    account["posts"].append(post)

            with open(get_twitter_cache_path(), "w") as f:
                f.write(json.dumps(previous_json))

    def generate_post(self) -> str:
        completion = generate_text(
            f"Generate a Twitter post about: {self.topic} in {get_twitter_language()}. "
            "The Limit is 2 sentences. Choose a specific sub-topic of the provided topic."
        )

        if get_verbose():
            info("Generating a post...")

        if completion is None:
            error("Failed to generate a post. Please try again.")
            sys.exit(1)

        completion = re.sub(r"\*", "", completion).replace('"', "")

        if get_verbose():
            info(f"Length of post: {len(completion)}")
        if len(completion) >= 260:
            return completion[:257].rsplit(" ", 1)[0] + "..."

        return completion
