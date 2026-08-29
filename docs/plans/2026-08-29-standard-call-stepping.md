# Godot 3 Standard Call Stepping Implementation Plan

> Execute each task in order. Keep engine and adapter commits independently testable.

**Goal:** Remove false exception presentation for normal stops and implement true Step Out so multiple GDScript calls on one line can be entered in evaluation order.

**Architecture:** Extend debug protocol v2 with `step_out`. Use the existing GDScript frame-depth hooks plus a one-shot VM return breakpoint. Keep DAP presentation logic in the Godot 3 adapter and preserve Godot 4 behavior.

**Repositories:**

- Engine: `D:\devlib\godot\godot-debug-v2`
- Adapter: `D:\work_mine\godot\GodotTools-debug-v2`

## Task 1: Specify Step Out in the engine model tests

**Files:**

- Modify: `misc/debugger_v2/test_debug_session_model.py`
- Modify if needed: `misc/debugger_v2/debug_session_model.py`

1. Add a failing test asserting `step_out` is accepted and maps to a distinct action.
2. Run `python misc/debugger_v2/test_debug_session_model.py` and confirm the new assertion fails for the missing command.
3. Extend the model to represent the new action.
4. Re-run the model suite and confirm it passes.
5. Commit as `test: specify protocol v2 step out`.

## Task 2: Implement the engine Step Out state

**Files:**

- Modify: `core/script_debugger.h`
- Modify: `core/script_debugger.cpp`
- Modify: `scene/debugger/debug_session_v2.h`
- Modify: `scene/debugger/debug_session_v2.cpp`
- Modify: `scene/debugger/script_debugger_remote.cpp`
- Modify: `modules/gdscript/gdscript_function.cpp`

1. Add `ACTION_STEP_OUT` and parse the `step_out` protocol command.
2. Add a one-shot function-return breakpoint state to `ScriptDebugger`, including an atomic consume operation gated by step depth zero.
3. Configure Step Out with depth one, one remaining stop, and the return flag. Clear the flag for all other resume modes and debugger termination paths.
4. After ordinary GDScript and self/base GDScript calls return, consume the flag and enter the normal break path before the next expression is evaluated.
5. Compile the affected engine target to catch C++ errors.
6. Run the model suite.
7. Commit as `feat: add protocol v2 step out`.

## Task 3: Add a real same-line call regression

**Files:**

- Add: `misc/debugger_v2/fixtures/call_stepping/project.godot`
- Add: `misc/debugger_v2/fixtures/call_stepping/main.gd`
- Modify: `misc/debugger_v2/fake_debug_server.py`
- Modify: `misc/debugger_v2/test_real_godot_protocol.py`

1. Add a fixture containing `combine(first(), second())` on one executable line.
2. Add a real-protocol test that breaks on the expression, enters `first`, steps out to the same caller line, then repeats for `second` and `combine`.
3. Assert stack-frame function names and line numbers at every stop.
4. Run the test against the pre-change executable if practical and confirm the missing `step_out` behavior fails.
5. Build the custom engine and run the complete real protocol-v2 suite.
6. Commit as `test: cover same-line call stepping`.

## Task 4: Correct adapter stop presentation and Step Out routing

**Files:**

- Modify: `D:\work_mine\godot\GodotTools-debug-v2\src\debugger\godot3\session_state_v2.ts`
- Modify: `D:\work_mine\godot\GodotTools-debug-v2\src\debugger\godot3\server_controller_v2.ts`
- Modify: `D:\work_mine\godot\GodotTools-debug-v2\src\debugger\godot3\debug_session.ts`
- Modify: `D:\work_mine\godot\GodotTools-debug-v2\src\debugger\godot3\protocol_v2.test.ts`
- Modify if needed: `D:\work_mine\godot\GodotTools-debug-v2\src\debugger\godot3\session_state_v2.test.ts`

1. Add failing unit tests for normal-stop and error-stop DAP presentation and for the `step_out` command type/state transition.
2. Add a pure stop-presentation helper in the protocol/session model so it can be tested without loading VS Code.
3. Make `onStopped` use `is_error` exclusively and omit error text on normal stops.
4. Route adapter Step Out to `execute("step_out")`.
5. Run TypeScript compilation and unit tests.
6. Commit as `fix: use standard Godot 3 stop semantics`.

## Task 5: Run adapter and cross-version regressions

**Files:**

- Modify if required: `D:\work_mine\godot\GodotTools-debug-v2\src\test\debugger_v2_integration.test.ts`
- Modify if required: `D:\work_mine\godot\GodotTools-debug-v2\package.json`
- Modify if required: `D:\work_mine\godot\GodotTools-debug-v2\package-lock.json`

1. Extend the adapter integration test to issue Step Out if the existing harness exposes it cleanly.
2. Run `npm run compile`.
3. Run `npm run test:debugger-v2`.
4. Run `npm run test:debugger-v2:integration` against the rebuilt Godot 3 executable.
5. Run `npm run test:godot4:integration`.
6. If packaging under the existing version would obscure the update, bump the patch version.
7. Commit any integration/package changes as `test: regress standard stepping adapters`.

## Task 6: Package and install the validated adapter

**Files:**

- Generated: `D:\work_mine\godot\GodotTools-debug-v2\*.vsix`

1. Package the VSIX using the repository's package script.
2. Record the VSIX SHA-256 and custom engine SHA-256.
3. Install the VSIX with `code --install-extension <vsix> --force`.
4. Verify the installed extension contents include `step_out` routing and normal-stop classification.
5. Report the two repository commits, executable path, VSIX path, hashes, and the required VS Code window reload.

