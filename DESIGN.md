# Branch Queue Manager: Design Notes

Banco Meridional's branches serve three service types: `deposit`, `withdrawal` and
`account_management`. Each service has its own agents, who work independently. This document
explains how the queues are structured and how the design would handle two agents calling at the
same moment.

## Structure

`BranchQueue` (in `branch_queue.py`) holds:

- **One FIFO queue per service type.** A `dict` maps each service type to a `collections.deque` of
  `Ticket`s, oldest at the front.
- **One global ticket counter** shared by all three queues, so every ticket number is unique
  across the branch.

```
_queues = {
    "deposit":            deque([#3 Ana, #7 Marta]),
    "withdrawal":         deque([#1 Luis, #2 Sofía, #5 Pedro]),
    "account_management": deque([#4 Jorge, #6 Elena]),
}
_next_number = 8
```

A ticket's position in its own queue decides when that client is called. The ticket number is
only an identifier and is never used to search for anyone.

## 1. Why a separate queue per service type makes `call_next` efficient

**The paper system is a single shared list.** All clients wait in arrival order, whatever their
service:

```
[#1 W, #2 W, #3 D, #4 A, #5 W, #6 A, #7 D]
```

When the deposits agent is free, they have to:

1. **Scan** from the front, skipping every withdrawal and account-management client, until they
   find the first deposit client. In the worst case that means walking past everyone in the room:
   O(n), where n is the total number of people waiting.
2. **Remove** that client from the middle of the list. In a Python `list`, every entry after them
   shifts one place forward: O(n) again.

The busier the branch, the slower every call gets. This is exactly the idle-agent problem the
operations manager described: a deposit client buried behind 40 withdrawal clients costs the
deposits agent a scan through all 40.

**With one queue per service**, the deposits agent's next client is always at the front of the
deposit queue:

1. Look up the deposit queue in the dict: O(1).
2. `popleft()` the front ticket: O(1). A `deque` removes from the front without shifting anything.
   A `list` would not (`list.pop(0)` is O(n)), which is why each queue is a `deque`.

How many people are waiting for withdrawals or account management makes no difference. The deposits
agent never looks at them.

| Operation | Single shared list | One `deque` per service |
|---|---|---|
| `issue_ticket` | O(1) append | O(1) append |
| `call_next` | O(n) scan + O(n) removal | **O(1)** |
| `peek_next` | O(n) scan | **O(1)** |
| `stats` | O(n) count | O(1) `len()` per queue |
| `list_waiting` | O(n) | O(n) (it shows everyone, so this is unavoidable) |

Splitting the queues doesn't lose anything. Arrival order *within* a service is preserved by each
deque, and agents never serve another service, so order *across* services doesn't matter to them.
The global counter still guarantees that no two tickets share a number.

## 2. Two agents of the same service type calling `call_next` at the same moment

Suppose two deposits agents become free at the same instant, and the deposit queue is
`[#3 Ana, #7 Marta]`.

**What goes wrong if "who's next?" and "remove them" are separate steps.** If `call_next` were
written as *look at the front, then remove the front*, the two agents' steps could interleave like
this:

| Step | Agent A | Agent B | Deposit queue |
|---|---|---|---|
| 1 | reads front → **#3 Ana** | | `[#3, #7]` |
| 2 | | reads front → **#3 Ana** | `[#3, #7]` |
| 3 | removes front (#3) | | `[#7]` |
| 4 | | removes front (#7) | `[]` |

Both agents call **Ana** to their desk. **Marta** has been removed from the queue, but nobody called
her: she is silently lost. The same thing happens with "is anyone waiting?" followed by "take them":
both agents see one client, both try to take them, and the second one fails or takes someone else.

**What must happen first.** Removing the ticket from the queue must come **first**, and it must be
**a single step that cannot be split**: one operation that both takes the front ticket and removes
it. Only the agent whose removal succeeded may call that client. The other agent's removal then
returns the next client (Marta), or reports that nobody is waiting. Each ticket can be removed only
once, so each client is called exactly once.

**How this code follows that rule:**

- `call_next` takes the client with a single `deque.popleft()`. There is no separate "look" or "is
  it empty?" step before it. An empty queue is detected when `popleft()` raises `IndexError`, which
  is turned into `EmptyQueueError`. Python documents `deque` appends and pops as thread-safe, so two
  threads can never pop the same ticket.
- `peek_next` is for display only (for example, a "next up" screen). It must never be used to decide
  whom to call, because by the time the agent acts, another agent may already have taken that client.
- `issue_ticket`'s `self._next_number += 1` is a separate read and write. Two threads issuing tickets
  at the same moment could both read the same value and get **the same ticket number**. The terminal
  app is single-threaded, so this cannot happen today. It must be fixed before the queue is shared,
  using the same rule: take the number and advance the counter in one step that cannot be split.

**When the queue moves to the touchscreen kiosks**, several devices will share the queue, and the
same rule has to be enforced where the shared state lives:

- **One process, several threads:** guard `issue_ticket` and `call_next` with a `threading.Lock`, so
  that taking a number or a ticket, and changing the queue, happen together.
- **Several processes or kiosks sharing a database:** claim the ticket with one atomic statement,
  such as an `UPDATE … WHERE status = 'waiting' … RETURNING` that selects the oldest ticket with
  `FOR UPDATE SKIP LOCKED`, and issue numbers from a database sequence. The database then guarantees
  that each ticket is claimed once and each number is used once.

## How to run

Requires Python 3.9 or newer and uses the standard library only. The app uses `collections`,
`dataclasses`, `datetime` and `typing`, and the tests also use `unittest`, `io` and `contextlib`.
No packages to install.

```bash
python3 main.py              # interactive menu
python3 -m unittest -v       # test suite
```

| File | Contents |
|---|---|
| `branch_queue.py` | `Ticket`, `BranchQueue` and the queue errors. Contains no input or output code. |
| `main.py` | Terminal menu: issue, call next, peek next, view waiting list, view stats, exit |
| `test_branch_queue.py` | Unit tests for the queue operations, the edge cases and the menu |
