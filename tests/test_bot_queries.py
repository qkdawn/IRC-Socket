"""Query workflows can be driven with explicit messages and time values."""

import unittest

from bot.queries import BotQueries
from common.irc_message import message


class BotQueryTests(unittest.TestCase):
    def setUp(self):
        self.queries = BotQueries()

    def test_who_returns_requests_and_final_replies_without_a_client(self):
        requests = self.queries.start_who(
            "#room", {"alice", "bob"}, "SuperBot", "irc.local", 100
        )
        self.assertEqual(requests, [message("ISON", "alice", "bob")])
        replies = self.queries.handle(
            message("303", "SuperBot", "bob alice"), "SuperBot"
        )
        self.assertEqual(
            replies,
            [
                message("PRIVMSG", "#room", "WHO member: alice"),
                message("PRIVMSG", "#room", "WHO member: bob"),
                message("PRIVMSG", "#room", "WHO complete: 2 members"),
            ],
        )
        self.assertIsNone(
            self.queries.handle(message("303", "SuperBot", "stale"), "SuperBot")
        )

    def test_empty_roster_queries_own_nickname(self):
        self.assertEqual(
            self.queries.start_who("#room", set(), "SuperBot", "irc.local", 100),
            [message("ISON", "SuperBot")],
        )

    def test_query_deadline_is_driven_by_supplied_time(self):
        for query in ("ISON", "LIST", "LUSERS"):
            with self.subTest(query=query):
                if query == "ISON":
                    self.queries.start_who(
                        "#room", {"alice"}, "SuperBot", "irc.local", 100
                    )
                else:
                    self.queries.start(query, "#room", 100)
                self.queries.check_timeouts(129.999)
                with self.assertRaisesRegex(TimeoutError, query):
                    self.queries.check_timeouts(130)

    def test_reconnect_reset_discards_every_query_and_partial_result(self):
        self.queries.start_who("#room", {"alice"}, "SuperBot", "irc.local", 100)
        self.queries.start("LIST", "#room", 100)
        self.queries.start("LUSERS", "#room", 100)
        self.queries.handle(message("322", "SuperBot", "#stale", "1", ""), "SuperBot")
        self.queries.reset()
        self.queries.check_timeouts(1000)
        for reply in (
            message("303", "SuperBot", "alice"),
            message("323", "SuperBot", "End of LIST"),
            message("251", "SuperBot", "Old statistics"),
        ):
            self.assertFalse(self.queries.handle(reply, "SuperBot"))
        self.assertEqual(self.queries.start("LIST", "#new", 1000), [message("LIST")])
        self.assertEqual(
            self.queries.handle(message("323", "SuperBot", "End of LIST"), "SuperBot"),
            [message("PRIVMSG", "#new", "CHANNELS complete: 0 channels (showing 0)")],
        )

    def test_ison_failure_drains_batches_before_accepting_another_query(self):
        requests = self.queries.start_who(
            "#room",
            {f"member{index}" for index in range(30)},
            "SuperBot",
            "irc.local",
            100,
        )
        self.assertGreater(len(requests), 1)
        self.assertEqual(
            self.queries.handle(
                message("421", "SuperBot", "ISON", "Unknown command"), "SuperBot"
            ),
            [],
        )
        self.assertEqual(
            self.queries.start_who("#other", {"new"}, "SuperBot", "irc.local", 101),
            [],
        )
        replies = []
        for _ in requests[1:]:
            replies.extend(
                self.queries.handle(message("303", "SuperBot", "member0"), "SuperBot")
            )
        self.assertEqual(
            replies,
            [message("PRIVMSG", "#room", "WHO unavailable: server rejected ISON.")],
        )
        self.assertEqual(
            self.queries.start_who("#other", {"new"}, "SuperBot", "irc.local", 102),
            [message("ISON", "new")],
        )

    def test_non_query_events_remain_available_to_the_client(self):
        for event in (
            message("PING", "probe"),
            message("JOIN", "#room", prefix="alice!u@host"),
            message("PRIVMSG", "#room", "!hello", prefix="alice!u@host"),
        ):
            self.assertIsNone(self.queries.handle(event, "SuperBot"))

    def test_invalid_request_does_not_start_a_query(self):
        with self.assertRaisesRegex(ValueError, "LIST or LUSERS"):
            self.queries.start("PRIVMSG", "#room", 100)
        self.queries.check_timeouts(1000)
