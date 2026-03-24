"""Alchemy — Local business outreach via Google Maps scraping + cold email."""

import os
import io
import re
import csv
import glob
import shlex
import zipfile
import platform
import subprocess

import requests
import yagmail

from cache import get_results_cache_path
from status import info, success, warning, error
from config import (
    get_google_maps_scraper_zip_url,
    get_google_maps_scraper_niche,
    get_scraper_timeout,
    get_outreach_message_subject,
    get_outreach_message_body_file,
    get_email_credentials,
)


class Outreach:
    """Scrape local businesses from Google Maps and send outreach emails."""

    def __init__(self) -> None:
        self.niche = get_google_maps_scraper_niche()
        self.email_creds = get_email_credentials()

    def start(self) -> None:
        if not self._check_go():
            error("Go is not installed. Install Go and try again.")
            return

        self._download_scraper()
        self._build_scraper()
        self._run_scraper()
        self._send_emails()

    # ─── Go + Scraper Setup ───

    def _check_go(self) -> bool:
        try:
            subprocess.run(["go", "version"], capture_output=True, check=True)
            return True
        except Exception:
            return False

    def _scraper_dir(self) -> str:
        for d in sorted(glob.glob("google-maps-scraper-*")):
            if os.path.isdir(d) and os.path.exists(os.path.join(d, "go.mod")):
                return d
        return ""

    def _binary_name(self) -> str:
        return "google-maps-scraper.exe" if platform.system() == "Windows" else "google-maps-scraper"

    def _download_scraper(self) -> None:
        if self._scraper_dir():
            info("Scraper already downloaded.")
            return

        url = get_google_maps_scraper_zip_url()
        info(f"Downloading scraper from {url}...")
        resp = requests.get(url, timeout=120)
        zf = zipfile.ZipFile(io.BytesIO(resp.content))

        for member in zf.namelist():
            if ".." in member or member.startswith("/"):
                warning(f"Skipping suspicious path: {member}")
                continue
            zf.extract(member)

        success("Scraper downloaded.")

    def _build_scraper(self) -> None:
        binary = self._binary_name()
        if os.path.exists(binary):
            info("Scraper already built.")
            return

        scraper_dir = self._scraper_dir()
        if not scraper_dir:
            error("Could not find scraper directory.")
            return

        info("Building scraper...")
        subprocess.run(["go", "mod", "download"], cwd=scraper_dir, check=True)
        subprocess.run(["go", "build"], cwd=scraper_dir, check=True)

        built = os.path.join(scraper_dir, binary)
        if os.path.exists(built):
            os.replace(built, binary)
            success("Scraper built.")
        else:
            error(f"Expected binary not found: {built}")

    def _run_scraper(self) -> None:
        info("Running scraper...")

        with open("niche.txt", "w") as f:
            f.write(self.niche)

        output = get_results_cache_path()
        binary = os.path.join(os.getcwd(), self._binary_name())
        args = shlex.split(f'-input niche.txt -results "{output}"')

        try:
            subprocess.run(
                [binary] + args,
                timeout=float(get_scraper_timeout()),
            )
        except subprocess.TimeoutExpired:
            warning("Scraper timed out.")
        finally:
            if os.path.exists("niche.txt"):
                os.remove("niche.txt")

        if os.path.exists(output):
            success(f"Scraper results saved to {output}")
        else:
            error("No scraper results found.")

    # ─── Email ───

    def _extract_email(self, website: str) -> str:
        """Extract first email address from a website's HTML."""
        try:
            resp = requests.get(website, timeout=15)
            if resp.status_code != 200:
                return ""
            pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,7}\b"
            found = re.findall(pattern, resp.text)
            return found[0] if found else ""
        except Exception:
            return ""

    def _send_emails(self) -> None:
        output = get_results_cache_path()
        if not os.path.exists(output):
            error("No results file to process.")
            return

        subject_template = get_outreach_message_subject()
        body_file = get_outreach_message_body_file()

        if not os.path.exists(body_file):
            error(f"Email body file not found: {body_file}")
            return

        with open(body_file, "r") as f:
            body_template = f.read()

        with open(output, "r", errors="ignore") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if len(rows) < 2:
            warning("No businesses found in results.")
            return

        yag = yagmail.SMTP(
            user=self.email_creds.get("username", ""),
            password=self.email_creds.get("password", ""),
            host=self.email_creds.get("smtp_server", "smtp.gmail.com"),
            port=self.email_creds.get("smtp_port", 587),
        )

        for row in rows[1:]:
            try:
                company = row[0] if row else "Unknown"
                websites = [w for w in row if w.startswith("http")]
                website = websites[0] if websites else ""

                if not website:
                    continue

                email = self._extract_email(website)
                if not email or "@" not in email:
                    continue

                subject = subject_template.replace("{{COMPANY_NAME}}", company)
                body = body_template.replace("{{COMPANY_NAME}}", company)

                info(f"Sending to {email}...")
                yag.send(to=email, subject=subject, contents=body)
                success(f"Sent to {email}")

            except Exception as err:
                error(f"Failed for {row[0] if row else 'unknown'}: {err}")
                continue
