# Godot 3.6.3 debugger protocol v2 verification

Verified on Windows 11 on 2026-08-29 (Asia/Shanghai). The implementation intentionally breaks compatibility with the stock Godot 3 debugger protocol.

## Delivery artifacts

| Artifact | Source revision | Size | SHA-256 |
| --- | --- | ---: | --- |
| `D:\devlib\godot\godot-debug-v2\bin\godot.windows.opt.tools.64.exe` | Godot `1fb92b2693f513be473422469f657f500357b094` | 70,988,800 bytes | `287F1E49ECE34762423B294E99E252799D1155682471618B193D436907204547` |
| `D:\work_mine\godot\GodotTools-debug-v2\godparty-godot-tools-0.1.0.vsix` | GodotTools `05fc0575489c221086d9a2c1dc3aac2b9bb76693` | 916,215 bytes | `ACB1EE15FD57C0E5F1EDCA3E25B39559EA8E7BF8C4CF40F735D046A61D8C462D` |

The engine reports `3.6.3.stable.custom_build.1fb92b269`. The VSIX was installed with `code --install-extension ... --force`, and the installed bundle was checked for the `GDDBG2` protocol marker.

## Automated integration gate

Command:

```powershell
python misc\debugger_v2\run_integration_tests.py `
  --godot bin\godot.windows.opt.tools.64.exe `
  --plugin D:\work_mine\godot\GodotTools-debug-v2 `
  --report misc\debugger_v2\integration-latest.json
```

All 13 gates passed. The run covered protocol/state models, dual-channel handshake, 100 engine steps, heartbeat timeout, reconnect, data-only disconnect, lazy variables, output backpressure, executable-line stepping, the custom Godot editor, TypeScript codec/state tests, and a real VS Code extension-host session.

| Gate | Result |
| --- | --- |
| Engine command ACK P95 | 2.51 ms |
| Engine control-disconnect recovery | 152.01 ms |
| Heartbeat recovery | 1001.49 ms |
| Lazy stack / 100-item page | 1.26 ms / 2.30 ms |
| Backpressure ACK / next-stop P95 | 2.20 ms / 2.39 ms |
| Backpressure drops | 769 data messages; no control messages |
| Godot editor | 101 stops completed |
| VS Code ACK P50 / P95 / max | 6.99 / 14.38 / 40.27 ms |
| VS Code next-stop P50 / P95 / max | 12.10 / 27.88 / 44.12 ms |

## Executable-line stepping

`GDScriptCompiler::_parse_block` now emits `OPCODE_LINE` from executable AST statement nodes instead of physical newline nodes. Blank lines and comment-only lines therefore do not consume a step; inline-comment statements remain stoppable, and multiple statements on one physical line share one stop.

The real protocol-v2 fixture starts at an external breakpoint and records the top stack frame after every acknowledged `next`. Its exact stop sequence was `[9, 14, 15, 19, 20, 21]`, skipping consecutive blank/comment-only regions at both the function and nested branch levels.

The local requirements were ACK P95 <= 100 ms, next-stop P95 <= 300 ms, disconnect recovery < 1.25 seconds, a bounded 262,144-byte data queue, no dropped control messages, and no permanent pause after frontend loss.

## Brotato stress matrix

Command:

```powershell
python misc\debugger_v2\brotato_stress.py `
  --godot bin\godot.windows.opt.tools.64.exe `
  --project D:\work_open\aistudy\Brotato_recovered\gdproj `
  --steps 50 `
  --report misc\debugger_v2\brotato-latest.json
```

The harness executes the recovered project with isolated user-data directories. It steps actual game code at the main object-pool initialization path (`main.gd:1887`), `EntityBirth.start` (`entity_birth.gd:34`), and the combat damage path (`main.gd:1717`). Each target also expands a 10,000-entry dictionary in a 100-item page, requests a revisioned remote scene, emits 4,000 output lines, and saturates the bounded data queue.

| Target | Steps | ACK P50 / P95 / max | Next-stop P50 / P95 / max |
| --- | ---: | --- | --- |
| Main initialization | 50 | 1.981 / 2.118 / 2.201 ms | 1.998 / 2.160 / 2.225 ms |
| Entity birth | 50 | 1.959 / 2.131 / 2.647 ms | 1.980 / 2.148 / 2.708 ms |
| Combat damage | 50 | 1.976 / 2.078 / 2.434 ms | 1.994 / 2.117 / 2.461 ms |

For every target, the scene revision was 1, the dictionary total/page were 10,000/100, the queue remained at 33,728 of 262,144 bytes, and 3,841 low-priority messages were deliberately dropped without losing control traffic. Data-channel reconnect advanced the generation to 2. Closing the control channel while paused resumed the game in about 152 ms; withholding heartbeats recovered in about 1.0 second.

## Compatibility regression

- `npm run compile`: passed.
- Godot 3 v2 TypeScript tests: 7/7 passed.
- Godot 3 executable-line stepping: exact stop sequence 6/6 passed.
- Godot 3 real VS Code DAP test: 100/100 acknowledged steps passed.
- Godot 4 variable-model unit tests: 14/14 passed.
- `npm run test:godot4:integration` with Godot 4.6.2: 8/8 real DAP tests passed.
- VSIX packaging and custom Godot editor build: passed.

The repository-wide `npm test` command is not a release gate because its single VS Code invocation mixes tests that require different workspace fixtures and engine paths. Separate Godot 3, Godot 4, and function-highlighting runners are used instead.

## Project configuration and rollback

`D:\work_open\aistudy\Brotato_recovered\.vscode\settings.json` points Godot 3 debugging at the custom binary. `launch.json` contains v2 full-game/current-scene entries and retains a clearly labelled stock-engine rollback entry. Because the protocol is intentionally incompatible, using the stock engine also requires switching back to a stock-compatible Godot Tools extension.

## Remaining limitations

- Protocol v2 accepts only major/minor `2.0`; stock Godot 3 frontends cannot attach.
- Godot 3 expression evaluation is disabled; values are expanded lazily through scopes and variable handles.
- Godot 3 `stepOut` currently maps to the engine's acknowledged `next` operation.
- A data-only loss while paused does not force the game to resume; the independent control channel remains usable, and reconnect begins after execution resumes. Control loss or heartbeat loss always auto-resumes.
- Non-continuable VM errors are reported with their stack but no longer create a terminal pause that cannot accept Continue.
