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

## Native runtime selection

Debug builds advertise `runtime_node_select` in an optional fourth hello-payload field (an array of capability names). Send a data request of the same name with `[object_id, visible]` and stop ID 0. ID 0 clears selection. A successful `runtime_node_select_result` carries `[object_id, kind]`, where kind is `2d`, `3d` or `none`; missing objects return `request_error`. The request works while running or paused and does not enable input picking.

The debugger owns the rendering resources; no nodes or scripts are added to the running project. CanvasItem bounds are transformed into their own viewport and drawn above CanvasLayers. Spatial/VisualInstance bounds use an unshaded world-space wireframe. Nodes are resolved by ObjectID on each update, and drawings are cleared after removal, disconnect or a paused heartbeat timeout.

Run the pixel-based rendering gate with Python and Pillow installed:

```powershell
python misc\debugger_v2\test_runtime_selection.py `
  --godot bin\godot.windows.opt.tools.64.exe `
  --output bin\runtime-selection-verification
```

The fixture checks stretched/transformed UI, CanvasLayers, sprites, collision shapes, subviewports, 3D bounds, selection during a breakpoint, toggling/clearing, deleted objects, connection loss and heartbeat expiry. PNGs and a JSON report are saved under the output directory.

