"""Alchemy — console output helpers."""

from termcolor import colored


def error(msg: str, show_emoji: bool = True) -> None:
    prefix = "X " if show_emoji else ""
    print(colored(f"{prefix}{msg}", "red"))


def success(msg: str, show_emoji: bool = True) -> None:
    prefix = "+ " if show_emoji else ""
    print(colored(f"{prefix}{msg}", "green"))


def info(msg: str, show_emoji: bool = True) -> None:
    prefix = "> " if show_emoji else ""
    print(colored(f"{prefix}{msg}", "magenta"))


def warning(msg: str, show_emoji: bool = True) -> None:
    prefix = "! " if show_emoji else ""
    print(colored(f"{prefix}{msg}", "yellow"))


def question(msg: str, show_emoji: bool = True) -> str:
    prefix = "? " if show_emoji else ""
    return input(colored(f"{prefix}{msg}", "magenta"))
