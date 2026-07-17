# Task Rules

## 1. Read Before You Write

**Never write before reading. Copy existing patterns.**

- Read the files you are about to touch; read, not skim.
- Copy existing patterns and styles. Check existing imports to see what the project actually depends on (e.g. don't reach for `axios` where everything uses `fetch`).
- If you cannot find a pattern, ask instead of guessing.

## 2. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

- Figure out what you are doing before you type. State your assumptions (e.g., "add authentication" is five different things, so name the one you picked) and name the tradeoffs.
- If multiple interpretations exist, present them — don't pick silently.
- If something is genuinely confusing, stop and ask rather than filling the gap with plausible-looking code. That is exactly the code that passes a casual review and fails when it matters.

## 3. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- Write the minimum code that solves the problem in front of you now, not the minimum that could solve every future version of it.
- No features beyond what was asked. No abstractions for single-use code.
- Skip error handling for errors that cannot occur, and hardcode values until there is a real reason to configure them.
- *The Test*: If the only reason something is abstracted is "in case we need to," you have over-built it. Ask: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 4. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Keep diffs as small as the task allows. Do not touch what you were not asked to touch.
- Match the existing style and do not reformat; a formatter pass buries the three lines that matter inside three hundred that do not.
- When your changes create orphans: remove imports/variables/functions that YOUR changes made unused. Don't remove pre-existing dead code unless asked; just mention it.
- *The Test*: Every changed line should trace directly to the user's request. If a line is there because "while I was in there," revert it.

## 5. Goal-Driven Execution

**Define success criteria before writing code.**

- Every task needs a success criterion before code is written. Transform tasks into verifiable goals (e.g., "Add validation" → "reject a missing or malformed email, return 400 with a clear message, and test both cases").
- For anything multi-step, state the plan first so the user can catch a wrong approach before you spend an hour building it. Use the format:

  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  3. [Step] → verify: [check]

- Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 6. Verification & Testing

**Write the failing test first. Test behavior that can break.**

- When fixing a bug, write the failing test first, watch it fail, then fix it; that is the only proof you fixed the cause and not the symptom.
- Test behavior that can actually break, not that a constructor sets a field.
- If something is hard to test, that is information about the design, not permission to skip it. Loop and verify until successful.

## 7. Debugging

**Investigate, do not guess.**

- Read the whole error and the stack trace.
- Reproduce the problem before you change anything.
- Change one thing at a time.
- Do not paper over an unexpected null with a null check; find out why it is null, or the bug just moves somewhere quieter.

## 8. Dependencies

**Every dependency is permanent code you do not control.**

- Before adding one, ask whether the project or the standard library can already do it (e.g. using `crypto.randomUUID()` over a `uuid` package).
- When you do add a dependency, state why explicitly, so the choice is visible rather than smuggled into the manifest.

## 9. Communication

**Explain what you did and why, not just a block of code.**

- Flag concerns even when you did exactly what was asked.
- Be precise about uncertainty: "I am not sure this library supports streaming" tells the user what to verify; "I think this should work" does not.

## 10. Common Failure Modes

**Recognize and avoid these anti-patterns:**

- **The Kitchen Sink**: Restructuring half the codebase while you are at it.
- **The Wrong Abstraction**: Copy-paste twice before you abstract.
- **The Optimistic Path**: The happy path handled and the 500/errors ignored.
- **The Runaway Refactor**: A fix that cascades across files.

*If you catch yourself in any of these, stop and adjust; do not push through.*
