# Unit tests — pure domain logic, no I/O

Scope: `Money` arithmetic, journal entry balancing, payment state transitions, policy evaluation,
actor construction rules.

No database, no HTTP, no fixtures that need a container. If a test here needs a connection, the
code under test has an I/O dependency it should not have — that is a design finding, not a
testing problem.

## Naming

**Name the test after the invariant it defends, not the function it calls.**

```
test_money_of_different_currencies_cannot_be_added        good
test_add()                                                  bad
test_transfer_below_available_balance_is_rejected          good
test_validate_transfer_2()                                  bad
```

A failing test should tell you what broke about the *system*, in the failure output, before you
open the file.
