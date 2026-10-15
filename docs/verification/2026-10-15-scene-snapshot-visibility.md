# Initial scene visibility delivery — 2026-10-15

The custom Godot 3 protocol v2 scene snapshot now includes optional compact native local/effective visibility metadata. Source feature commit: `6fbcb49b76`. Original four-field tree records and the first two response fields are unchanged.

## Engine delivery

- Configured executable replaced: `D:\devlib\godot\godot-debug-v2\bin\godot.windows.opt.tools.64.exe`.
- Version: `3.6.3.stable.custom_build.6fbcb49b7`.
- SHA-256: `86283E96CBFF66F322C03F401A89D5D88D341EAD92D01FA85B4E0B52D573361D`.
- Backup: `bin/backups/godot.windows.opt.tools.64.before-scene-visibility-20261015-114352.exe`.
- Previous SHA-256: `18923F0285D7C4C784F138EE5769B7E822AA414CD263B3C3FCD7DEC89BA6CFFB`.
- Built with MSVC 14.3 / SCons, `platform=windows target=release_debug tools=yes bits=64 debug_symbols=yes -j16`. Separate candidate: `bin/godot-scene-visibility.windows.opt.tools.64.exe`. Temporary executable-name change in platform/windows/SCsub was restored byte-for-byte.
- Replaced via a verified staged file and backup rename, without terminating user processes. Post-replacement subprocess version and hash checks passed.

## Verification

- Complete debugger-v2 integration suite: **14 gates passed**, including handshake, execution control, heartbeat recovery, reconnection, paged variables, output backpressure, source/call stepping, the custom editor and VS Code DAP. Report: `bin/scene-visibility-integration.json`.
- The editor smoke test now uses a temporary settings/cache directory and a free debugger port. Its former fixed port collided with the user's running VS Code listener; the isolated test completed 100 stop cycles. The desktop VS Code installation was updating, so the final gate used the existing portable VS Code 1.96.4 installation via `GODPARTY_VSCODE_PATH`.
- Plugin targeted extension-host suite: **46 passed**, one optional workspace-specific test skipped. The real engine fixture verifies initial hidden Controls, inherited hiding, hidden CanvasLayer descendants, independent visible CanvasLayers, top-level CanvasItems, and Spatial inheritance, before any object inspection. Script-only changes and paused native writes update subsequent snapshots correctly.
- Real Brotato: 2,079-node scene, 1,839 hidden nodes in the captured state. Before clicking or inspecting the hidden nodes, the UI showed a closed eye for `/root/TitleScreen/AnimatedBackgroundContainer/AbyssalTerrorsTitleScreenBackground/Logo` and inherited-hidden status for its `TextureRect` child. Native Inspector values independently confirmed local values false and true respectively. The rendered UI test passed.

GodParty Godot Tools 0.1.10 was packaged and installed alongside this engine. Reload VS Code and restart the Godot debug session; an existing process continues to use its mapped binary. Older plugin clients ignore the optional metadata. New plugin clients keep old engines usable and show an explicit unknown state where effective visibility is unavailable.
