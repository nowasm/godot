#!/usr/bin/env python3
"""Run the delivery step/inspection stress matrix against the recovered Brotato project."""

from __future__ import annotations

import argparse
import json
import os
import socket
import select
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from fake_debug_server import (
    ProtocolError,
    _ack_for,
    _command,
    _receive_envelope,
    _receive_packet,
    _send_packet,
)


TARGETS = {
    "main_init": ("res://main.gd", 1887),
    "entity_birth": ("res://entities/birth/entity_birth.gd", 34),
    "combat": ("res://main.gd", 1717),
}


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, int(len(values) * 0.95) - 1)]


def p50(values: list[float]) -> float:
    return sorted(values)[len(values) // 2]


def driver_source(target: str) -> str:
    common = (
        "extends SceneTree\n"
        "func _init():\n"
        "    call_deferred(\"_exercise\")\n"
        "func _exercise():\n"
        "    var huge_dictionary = {}\n"
        "    for index in range(10000):\n"
        "        huge_dictionary[\"key_%s\" % index] = index\n"
        "    for index in range(4000):\n"
        "        print(\"debug-v2-pressure-%s\" % index)\n"
    )
    if target == "entity_birth":
        return common + (
            "    var birth = load(\"res://entities/birth/entity_birth.tscn\").instance()\n"
            "    get_root().add_child(birth)\n"
            "    for index in range(60):\n"
            "        birth.start(1, null, Vector2(index, index))\n"
            "    birth.queue_free()\n"
            "    quit()\n"
        )
    if target == "main_init":
        return common + (
            "    var main = Node.new()\n"
            "    main.set_script(load(\"res://main.gd\"))\n"
            "    for index in range(60):\n"
            "        main.get_node_from_pool(index, get_root())\n"
            "    main.free()\n"
            "    quit()\n"
        )
    return common + (
        "    var main = Node.new()\n"
        "    main.set_script(load(\"res://main.gd\"))\n"
        "    for index in range(60):\n"
        "        main.handle_stat_damages([], 0)\n"
        "    main.free()\n"
        "    quit()\n"
    )


def serve(listener: socket.socket, result: dict[str, Any], target: str, steps: int) -> None:
    connections: list[socket.socket] = []
    try:
        hellos: list[list[Any]] = []
        for _ in range(2):
            connection, _ = listener.accept()
            connection.settimeout(5.0)
            connections.append(connection)
            hello = _receive_packet(connection)
            if not isinstance(hello, list) or len(hello) != 11:
                raise ProtocolError("invalid Brotato debugger hello")
            hellos.append(hello)
            _send_packet(connection, _ack_for(hello))
        control_index = next(i for i, hello in enumerate(hellos) if hello[9] == "control_hello")
        data_index = next(i for i, hello in enumerate(hellos) if hello[9] == "data_hello")
        control, data = connections[control_index], connections[data_index]
        control_hello, data_hello = hellos[control_index], hellos[data_index]
        noncontinuable_errors: list[Any] = []
        stopped = None
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline and stopped is None:
            readable, _, _ = select.select([control, data], [], [], 0.25)
            for connection in readable:
                try:
                    packet = _receive_packet(connection)
                except ProtocolError as error:
                    raise ProtocolError(f"{error}; non-continuable errors: {noncontinuable_errors[:10]}") from error
                if not isinstance(packet, list) or len(packet) != 11:
                    continue
                if packet[9] == "stopped":
                    stopped = packet
                elif packet[9] == "noncontinuable_error":
                    noncontinuable_errors.append(packet[10])
        if stopped is None:
            raise ProtocolError(f"target breakpoint was not reached; non-continuable errors: {noncontinuable_errors[:10]}")
        result["noncontinuable_errors"] = noncontinuable_errors
        stop_id = stopped[8]
        control_sequence = 2
        request_id = 10
        ack_ms: list[float] = []
        stop_ms: list[float] = []
        for _ in range(steps):
            began = time.perf_counter()
            _send_packet(control, _command(control_hello, control_sequence, request_id, stop_id, "next"))
            ack = _receive_envelope(control, "ack")
            if not ack[10][0] or ack[7] != request_id:
                raise ProtocolError(f"Brotato step was rejected after stop {stopped[10]}: {ack}")
            ack_ms.append((time.perf_counter() - began) * 1000.0)
            _receive_envelope(control, "running")
            stopped = _receive_envelope(control, "stopped")
            stop_ms.append((time.perf_counter() - began) * 1000.0)
            stop_id = stopped[8]
            control_sequence += 1
            request_id += 1

        data_sequence = 2
        data_request = 10000
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "stack_trace", [0, 100]))
        stack = _receive_envelope(data, "stack_trace_result")
        frames = stack[10][1]
        dictionary_handle = 0
        for frame in frames:
            data_sequence += 1
            data_request += 1
            _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "scopes", [frame[0]]))
            scopes = _receive_envelope(data, "scopes_result")[10][0]
            locals_handle = scopes[0][1]
            data_sequence += 1
            data_request += 1
            _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "variables", [locals_handle, 0, 100]))
            variables = _receive_envelope(data, "variables_result")[10][2]
            descriptor = next((item for item in variables if item[0] == "huge_dictionary"), None)
            if descriptor:
                dictionary_handle = descriptor[3]
                break
        if not dictionary_handle:
            raise ProtocolError("large dictionary was not available through lazy stack scopes")
        data_sequence += 1
        data_request += 1
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "variables", [dictionary_handle, 5000, 100]))
        dictionary_page = _receive_envelope(data, "variables_result")[10]
        if dictionary_page[0] != 10000 or len(dictionary_page[2]) != 100:
            raise ProtocolError(f"large dictionary page is invalid: total={dictionary_page[0]}, page={len(dictionary_page[2])}")

        data_sequence += 1
        data_request += 1
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "scene_snapshot"))
        scene = _receive_envelope(data, "scene_snapshot_result")[10]
        if scene[0] < 1 or not scene[1]:
            raise ProtocolError("remote scene snapshot was empty or unrevisioned")
        data_sequence += 1
        data_request += 1
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "stress_data_queue", [4096]))
        _receive_envelope(data, "stress_data_queue_result")
        data_sequence += 1
        data_request += 1
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "queue_stats"))
        stats = _receive_envelope(data, "queue_stats_result")[10]
        if stats[1] > stats[2]:
            raise ProtocolError(f"data queue exceeded bound: {stats[1]} > {stats[2]}")
        if stats[3] < 1:
            raise ProtocolError("Brotato pressure run did not exercise bounded data-message drops")

        source, line = TARGETS[target]
        data_sequence += 1
        data_request += 1
        _send_packet(data, _command(data_hello, data_sequence, data_request, stop_id, "breakpoint", [source, line, False]))
        _receive_envelope(data, "breakpoint_result")
        _send_packet(control, _command(control_hello, control_sequence, request_id, stop_id, "continue"))
        _receive_envelope(control, "ack")
        _receive_envelope(control, "running")

        result.update({
            "target": target,
            "steps": steps,
            "ack_p50_ms": round(p50(ack_ms), 3),
            "ack_p95_ms": round(p95(ack_ms), 3),
            "ack_max_ms": round(max(ack_ms), 3),
            "stop_p50_ms": round(p50(stop_ms), 3),
            "stop_p95_ms": round(p95(stop_ms), 3),
            "stop_max_ms": round(max(stop_ms), 3),
            "dictionary_total": dictionary_page[0],
            "dictionary_page": len(dictionary_page[2]),
            "scene_revision": scene[0],
            "queue_bytes": stats[1],
            "queue_limit_bytes": stats[2],
            "dropped_data_messages": stats[3],
        })
    except BaseException as error:
        result["error"] = error
    finally:
        for connection in connections:
            connection.close()
        listener.close()


def run_target(godot: Path, project: Path, target: str, steps: int) -> dict[str, Any]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    result: dict[str, Any] = {}
    server = threading.Thread(target=serve, args=(listener, result, target, steps), daemon=True)
    server.start()
    source, line = TARGETS[target]
    with tempfile.TemporaryDirectory(prefix=f"brotato-debug-v2-{target}-") as temporary:
        driver = Path(temporary) / "driver.gd"
        driver.write_text(driver_source(target), encoding="utf-8")
        command = [
            str(godot), "--path", str(project), "--remote-debug", f"127.0.0.1:{listener.getsockname()[1]}",
            "--breakpoints", f"{source}:{line}", "--no-window", "--audio-driver", "Dummy", "--script", str(driver),
        ]
        environment = os.environ.copy()
        environment["APPDATA"] = str(Path(temporary) / "appdata")
        environment["LOCALAPPDATA"] = str(Path(temporary) / "localappdata")
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, env=environment, check=False)
    server.join(timeout=10)
    if server.is_alive():
        raise ProtocolError(f"{target} frontend did not finish")
    if "error" in result:
        diagnostic_lines = [line for line in (completed.stdout + "\n" + completed.stderr).splitlines() if "ERROR" in line or "SCRIPT" in line]
        raise ProtocolError(f"{result['error']}\nGodot diagnostics:\n" + "\n".join(diagnostic_lines[:80]))
    if completed.returncode != 0:
        raise ProtocolError(f"{target} exited with {completed.returncode}:\n{completed.stdout}\n{completed.stderr}")
    if result["ack_p95_ms"] > 100 or result["stop_p95_ms"] > 300:
        raise ProtocolError(f"{target} latency gate failed: {result}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    results = [run_target(args.godot.resolve(), args.project.resolve(), target, args.steps) for target in TARGETS]
    for result in results:
        print(f"Brotato {result['target']}: PASS (steps={result['steps']}, ack_p95={result['ack_p95_ms']:.2f} ms, stop_p95={result['stop_p95_ms']:.2f} ms)")
    if args.report:
        args.report.resolve().write_text(json.dumps({"godot": str(args.godot.resolve()), "project": str(args.project.resolve()), "targets": results}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
