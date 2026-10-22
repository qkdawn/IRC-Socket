# IPv6 IRC Server and Bot

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

## Extra Bot commands

Send these in the configured channel:

| Command | IRC request | Purpose |
|---|---|---|
| `!who` | `ISON` | Confirm known channel members are online. |
| `!channels` | `LIST` | Discover server channels and their user counts, including channels the Bot has not joined. |
| `!network` | `LUSERS` | Report the server's network-wide user/service/server statistics. |

`!channels` displays at most 10 channels and reports the total returned by the
server. Both new commands reject extra arguments, report unsupported commands,
and reconnect after 30 seconds without a complete reply. `!time` continues to
report the Bot's local clock.

## Code organization

- `common/`: IRC messages, framing and protocol validation; no socket operations.
- `bot/client.py`: connection lifecycle and event coordination; `bot/queries.py`
  owns ISON/LIST/LUSERS state and generates requests/replies without sockets.
- `bot/commands.py` and `bot/state.py`: command decisions and channel membership.
- `server/`: listener, sessions, locked state and command handlers in separate
  modules; `interfaces.py` defines delivery and handler contracts. Handlers use
  state operations instead of reading the nickname/client/channel containers.

## Code-only package

Run `python scripts/package_code.py` to rebuild
`submission/group_04_midproject.zip`. It contains only `bot/`, `common/`,
`server/` Python sources and the Bot's `bot/data/facts.txt`. Extract it and run
the commands above from the folder containing those packages. Documentation,
assessment forms, logs, tests and caches remain outside this ZIP.
