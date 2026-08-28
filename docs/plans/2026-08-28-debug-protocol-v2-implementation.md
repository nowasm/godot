# Godot 3 Debug Protocol v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Godot 3.6.3 single-stream remote debugger with an incompatible dual-channel, acknowledged, recoverable, lazy-data protocol whose step-control P95 latency stays below 300 ms in Brotato.

**Architecture:** A shared C++ protocol layer defines framed Variant messages, session generations, stop IDs, request IDs, and explicit runtime states. The engine connects to an editor or VS Code server using independent control and data sockets; execution commands and heartbeats use the control socket, while stack, variables, scene, inspector, profiler, and output use a bounded data socket. Both frontends request stack and variable pages only when the user opens them.

**Tech Stack:** Godot 3.6.3 C++14, SCons/MSVC, `StreamPeerTCP`, `PacketPeerStream`, GDScript integration fixtures, TypeScript, Node.js `net`, VS Code Debug Adapter Protocol, Vitest.

---

### Task 1: Protocol envelope and session state model

**Files:**
- Create: `scene/debugger/debug_protocol_v2.h`
- Create: `scene/debugger/debug_protocol_v2.cpp`
- Modify: `scene/debugger/SCsub`
- Create: `misc/debugger_v2/test_protocol_model.py`

**Step 1: Write the failing protocol model test**

Create a lightweight Python contract test that asserts the protocol constants and required envelope fields exist in the C++ header and that state names are unique. The required envelope is:

```text
[magic, major, minor, session_id, generation, channel, sequence,
 request_id, stop_id, message_type, payload]
```

Run:

```powershell
python misc/debugger_v2/test_protocol_model.py
```

Expected: FAIL because `debug_protocol_v2.h` does not exist.

**Step 2: Implement the shared protocol model**

Define:

```cpp
class DebugProtocolV2 {
public:
    static const char *MAGIC;
    static const int MAJOR = 2;
    static const int MINOR = 0;

    enum Channel { CHANNEL_CONTROL, CHANNEL_DATA };
    enum State { STATE_DISCONNECTED, STATE_CONNECTING, STATE_RUNNING,
        STATE_PAUSE_REQUESTED, STATE_PAUSED, STATE_RESUME_REQUESTED };

    struct Envelope {
        uint64_t session_id = 0;
        uint32_t generation = 0;
        Channel channel = CHANNEL_CONTROL;
        uint64_t sequence = 0;
        uint64_t request_id = 0;
        uint64_t stop_id = 0;
        String type;
        Array payload;
    };

    static Array encode(const Envelope &p_message);
    static Error decode(const Variant &p_packet, Envelope &r_message, String &r_error);
};
```

Validation rejects the wrong magic, major version, channel, field count, or field types. No decoder error may mutate the destination envelope.

**Step 3: Run contract and formatting checks**

Run:

```powershell
python misc/debugger_v2/test_protocol_model.py
python misc/scripts/clang_format.py scene/debugger/debug_protocol_v2.h scene/debugger/debug_protocol_v2.cpp
git diff --check
```

Expected: PASS and no whitespace errors.

**Step 4: Compile the new translation unit**

Run:

```powershell
scons platform=windows tools=yes target=release_debug -j8
```

Expected: editor build succeeds.

**Step 5: Commit**

```powershell
git add scene/debugger/debug_protocol_v2.h scene/debugger/debug_protocol_v2.cpp scene/debugger/SCsub misc/debugger_v2/test_protocol_model.py
git commit -m "debugger: add protocol v2 message model"
```

### Task 2: Runtime dual-channel transport and handshake

**Files:**
- Create: `scene/debugger/debug_transport_v2.h`
- Create: `scene/debugger/debug_transport_v2.cpp`
- Modify: `scene/debugger/script_debugger_remote.h`
- Modify: `scene/debugger/script_debugger_remote.cpp`
- Modify: `main/main.cpp`
- Create: `misc/debugger_v2/fake_debug_server.py`

**Step 1: Add a failing dual-channel handshake test**

The fake server listens on one port, accepts two clients, decodes their first packets, and asserts exactly one `control_hello` and one `data_hello` with the same session ID and generation.

Run the custom Godot binary against a minimal project with `--remote-debug 127.0.0.1:<port>`.

Expected before implementation: timeout after receiving only the legacy connection.

**Step 2: Implement `DebugTransportV2`**

Store independent TCP and packet peers:

```cpp
Ref<StreamPeerTCP> control_tcp;
Ref<PacketPeerStream> control_peer;
Ref<StreamPeerTCP> data_tcp;
Ref<PacketPeerStream> data_peer;
```

`connect_to_host()` connects both sockets, sends role handshakes, waits for `hello_ack`, and records negotiated limits. It exposes `send_control`, `send_data`, `poll_control`, `poll_data`, `is_control_connected`, and `is_data_connected`.

The session ID combines process ID, monotonic time, and a random component. Connection retry metadata retains host and port but never blocks the game main thread after startup.

**Step 3: Integrate runtime construction**

`ScriptDebuggerRemote` owns the transport. `main/main.cpp` enables the remote debugger only after both channel handshakes succeed. Initial failure exits with a clear protocol-v2 error.

**Step 4: Run handshake test and build**

Expected: both roles connect, share the session ID, and receive acknowledgements.

**Step 5: Commit**

```powershell
git add scene/debugger/debug_transport_v2.* scene/debugger/script_debugger_remote.* main/main.cpp misc/debugger_v2/fake_debug_server.py
git commit -m "debugger: establish protocol v2 dual channels"
```

### Task 3: Recoverable execution-control state machine

**Files:**
- Create: `scene/debugger/debug_session_v2.h`
- Create: `scene/debugger/debug_session_v2.cpp`
- Modify: `scene/debugger/script_debugger_remote.h`
- Modify: `scene/debugger/script_debugger_remote.cpp`
- Extend: `misc/debugger_v2/fake_debug_server.py`

**Step 1: Add failing state-machine scenarios**

Cover:

- pause while running;
- duplicate pause while paused;
- step with the current stop ID;
- duplicate request ID;
- stale stop ID;
- out-of-order request ID;
- control disconnect while paused.

Expected before implementation: duplicate break logs an engine error and disconnect leaves the game stopped.

**Step 2: Implement `DebugSessionV2`**

The class owns state, session generation, sequence counters, request acknowledgement cache, current stop ID, and heartbeat timestamps. It returns a typed decision for every control message and never performs socket I/O.

**Step 3: Replace the legacy pause loop**

On breakpoint, send a minimal `stopped` event and enter `STATE_PAUSED`. Poll only control messages in the pause loop. A valid resume request receives `accepted`, transitions to `STATE_RESUME_REQUESTED`, configures `set_depth()` and `set_lines_left()`, sends `running`, and exits.

If no valid heartbeat arrives for 1000 ms or the control socket disconnects, invalidate the stop, send diagnostics when possible, configure continue semantics, and leave the pause loop. Reconnect attempts occur from `idle_poll()`.

**Step 4: Verify recovery and latency**

Run 100 pause/step cycles. Expected: no duplicate-break error, disconnect resumes within 1.25 seconds, and the local P95 command acknowledgement is below 50 ms.

**Step 5: Commit**

```powershell
git add scene/debugger/debug_session_v2.* scene/debugger/script_debugger_remote.* misc/debugger_v2/fake_debug_server.py
git commit -m "debugger: make execution control acknowledged and recoverable"
```

### Task 4: Lazy stack, scope, and variable handle store

**Files:**
- Create: `scene/debugger/debug_variable_store_v2.h`
- Create: `scene/debugger/debug_variable_store_v2.cpp`
- Modify: `scene/debugger/script_debugger_remote.h`
- Modify: `scene/debugger/script_debugger_remote.cpp`
- Create: `misc/debugger_v2/fixtures/lazy_variables/project.godot`
- Create: `misc/debugger_v2/fixtures/lazy_variables/main.gd`
- Extend: `misc/debugger_v2/fake_debug_server.py`

**Step 1: Add failing lazy-data tests**

The fixture contains scalars, a 10,000-item array, a dictionary, a long string, and an object. Assert that `stopped` contains none of them, stack is requested separately, scope handles are stop-scoped, arrays page in 100-item chunks, long strings are previewed, and old handles fail after resume.

**Step 2: Implement the handle store**

Each stop owns a handle table. Scalars are returned inline. Arrays, dictionaries, objects, and long values receive handles and summaries. `variables` accepts `start` and `count`, clamps count to the negotiated page size, and returns a continuation token when more entries remain.

Only the requested scope calls the corresponding GDScript debug API. Globals are never collected unless requested.

**Step 3: Route stack and variable messages over the data channel**

Implement `stack_trace`, `scopes`, `variables`, and `inspect_object` request/result messages. Cancel requests when their stop ID or data generation becomes stale.

**Step 4: Verify packet size and response time**

Expected: initial `stopped` packet remains bounded, each variable page contains at most 100 descriptors, a 10,000-item array is not encoded in full, and each local page returns within 200 ms.

**Step 5: Commit**

```powershell
git add scene/debugger/debug_variable_store_v2.* scene/debugger/script_debugger_remote.* misc/debugger_v2
git commit -m "debugger: load stack variables lazily"
```

### Task 5: Bounded data queues, scene requests, and tracing

**Files:**
- Create: `scene/debugger/debug_trace_v2.h`
- Create: `scene/debugger/debug_trace_v2.cpp`
- Modify: `scene/debugger/debug_transport_v2.h`
- Modify: `scene/debugger/debug_transport_v2.cpp`
- Modify: `scene/debugger/script_debugger_remote.cpp`
- Modify: `scene/main/scene_tree.cpp`
- Extend: `misc/debugger_v2/fake_debug_server.py`

**Step 1: Add a failing backpressure test**

Queue more than the configured data limit using output and scene requests while repeatedly stepping on the control channel. Assert that low-priority records are dropped and every control request is acknowledged.

**Step 2: Implement bounded priority queues**

Priorities are active stack/variables, explicit inspector/scene requests, profiler/scene updates, then output. Drop superseded or oldest low-priority items first and report counters after pressure subsides.

**Step 3: Make scene and inspector explicit**

Remove stop-triggered scene refresh. Send snapshots only for `scene_snapshot` requests. Include a monotonically increasing revision so later delta support does not require another protocol break.

**Step 4: Add trace rings**

Record message metadata, state transitions, queue latency, processing time, payload size, and failure reason without recording complete values. Implement `export_trace` on the data channel.

**Step 5: Verify and commit**

Expected: control P95 remains below 50 ms under data saturation and queue memory remains bounded.

```powershell
git add scene/debugger/debug_trace_v2.* scene/debugger/debug_transport_v2.* scene/debugger/script_debugger_remote.cpp scene/main/scene_tree.cpp misc/debugger_v2
git commit -m "debugger: isolate control traffic from debugger data"
```

### Task 6: Godot editor protocol-v2 frontend

**Files:**
- Create: `editor/debugger_session_v2.h`
- Create: `editor/debugger_session_v2.cpp`
- Modify: `editor/script_editor_debugger.h`
- Modify: `editor/script_editor_debugger.cpp`
- Modify: `editor/editor_node.cpp`

**Step 1: Add an editor handshake smoke scenario to the fake runtime**

The scenario connects as runtime control and data channels, verifies acknowledgements, emits `stopped`, and records editor commands.

**Step 2: Implement dual-channel accept and pairing**

Accept any connection on the configured port, read its hello, pair by session ID, reject duplicate roles, and activate only a complete control/data pair.

**Step 3: Implement execution state UI**

Map pause, continue, step, and next buttons to request IDs and stop IDs. Disable controls until acknowledgement. Display connection health and last acknowledgement latency. Treat duplicate and stale responses as nonfatal diagnostics.

**Step 4: Implement lazy stack and variables**

Request stack after `stopped`. Request scopes only when a frame is selected and variable pages only when expanded. Do not automatically inspect every object. Keep remote scene local until the user explicitly opens or refreshes it.

**Step 5: Verify with the fake runtime and compile**

Expected: the editor completes 100 synthetic step cycles, survives data disconnect, and returns to running UI state after control timeout.

**Step 6: Commit**

```powershell
git add editor/debugger_session_v2.* editor/script_editor_debugger.* editor/editor_node.cpp
git commit -m "editor: support Godot debug protocol v2"
```

### Task 7: VS Code protocol codec and controller tests

**Repository:** `D:\work_mine\godot\GodotTools-debug-v2`

**Files:**
- Create: `src/debugger/godot3/protocol_v2.ts`
- Create: `src/debugger/godot3/protocol_v2.test.ts`
- Create: `src/debugger/godot3/session_state_v2.ts`
- Create: `src/debugger/godot3/session_state_v2.test.ts`
- Modify: `src/debugger/godot3/variables/variant_encoder.ts`
- Modify: `src/debugger/godot3/variables/variant_decoder.ts`

**Step 1: Write failing TypeScript tests**

Test envelope round trips, partial TCP buffers, multiple packets per buffer, invalid versions, duplicate acknowledgements, stale stop IDs, and channel pairing.

Run:

```powershell
npx vitest run src/debugger/godot3/protocol_v2.test.ts src/debugger/godot3/session_state_v2.test.ts
```

Expected: FAIL because the modules do not exist.

**Step 2: Implement codec and frontend state model**

Use the existing Godot Variant encoder/decoder for the outer envelope. The incremental decoder retains incomplete packets and never calls `readUInt32LE` without four available bytes.

**Step 3: Run tests and commit**

```powershell
npm run compile
npx vitest run src/debugger/godot3/protocol_v2.test.ts src/debugger/godot3/session_state_v2.test.ts
git add src/debugger/godot3
git commit -m "debugger: add Godot 3 protocol v2 client model"
```

### Task 8: VS Code dual-channel DAP integration

**Repository:** `D:\work_mine\godot\GodotTools-debug-v2`

**Files:**
- Modify: `src/debugger/godot3/server_controller.ts`
- Modify: `src/debugger/godot3/debug_session.ts`
- Modify: `src/debugger/godot3/helpers.ts`
- Create: `src/debugger/godot3/server_controller.test.ts`
- Create: `test_projects/test-dap-project-godot3/project.godot`
- Create: `test_projects/test-dap-project-godot3/Main.tscn`
- Create: `test_projects/test-dap-project-godot3/Main.gd`

**Step 1: Add failing controller tests**

Use two local sockets to verify channel pairing, heartbeat, command acknowledgements, stopped/running events, disconnect recovery, request cancellation, and data backpressure.

**Step 2: Replace the Godot 3 controller**

The server accepts and pairs control/data channels by session ID. DAP execution responses complete after engine acknowledgement. `stackTrace`, `scopes`, and `variables` map to paged protocol requests and honor DAP `start`/`count`. Object inspection is explicit instead of recursive.

Enable DAP cancellation support and return clear errors for stale handles or reset data channels.

**Step 3: Verify Godot 4 remains unchanged**

Run the existing Godot 4 debugger tests in addition to all new Godot 3 tests.

**Step 4: Compile, package, and commit**

```powershell
npm run compile
npm test
npm run package
git add src/debugger/godot3 test_projects/test-dap-project-godot3
git commit -m "debugger: integrate protocol v2 with VS Code DAP"
```

### Task 9: End-to-end latency and failure harness

**Files:**
- Create: `misc/debugger_v2/run_integration_tests.py`
- Create: `misc/debugger_v2/README.md`
- Modify: `docs/plans/2026-08-28-debug-protocol-v2-design.md`

**Step 1: Automate the custom editor and VS Code server modes**

The harness starts the custom Godot binary, runs the minimal project, executes 100 step cycles, saturates the data path, severs each channel, and correlates exported traces.

**Step 2: Enforce metrics**

Fail when:

- step command-to-ack P95 exceeds 100 ms locally;
- command-to-next-stop P95 exceeds 300 ms;
- disconnect recovery exceeds 1.25 seconds;
- a control message is dropped;
- data queue memory exceeds its configured limit;
- the game remains alive but permanently paused after frontend exit.

**Step 3: Run the harness and commit**

```powershell
python misc/debugger_v2/run_integration_tests.py --godot bin/godot.windows.opt.tools.64.exe
git add misc/debugger_v2 docs/plans/2026-08-28-debug-protocol-v2-design.md
git commit -m "test: verify debugger v2 latency and recovery"
```

### Task 10: Brotato stress verification and delivery build

**Files:**
- Modify only if needed: `D:\work_open\aistudy\Brotato_recovered\.vscode\settings.json`
- Modify only if needed: `D:\work_open\aistudy\Brotato_recovered\.vscode\launch.json`
- Create: `docs/verification/2026-08-28-debug-protocol-v2.md`

**Step 1: Point Brotato to the custom engine and development extension**

Keep the stock Godot executable available as a rollback path. Use the custom editor binary and packaged protocol-v2 VS Code extension only for v2 sessions.

**Step 2: Run the agreed stress matrix**

- 50 steps at `main.gd` initialization;
- 50 entity-birth steps;
- 50 combat-scene steps;
- large dictionary expansion;
- remote scene request;
- heavy output;
- data-channel disconnect;
- control-channel disconnect while paused.

**Step 3: Record evidence**

Document versions, commands, P50/P95/max latency, recovery time, trace locations, and any remaining limitations.

**Step 4: Build final artifacts**

Produce the custom Godot editor executable and GodParty VSIX. Verify both hashes and paths.

**Step 5: Commit verification documentation**

```powershell
git add docs/verification/2026-08-28-debug-protocol-v2.md
git commit -m "docs: verify debugger v2 with Brotato"
```
