# Rubric mapping and completion status

The table separates implemented evidence from the VM/HexChat evidence still required for a full mark. A code module being present does not by itself prove the live-network criterion.

| Item | Marks | Implemented evidence | Current status / evidence still needed |
|---|---:|---|---|
| C - IRC protocol data model | 7 | `common/irc_message.py`, `common/stream.py`, `common/numerics.py`, `server/state.py` | Code covered; verify malformed, split, coalesced and long lines against HexChat traffic. |
| D - Documentation/readability | 7 | Type hints, focused comments, module docstrings, tests and `docs/` | Code covered; keep comments focused on protocol/network reasons and record team contributions. |
| E - Bot connection | 7 | `bot/client.py` IPv6 socket, registration, reconnect, PING/PONG and error recovery | Run on Windows VM against Ubuntu IPv6 address; observe low CPU and reconnect after server restart. |
| F - Bot channel/user tracking | 4 | `bot/state.py`, NAMES/JOIN/PART/QUIT/NICK handlers | Verify with HexChat users joining, leaving, renaming and reconnecting. |
| G - Bot private replies | 5 | `facts.txt`, private `PRIVMSG` routing and random reply | Verify HexChat private-message tab and repeat messages for varied facts. |
| H - Bot channel commands | 5 | `!hello`, `!slap`, optional target and exclusion rules | Verify no-argument, valid target, absent target, sole-user and multi-user cases in HexChat. |
| I - Extra Bot feature | 3 | `!who` uses new IRC `ISON` and numeric `303` | Tested against upstream miniircd over IPv6 loopback; group confirms prior VM/HexChat validation. |
| J - Multiple IRC clients | 9 | IPv6 accept loop, per-client sessions, registration and locked shared state | Verify several HexChat clients concurrently and confirm CPU remains below the rubric expectation. |
| K - Errors/unusual conditions | 9 | Numeric errors, malformed-line handling, unknown commands, disconnect cleanup, PING timeout | Verify duplicate nick, missing parameters, unknown target/command, malformed input and idle client. |
| L - Private user messaging | 7 | Direct nickname lookup and one-recipient `PRIVMSG` routing | Verify sender/receiver tabs and that unrelated channel users receive nothing. |
| M - Join/leave channels | 10 | JOIN/PART/NAMES, channel membership indexes and QUIT cleanup | Verify existing roster, new-user notification, `/names`, `/part`, quit and empty-channel cleanup. |
| N - Channel messaging | 10 | Channel membership validation and broadcast to same-channel peers | Verify multi-channel isolation and that users outside the channel receive nothing. |

## Not yet proven by local tests

The local automated suite proves protocol logic and an IPv6 `::1` integration path. It does not replace final testing on the supplied Windows and Ubuntu VMs with HexChat. The final self-assessment should only claim the higher rubric level after those live tests are recorded.
