# GDScript Skip Non-Executable Lines Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Godot 3.6.3 GDScript step-over stop only on executable statements, automatically skipping blank and comment-only lines.

**Architecture:** Move line-stop bytecode generation from parser newline nodes to executable AST statement nodes in `GDScriptCompiler::_parse_block`. Validate the behavior through a real protocol-v2 session that records stack-frame line numbers after each acknowledged step.

**Tech Stack:** Godot 3.6.3 C++, GDScript bytecode compiler/VM, Python 3 protocol-v2 black-box harness, SCons/MSVC Windows build.

---

### Task 1: Add a failing real-debugger line sequence test

**Files:**
- Create: `misc/debugger_v2/fixtures/executable_lines/main.gd`
- Create: `misc/debugger_v2/fixtures/executable_lines/project.godot`
- Modify: `misc/debugger_v2/fake_debug_server.py`
- Modify: `misc/debugger_v2/run_integration_tests.py`

**Step 1: Create the fixture**

Add a `SceneTree` script whose `_exercise` function contains executable assignments separated by blank lines, comment-only lines, a conditional block, and two statements on one physical line. Keep expected executable line numbers explicit in the Python scenario.

**Step 2: Add the protocol scenario**

Add `executable_lines` to the accepted scenarios. Launch the fixture with a breakpoint on its first assignment, receive the initial `stopped` event, request `stack_trace` over the data channel after every stop, and send acknowledged `next` commands until `quit()`.

**Step 3: Assert the exact stop sequence**

Assert that the top-frame line sequence contains only executable source lines and that the same-line pair produces one stop. Print both expected and actual sequences on failure.

**Step 4: Run the new scenario against the current binary**

Run:

```powershell
python misc\debugger_v2\fake_debug_server.py --godot bin\godot.windows.opt.tools.64.exe --scenario executable_lines
```

Expected: FAIL because at least one blank or comment-only line appears in the actual stop sequence.

**Step 5: Commit the failing test**

```powershell
git add misc/debugger_v2/fixtures/executable_lines misc/debugger_v2/fake_debug_server.py misc/debugger_v2/run_integration_tests.py
git commit -m "test: expose non-executable gdscript step stops"
```

### Task 2: Generate line opcodes from executable statements

**Files:**
- Modify: `modules/gdscript/gdscript_compiler.cpp:1317-1332`

**Step 1: Add a small line-opcode helper**

Within `_parse_block`, add debug-only logic that emits `OPCODE_LINE` with a statement node's `line` when that line differs from the last emitted executable line. The helper must update `codegen.current_line`.

**Step 2: Ignore parser newline nodes**

Make `TYPE_NEWLINE` produce no bytecode. Before compiling every other statement type, emit its executable source line. Preserve `OPCODE_BREAKPOINT` and all expression/control-flow compilation.

**Step 3: Remove redundant synthetic control-flow line markers**

Remove or adapt the explicit `else` body `OPCODE_LINE` insertion so an `else` keyword or empty body cannot become an artificial stop. Let the first executable child statement own the next line marker.

**Step 4: Build the custom tools binary**

Run the repository's existing Windows tools build command for `bin/godot.windows.opt.tools.64.exe`.

Expected: compilation succeeds with no new warnings or errors.

**Step 5: Run the focused scenario**

Run:

```powershell
python misc\debugger_v2\fake_debug_server.py --godot bin\godot.windows.opt.tools.64.exe --scenario executable_lines
```

Expected: PASS and the reported stop sequence equals the executable-line sequence.

**Step 6: Commit the implementation**

```powershell
git add modules/gdscript/gdscript_compiler.cpp
git commit -m "debugger: step only on executable gdscript lines"
```

### Task 3: Run regression gates and refresh delivery evidence

**Files:**
- Modify: `docs/verification/2026-08-28-debug-protocol-v2.md`

**Step 1: Run the debugger-v2 integration suite**

```powershell
python misc\debugger_v2\run_integration_tests.py --godot bin\godot.windows.opt.tools.64.exe --plugin D:\work_mine\godot\GodotTools-debug-v2 --report misc\debugger_v2\integration-latest.json
```

Expected: every protocol model, engine, editor, VS Code unit, and real DAP gate passes, including `executable_lines`.

**Step 2: Run the Brotato stress matrix**

```powershell
python misc\debugger_v2\brotato_stress.py --godot bin\godot.windows.opt.tools.64.exe --project D:\work_open\aistudy\Brotato_recovered\gdproj --steps 50 --report misc\debugger_v2\brotato-latest.json
```

Expected: all three targets pass, ACK P95 remains below 100 ms, and next-stop P95 remains below 300 ms.

**Step 3: Record the new behavior and artifact hash**

Document the executable-line scenario result, final regression totals, new engine revision, binary size, and SHA-256. Note that the VS Code plugin does not require a new build for this behavior.

**Step 4: Commit verification evidence**

```powershell
git add docs/verification/2026-08-28-debug-protocol-v2.md
git commit -m "docs: verify executable-line stepping"
```

