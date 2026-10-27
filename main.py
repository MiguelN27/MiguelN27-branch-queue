"""Terminal menu for the Banco Meridional branch queue.

Run with: python3 main.py
"""

from branch_queue import SERVICE_TYPES, BranchQueue, EmptyQueueError, Ticket

MENU = """
=== Banco Meridional - Branch Queue ===
1. Issue a new ticket
2. Call next client
3. Peek at next client
4. View waiting list
5. View queue stats
0. Exit"""


def format_ticket(ticket: Ticket) -> str:
    return (
        f"#{ticket.number:04d}  {ticket.client_name}  [{ticket.service_type}]"
        f"  issued {ticket.issued_at:%H:%M:%S}"
    )


def prompt_service() -> str:
    """Ask for a service type by number or name.

    Unrecognised input is returned as typed so BranchQueue rejects it
    with its own message.
    """
    options = "  ".join(f"{i}) {service}" for i, service in enumerate(SERVICE_TYPES, 1))
    answer = input(f"Service type [{options}]: ").strip().lower()
    if answer.isdigit() and 1 <= int(answer) <= len(SERVICE_TYPES):
        return SERVICE_TYPES[int(answer) - 1]
    return answer


def issue_ticket(branch: BranchQueue) -> None:
    name = input("Client name: ")
    ticket = branch.issue_ticket(name, prompt_service())
    print(f"Ticket issued: {format_ticket(ticket)}")


def call_next(branch: BranchQueue) -> None:
    ticket = branch.call_next(prompt_service())
    print(f"Now calling: {format_ticket(ticket)}")


def peek_next(branch: BranchQueue) -> None:
    service = prompt_service()
    ticket = branch.peek_next(service)
    if ticket is None:
        print(f"No clients waiting for {service!r}.")
    else:
        print(f"Next up: {format_ticket(ticket)}")


def show_waiting(branch: BranchQueue) -> None:
    for service, tickets in branch.list_waiting().items():
        print(f"\n{service} ({len(tickets)} waiting)")
        if not tickets:
            print("  (no one waiting)")
        for position, ticket in enumerate(tickets, 1):
            print(f"  {position}. {format_ticket(ticket)}")


def show_stats(branch: BranchQueue) -> None:
    stats = branch.stats()
    width = max(len(key) for key in stats)
    for key, count in stats.items():
        print(f"  {key:<{width}}  {count}")


ACTIONS = {
    "1": issue_ticket,
    "2": call_next,
    "3": peek_next,
    "4": show_waiting,
    "5": show_stats,
}


def main() -> None:
    branch = BranchQueue()
    try:
        while True:
            print(MENU)
            choice = input("Choose an option: ").strip()
            if choice == "0":
                break
            action = ACTIONS.get(choice)
            if action is None:
                print(f"Unknown option {choice!r}. Enter a number from the menu.")
                continue
            try:
                action(branch)
            except (ValueError, EmptyQueueError) as error:
                print(f"Error: {error}")
    except (EOFError, KeyboardInterrupt):
        # Ctrl+D / Ctrl+C, or piped input that ran out.
        print()
    print("Goodbye.")


if __name__ == "__main__":
    main()
