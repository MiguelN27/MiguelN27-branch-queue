import unittest
from datetime import datetime

from branch_queue import SERVICE_TYPES, BranchQueue, EmptyQueueError, Ticket


class IssueTicketTests(unittest.TestCase):
    def setUp(self):
        self.branch = BranchQueue()

    def test_returns_ticket_with_client_details(self):
        before = datetime.now()
        ticket = self.branch.issue_ticket("Ana Pérez", "deposit")
        after = datetime.now()

        self.assertIsInstance(ticket, Ticket)
        self.assertEqual(ticket.number, 1)
        self.assertEqual(ticket.client_name, "Ana Pérez")
        self.assertEqual(ticket.service_type, "deposit")
        self.assertTrue(before <= ticket.issued_at <= after)

    def test_ticket_joins_its_own_service_queue(self):
        ticket = self.branch.issue_ticket("Luis", "withdrawal")

        waiting = self.branch.list_waiting()
        self.assertEqual(waiting["withdrawal"], [ticket])
        self.assertEqual(waiting["deposit"], [])
        self.assertEqual(waiting["account_management"], [])

    def test_strips_surrounding_whitespace_from_name(self):
        ticket = self.branch.issue_ticket("  Marta  ", "account_management")
        self.assertEqual(ticket.client_name, "Marta")


class CallNextTests(unittest.TestCase):
    def setUp(self):
        self.branch = BranchQueue()

    def test_returns_and_removes_longest_waiting_client(self):
        first = self.branch.issue_ticket("Ana", "deposit")
        second = self.branch.issue_ticket("Luis", "deposit")

        self.assertEqual(self.branch.call_next("deposit"), first)
        self.assertEqual(self.branch.list_waiting()["deposit"], [second])

    def test_only_calls_from_the_requested_service(self):
        withdrawal = self.branch.issue_ticket("Ana", "withdrawal")
        deposit = self.branch.issue_ticket("Luis", "deposit")

        self.assertEqual(self.branch.call_next("deposit"), deposit)
        self.assertEqual(self.branch.list_waiting()["withdrawal"], [withdrawal])

    def test_raises_empty_queue_error_when_nobody_waiting(self):
        with self.assertRaises(EmptyQueueError):
            self.branch.call_next("deposit")


class PeekNextTests(unittest.TestCase):
    def setUp(self):
        self.branch = BranchQueue()

    def test_returns_next_client_without_removing(self):
        first = self.branch.issue_ticket("Ana", "deposit")
        self.branch.issue_ticket("Luis", "deposit")

        self.assertEqual(self.branch.peek_next("deposit"), first)
        self.assertEqual(self.branch.peek_next("deposit"), first)
        self.assertEqual(self.branch.stats()["deposit"], 2)

    def test_returns_none_when_nobody_waiting(self):
        self.assertIsNone(self.branch.peek_next("withdrawal"))


class ListWaitingTests(unittest.TestCase):
    def test_groups_tickets_by_service_in_call_order(self):
        branch = BranchQueue()
        a = branch.issue_ticket("Ana", "deposit")
        b = branch.issue_ticket("Luis", "withdrawal")
        c = branch.issue_ticket("Marta", "deposit")
        d = branch.issue_ticket("Jorge", "account_management")

        self.assertEqual(
            branch.list_waiting(),
            {
                "deposit": [a, c],
                "withdrawal": [b],
                "account_management": [d],
            },
        )

    def test_includes_every_service_when_empty(self):
        self.assertEqual(
            BranchQueue().list_waiting(),
            {service: [] for service in SERVICE_TYPES},
        )


class StatsTests(unittest.TestCase):
    def test_counts_per_service_and_total(self):
        branch = BranchQueue()
        branch.issue_ticket("Ana", "deposit")
        branch.issue_ticket("Luis", "deposit")
        branch.issue_ticket("Marta", "withdrawal")

        self.assertEqual(
            branch.stats(),
            {"deposit": 2, "withdrawal": 1, "account_management": 0, "total": 3},
        )

    def test_counts_drop_after_call_next(self):
        branch = BranchQueue()
        branch.issue_ticket("Ana", "deposit")
        branch.call_next("deposit")

        self.assertEqual(branch.stats()["deposit"], 0)
        self.assertEqual(branch.stats()["total"], 0)


if __name__ == "__main__":
    unittest.main()
