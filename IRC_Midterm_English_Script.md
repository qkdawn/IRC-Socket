# IRC Socket Programming Midterm Presentation Script

## Slide 1 | Project scope and completion status | 0:00-0:20

Good morning, and thank you for having us. Our project implements a lightweight IPv6 IRC server and a command Bot using Python sockets. In this midterm review, we will explain how the implementation meets the coursework requirements and what behavior has been completed.

## Slide 2 | Project scope and code structure | 0:20-1:00

The implementation is divided into three modules. The `common` module contains the IRC message model and the TCP stream decoder. The `server` module accepts IPv6 clients, manages sessions, stores shared user and channel state, and routes messages. The `bot` module connects as an IRC client, tracks channel members, and makes command decisions.

This separation keeps protocol parsing, server behavior, and Bot behavior independent and maintainable. Each module can be developed and understood separately while still working together as one IRC system.

## Slide 3 | Protocol foundation | 0:55-1:40

The first implementation problem is that TCP does not preserve application message boundaries. One read may contain only part of an IRC message, or several messages together.

Our `IRCMessage` class stores the command, prefix, and logical parameters. For example, it parses `PRIVMSG #hello :Hi Bob` into a target and a message body. The `IRCStreamDecoder` buffers incomplete data until it receives a complete CRLF line, and it can decode several messages from one read.

Before a message reaches the server state, the decoder also checks UTF-8 validity and the IRC 512-byte limit. This gives the rest of the system a consistent message format and prevents malformed input from being processed as normal state.

## Slide 4 | Bot functionality | 1:40-2:35

The Bot first opens an AF_INET6 TCP connection, sends `NICK` and `USER`, waits for the `001` welcome response, and then joins the configured channel.

While it is connected, the Bot answers `PING` with `PONG` and reconnects after a connection failure. It builds its member list from `NAMES` replies and updates that list when users JOIN, PART, QUIT, or change their nickname.

The Bot also provides the required user-facing features. It responds to `!hello`, handles `!slap` with and without a target, and provides `!who` to check known channel members online using IRC ISON. When a user sends a private message to the Bot, it returns a fact from `facts.txt`.

This implements the required Bot connection, tracking, command, and private-message behavior in the required IPv6 environment.

## Slide 5 | IRC server core behavior | 2:35-3:50

The server creates an independent session for each client. It maintains shared nickname and channel indexes in `IRCState`, and protects those indexes when several clients operate at the same time.

The server handles registration and supports JOIN, PART, NAMES, QUIT, channel messages, and private messages. A channel message is sent only to users in that channel. A private message is sent only to the named user. When a client leaves or disconnects, the server removes its nickname and channel membership so that later clients see the correct state.

This is also where the implementation supports the multiple-client requirements. Two clients can join the same channel and exchange messages, while private messages remain separate from channel traffic.

## Slide 6 | Errors and reliability | 3:50-5:00

The final area is error handling and reliability. The server returns numeric errors for missing parameters, invalid channels, duplicate nicknames, unknown targets, and malformed commands.

It also checks the actual UTF-8 byte length of a relayed `PRIVMSG`. If adding the sender prefix would make the line longer than the IRC limit, the server returns error `417` instead of sending an invalid message.

Disconnect cleanup, nickname reuse, and PING timeout handling keep the shared state correct. Malformed input remains isolated to one client session and does not stop the entire server.

That completes our midterm progress review. The core implementation and the main coursework requirements are complete, and the remaining work is to organize the project materials and finalize the submission. Thank you.
