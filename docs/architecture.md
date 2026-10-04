# Architecture

`common` contains only protocol concerns: `IRCMessage` models one IRC message and `IRCStreamDecoder` handles TCP fragmentation, coalescing, UTF-8 and CRLF framing.

`server` separates the accept loop (`server.py`), one connection (`client_session.py`), shared state (`state.py`), and command behavior (`handlers.py`). All mutable indexes are protected by `IRCState.lock`. Socket writes go through `ClientSession.send`, which serializes concurrent writers.

`bot` has a transport client, a small channel membership model, and pure command decisions. This keeps `!slap` selection and private fact replies testable without a socket.

