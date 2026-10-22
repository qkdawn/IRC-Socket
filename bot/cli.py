"""Command-line configuration for the bot."""

import argparse
import logging

from .client import BotClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPv6 IRC bot")
    parser.add_argument("--host", default="fc00:1337::17")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--name", default="SuperBot", dest="nickname")
    parser.add_argument("--channel", default="#hello")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        client = BotClient(args.host, args.port, args.nickname, args.channel)
    except ValueError as exc:
        build_parser().error(str(exc))
    try:
        client.run()
    except KeyboardInterrupt:
        client.stop()
