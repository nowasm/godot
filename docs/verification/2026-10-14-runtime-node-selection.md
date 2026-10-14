# Godot 3 native runtime node selection delivery

Verified on Windows on 2026-10-14 (Asia/Shanghai).

## Delivered artifacts

| Artifact | Version/source | SHA256 |
| --- | --- | --- |
| `D:\devlib\godot\godot-debug-v2\bin\godot.windows.opt.tools.64.exe` | `3.6.3.stable.custom_build.87c252094`, source `87c2520943` | `18923F0285D7C4C784F138EE5769B7E822AA414CD263B3C3FCD7DEC89BA6CFFB` |
| `D:\work_mine\godot\GodotTools-debug-v2\godparty-godot-tools-0.1.7.vsix` | GodParty Godot Tools 0.1.7, installed in the user's VS Code | `FC8C892D83C9C7C1DA4313DC1505B2B5FF941DCDF1E2823F6D63705236FFAA95` |

The configured executable was replaced with a byte-identical copy of the final candidate that passed pixel-rendering tests. Its version was verified through a subprocess after replacement. Existing mapped executables were renamed before the swap so ongoing user processes did not have to be terminated. Restart a Godot session and reload the VS Code window to use both new components.

## Behavior

- The v2 handshake advertises `runtime_node_select`; older engine binaries keep native outlines disabled in the new plugin.
- Clicking a node in the sidebar or dedicated scene-tree column outlines CanvasItem bounds, or a Spatial/VisualInstance AABB, in the running game.
- Bounds follow transforms and viewports. Outlines also update while paused. The renderer creates no scene nodes or game scripts and captures no input.
- Toggle/clear works through the existing outline controls. Removed nodes, channel loss and paused heartbeat expiry clear the rendering resources. Reconnect restores the frontend's requested outline.
- This ports selected-node highlighting. Godot 4's game-window input picker, multi-select and camera manipulation tools are outside this change.

## Evidence

- Final native rendering fixture: stretched Control bounds, moving/rotated/scaled UI, CanvasLayers, Sprite bounds, CollisionShape2D bounds, nested Viewports, Spatial AABBs, paused selection, disable/clear/deletion/disconnect and heartbeat expiry all passed. PNGs and JSON: `bin/runtime-selection-release/`.
- Existing debugger integration: all 14 gates passed, including the Godot editor, execution/stepping, reconnect, paged variables, output backpressure and the real VS Code sessions. Report: `bin/runtime-selection-integration.json`.
- Plugin compilation/lint and targeted extension-host tests: 22 passed; one workspace-specific opt-in test skipped in the Godot 4 workspace. Capability tests cover old hellos, mismatched channel capabilities and select/hide/clear payloads.
- Separate VS Code/Brotato session passed with 2079 runtime nodes and /root/TitleScreen selected. The Godot 3 outline button appeared, both toggle directions were exercised, and tree/property interaction remained functional. No Brotato project source or configuration was edited.

## Rollback

Original executable backup: `D:\devlib\godot\godot-debug-v2\bin\backups\godot.windows.opt.tools.64.before-node-selection-20261014-175213.exe`.

Original SHA256: `67EAFCD1C0BB9EF20948245BC0A238E559268B383EABE864B780245EFAF14802`.

Restore this backup to the configured executable path when no new engine instance is running. Plugin 0.1.7 remains compatible with this previous v2 engine; its outline controls will be hidden because the old handshake has no selection capability.
