"""Command-line configuration for the bot."""

import argparse

from .client import BotClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPv6 IRC coursework bot")
    parser.add_argument("--host", default="fc00:1337::17")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--name", default="SuperBot", dest="nickname")
    parser.add_argument("--channel", default="#hello")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    client = BotClient(args.host, args.port, args.nickname, args.channel)
    try:
        client.run()
    except KeyboardInterrupt:
        client.stop()

