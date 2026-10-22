# Operating the IRC system

The server listens on IPv6 `::` port `6667`. The supplied Ubuntu VM uses `fc00:1337::17/96`; the Windows bot VM uses `fc00:1337::19/96`.

The bot accepts `--host`, `--port`, `--name`, and `--channel`. It joins the configured channel after receiving IRC welcome `001` and responds to `!hello`, `!slap`, `!time`, `!who`, `!channels`, `!network`, and private messages. `!time` returns the Bot machine's local clock with UTC offset. `!who` uses IRC `ISON` and numeric `303` to check which known channel members are online.

`!channels` sends `LIST` and processes `322`/`323` to discover server channels,
including channels the Bot has not joined, with user counts. It displays up to
10 entries and the total returned. `!network` sends `LUSERS` and relays the
server's `251` network-wide user/service/server statistics. These queries do
not depend on the Bot's channel membership snapshot. One request per command
can be pending; repeated requests get a retry response. Unsupported or throttled
queries produce an unavailable response, and incomplete queries reconnect after
30 seconds. See [criterion I evidence](criterion-i.md) for the protocol mapping.

`!slap` rejects explicit self/Bot targets. Without a target it excludes the sender and Bot, reporting no eligible member if necessary. An absent named target falls back to the sender, as specified by the command behavior.

While the initial channel roster is loading, the Bot defers `!slap` and `!who`
until the NAMES `366` reply, then executes them automatically. It queues at most
100 commands and reports a full queue to additional callers. A missing roster
completion triggers reconnection after 30 seconds; stale queued commands are
discarded on reconnection. Greetings, private facts and PING/PONG remain available.

Facts come from non-empty UTF-8 lines in `bot/data/facts.txt`. Lines containing
NUL are skipped; an empty or unreadable file uses a fallback fact. Long facts
are sent as consecutive private messages with at most 256 UTF-8 payload bytes
each, preserving complete characters and the full fact text.

The server sends PING after 30 seconds without a received command. If a matching PONG does not arrive within another 30 seconds, it disconnects the client. Other commands do not extend that deadline. It checks once per second.

Use HexChat for manual verification. Keep the server console open so malformed commands, disconnects, and concurrent clients can be observed.
