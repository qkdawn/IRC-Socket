# Coursework IRC Socket Project

IPv6 IRC server and bot. Requires Python 3.10 or later; no third-party packages.

## Quick start

Run commands from the directory containing `bot/`, `server/`, and `common/`.

Run the server on Ubuntu:

```bash
python3 -m server --host :: --port 6667
```

Run the bot on the Windows VM:

```powershell
py -3 -m bot --host fc00:1337::17 --port 6667 --name SuperBot --channel '#hello'
```

Configure the VM IPv6 addresses and allow TCP port 6667 through the firewall.
Stop either program with Ctrl+C.
