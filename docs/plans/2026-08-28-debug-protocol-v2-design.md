# Godot 3 Debug Protocol v2 Design

## Status

Validated design for a deliberately incompatible replacement of the Godot 3.6.3 remote script debugger protocol.

## Context

Godot 3.6.3 currently uses one `PacketPeerStream` connection for debugger control, stack variables, remote scene inspection, profiling, and output. A stopped game waits in `ScriptDebuggerRemote::debug()` until the editor sends a resume command. The loop has no reliable disconnect escape path, and a duplicated `break` command while already stopped can desynchronize the engine and debugger frontend. Large variable graphs, scene trees, and output also compete with step commands on the same connection.

The observed failure in Brotato stopped at a trivial line in `main.gd`, logged `Got break when already broke!`, lost the TCP debugger connection, and left the editor and game processes alive. This design treats debugger liveness and control latency as protocol guarantees instead of frontend conventions.

## Goals

- Keep step-in, step-over, continue, and pause control latency below 300 ms at the 95th percentile in a live Brotato combat scene.
- Never leave the game permanently stopped after the debugger frontend or data channel disconnects.
- Make all control commands ordered, acknowledged, idempotent, and scoped to one stop generation.
- Load stack frames, variables, objects, and scene data only when requested.
- Keep large debugger data and console output from blocking execution control.
- Support the custom Godot editor and the companion VS Code extension with identical session semantics.
- Provide enough trace data to identify whether latency originated in the engine, transport, or frontend.

## Non-goals

- Compatibility with the official Godot 3.6.3 debugger protocol or unmodified Godot 3 debugger clients.
- Changes to the Godot 4 debugger path in the VS Code extension.
- Evaluating arbitrary expressions in the first implementation.
- Preserving variable handles after execution resumes.

## Architecture

The new protocol uses two TCP connections to the same debugger server endpoint. Each connection identifies its role during the handshake.

### Control channel

The control channel carries:

- protocol and capability negotiation;
- breakpoints and breakpoint synchronization;
- pause, continue, step-in, and step-over commands;
- stopped and running events;
- command acknowledgements;
- heartbeat and session lifecycle messages.

No variable, scene tree, profiler, or output payload may use the control channel.

### Data channel

The data channel carries:

- stack traces and scopes;
- paged variables and object properties;
- remote scene snapshots and deltas;
- profiler samples;
- console output;
- exported diagnostic traces.

The channel uses bounded queues and chunked responses. Low-priority data may be dropped or invalidated under pressure without affecting control commands.

### Handshake

Both connections exchange:

- protocol magic and major/minor version;
- session ID and session generation;
- channel role;
- supported capabilities;
- maximum packet and chunk sizes;
- heartbeat interval and timeout.

An incompatible peer is rejected immediately with a structured error. The engine does not enter a debugger stop for an incomplete session.

## Session state machine

The shared session state is explicit:

```text
DISCONNECTED
    -> CONNECTING
    -> RUNNING
    -> PAUSE_REQUESTED
    -> PAUSED
    -> RESUME_REQUESTED
    -> RUNNING
```

Every stop creates a monotonically increasing `stop_id`. Pause and resume commands carry a `request_id`, `session_generation`, and relevant `stop_id`.

- A duplicate `request_id` returns its cached acknowledgement.
- A resume command for an old `stop_id` is rejected without changing state.
- A repeated pause while `PAUSED` returns `already_paused` and the active `stop_id`.
- A command from an old session generation is discarded.
- The frontend disables execution-control buttons until it receives an acknowledgement or timeout.

A resume command follows this lifecycle:

```text
command -> accepted acknowledgement -> running event -> next stopped event
```

The engine acknowledges acceptance before leaving the pause loop so the frontend can distinguish transport latency from execution time.

## Stop and variable data flow

When GDScript stops, the engine sends only a minimal `stopped` event on the control channel:

- stop ID;
- reason;
- thread ID;
- script path, line, and function;
- engine timestamp.

The target budget is 50 ms from breakpoint detection to sending this event. The frontend should select and highlight the source line within 300 ms.

All other information is requested lazily:

1. `stack_trace(stop_id, start, count)` loads only the requested frame page.
2. `scopes(stop_id, frame_id)` returns lightweight scope handles.
3. `variables(stop_id, handle, start, count)` returns a page and optional continuation token.
4. Nodes, resources, and custom objects are represented by object handles until inspected.
5. Long strings and binary values return bounded previews with an explicit full-value request.

Variable handles are valid only for their `stop_id`. Resuming execution invalidates all handles and per-stop caches. Repeated requests within the same stop reuse cached stack and variable pages.

Requests that exceed 200 ms return a partial page and continuation token rather than blocking control processing.

## Remote scene and inspector

The remote scene tree is not refreshed automatically on every stop. Opening it requests a snapshot. Subsequent updates are sent as revisioned node additions, removals, renames, and property-version changes.

Only the selected remote object is inspected. Inspector refresh is revision-aware and does not resend unchanged properties. Scene and inspector requests are cancelable and are invalidated when the data channel reconnects or execution resumes.

## Backpressure and prioritization

The data channel uses bounded priority queues:

1. active stack and variable responses;
2. explicit object and scene requests;
3. scene deltas and profiler data;
4. console output.

When the memory limit is reached, old console output, profiler samples, and superseded scene deltas are discarded first. A structured dropped-data counter is reported later. Control traffic never enters this queue.

## Disconnect and recovery

The control channel sends a heartbeat every 250 ms. If the engine is paused and receives no valid control heartbeat for one second, it:

1. invalidates the active stop and all variable handles;
2. leaves the debugger pause loop;
3. resumes game execution;
4. records the disconnect reason;
5. retries connection in the background without blocking the main thread.

A reconnected frontend creates a new `session_generation` and sends a full breakpoint snapshot. Old requests and handles cannot affect the new session.

The data channel reconnects independently. Its loss never changes execution state. Pending data requests fail with `channel_reset` and can be retried by the frontend.

Malformed packets, invalid versions, and unknown required messages close the affected session with a structured diagnostic rather than leaving either side in a partial state.

## Diagnostics

The engine and both frontends maintain fixed-size trace rings containing:

- message type and request ID;
- session generation and stop ID;
- state transitions;
- queue wait and processing durations;
- payload size;
- timeout, cancellation, and drop reasons.

Traces exclude complete variable values. A frontend action exports the trace for correlation across engine and client clocks.

## Components

### Godot runtime

- Protocol codec and message definitions.
- Dual-channel client and handshake.
- Session state machine and idempotency cache.
- Control and data dispatchers.
- Per-stop stack, scope, variable, and object handle store.
- Bounded data queues and trace ring.
- GDScript VM integration through `ScriptDebuggerRemote`.

### Godot editor

- Dual-channel server and session controller.
- Execution-command acknowledgement handling.
- Lazy stack and paged variable model.
- Revisioned remote scene and Inspector clients.
- Connection health and last-control-latency UI.
- Diagnostic trace export.

### VS Code extension

- Godot 3 protocol v2 controller.
- DAP mapping for `next`, `stepIn`, `continue`, `pause`, `stackTrace`, `scopes`, and `variables`.
- Lazy variables and cancellation support.
- Scene tree and Inspector integration over the data channel.
- Connection health and diagnostic logging.
- No behavioral change to its Godot 4 debugger implementation.

## Verification

### Automated protocol tests

A fake debugger frontend launches a minimal Godot project and covers:

- handshake and capability mismatch;
- 100 consecutive step cycles;
- duplicate, stale, and out-of-order commands;
- paged variables and invalidated handles;
- saturated data-channel queues while stepping;
- data-channel loss and reconnect;
- control-channel loss while paused;
- automatic resume within 1.25 seconds;
- reconnect and full breakpoint resynchronization;
- malformed messages and bounded queue behavior.

The Windows test records command-to-acknowledgement and command-to-next-stop latency. The 95th percentile for 100 step cycles must not exceed 300 ms.

### Brotato stress verification

Run both the custom editor and VS Code clients against Brotato and verify:

- 50 steps during `main.gd` initialization;
- 50 steps through entity birth code;
- 50 steps in a high-node combat scene;
- stepping while expanding a large dictionary;
- stepping while requesting the remote scene and generating heavy output;
- closing the frontend while paused and observing game recovery within one second.

No run may report a duplicate-break engine error, remain permanently paused after disconnect, or lose control-channel state.

## Delivery strategy

Implementation proceeds in independently testable layers:

1. protocol model and session state tests;
2. engine control channel and disconnect recovery;
3. data channel and lazy variables;
4. Godot editor frontend;
5. VS Code frontend;
6. automated latency harness;
7. Brotato stress verification and tuning.
