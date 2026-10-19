---
title: Testing standards
owner: cto
status: active
updated: 2026-10-19
related: [README.md, definition-of-done.md]
---

# Testing standards

1. **Every behavior change has a test** that fails without the change and passes with it. Write the test first where practical, and watch it fail.
2. **Bug fixes start with a test that reproduces the bug.**
3. **Run the suite your step needs,** with the commands in the product's runbook, not only your new tests. Report the exact commands and results. A failure you didn't cause still goes in your report, by name.
   - **While a task iterates** (Senior, code reviewer): the **task suite**, the suites the task's diff can affect (the runbook's "Task suite", where the product has one).
   - **Before every landing,** and once per Staff spawn: the **full suite** (engineering README §4–5).
4. **Test real behavior.** Mock only what you can't run (paid services, production systems, the network). Never assert on mock calls when you can assert on results.
5. **No network or production data in tests.** No real credentials.
6. **Deterministic.** No sleeps for timing, no dependence on test order, the clock or randomness without seeding.
7. **Cover the edges** the acceptance criteria imply: empty, too long, invalid, unauthorized, duplicate, concurrent where relevant.
8. **A repo without tests:** add the smallest test setup that fits its stack, in the design doc (M and L) or as its own S-size task. Don't silently skip testing.
9. **Tests hold up when other workstreams land** ([lessons learned](lessons-learned.md)):
   - A test that builds its own registry, fixture bank or config overrides every part it depends on together (for example both `types` and `templates`), and never assumes another workstream's content is absent from the shared defaults.
   - Tests that do slow work (whole runs, enumerations, child processes) set an explicit timeout instead of relying on the runner's default, so they pass on a machine shared by parallel workstreams.
10. **Platform checks and spikes must be able to fail** ([lessons learned](lessons-learned.md): spikes often first ship checks that couldn't fail). When a test records how a platform behaves (a browser, Windows, a cloud API) rather than our code:
    - a `pass` rests on the mechanism's own evidence (its error code, its message, its event naming the file), never on something merely not happening (a missing marker, a file not appearing);
    - each such check has a control run in which the mechanism is off and the thing does happen, through the same path;
    - the fixture can't produce the outcome by itself (e.g. a server that never finishes a body makes every download look held);
    - a reading is derived from what was observed, never written because a step ran;
    - outcomes that are results, not requirements, are recorded (and stated in the report), so a platform change shows up instead of failing silently or passing vacuously.
11. **A check that must agree with another parser is tested against that parser** ([lessons learned](lessons-learned.md)). When our code validates a string that a library then parses (a database URL for `pg`, a MIME header, a path, HTML), a test runs the library's own parser on the same inputs and asserts it reads what our check approved: generated shapes, not one example, covering every code point at each boundary, escapes and repeats. One probe that "reads the same" isn't evidence: a parser can have a second path (for example, `pg-connection-string` `encodeURI`s any string holding a space) that a plain input never takes.
12. **Mutation checks run in a copy, never in the worktree** ([lessons learned](lessons-learned.md)). To show a test fails without the code or data it guards, export the commit into your own scratchpad (`git archive <commit> | tar -x -C <scratchpad>/copy`), mutate and run there, and say which line failed. Never edit a tracked file in the shared worktree "temporarily": a stop mid-check leaves the change behind, and the permission system may refuse it as a change to a shared resource. Specs that ask for a mutation say "in a scratch copy".
13. **A module mock keeps the real module's other exports** ([lessons learned](lessons-learned.md)). Some runners' module mocks (Bun's `mock.module`, for one) are process-wide and outlives the file that sets it, so a partial mock changes what every later file imports, and a test can pass or fail with the run order. Mock as `{ ...(await import("<module>")), <the overrides> }` and say in a comment that it outlives the file. A task that adds a test mocking a shared module also shows the new file passing after and before each other file that mocks the same module (two-file runs, both orders).
