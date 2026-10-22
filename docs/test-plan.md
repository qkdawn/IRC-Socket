# Test plan

1. Run `python -m unittest discover -v` and retain the output for the self-assessment.
2. On Ubuntu, run the server bound to `::` and port `6667`.
3. Connect two HexChat clients over IPv6. Register distinct nicknames, join `#hello`, exchange channel messages, use `/msg` for private messages, use `/names`, `/part`, and disconnect.
4. Run the Windows bot with all four command-line options. Verify `!hello`, both forms of `!slap`, `!who`, `!channels`, `!network`, private facts, join membership and PING/PONG. Repeat the three extra-feature commands against miniircd as described in `criterion-i.md`.
5. Repeat with a malformed command, duplicate nickname, unknown user, empty channel target and an idle client. Confirm the server remains running and returns a numeric error or removes the dead client.

## Regression coverage

The automated suite includes maximum-length PING/ISON requests, complete-or-error
ISON overflow handling (with smaller-batch recovery), USER rejection and retry,
registration-only private-message routing, disconnects during a
multi-channel JOIN, Bot registration and liveness deadlines, ISON batch errors
and timeouts, NAMES event ordering, empty facts files, and whitespace-preserving
message round trips. Startup failures, stopping during Bot socket creation, and
failed live-validation registration also verify socket cleanup. Tests run a real
Bot and multiple clients over IPv6 loopback. These checks complement validation
on the target VM network.
Shutdown regression tests also cover late session admission, calls to start a
stopped server, and thread-start failure cleanup.
CLI tests verify invalid ports fail before networking; the server may bind port
0 for automated tests, while the Bot requires a nonzero destination port.
Failure-propagation tests cover 400 same-channel send failures without recursion,
socket closure before peer notification, and continued delivery to healthy users
with one QUIT notification per departure across shared channels.
Concurrent delivery tests pause JOIN delivery, disconnect its sender, then verify
JOIN-before-QUIT ordering and identical final server/Bot membership. Another test
fails the JOIN sender's socket before delivering to a healthy peer. ISON throttle
tests verify both one- and multiple-batch failures, drained replies, no spurious
query timeout and successful retry.
Nickname/disconnect regression tests pause nickname mutation while another
thread disconnects the client, then verify NICK-before-QUIT and the Bot's final
roster. Delivery tests block one writer and verify another client's broadcast
and PONG delivery, isolated cleanup after the 256-message queue fills, and
idle-writer shutdown. Controlled-clock tests verify that queued PINGs do not
start deadlines or duplicate probes, and that immediate PONGs clear the probe.
Bot readiness regressions cover membership commands before its own JOIN and
between NAMES chunks, automatic execution after 366, unrelated-channel replies,
queue saturation, the NAMES deadline, and stale-command removal on reconnect.
Fact-file tests cover NUL rejection, all-invalid fallback, and long ASCII/Unicode
facts split without text loss. Relay tests use maximum supported identity fields,
and real IPv6 integration reconstructs a long fact and verifies later commands.
Extra-feature tests cover LIST/LUSERS dispatch, completion markers, empty and
large channel lists, bounded result storage/output, interleaved queries,
unsolicited/misaddressed/malformed replies, unsupported/throttled commands,
duplicate requests, query deadlines, reconnect cleanup and Unicode reply
chunking. Server regressions cover registration gating, LIST filtering and
LUSERS counts that exclude incomplete registrations. Real IPv6 integration
verifies discovery of a channel the Bot has not joined and network-wide counts.
The query component is also tested directly without a socket or real clock,
including response generation, failure-batch draining, deadlines and resets.
State API tests verify detached snapshots, case-insensitive filtering and
registered counts across disconnects. A handler test supplies only state
operations, with no storage containers or lock, to verify that boundary.
Server registration-deadline tests cover silent, NICK-only and USER-only clients,
PING/PONG and nickname changes that cannot extend the deadline, and registration
completed just before expiry. An IPv6 socket test verifies closure and nickname
reuse; a controlled clock verifies cleanup through 300 seconds.

Run `python submission_tools/verify_miniircd.py` for a local check against
unmodified upstream miniircd. It records the upstream checksum and actual
ISON/LIST/LUSERS results in `submission_tools/miniircd_results.txt`. Final VM
and HexChat acceptance is assigned to the other testers.

## Live IPv6 validation helper

After the Ubuntu server is running on `fc00:1337::17`, run this from the project root on the Windows VM:

```powershell
python scripts/live_validate.py --host fc00:1337::17 --port 6667
```

The helper checks registration, `JOIN`, channel `PRIVMSG`, private `PRIVMSG`, and the `401` unknown-target error. A successful run prints one `PASS` line for each check. It does not replace the HexChat and Bot checks above.

## Linux CPU measurement helper

With Python and sysstat (`pidstat`) installed on Linux, run:

```sh
python /path/to/NetworkProject1/scripts/cpu_validate.py --output /path/to/new-evidence
```

The helper starts the server, Bot and two IPv6 loopback clients and checks paced
traffic for 60 rounds while collecting 60 CPU samples per process. It records
the actual environment and source hashes in `summary.json`, and returns a
nonzero exit code for a failed run. An optional `--source-archive` records an
archive checksum. Use a new output directory for each run to preserve previous
evidence. Linux measurements do not establish the Windows Bot CPU criterion.
