# Godot 3 debugger protocol v2 verification

This directory contains black-box tests for the breaking debugger-v2 transport. The suite covers the protocol model, dual-channel pairing, 100 acknowledged steps under output pressure, heartbeat recovery, both-channel reconnect, data-only disconnect, lazy paged variables, bounded queues, trace redaction, the custom Godot editor, and the VS Code DAP client.

Run the complete Windows gate from the Godot source root:

```powershell
python misc\debugger_v2\run_integration_tests.py `
  --godot bin\godot.windows.opt.tools.64.exe `
  --plugin D:\work_mine\godot\GodotTools-debug-v2
```

Use `--report <path>` to retain a machine-readable record. `--skip-editor` and `--skip-vscode` are intended only for narrow engine development loops; a delivery build must run every gate.

The suite fails if command ACK P95 exceeds 100 ms, command-to-next-stop P95 exceeds 300 ms, paused disconnect recovery reaches 1.25 seconds, the data queue exceeds its configured bound, control state is lost, a stale handle is accepted, a trace contains variable values, or a frontend exit leaves the game permanently paused.

Individual engine scenarios can be run with:

```powershell
python misc\debugger_v2\fake_debug_server.py --godot bin\godot.windows.opt.tools.64.exe --scenario backpressure
```

Supported scenarios are `handshake`, `control`, `timeout`, `reconnect`, `data_disconnect`, `lazy`, and `backpressure`.

