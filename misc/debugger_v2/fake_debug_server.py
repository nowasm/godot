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


def _serve(listener: socket.socket, result: dict[str, Any]) -> None:
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
    except BaseException as error:  # Relay thread failures to the test runner.
        result["error"] = error
    finally:
        for connection in connections:
            connection.close()
        listener.close()


def run_handshake_test(godot: Path) -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    port = listener.getsockname()[1]

    result: dict[str, Any] = {}
    server = threading.Thread(target=_serve, args=(listener, result), daemon=True)
    server.start()

    with tempfile.TemporaryDirectory(prefix="godot-debug-v2-") as temp_directory:
        project = Path(temp_directory)
        (project / "project.godot").write_text(
            '[application]\nconfig/name="debug-v2-handshake"\n', encoding="utf-8"
        )
        (project / "main.gd").write_text(
            "extends SceneTree\nfunc _init():\n    quit()\n", encoding="utf-8"
        )
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
    print(f"debug protocol v2 dual-channel handshake: PASS (session={session_id})")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", required=True, type=Path)
    arguments = parser.parse_args()
    run_handshake_test(arguments.godot.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
