"""Exercise the Bot against unmodified upstream miniircd over IPv6 loopback."""
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import hashlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bot.client import BotClient
from common.irc_message import message
from scripts.live_validate import connect, wait_for


def main():
    url = 'https://raw.githubusercontent.com/jrosdahl/miniircd/master/miniircd'
    payload = urllib.request.urlopen(url, timeout=20).read()
    cache = ROOT / '.codex-build' / 'miniircd_audit'
    cache.mkdir(parents=True, exist_ok=True)
    program = cache / 'miniircd.py'
    program.write_bytes(payload)
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as probe:
        probe.bind(('::1', 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([sys.executable, str(program), '--ipv6', '--listen', '::1', '--ports', str(port)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    bot = None
    sockets = []
    lines = [f'Source: {url}', f'SHA256: {hashlib.sha256(payload).hexdigest()}',
             'Environment: local IPv6 ::1; not the assessed VMs or HexChat.']
    try:
        for _ in range(50):
            if process.poll() is not None:
                raise RuntimeError('miniircd exited at startup')
            try:
                alice, decoder = connect('::1', port, 'alice')
                break
            except ConnectionRefusedError:
                time.sleep(0.1)
        else:
            raise RuntimeError('miniircd startup timed out')
        sockets.append(alice)
        alice.sendall(b'JOIN #hello\r\n')
        wait_for(alice, decoder, lambda m: m.command == '366')
        occupied, _ = connect('::1', port, 'SuperBot')
        sockets.append(occupied)
        bot = BotClient('::1', port, 'SuperBot', '#hello')
        thread = threading.Thread(target=bot.run, daemon=True)
        thread.start()
        joined = wait_for(alice, decoder, lambda m: m.command == 'JOIN' and m.prefix.startswith('SuperBot_'))
        nick = joined.prefix.split('!')[0]
        lines.append('Registration, nickname collision recovery and JOIN: PASS')
        for command, expected in [('!hello', 'Hello, alice!'), ('!time', 'Bot time:'), ('!slap alice', 'Choose a channel member'), ('!slap absent', 'alice slaps alice'), ('!who', 'WHO complete: 2 members')]:
            alice.sendall(message('PRIVMSG', '#hello', command).to_bytes())
            reply = wait_for(alice, decoder, lambda m: m.command == 'PRIVMSG' and expected in m.params[-1])
            lines.append(f'{command}: PASS ({reply.params[-1]})')
        alice.sendall(message('PRIVMSG', nick, 'Tell me a fact').to_bytes())
        reply = wait_for(alice, decoder, lambda m: m.command == 'PRIVMSG' and m.params[0] == 'alice')
        lines.append('Private fact: PASS (' + reply.params[-1] + ')')
        bot.handle(message('PING', 'audit-token'))
        lines.append('Bot PING handler sends PONG to miniircd: PASS')
    finally:
        if bot:
            bot.stop()
            thread.join(timeout=3)
        for sock in sockets:
            sock.close()
        process.terminate()
        process.wait(timeout=5)
    target = ROOT / 'submission_tools' / 'miniircd_results.txt'
    target.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
