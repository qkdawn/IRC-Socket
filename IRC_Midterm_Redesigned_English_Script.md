## Slide 1 (0:00–0:20)

Good morning. This is our midterm progress report for the socket programming coursework. We have implemented the shared IRC protocol layer, a command Bot, and a lightweight server using Python sockets. I will explain the required behavior and how our current code provides it.

## Slide 2 (0:20–0:40)

Our code has three parts. Common holds the IRC message model and stream decoder. Server handles client sessions, shared state, and message delivery. Bot handles the connection, channel members, and commands. We keep protocol parsing separate from socket operations, with focused functions and comments explaining the network behavior.

## Slide 3 (0:40–1:15)

IRC messages travel over a TCP byte stream. A single read can contain half a message or several messages together, so we cannot treat each read as one command. IRCStreamDecoder keeps incomplete data until a full CRLF line arrives. IRCMessage then separates the prefix, command, and parameters, as this example shows. We also check UTF-8 and the 512-byte line limit, including CRLF. The same message model generates replies, so both programs use a consistent format.

## Slide 4 (1:15–2:35)

The Bot runs in the Windows environment and connects over IPv6. Its host, port, nickname, and channel are configurable from the command line. It sends NICK and USER, waits for the 001 welcome, and then joins the channel. While connected, it answers PING with PONG. If the connection fails, it waits before reconnecting and rebuilds its member list.

For member tracking, the Bot collects the initial NAMES replies and updates the list when users join, leave, quit, or change nicknames.

The commands shown here are implemented. Hello greets the sender. Slap supports a named target or a random eligible member. Without a target, it excludes the Bot and requester when other users are available. A missing named target falls back to the requester. Who uses IRC ISON and numeric 303 to check known channel members online. Time reports the Bot machine's local clock. A private message gets a random fact loaded from facts.txt.

## Slide 5 (2:35–4:05)

The server runs on Ubuntu and listens on the IPv6 unspecified address, double colon, at port 6667. It accepts clients and gives each connection its own session. Registration stores the nickname, username, and real name, then sends the welcome replies.

Several clients can operate at once. The shared user and channel indexes use a lock, and each session serializes its outgoing socket writes.

There are two delivery paths. If Alice sends a message to hash hello, the server checks channel membership and forwards it to the other members of that channel. It does not forward it to users outside that channel. If Alice sends a private message to Bob, only Bob receives it. An unknown nickname gets an error response.

JOIN adds a member and supplies the current member list through NAMES. PART removes the user from that channel but keeps the connection active. QUIT or a lost connection removes the user from all channels and clears the nickname entry. Empty channels are removed as well. These are the current implementations of the client, channel, and messaging requirements.

## Slide 6 (4:05–5:00)

The final part is handling invalid requests and lost connections. Unknown commands, invalid or occupied nicknames, missing parameters, and unknown targets receive the appropriate numeric response.

Malformed byte streams follow a separate path: the server sends ERROR and closes the affected session. Other clients continue running. For a relayed message, the server checks the full UTF-8 length after adding the sender prefix. If it exceeds 512 bytes, the server returns 417.

Disconnect cleanup also checks which connection owns a nickname before deleting it. The server has a PING-based timeout mechanism, while the Bot can reconnect after a connection failure. This summarizes our implemented protocol, Bot, server, and error-handling functions at midterm. Thank you.