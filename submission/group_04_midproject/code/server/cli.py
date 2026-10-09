"""Command-line configuration for the IRC server."""

import argparse
import logging

from .server import IRCServer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPv6 coursework IRC server")
    parser.add_argument("--host", default="::", help="IPv6 listen address")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--name", default="coursework.local", dest="server_name")
    return parser


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = IRCServer(args.host, args.port, args.server_name)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.stop()
