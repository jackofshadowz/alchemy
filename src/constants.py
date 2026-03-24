"""Alchemy — UI constants and browser selectors."""

# Main menu
MAIN_MENU = [
    "YouTube Shorts Automation",
    "Twitter Bot",
    "Affiliate Marketing",
    "Outreach",
    "Quit",
]

# YouTube sub-menu
YOUTUBE_MENU = [
    "Upload Short",
    "Show all Shorts",
    "Setup CRON Job",
    "Back",
]

# Twitter sub-menu
TWITTER_MENU = [
    "Post something",
    "Show all Posts",
    "Setup CRON Job",
    "Back",
]

# Scheduling options
SCHEDULE_OPTIONS = [
    "Once a day",
    "Twice a day",
    "Three times a day",
    "Back",
]

# YouTube Studio selectors (Playwright)
YT_TEXTBOX = "textbox"
YT_KIDS_YES = "VIDEO_MADE_FOR_KIDS_MFK"
YT_KIDS_NO = "VIDEO_MADE_FOR_KIDS_NOT_MFK"
YT_NEXT = "next-button"
YT_RADIO = '//*[@id="radioLabel"]'
YT_DONE = "done-button"

# Amazon selectors (Playwright)
AMAZON_TITLE = "productTitle"
AMAZON_BULLETS = "feature-bullets"
