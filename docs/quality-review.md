# Quality review, 22 October 2026

The review used the review, health and ai-slop-cleaner workflows to examine the
protocol boundaries, connection lifecycle, concurrent state, Bot membership
updates, error handling, documentation wording and packaged runtime sources.

## Corrected defects

- ISON replies include the complete byte budget and omit whole nicknames when
  the response would exceed 512 bytes. Bot requests budget both directions.
- USER registration rejects unsafe usernames and usernames over 30 ASCII
  characters, allowing a valid retry on the same connection.
- Private routing and ISON visibility require completed registration.
- Bot registration, PONG and ISON queries have monotonic deadlines. Reconnection
  discards late ISON responses; failed batches are drained before a new query.
- Maximum-length PING tokens are preserved in bounded PONG replies.
- Disconnected clients cannot restore nickname or channel indexes. Heartbeat
  decisions and PONG updates use the shared state lock.
- NAMES snapshots retain interleaved membership events. Serialization preserves
  trailing whitespace and rejects embedded CR, LF and NUL.
- Invalid configuration fails before networking; empty or unreadable facts files
  use a fallback reply.
- Bot exits always close their socket. Server listener setup failures and failed
  validation connections close their sockets. Normal Bot shutdown does not log
  a spurious connection warning.
- The CPU validation helper resolves sources from its script location, performs
  no output writes at import, records the actual platform and source hashes,
  and reports unsupported platforms as failed measurements. It parses pidstat
  columns by header and PID, serializes client writes, and closes clients whose
  initialization fails.
- Server shutdown and session admission share a lock. Stopped servers cannot
  create a new listener or admit a late accepted socket; thread-start failures
  close the socket and remove the session state.
- Document-generator text matches the no-eligible-member slap behavior and labels
  earlier CPU values as historical instead of evidence for modified sources.
- Invalid server/Bot ports are rejected before socket creation with a command-line
  usage error instead of an OverflowError traceback. The server retains port 0
  for ephemeral listeners; the Bot requires a destination port from 1 to 65535.
- Disconnects remove routes and close sockets before peer notifications. Send
  failures queue further QUIT messages instead of recursing through failed peers;
  a 400-client failure regression verifies cleanup without stack overflow and a
  separate regression verifies healthy delivery and one QUIT per departure.
- Commands received before the initial roster completes no longer treat missing
  snapshot entries as absent users. The Bot defers membership-dependent commands
  until 366, preserves events before its own JOIN, bounds the deferred queue at
  100 requests, and reconnects after 30 seconds without roster completion.
- Long facts are sent in complete UTF-8 chunks with space reserved for relay
  prefixes, so local file content cannot produce an oversized outgoing reply.
  NUL-containing lines are skipped; an all-invalid file uses the fallback fact.
  Relay and real IPv6 tests verify that long Unicode content is preserved and
  the Bot continues answering commands afterwards.
- Criterion I now has three extra IRC queries with different purposes: ISON
  for presence, LIST for channel discovery, and LUSERS for network statistics.
  LIST results have bounded storage/output, independent query deadlines and
  clear errors; reconnection clears partial results. Both the project server
  and unmodified upstream miniircd pass the new feature checks. The latter
  discovers a channel outside the Bot's roster and counts an off-channel user.
  See `docs/criterion-i.md` for the rubric wording and protocol mapping.
- The cohesion refactor moves query batching, pending state, numeric replies
  and deadlines into `bot/queries.py`, with explicit time inputs and generated
  message outputs. The client retains connection and event coordination.
  Server handlers use state snapshot/count/PONG operations without accessing
  live containers or locks. Structural delivery/handler contracts replace the
  untyped connection and implicit handler dependency. See `docs/architecture.md`.

## Verification

- Windows `python -m pytest -q`: 135 tests and 75 subtests passed.
- Windows `python -m unittest discover -q`: 135 tests passed.
- Before the criterion I extension, Ubuntu WSL2 `python3 -m unittest discover`
  passed the then-current 106 tests; it has not been rerun for this extension.
- `ruff check .` and `git diff --check`: passed.
- Upstream miniircd over IPv6 loopback: registration, nickname collision,
  channel commands, private facts and PING handling passed. Source checksum and
  responses are recorded in `submission_tools/miniircd_results.txt`.
- The 22 runtime source/data files match between the project, submission
  directory and ZIP; the ZIP passes its CRC check.
- The submission ZIP contains only the three runtime packages at its root:
  21 Python files and `bot/data/facts.txt`. Documents, assessment forms,
  verification logs, README files, tests and caches are excluded. Rebuild with
  `python scripts/package_code.py`; original local documents remain available.
- Runtime source and editable presentation/Word text were checked for obsolete
  branding. Official assessment forms retain their original terminology.
- 19 query scenarios matched the previous submission runtime byte-for-byte,
  including batching, interleaved results, errors, bounded lists and deadlines.
  Direct component tests also verify that queries need no client or real clock.
- Protocol annotations have been added; no standalone mypy/pyright checker was
  installed, so no complete static type-check result is claimed.
- Before the criterion I extension, a bounded matrix of 1,020 valid serialized
  command/parameter combinations produced no unexpected handler exceptions.
  This is not exhaustive fuzzing or evidence for the new command handlers.
- Before the criterion I extension, Ubuntu WSL2 / Python 3.12.3: 60 paced IPv6 loopback traffic rounds and 60
  pidstat samples per process passed. Server average CPU was 0.3333%, Bot average
  0.1333%; both peaked at 2%. These are historical measurements, not CPU
  evidence for the modified source files. Raw samples and summary remain under
  `.codex-output/quality-audit/cpu-wsl-fact-offset/`.

## Remaining Limits

The absent-target slap behavior follows the requirement to fall back to the
sender. This conflicts with the rubric's general sender-exclusion wording;
the behavior and exception remain explicit in the documentation.

Criterion I's additional-command and different-purpose implementation is now
covered by ISON, LIST and LUSERS, verified on miniircd over IPv6 loopback.
Awarded marks remain the assessor's decision. The local-clock `!time` command
does not send an additional IRC command and is not counted in that evidence.

Local IPv6 checks do not establish the final Windows/Ubuntu VM, HexChat or
Windows Bot CPU criteria. The user has assigned that acceptance testing to
other people; it is outside this code-review handoff.
The latest connection attempt from this host to `[fc00:1337::17]:6667` returned
Windows error 10051. The supplied endpoint is not reachable through the current
network path, so remote acceptance cannot be performed from this session yet.
The CPU helper requires Linux with sysstat/pidstat; its platform-failure test
on Windows is not a CPU measurement.
The automated checks and review do not establish that all possible defects
are absent. No GitHub publication is implied by this report.
