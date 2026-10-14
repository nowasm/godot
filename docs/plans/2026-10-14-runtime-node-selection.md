# Godot 3 Runtime Node Selection Implementation Plan

> **For Codex:** Implement and verify the following steps in this session.

**Goal:** Backport Godot 4's native selected-node bounds rendering to the custom Godot 3 v2 engine, connect it to GodParty, and replace the user's engine binary after validation.

**Architecture:** A debugger-owned RuntimeNodeSelect draws directly through VisualServer; it creates no project nodes and installs no input handlers. Port the Godot 4 bounds/transform algorithms to CanvasItem and Spatial APIs. Add an optional handshake capability and an additive v2 data request, leaving execution-control messages unchanged.

**Tech Stack:** Godot 3.6.3 C++, VisualServer canvas/mesh APIs, existing v2 TCP transport, TypeScript VS Code adapter, SCons/MSVC, black-box rendering/protocol tests.

## Decisions

- Port native rendering rather than injecting an autoload/overlay into Brotato. Use per-viewport top-level canvases for 2D and a world-space wireframe AABB for 3D, including transforms and CanvasLayers. Reuse Godot 4's editor bounds and collision-shape fallback logic.
- Scope is highlighting the node selected in VS Code. Game-window input picking, editor camera overrides and multi-selection are separate Godot 4 tools and are not needed for the requested debugging workflow.
- Advertise `runtime_node_select` in the optional fourth hello-payload field. Older adapters ignore it; newer adapters keep highlighting disabled for older engine binaries. No protocol-major change.
- `runtime_node_select` data requests carry `[object_id, visible]`; object ID 0 clears selection. Handle them before paused-stack checks so they work while running and stopped. Keep stop ID 0 for runtime selection.
- Resolve ObjectIDs on every update. Clear/free drawings when nodes disappear, channels disconnect, the debug session ends, or the debugger is destroyed. Cache unchanged geometry to avoid repeatedly redrawing a paused scene.
- Keep engine changes on `codex/godot3-debug-protocol-v2-impl`, plugin changes on `codex/godot4-debug-protocol-v2`, and master clean.

## Tasks and validation

1. Add `scene/debugger/runtime_node_select.{h,cpp}`, integrate with running and paused debugger loops, and advertise the capability in both initial and reconnect handshakes.
2. Add capability-gated highlighting to the Godot 3 adapter, generalize the shared toolbar support checks, and test old/new hello negotiation and select/toggle/clear requests.
3. Add a small rendering fixture and protocol harness. Verify normal/transformed Control bounds, CanvasLayer/viewport transforms, Sprite/collision bounds, 3D AABBs, runtime movement, clear/disable, node deletion, and disconnect. Inspect saved viewport pixels rather than only request acknowledgements.
4. Back up the current executable. Build incrementally with SCons/MSVC; stage the candidate separately and keep the configured executable at its original version during validation. Run the existing debugger integration gate and Brotato/plugin smoke checks.
5. Package/install the matching plugin, replace the configured binary with the validated candidate, verify hashes/version, and record rollback paths/results.

## Source reference

Godot 4.6.2 `scene/debugger/scene_debugger.cpp`, RuntimeNodeSelect::_set_selected_nodes and _update_selection, in the local `D:\devlib\godot\godot-4.6.2-debug-v2` checkout.

## Validation results

- Compiled successfully with SCons 4.8.1 and MSVC 14.3, `platform=windows target=release_debug tools=yes bits=64 debug_symbols=yes -j16`, using a temporary output basename for the candidate. The Windows build script was restored exactly afterward.
- Pixel-rendering checks passed for stretched Control bounds, moved/rotated/scaled Controls, CanvasLayer transforms, Sprite and CollisionShape2D bounds, nested Viewport rendering, Spatial AABBs, paused selection, clear/disable/deletion/disconnect and paused heartbeat timeout. Evidence is in `bin/runtime-selection-final/`.
- All 14 existing engine/debugger integration gates passed, including the custom Godot editor and both real VS Code stepping tests. Report: `bin/runtime-selection-integration.json`.
- Plugin targeted regression: 22 passed; one workspace-specific opt-in test skipped in the Godot 4 test workspace. Older hello payloads and mismatched channel capabilities do not enable outlines.
- Separate real VS Code/Brotato session: 2079 runtime nodes, /root/TitleScreen selected, Godot 3 outline toggle visible and both toggle directions exercised through the actual webview. The engine exposed the negotiated capability. No Brotato source/configuration changes were made.
- Original executable backed up to `bin/backups/godot.windows.opt.tools.64.before-node-selection-20261014-175213.exe`, SHA256 `67EAFCD1C0BB9EF20948245BC0A238E559268B383EABE864B780245EFAF14802`.
