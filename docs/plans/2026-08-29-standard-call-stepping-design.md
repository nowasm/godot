# Godot 3 Standard Call Stepping Design

## Goal

Make the custom Godot 3.6.3 debugger follow familiar source-debugger behavior while preserving the existing sub-300 ms stepping target:

- A normal breakpoint or step stop is presented as a breakpoint, not an exception.
- **Step Over (F10)** executes the complete current source line.
- **Step Into (F11)** enters the next GDScript function call in the language's real evaluation order.
- **Step Out (Shift+F11)** returns to the caller and stops immediately after the completed call, even when another call remains on the same source line.

Compatibility with the stock Godot 3 remote-debugger protocol is not required. Godot 4 DAP behavior must remain unchanged.

## Current Problems

### Normal stops are rendered as exceptions

Godot reports a normal break using the text `Breakpoint` and `is_error = false`. The VS Code adapter currently classifies any non-empty text as an exception. VS Code therefore opens the red inline `Exception has occurred` panel for ordinary breakpoints.

The adapter must use `is_error` as the sole exception discriminator. For non-error stops it must emit `reason: breakpoint` without exception text. Real runtime errors retain `reason: exception` and their diagnostic text.

### Step Out is only an alias for Step Over

The adapter currently translates Step Out to the protocol-v2 `next` command. The engine consequently has no way to distinguish leaving the current function from moving to the next executable source line.

Protocol v2 will gain a breaking `step_out` execution command and matching engine action.

### Line-only stepping cannot revisit a partially evaluated line

GDScript's existing step counters stop at `OPCODE_LINE` boundaries. Once a call on a compound line returns, there is no new line opcode before the next call. A conventional Step Out therefore needs a VM-level stop point immediately after a GDScript call returns to its caller.

## Design

### Stop presentation

The Godot 3 adapter derives the DAP stopped event as follows:

| Godot `is_error` | DAP reason | DAP text |
| --- | --- | --- |
| `false` | `breakpoint` | omitted |
| `true` | `exception` | Godot error text, when present |

This removes the intrusive red panel for ordinary breakpoints without hiding genuine errors.

### Protocol command

Add `step_out` to protocol-v2 execution commands. The adapter sends it for DAP Step Out. The engine validates it and maps it to a new `ACTION_STEP_OUT` state.

### Engine stepping state

When Step Out is requested, the engine:

1. Sets the existing GDScript step depth to one frame.
2. Keeps one step stop armed.
3. Arms a one-shot `break_on_function_return` flag on `ScriptDebugger`.

The existing enter/exit hooks keep the depth positive while execution is in the current function or any deeper calls. Exiting the current function reduces the depth to zero.

Immediately after a GDScript call opcode returns, the caller checks and consumes the one-shot flag. If the step depth is now zero, it invokes the normal debugger break path before evaluating the rest of the source line. This makes the caller's partially evaluated line observable without manufacturing a source line or treating the stop as an error.

The flag is cleared by Step Into, Step Over, Continue, disconnect, timeout, and any unrelated debugger stop. It cannot leak into a later execution command.

Native and built-in calls are executed normally because the GDScript debugger cannot enter their implementation. GDScript calls through both ordinary and self/base call opcodes participate in the return stop.

### Expected same-line behavior

For:

```gdscript
var result = combine(first(), second())
```

starting at the expression line:

1. F11 enters `first()`.
2. Shift+F11 returns to the same caller line after `first()`.
3. F11 enters `second()`.
4. Shift+F11 returns to the same caller line after `second()`.
5. F11 enters `combine()`.
6. Shift+F11 returns to the same caller line after `combine()`.
7. F10 moves to the next executable line.

This follows GDScript's actual argument evaluation order rather than source-text guessing in the adapter.

## Verification

- Unit-test stop classification so `Breakpoint` with `is_error = false` has no exception text, while real errors remain exceptions.
- Unit-test protocol-v2 acceptance and mapping of `step_out`.
- Add a real custom-engine fixture with three calls on one line. Drive it over TCP and assert each top stack frame and caller line after every Step Into/Step Out transition.
- Run the complete Godot 3 protocol-v2 model and real-engine suites.
- Run the VS Code adapter unit and Godot 3 integration suites.
- Run the existing Godot 4 DAP regression suite to prove the changes are isolated.

