#!/usr/bin/env python3
"""Black-box protocol-v2 handshake and execution-control test server."""

from __future__ import annotations

import argparse
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


MAGIC = "GDDBG2"
MAJOR = 2
MINOR = 0

TYPE_NIL = 0
TYPE_BOOL = 1
TYPE_INT = 2
TYPE_STRING = 4
TYPE_ARRAY = 19
FLAG_64 = 1 << 16


class ProtocolError(RuntimeError):
    pass


def _read_exact(connection: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = connection.recv(remaining)
        if not chunk:
            raise ProtocolError("connection closed in the middle of a packet")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _decode_variant(data: bytes, offset: int = 0) -> tuple[Any, int]:
    if len(data) - offset < 4:
        raise ProtocolError("truncated Variant header")
    raw_type = struct.unpack_from("<I", data, offset)[0]
    offset += 4
    variant_type = raw_type & 0xFF

    if variant_type == TYPE_NIL:
        return None, offset
    if variant_type == TYPE_BOOL:
        if len(data) - offset < 4:
            raise ProtocolError("truncated bool")
        return bool(struct.unpack_from("<I", data, offset)[0]), offset + 4
    if variant_type == TYPE_INT:
        if raw_type & FLAG_64:
            if len(data) - offset < 8:
                raise ProtocolError("truncated int64")
            return struct.unpack_from("<q", data, offset)[0], offset + 8
        if len(data) - offset < 4:
            raise ProtocolError("truncated int32")
        return struct.unpack_from("<i", data, offset)[0], offset + 4
    if variant_type == TYPE_STRING:
        if len(data) - offset < 4:
            raise ProtocolError("truncated string length")
        length = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        padded = (length + 3) & ~3
        if len(data) - offset < padded:
            raise ProtocolError("truncated string")
        return data[offset : offset + length].decode("utf-8"), offset + padded
    if variant_type == TYPE_ARRAY:
        if len(data) - offset < 4:
            raise ProtocolError("truncated array length")
        count = struct.unpack_from("<I", data, offset)[0] & 0x7FFFFFFF
        offset += 4
        result: list[Any] = []
        for _ in range(count):
            value, offset = _decode_variant(data, offset)
            result.append(value)
        return result, offset

    raise ProtocolError(f"unsupported Variant type {variant_type}")


def _encode_variant(value: Any) -> bytes:
    if value is None:
        return struct.pack("<I", TYPE_NIL)
    if isinstance(value, bool):
        return struct.pack("<II", TYPE_BOOL, int(value))
    if isinstance(value, int):
        if -(1 << 31) <= value <= (1 << 31) - 1:
            return struct.pack("<Ii", TYPE_INT, value)
        return struct.pack("<Iq", TYPE_INT | FLAG_64, value)
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        padding = b"\0" * ((-len(encoded)) % 4)
        return struct.pack("<II", TYPE_STRING, len(encoded)) + encoded + padding
    if isinstance(value, (list, tuple)):
        return (
            struct.pack("<II", TYPE_ARRAY, len(value))
            + b"".join(_encode_variant(item) for item in value)
        )
    raise ProtocolError(f"cannot encode Python type {type(value).__name__}")


def _receive_packet(connection: socket.socket) -> Any:
    size = struct.unpack("<I", _read_exact(connection, 4))[0]
    body = _read_exact(connection, size)
    value, used = _decode_variant(body)
    if used != len(body):
        raise ProtocolError("trailing bytes after Variant packet")
    return value


def _send_packet(connection: socket.socket, value: Any) -> None:
    body = _encode_variant(value)
    connection.sendall(struct.pack("<I", len(body)) + body)


def _ack_for(hello: list[Any]) -> list[Any]:
    return [
        MAGIC,
        MAJOR,
        MINOR,
        hello[3],
        hello[4],
        hello[5],
        1,
        hello[7],
        0,
        "hello_ack",
        [250, 1000, 100],
    ]


def _command(hello: list[Any], sequence: int, request_id: int, stop_id: int, message_type: str) -> list[Any]:
    return [
        MAGIC,
        MAJOR,
        MINOR,
        hello[3],
        hello[4],
        0,
        sequence,
        request_id,
        stop_id,
        message_type,
        [],
    ]


def _receive_envelope(connection: socket.socket, message_type: str) -> list[Any]:
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        packet = _receive_packet(connection)
        if isinstance(packet, list) and len(packet) == 11 and packet[9] == message_type:
            return packet
    raise ProtocolError(f"timed out waiting for {message_type}")


def _assert_ack(packet: list[Any], request_id: int, accepted: bool, reason: str, duplicate: bool = False) -> None:
    if packet[7] != request_id:
        raise ProtocolError(f"ack request id {packet[7]} != {request_id}")
    payload = packet[10]
    if payload[:3] != [accepted, duplicate, reason]:
        raise ProtocolError(f"unexpected ack payload for request {request_id}: {payload}")


def _exercise_control(control: socket.socket, hello: list[Any], result: dict[str, Any]) -> None:
    _send_packet(control, _command(hello, 2, 2, 0, "pause"))
    _assert_ack(_receive_envelope(control, "ack"), 2, True, "accepted")
    stopped = _receive_envelope(control, "stopped")
    if len(stopped[10]) != 3:
        raise ProtocolError(f"stopped event is not minimal: {stopped[10]}")
    stop_id = stopped[8]
    sequence = 10

    pause = _command(hello, sequence, 10, stop_id, "pause")
    _send_packet(control, pause)
    _assert_ack(_receive_envelope(control, "ack"), 10, True, "already_paused")

    _send_packet(control, pause)
    _assert_ack(_receive_envelope(control, "ack"), 10, True, "already_paused", duplicate=True)

    sequence += 1
    _send_packet(control, _command(hello, sequence, 11, stop_id - 1, "next"))
    _assert_ack(_receive_envelope(control, "ack"), 11, False, "stale_stop_id")

    sequence += 1
    _send_packet(control, _command(hello, sequence, 9, stop_id, "next"))
    _assert_ack(_receive_envelope(control, "ack"), 9, False, "out_of_order_request_id")

    acknowledgement_msec: list[float] = []
    for cycle in range(20):
        sequence += 1
        request_id = 20 + cycle
        started = time.perf_counter()
        _send_packet(control, _command(hello, sequence, request_id, stop_id, "next"))
        _assert_ack(_receive_envelope(control, "ack"), request_id, True, "accepted")
        acknowledgement_msec.append((time.perf_counter() - started) * 1000.0)
        _receive_envelope(control, "running")
        stopped = _receive_envelope(control, "stopped")
        if stopped[8] <= stop_id:
            raise ProtocolError("stop id did not increase after next")
        stop_id = stopped[8]

    sorted_latency = sorted(acknowledgement_msec)
    p95_index = max(0, int(len(sorted_latency) * 0.95) - 1)
    result["ack_p95_msec"] = sorted_latency[p95_index]
    if result["ack_p95_msec"] >= 50.0:
        raise ProtocolError(f"local control ack P95 is {result['ack_p95_msec']:.2f} ms")

    result["control_closed_at"] = time.perf_counter()
    control.shutdown(socket.SHUT_RDWR)
    control.close()


def _exercise_timeout(control: socket.socket, hello: list[Any], result: dict[str, Any]) -> None:
    _send_packet(control, _command(hello, 2, 2, 0, "pause"))
    _assert_ack(_receive_envelope(control, "ack"), 2, True, "accepted")
    _receive_envelope(control, "stopped")
    started = time.perf_counter()
    diagnostic = _receive_envelope(control, "diagnostic")
    result["timeout_recovery_msec"] = (time.perf_counter() - started) * 1000.0
    if diagnostic[10] != ["control_timeout_auto_continue"]:
        raise ProtocolError(f"unexpected timeout diagnostic: {diagnostic[10]}")
    if not 900.0 <= result["timeout_recovery_msec"] < 1250.0:
        raise ProtocolError(
            f"heartbeat timeout recovery took {result['timeout_recovery_msec']:.2f} ms"
        )


def _serve(listener: socket.socket, result: dict[str, Any], scenario: str) -> None:
    connections: list[socket.socket] = []
    try:
        listener.settimeout(5.0)
        hellos: list[list[Any]] = []
        for _ in range(2):
            connection, _ = listener.accept()
            connections.append(connection)
            connection.settimeout(3.0)
            packet = _receive_packet(connection)
            if not isinstance(packet, list) or len(packet) != 11:
                raise ProtocolError("hello is not a protocol-v2 envelope")
            if packet[:3] != [MAGIC, MAJOR, MINOR]:
                raise ProtocolError("hello has the wrong protocol signature")
            hellos.append(packet)
            _send_packet(connection, _ack_for(packet))

        roles = {hello[9] for hello in hellos}
        channels = {hello[5] for hello in hellos}
        if roles != {"control_hello", "data_hello"}:
            raise ProtocolError(f"unexpected channel roles: {sorted(roles)}")
        if channels != {0, 1}:
            raise ProtocolError(f"unexpected channel ids: {sorted(channels)}")
        if len({(hello[3], hello[4]) for hello in hellos}) != 1:
            raise ProtocolError("control and data channels do not share a session")
        result["hellos"] = hellos
        if scenario == "control":
            control_index = next(index for index, hello in enumerate(hellos) if hello[9] == "control_hello")
            _exercise_control(connections[control_index], hellos[control_index], result)
            connections.pop(control_index)
        elif scenario == "timeout":
            control_index = next(index for index, hello in enumerate(hellos) if hello[9] == "control_hello")
            _exercise_timeout(connections[control_index], hellos[control_index], result)
        elif scenario == "reconnect":
            original_session = hellos[0][3]
            original_generation = hellos[0][4]
            for connection in connections:
                connection.shutdown(socket.SHUT_RDWR)
                connection.close()
            connections.clear()
            reconnected: list[list[Any]] = []
            for _ in range(2):
                connection, _ = listener.accept()
                connections.append(connection)
                connection.settimeout(3.0)
                packet = _receive_packet(connection)
                if not isinstance(packet, list) or len(packet) != 11:
                    raise ProtocolError("reconnect hello is not a protocol-v2 envelope")
                reconnected.append(packet)
                _send_packet(connection, _ack_for(packet))
            if {packet[9] for packet in reconnected} != {"control_hello", "data_hello"}:
                raise ProtocolError("reconnect did not restore both channel roles")
            if {packet[3] for packet in reconnected} != {original_session}:
                raise ProtocolError("reconnect changed the session id")
            if {packet[4] for packet in reconnected} != {original_generation + 1}:
                raise ProtocolError("reconnect did not advance the generation")
            result["reconnected_generation"] = original_generation + 1
    except BaseException as error:  # Relay thread failures to the test runner.
        result["error"] = error
    finally:
        for connection in connections:
            connection.close()
        listener.close()


def run_test(godot: Path, scenario: str) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    port = listener.getsockname()[1]

    result: dict[str, Any] = {}
    server = threading.Thread(target=_serve, args=(listener, result, scenario), daemon=True)
    server.start()

    with tempfile.TemporaryDirectory(prefix="godot-debug-v2-") as temp_directory:
        project = Path(temp_directory)
        (project / "project.godot").write_text(
            '[application]\nconfig/name="debug-v2-handshake"\n', encoding="utf-8"
        )
        if scenario in ("control", "timeout"):
            script = (
                "extends SceneTree\n"
                "var total = 0\n"
                "func _init():\n"
                "    call_deferred(\"_exercise\")\n"
                "func _exercise():\n"
                "    for index in range(1000000):\n"
                "        total += index\n"
                "    quit()\n"
            )
        elif scenario == "reconnect":
            script = (
                "extends SceneTree\n"
                "func _init():\n"
                "    call_deferred(\"_wait\")\n"
                "func _wait():\n"
                "    yield(create_timer(0.75), \"timeout\")\n"
                "    quit()\n"
            )
        else:
            script = "extends SceneTree\nfunc _init():\n    quit()\n"
        (project / "main.gd").write_text(script, encoding="utf-8")
        command = [
            str(godot),
            "--path",
            str(project),
            "--remote-debug",
            f"127.0.0.1:{port}",
            "--script",
            "main.gd",
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=15.0, check=False
        )

    server.join(timeout=6.0)
    if server.is_alive():
        raise ProtocolError("fake server did not finish")
    if "error" in result:
        raise result["error"]
    if completed.returncode != 0:
        raise ProtocolError(
            f"Godot exited with {completed.returncode}:\n{completed.stdout}\n{completed.stderr}"
        )

    session_id = result["hellos"][0][3]
    if scenario == "control":
        recovery_msec = (time.perf_counter() - result["control_closed_at"]) * 1000.0
        if recovery_msec >= 1250.0:
            raise ProtocolError(f"control disconnect recovery took {recovery_msec:.2f} ms")
        print(
            "debug protocol v2 execution control: PASS "
            f"(ack_p95={result['ack_p95_msec']:.2f} ms, recovery={recovery_msec:.2f} ms)"
        )
    elif scenario == "timeout":
        print(
            "debug protocol v2 heartbeat recovery: PASS "
            f"(recovery={result['timeout_recovery_msec']:.2f} ms)"
        )
    elif scenario == "reconnect":
        print(
            "debug protocol v2 nonblocking reconnect: PASS "
            f"(generation={result['reconnected_generation']})"
        )
    else:
        print(f"debug protocol v2 dual-channel handshake: PASS (session={session_id})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True, type=Path)
    parser.add_argument(
        "--scenario",
        choices=("handshake", "control", "timeout", "reconnect"),
        default="handshake",
    )
    arguments = parser.parse_args()
    run_test(arguments.godot.resolve(), arguments.scenario)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
