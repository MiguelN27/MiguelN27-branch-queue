import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest import mock

import main
from branch_queue import (
    SERVICE_TYPES,
    BranchQueue,
    EmptyQueueError,
    InvalidServiceTypeError,
    Ticket,
)


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

    def test_changing_returned_lists_does_not_change_the_queues(self):
        branch = BranchQueue()
        ticket = branch.issue_ticket("Ana", "deposit")

        waiting = branch.list_waiting()
        waiting["deposit"].clear()
        waiting["withdrawal"].append(ticket)

        self.assertEqual(branch.list_waiting()["deposit"], [ticket])
        self.assertEqual(branch.stats()["withdrawal"], 0)


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


class GlobalNumberingTests(unittest.TestCase):
    def test_numbers_are_sequential_and_unique_across_services(self):
        branch = BranchQueue()
        services = [
            "deposit", "withdrawal", "account_management",
            "withdrawal", "deposit", "deposit",
        ]

        numbers = [
            branch.issue_ticket(f"Client {i}", service).number
            for i, service in enumerate(services)
        ]

        self.assertEqual(numbers, [1, 2, 3, 4, 5, 6])

    def test_numbers_are_not_reused_after_clients_are_called(self):
        branch = BranchQueue()
        branch.issue_ticket("Ana", "deposit")
        branch.issue_ticket("Luis", "withdrawal")
        branch.call_next("deposit")
        branch.call_next("withdrawal")

        self.assertEqual(branch.issue_ticket("Marta", "deposit").number, 3)


class ArrivalOrderTests(unittest.TestCase):
    def test_each_queue_is_called_in_strict_arrival_order(self):
        branch = BranchQueue()
        services = [
            "withdrawal", "deposit", "deposit", "account_management",
            "withdrawal", "deposit", "withdrawal",
        ]
        issued = {service: [] for service in SERVICE_TYPES}
        for i, service in enumerate(services):
            issued[service].append(branch.issue_ticket(f"Client {i}", service))

        for service in SERVICE_TYPES:
            for expected in issued[service]:
                self.assertEqual(branch.peek_next(service), expected)
                self.assertEqual(branch.call_next(service), expected)

    def test_late_arrivals_join_behind_clients_already_waiting(self):
        branch = BranchQueue()
        ana = branch.issue_ticket("Ana", "deposit")
        luis = branch.issue_ticket("Luis", "deposit")
        self.assertEqual(branch.call_next("deposit"), ana)

        marta = branch.issue_ticket("Marta", "deposit")

        self.assertEqual(branch.call_next("deposit"), luis)
        self.assertEqual(branch.call_next("deposit"), marta)


class EmptyQueueTests(unittest.TestCase):
    def setUp(self):
        self.branch = BranchQueue()
        self.branch.issue_ticket("Ana", "deposit")
        self.branch.call_next("deposit")  # deposit queue is now drained

    def test_call_next_on_drained_queue_raises_meaningful_error(self):
        with self.assertRaises(EmptyQueueError) as caught:
            self.branch.call_next("deposit")
        self.assertEqual(str(caught.exception), "No clients waiting for 'deposit'.")

    def test_peek_next_on_drained_queue_returns_none(self):
        self.assertIsNone(self.branch.peek_next("deposit"))

    def test_queue_keeps_working_after_an_empty_call(self):
        with self.assertRaises(EmptyQueueError):
            self.branch.call_next("deposit")

        luis = self.branch.issue_ticket("Luis", "deposit")

        self.assertEqual(self.branch.call_next("deposit"), luis)


class InvalidInputTests(unittest.TestCase):
    def setUp(self):
        self.branch = BranchQueue()

    def test_issue_ticket_rejects_unknown_service_with_clear_message(self):
        with self.assertRaises(InvalidServiceTypeError) as caught:
            self.branch.issue_ticket("Pedro", "loan")
        self.assertEqual(
            str(caught.exception),
            "Invalid service type 'loan'. "
            "Valid types: deposit, withdrawal, account_management.",
        )

    def test_rejected_service_is_not_queued_and_does_not_use_a_number(self):
        for bad in ("loan", "", "Deposit", None, ["deposit"]):
            with self.subTest(service_type=bad):
                with self.assertRaises(InvalidServiceTypeError):
                    self.branch.issue_ticket("Pedro", bad)

        self.assertEqual(self.branch.stats()["total"], 0)
        self.assertEqual(self.branch.issue_ticket("Pedro", "deposit").number, 1)

    def test_call_and_peek_reject_unknown_service(self):
        for operation in (self.branch.call_next, self.branch.peek_next):
            with self.subTest(operation=operation.__name__):
                with self.assertRaises(InvalidServiceTypeError):
                    operation("loan")

    def test_blank_client_name_is_rejected_without_using_a_number(self):
        for bad in ("", "   "):
            with self.subTest(client_name=bad):
                with self.assertRaisesRegex(ValueError, "Client name cannot be empty"):
                    self.branch.issue_ticket(bad, "deposit")

        self.assertEqual(self.branch.issue_ticket("Ana", "deposit").number, 1)


def run_cli(*inputs):
    """Run the menu with scripted input and return what it printed.

    Running out of input behaves like the user pressing Ctrl+D.
    """
    output = io.StringIO()
    with mock.patch("builtins.input", side_effect=[*inputs, EOFError()]):
        with redirect_stdout(output):
            main.main()
    return output.getvalue()


class CliTests(unittest.TestCase):
    def test_call_next_on_empty_queue_shows_message_and_keeps_running(self):
        output = run_cli("2", "deposit", "5", "0")

        self.assertIn("Error: No clients waiting for 'deposit'.", output)
        self.assertRegex(output, r"total\s+0")  # stats still ran afterwards
        self.assertTrue(output.rstrip().endswith("Goodbye."))

    def test_peek_next_on_empty_queue_shows_message(self):
        output = run_cli("3", "2", "0")

        self.assertIn("No clients waiting for 'withdrawal'.", output)

    def test_invalid_service_is_rejected_and_does_not_use_a_number(self):
        output = run_cli("1", "Pedro", "loan", "1", "Pedro", "deposit", "0")

        self.assertIn("Error: Invalid service type 'loan'.", output)
        self.assertIn("Ticket issued: #0001  Pedro  [deposit]", output)

    def test_service_accepts_number_or_name_in_any_case(self):
        output = run_cli("1", "Ana", "3", "1", "Luis", "  WITHDRAWAL ", "0")

        self.assertIn("#0001  Ana  [account_management]", output)
        self.assertIn("#0002  Luis  [withdrawal]", output)

    def test_unknown_menu_option_keeps_running(self):
        output = run_cli("9", "0")

        self.assertIn("Unknown option '9'.", output)
        self.assertTrue(output.rstrip().endswith("Goodbye."))

    def test_ctrl_c_or_ctrl_d_mid_prompt_exits_cleanly(self):
        for interrupt in (KeyboardInterrupt(), EOFError()):
            with self.subTest(interrupt=type(interrupt).__name__):
                output = run_cli("1", "Ana", interrupt)
                self.assertTrue(output.rstrip().endswith("Goodbye."))


if __name__ == "__main__":
    unittest.main()
