# Architecture

`common` contains only protocol concerns: `IRCMessage` models one IRC message and `IRCStreamDecoder` handles TCP fragmentation, coalescing, UTF-8 and CRLF framing.

`server` separates the accept loop (`server.py`), one connection (`client_session.py`), shared state (`state.py`), and command behavior (`handlers.py`). Mutable indexes are protected by `IRCState.lock`. `ClientSession.send` enqueues bounded output; a dedicated writer thread sends each client's messages in order.

`interfaces.py` defines structural `ClientConnection` and `HandlerServer`
contracts. `ClientState.connection` declares the send/close operations instead
of using `Any`; handlers depend on the server operations they actually use.
References needed only for annotations use `TYPE_CHECKING`, avoiding runtime
import cycles. The concrete server supplies the implementation without a new
base class or dependency-injection framework.

`IRCState.list_channels()` returns a sorted, detached channel-count snapshot;
`registered_user_count()` excludes incomplete registrations. Matching PONG
handling calls `acknowledge_ping()`. Command handlers do not access the live
client/channel/nickname containers or acquire their lock. Listener/session
admission, shutdown and heartbeat coordination still use the shared lock where
several lifecycle decisions must remain atomic.

Disconnect cleanup removes the client's routes and closes its socket before
notifying peers. Send failures queue further QUIT notifications for iterative
delivery, so a channel-wide connection failure cannot recurse through every
disconnected user. Healthy peers receive one notification per departure even
when they share multiple channels.
JOIN, NICK and PART state changes and their notifications enter each recipient's
queue under the same state lock used by disconnect cleanup and QUIT enqueueing.
Handlers use `IRCServer.join_channel()`, `set_nickname()` and `part_channel()`
to preserve this ordering. A subsequent QUIT follows the earlier JOIN or NICK,
and an old user's PART precedes a replacement user's JOIN even when the
nickname is reused, keeping the Bot's roster consistent with server state.
Each session holds at most 256 pending messages and writes outside the state
lock. A slow socket cannot stall another client's delivery. Queue overflow or
a socket write failure closes that session and removes its routes. LIST reply
production uses `send(..., wait_for_space=True)` outside the state lock: it
waits up to one second for each queue slot instead of treating a full reply
queue as an immediate connection failure. The writer signals available slots;
the condition wait releases the session lock, so close can wake the producer.
A queue that does not drain within that deadline closes the connection.
Close also wakes an idle writer and discards pending output. Server PING
deadlines start when the writer takes the probe, before socket I/O so a fast
PONG cannot race the timestamp. A queued probe suppresses duplicate probes
without starting a PONG timeout.

`bot` separates transport/event coordination (`client.py`), query workflows
(`queries.py`), channel membership (`state.py`) and command decisions
(`commands.py`). Command initialization reads the local facts file; command
decisions and query processing can be tested without a socket.

The command processor returns distinct actions for presence checks (`ISON`),
channel discovery (`LIST`) and network statistics (`LUSERS`). `BotQueries` owns
their batching, pending destinations, numeric replies, result limits and
deadlines. Its inputs are messages, context values and explicit monotonic time;
its output is a list of IRC messages, with `None` indicating an unrelated event.
It imports neither sockets nor the client, membership state or command processor.

`BotClient` supplies identity/membership snapshots, obtains time, transmits the
generated messages and handles reconnects. It resets the query component on a
new connection. Registration/keepalive, membership events and PRIVMSG dispatch
have separate methods. Text chunking remains at the delivery boundary so long
facts and network summaries share the same UTF-8-safe relay budget.

LIST and LUSERS track independent destinations and deadlines; LIST stores at
most 10 entries while counting the full result. The server releases its state
lock before sending any LIST reply. Runtime package dependencies remain
`bot -> common` and `server -> common`, with no Bot/Server cross-imports.

