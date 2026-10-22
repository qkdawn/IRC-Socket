# Implemented IRC subset

The implementation follows the client/server message format from RFC 2812 for this supported command set:

`NICK`, `USER`, `JOIN`, `PART`, `PRIVMSG`, `NAMES`, `QUIT`, `PING`, `PONG`, `TIME`, `ISON`, `LIST`, and `LUSERS`.

Local registration policy limits USER usernames to 1-30 printable ASCII characters,
excluding spaces, `!`, `@`, and `:`. Invalid usernames receive `461 USER` and may
be retried on the same connection. A NICK reserves the nickname immediately, but
private-message delivery and ISON visibility require completed NICK/USER registration.
The server requires registration within 30 seconds of connection creation,
using a monotonic timestamp independent of activity. PING, PONG and nickname
changes do not extend this deadline. Its one-second monitor closes expired
unregistered connections and releases their reserved nicknames at the next check.
Completed registrations continue to use the normal idle/PONG deadlines.

ISON returns one `303` reply per request, with unique online nicknames in their
registered spelling. The complete reply, including prefix and CRLF, must fit
within 512 bytes. If the requested online names cannot fit, the server sends one
`417 ISON` error instead of a partial presence list; clients should retry with a
smaller batch. This is a local error extension and retains one response per
request. The Bot recognizes `263`, `417`, `421` and `461` for ISON, discards
partial results from failed queries, and drains outstanding batches before
allowing another query. A `263 ISON` rejection completes that batch as a failure
instead of waiting for a query timeout and reconnecting.

LIST returns a sorted snapshot of channel names and member counts in `322`
replies, followed by `323`, including when no channels match. An optional
comma-separated channel filter is case-insensitive. LUSERS returns `251` with
the number of registered clients, zero services and one server. Both commands
require completed registration. Channel modes, secret channels and multiple
linked servers remain outside this server's supported subset.

The Bot maps `!channels` to LIST and `!network` to LUSERS, keeping separate
pending destinations and monotonic deadlines. It retains at most 10 LIST
entries, counts all valid entries, and emits the result only after `323`.
Registration-time or unsolicited `251` replies do not trigger a channel reply.
Numerics `263`, `421` and `461` terminate the corresponding query with a clear
unavailable message. Replies for other recipients are ignored. A query with no
complete reply within 30 seconds reconnects and discards partial results, so
late replies from the previous connection cannot complete a new query.

Server names are limited to 1-63 printable ASCII characters without spaces or
colons. PONG echoes the complete PING token; optional routing fields are omitted
when needed to keep a maximum-length reply within 512 bytes.
Commands contain ASCII letters or three numeric digits. Embedded CR, LF and NUL
are rejected; whitespace in a trailing parameter survives serialization unchanged.

The Bot allows 30 seconds after connection for registration (`001`). Once
registered, it sends PING after 30 seconds without a complete incoming message.
A matching PONG must arrive within another 30 seconds. Registration or PONG
timeouts close the socket and trigger reconnection after the configured delay
(3 seconds by default). Unrelated traffic does not extend either deadline.
The server uses the same 30-second idle and 30-second PONG deadlines and only
accepts a matching PONG. Its PONG deadline begins when the client's writer
starts sending the probe; waiting in the output queue does not consume that
deadline or generate duplicate probes. Each client has an independent output
queue capped at 256 pending messages. Queue overflow or a socket write failure
(including the one-second socket timeout) disconnects that client and releases
its routes, allowing other clients to continue receiving messages.
The Bot budgets ISON batches for both request and reply
lengths. ISON errors produce an unavailable result after all batches finish;
missing replies trigger reconnection after 30 seconds to discard stale replies.
Invalid Bot nicknames use `SuperBot`; invalid channel settings fail before connection.

The Bot starts a NAMES snapshot and 30-second deadline before sending its JOIN.
Membership-dependent `!slap` and `!who` commands wait in a bounded queue until
`366` commits the snapshot and its interleaved membership events. The queue
holds at most 100 commands; further requests receive a retry response. Missing
`366` triggers reconnection and discards queued requests from that connection.

The server emits registration numerics `001`-`004`, LUSERS numeric `251`, ISON numeric `303`, LIST numerics `322` and `323`, names numerics `353` and `366`, time numeric `391`, and errors `401`, `403`, `404`, `412`, `417`, `421`, `431`, `432`, `433`, `442`, `451`, `461`, and `462` where applicable. TLS, server-to-server links, modes, permissions, and advanced channel management are not currently implemented.

In code, `IRCMessage.params` stores decoded logical values without the wire-level
trailing-field delimiter. For example, `:hello` on the wire is stored as `hello`,
while a real value beginning with a colon is stored as `:hello` and serialized as
`::hello`. Callers should pass logical values and never add the delimiter manually.
