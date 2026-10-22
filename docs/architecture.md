# Architecture

`common` contains only protocol concerns: `IRCMessage` models one IRC message and `IRCStreamDecoder` handles TCP fragmentation, coalescing, UTF-8 and CRLF framing.

`server` separates the accept loop (`server.py`), one connection (`client_session.py`), shared state (`state.py`), and command behavior (`handlers.py`). Mutable indexes are protected by `IRCState.locked()`. `ClientSession.send` enqueues bounded output; a dedicated writer thread sends each client's messages in order.

`interfaces.py` defines structural `ClientConnection` and `HandlerServer`
contracts. `ClientState.connection` declares the send/close operations instead
of using `Any`; handlers depend on the server operations they actually use.
References needed only for annotations use `TYPE_CHECKING`, avoiding runtime
import cycles. The concrete server supplies the implementation without a new
base class or dependency-injection framework. All handler client parameters use
`ClientState`; fixed client fields are accessed directly.

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
a socket write failure closes that session and removes its routes. LIST and
NAMES reply production uses the separate `send_reply()` interface outside the
state lock. It waits up to one second for each queue slot instead of treating a full reply
queue as an immediate connection failure. The writer signals available slots;
the condition wait releases the session lock, so close can wake the producer.
A queue that does not drain within that deadline closes the connection.
`send()` never waits for queue space. State transactions track nested ownership;
`send_reply()` raises before enqueueing if the calling thread holds the state
lock. Another thread holding the lock does not prevent reply production.
Close also wakes an idle writer and discards pending output. Server PING
deadlines start when the writer takes the probe, before socket I/O so a fast
PONG cannot race the timestamp. A queued probe suppresses duplicate probes
without starting a PONG timeout.
On malformed input, the session waits at most one second for the writer to
send ERROR before closing. A write failure or concurrent close wakes that
wait; a stalled peer still has a bounded cleanup path.

`bot` separates transport/event coordination (`client.py`), query workflows
(`queries.py`), channel membership (`state.py`) and command decisions
(`commands.py`). Command initialization reads the local facts file; command
decisions and query processing can be tested without a socket. Slap selection
has its own helper; extra-query errors, LIST accumulation and LIST completion
have separate methods so command routing stays short.

The command processor returns distinct actions for presence checks (`ISON`),
channel discovery (`LIST`) and network statistics (`LUSERS`). `BotQueries` owns
their batching, pending destinations, numeric replies, result limits and
deadlines. Its inputs are messages, context values and explicit monotonic time;
its output is a list of IRC messages, with `None` indicating an unrelated event.
It imports neither sockets nor the client, membership state or command processor.
An active ISON batch group is represented by one `_WhoQuery` object containing
its destination, start time, remaining batches, accumulated names and failure
status. No active query is represented by `None`. Completion, timeout and
reconnection discard the whole object, so a later request starts with fresh
results and a fresh deadline.

`BotClient` supplies identity/membership snapshots, obtains time, transmits the
generated messages and handles reconnects. It resets the query component on a
new connection. Registration/keepalive, membership events and PRIVMSG dispatch
have separate methods. Text chunking remains at the delivery boundary so long
facts and network summaries share the same UTF-8-safe relay budget.
PRIVMSG processing dispatches `CommandAction` values through one typed handler
table. Deferred commands, ISON requests and other queries have dedicated
execution methods; LIST and LUSERS share the same query executor with their
command bound in the table. Text replies continue through the normal send path.

LIST and LUSERS track independent destinations and deadlines; LIST stores at
most 10 entries while counting the full result. The server releases its state
lock before sending any LIST reply. Runtime package dependencies remain
`bot -> common` and `server -> common`, with no Bot/Server cross-imports.

