# Operating and submitting the project

The server listens on IPv6 `::` port `6667`. The supplied Ubuntu VM uses `fc00:1337::17/96`; the Windows bot VM uses `fc00:1337::19/96`.

The bot accepts `--host`, `--port`, `--name`, and `--channel`. It joins the configured channel after receiving IRC welcome `001` and responds to `!hello`, `!slap`, `!time`, and private messages.

Use HexChat for manual verification. Keep the server console open so malformed commands, disconnects, and concurrent clients can be observed.

