# Godot 3.6.3 debugger protocol v2 verification

Verified on Windows 11 on 2026-08-29 (Asia/Shanghai). The implementation intentionally breaks compatibility with the stock Godot 3 debugger protocol.

## Delivery artifacts

| Artifact | Source revision | Size | SHA-256 |
| --- | --- | ---: | --- |
| `D:\devlib\godot\godot-debug-v2\bin\godot.windows.opt.tools.64.exe` | Godot `593813e3c42dc67a23cfd1ae8de3b2b1cc6f4ceb` | 70,989,312 bytes | `5C6A411073817D3D96CB17DE1A4443422318CC3FC78D9CFCB39C3D03F390DEA9` |
| `D:\work_mine\godot\GodotTools-debug-v2\godparty-godot-tools-0.1.0.vsix` | GodotTools `05fc0575489c221086d9a2c1dc3aac2b9bb76693` | 916,215 bytes | `ACB1EE15FD57C0E5F1EDCA3E25B39559EA8E7BF8C4CF40F735D046A61D8C462D` |

The engine reports `3.6.3.stable.custom_build.593813e3c`. The VSIX was installed with `code --install-extension ... --force`, and the installed bundle was checked for the `GDDBG2` protocol marker.

## Automated integration gate

Command:

```powershell
python misc\debugger_v2\run_integration_tests.py `
  --godot bin\godot.windows.opt.tools.64.exe `
  --plugin D:\work_mine\godot\GodotTools-debug-v2 `
  --report misc\debugger_v2\integration-latest.json
```

All 12 gates passed. The run covered protocol/state models, dual-channel handshake, 100 engine steps, heartbeat timeout, reconnect, data-only disconnect, lazy variables, output backpressure, the custom Godot editor, TypeScript codec/state tests, and a real VS Code extension-host session.

| Gate | Result |
| --- | --- |
| Engine command ACK P95 | 2.35 ms |
| Engine control-disconnect recovery | 152.01 ms |
| Heartbeat recovery | 1001.49 ms |
| Lazy stack / 100-item page | 1.26 ms / 2.30 ms |
| Backpressure ACK / next-stop P95 | 2.20 ms / 2.39 ms |
| Backpressure drops | 769 data messages; no control messages |
| Godot editor | 101 stops completed |
| VS Code ACK P50 / P95 / max | 7.13 / 13.25 / 21.18 ms |
| VS Code next-stop P50 / P95 / max | 10.47 / 21.62 / 49.71 ms |

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
| Main initialization | 50 | 1.894 / 2.203 / 2.638 ms | 1.934 / 2.232 / 2.675 ms |
| Entity birth | 50 | 1.961 / 2.104 / 2.622 ms | 1.997 / 2.146 / 2.663 ms |
| Combat damage | 50 | 1.941 / 2.122 / 2.543 ms | 1.971 / 2.149 / 2.576 ms |

For every target, the scene revision was 1, the dictionary total/page were 10,000/100, the queue remained at 33,728 of 262,144 bytes, and 3,841 low-priority messages were deliberately dropped without losing control traffic. Data-channel reconnect advanced the generation to 2. Closing the control channel while paused resumed the game in about 152 ms; withholding heartbeats recovered in about 1.0 second.

## Compatibility regression

- `npm run compile`: passed.
- Godot 3 v2 TypeScript tests: 7/7 passed.
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

