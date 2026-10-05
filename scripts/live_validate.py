"""Exercise the IRC server over the supplied IPv6 VM network."""

from __future__ import annotations

import argparse
import pathlib
import socket
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from common.stream import IRCStreamDecoder


def wait_for(
    sock: socket.socket, decoder: IRCStreamDecoder, predicate, timeout: float = 5.0
):
    deadline = time.monotonic() + timeout
    pending = []
    sock.settimeout(0.5)
    while time.monotonic() < deadline:
        for index, incoming in enumerate(pending):
            if predicate(incoming):
                return pending.pop(index)
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            raise RuntimeError("server closed the connection")
        pending.extend(decoder.feed(data))
    raise TimeoutError(f"timed out; received {[msg.serialize() for msg in pending]}")


def connect(host: str, port: int, nickname: str):
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    sock.connect((host, port))
    decoder = IRCStreamDecoder()
    sock.sendall(f"NICK {nickname}\r\nUSER {nickname} 0 * :{nickname}\r\n".encode())
    wait_for(sock, decoder, lambda msg: msg.command == "001")
    return sock, decoder


def main() -> int:
    parser = argparse.ArgumentParser(description="Live IPv6 IRC validation")
    parser.add_argument("--host", default="fc00:1337::17")
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument("--channel", default="#livepre")
    args = parser.parse_args()

    alice = bob = None
    try:
        alice, alice_decoder = connect(args.host, args.port, "prealice")
        bob, bob_decoder = connect(args.host, args.port, "prebob")
        print("REGISTRATION=PASS")

        alice.sendall(f"JOIN {args.channel}\r\n".encode())
        bob.sendall(f"JOIN {args.channel}\r\n".encode())
        wait_for(alice, alice_decoder, lambda msg: msg.command == "JOIN")
        wait_for(bob, bob_decoder, lambda msg: msg.command == "JOIN")
        print("JOIN=PASS")

        alice.sendall(f"PRIVMSG {args.channel} :live channel check\r\n".encode())
        wait_for(
            bob,
            bob_decoder,
            lambda msg: msg.command == "PRIVMSG"
            and msg.params[-1] == "live channel check",
        )
        print("CHANNEL_MESSAGE=PASS")

        alice.sendall(b"PRIVMSG prebob :live private check\r\n")
        wait_for(
            bob,
            bob_decoder,
            lambda msg: msg.command == "PRIVMSG"
            and msg.params[-1] == "live private check",
        )
        print("PRIVATE_MESSAGE=PASS")

        alice.sendall(b"PRIVMSG missing_live_user :should fail\r\n")
        wait_for(alice, alice_decoder, lambda msg: msg.command == "401")
        print("UNKNOWN_TARGET=PASS")
        return 0
    except Exception as exc:
        print(f"LIVE_VALIDATION=FAIL: {exc}")
        print("Check that Ubuntu is running: python3 -m server --host :: --port 6667")
        return 1
    finally:
        for sock in (alice, bob):
            if sock is not None:
                try:
                    sock.sendall(b"QUIT :live validation\r\n")
                except OSError:
                    pass
                sock.close()


if __name__ == "__main__":
    raise SystemExit(main())
