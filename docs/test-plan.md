# Test plan

1. Run `python -m unittest discover -v` and retain the output for the self-assessment.
2. On Ubuntu, run the server bound to `::` and port `6667`.
3. Connect two HexChat clients over IPv6. Register distinct nicknames, join `#hello`, exchange channel messages, use `/msg` for private messages, use `/names`, `/part`, and disconnect.
4. Run the Windows bot with all four command-line options. Verify `!hello`, both forms of `!slap`, `!time`, private facts, join membership and PING/PONG.
5. Repeat with a malformed command, duplicate nickname, unknown user, empty channel target and an idle client. Confirm the server remains running and returns a numeric error or removes the dead client.

## Live IPv6 validation helper

After the Ubuntu server is running on `fc00:1337::17`, run this from the project root on the Windows VM:

```powershell
python scripts/live_validate.py --host fc00:1337::17 --port 6667
```

The helper checks registration, `JOIN`, channel `PRIVMSG`, private `PRIVMSG`, and the `401` unknown-target error. A successful run prints one `PASS` line for each check. It does not replace the HexChat and Bot checks above.
