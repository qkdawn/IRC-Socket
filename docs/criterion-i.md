# Criterion I: extra Bot features

The supplied `4. Marking Criteria.pdf`, item I (3 marks), describes the highest
level as "Uses many IRC commands not used in previous items or different
purpose" and specifies testing on miniircd.

| Channel command | IRC exchange | Purpose |
|---|---|---|
| `!who` | `ISON` -> `303` | Confirm the online presence of known channel members. |
| `!channels` | `LIST` -> `322` entries, `323` completion | Discover server channels and their user counts, including channels outside the Bot's roster. |
| `!network` | `LUSERS` -> `251` | Report network-wide users, services and servers, including users outside the configured channel. |

These three requests are separate IRC commands with different purposes. The
existing `!time` reads the local clock and is not counted in this evidence.

## Protocol and processing

RFC 2812 sections 3.2.6 (LIST), 3.4.2 (LUSERS) and 4.9 (ISON) define the
requests. Section 5.1 defines `251`, `303`, `322` and `323` replies.

`bot/commands.py` maps channel input to pure command actions. `bot/queries.py`
generates the IRC requests and processes numeric replies; `bot/client.py`
supplies the context and time, sends messages and reconnects on timeout. The
pending-query map stores a response channel and monotonic start time for each LIST/LUSERS
request. One request of each type may be outstanding; repeated requests report
that the query is busy. Unsupported/throttled requests receive an unavailable
response. Missing completion after 30 seconds causes reconnection and clears
all partial results.

LIST entries are accumulated until `323`; at most 10 are stored and displayed,
with the total valid entries reported separately. LUSERS forwards the server's
`251` summary rather than inventing a count from the Bot's channel roster.
Unsolicited registration statistics and replies for another nickname do not
trigger channel replies. Long text uses complete UTF-8 chunks with relay-prefix
space reserved. Neither command alters channel membership or server settings.

The project's server also implements LIST and LUSERS, with registration checks,
snapshots under the state lock, sorted LIST results and an end marker for an
empty list. LUSERS excludes incomplete registrations.

## Recorded miniircd evidence

Run from the project root:

```sh
python submission_tools/verify_miniircd.py
```

The script starts unmodified upstream miniircd on IPv6 `::1` and checks:

1. Alice and the Bot share `#hello`; `!who` reports 2 known online members.
2. Alice also joins `#discovery`, which the Bot has not joined. `!channels`
   reports both channels and terminates with a 2-channel summary.
3. Another registered client remains outside both channels. `!network` reports
   3 users, demonstrating a network-wide count distinct from the roster of 2.
4. Existing greetings, local time, slap behavior, private facts, registration
   collision recovery and PING handling continue to work.

Actual results and the upstream source SHA256 are recorded in
`submission_tools/miniircd_results.txt`. Evidence and documentation are retained
locally, separate from the code-only submission ZIP.
The tests in `tests/test_extra_features.py` exercise failure paths and limits;
`tests/test_integration.py` runs the commands against the project server over
real IPv6 sockets. VM/HexChat acceptance belongs to the other testers.

`tests/test_bot_queries.py` also drives requests, replies, explicit deadlines
and reconnect resets directly against the query component without a client.

This provides implementation and miniircd evidence for the highest description
of item I. The assessor determines the awarded marks.
