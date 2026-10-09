# Operating and submitting the project

The server listens on IPv6 `::` port `6667`. The supplied Ubuntu VM uses `fc00:1337::17/96`; the Windows bot VM uses `fc00:1337::19/96`.

The bot accepts `--host`, `--port`, `--name`, and `--channel`. It joins the configured channel after receiving IRC welcome `001` and responds to `!hello`, `!slap`, `!time`, `!who`, and private messages. `!time` returns the Bot machine's local clock with UTC offset. `!who` uses IRC `ISON` and numeric `303` to check known channel members online; this supplies the required new IRC command for the extra feature.

`!slap` rejects explicit self/Bot targets. Without a target it excludes the sender and Bot, reporting no eligible member if necessary. An absent named target falls back to the sender, as required by the project brief.

The server probes idle clients with PING at 30 seconds and removes clients with no command/PONG for more than 60 seconds. It checks once per second.

Use HexChat for manual verification. Keep the server console open so malformed commands, disconnects, and concurrent clients can be observed.
