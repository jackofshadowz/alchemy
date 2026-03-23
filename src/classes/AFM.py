import os
from urllib.parse import urlparse
from typing import Any

from status import *
from config import *
from constants import *
from llm_provider import generate_text
from .Twitter import Twitter

from playwright.sync_api import sync_playwright


class AffiliateMarketing:
    """
    This class handles all affiliate marketing related operations.
    """

    def __init__(
        self,
        affiliate_link: str,
        browser_profile_path: str,
        twitter_account_uuid: str,
        account_nickname: str,
        topic: str,
    ) -> None:
        self._browser_profile_path: str = browser_profile_path

        # Initialize Playwright with persistent context
        self._pw = sync_playwright().start()
        self.browser_ctx = self._pw.firefox.launch_persistent_context(
            user_data_dir=browser_profile_path,
            headless=get_headless(),
        )
        self.page = self.browser_ctx.new_page()

        # Set the affiliate link
        self.affiliate_link: str = affiliate_link

        parsed_link = urlparse(self.affiliate_link)
        if parsed_link.scheme not in ["http", "https"] or not parsed_link.netloc:
            raise ValueError(
                f"Affiliate link is invalid. Expected a full URL, got: {self.affiliate_link}"
            )

        self.account_uuid: str = twitter_account_uuid
        self.account_nickname: str = account_nickname
        self.topic: str = topic

        # Scrape the product information
        self.scrape_product_information()

    def __del__(self):
        try:
            self.browser_ctx.close()
            self._pw.stop()
        except Exception:
            pass

    def scrape_product_information(self) -> None:
        self.page.goto(self.affiliate_link)
        self.page.wait_for_load_state("networkidle")

        product_title: str = self.page.locator(f"#{AMAZON_PRODUCT_TITLE_ID}").text_content().strip()

        features: Any = self.page.locator(f"#{AMAZON_FEATURE_BULLETS_ID}").all()

        if get_verbose():
            info(f"Product Title: {product_title}")

        if get_verbose():
            info(f"Features: {features}")

        self.product_title: str = product_title
        self.features: Any = features

    def generate_response(self, prompt: str) -> str:
        return generate_text(prompt)

    def generate_pitch(self) -> str:
        pitch: str = (
            self.generate_response(
                f'I want to promote this product on my website. Generate a brief pitch about this product, return nothing else except the pitch. Information:\nTitle: "{self.product_title}"\nFeatures: "{str(self.features)}"'
            )
            + "\nYou can buy the product here: "
            + self.affiliate_link
        )

        self.pitch: str = pitch
        return pitch

    def share_pitch(self, where: str) -> None:
        if where == "twitter":
            twitter: Twitter = Twitter(
                self.account_uuid,
                self.account_nickname,
                self._browser_profile_path,
                self.topic,
            )

            twitter.post(self.pitch)

    def quit(self) -> None:
        self.browser_ctx.close()
        self._pw.stop()
