"""Command-line configuration for the IRC server."""

import argparse
import logging

from .server import IRCServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPv6 IRC server")
    parser.add_argument("--host", default="::", help="IPv6 listen address")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--name", default="irc.local", dest="server_name")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        server = IRCServer(args.host, args.port, args.server_name)
    except ValueError as exc:
        build_parser().error(str(exc))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()
