---
description: "Systematic Python debugging workflow — reproduce, isolate, inspect, fix, verify"
agent: copilot
---

# Python Debug

Systematic debugging workflow for Python issues.

## Steps

1. **Reproduce** — get the exact error. Run the failing command or test:
   - `pytest tests/test_<module>.py::<test_name> -xvs` for test failures
   - Copy the full traceback including the exception type and message

2. **Isolate** — narrow the scope:
   - Read the traceback bottom-up to find the originating line
   - Check if the error is in project code or a dependency
   - Add `breakpoint()` (Python 3.7+) at the failing line if needed
   - Use `pytest --lf` to re-run only last-failed tests

3. **Inspect** — gather state:
   - Check variable types and values at the failure point
   - Look for `None` where an object is expected
   - Check for off-by-one errors in sequences
   - Verify assumptions about data shapes (dict keys, list lengths)

4. **Fix** — make the minimal change:
   - Fix the root cause, not the symptom
   - Write a regression test that fails before the fix

5. **Verify** — confirm the fix:
   - Run the specific failing test
   - Run the full test suite to check for regressions
   - Run the type checker if the project uses one
