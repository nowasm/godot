#!/usr/bin/env python3
"""Black-box native-selection rendering checks, through the real v2 transport."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import subprocess
import threading
import time

from PIL import Image
from fake_debug_server import _ack_for, _command, _receive_envelope, _receive_packet, _send_packet

ROOT = Path(__file__).resolve().parents[2]


class Client:
    def __init__(self, binary: Path, output: Path):
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(15)
        self.process = subprocess.Popen([
            str(binary), "--path", str(ROOT / "misc/debugger_v2/fixtures/runtime_selection"),
            "--remote-debug", f"127.0.0.1:{self.listener.getsockname()[1]}",
            "--no-window", "--audio-driver", "Dummy", "--resolution", "640x480",
        ], stdout=(output / "engine.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT)
        self.sockets = {}
        self.hello = {}
        try:
            for _ in range(2):
                connection, _ = self.listener.accept()
                connection.settimeout(5)
                hello = _receive_packet(connection)
                self.sockets[hello[5]] = connection
                self.hello[hello[5]] = hello
                assert "runtime_node_select" in hello[10][3], hello
                _send_packet(connection, _ack_for(hello))
        except Exception:
            for connection in self.sockets.values():
                connection.close()
            self.listener.close()
            self.process.terminate()
            self.process.wait(timeout=10)
            raise
        self.sequence = [1, 1]
        self.request_id = 10
        self.running = True
        self.lock = threading.Lock()
        self.heartbeat = threading.Thread(target=self._heartbeats, daemon=True)
        self.heartbeat.start()

    def _heartbeats(self):
        while self.running:
            try:
                with self.lock:
                    self.sequence[0] += 1
                    _send_packet(self.sockets[0], _command(self.hello[0], self.sequence[0], 0, 0, "heartbeat"))
            except OSError:
                return
            time.sleep(0.2)

    def request(self, name, payload, result=None):
        self.sequence[1] += 1
        self.request_id += 1
        _send_packet(self.sockets[1], _command(self.hello[1], self.sequence[1], self.request_id, 0, name, payload))
        message = _receive_envelope(self.sockets[1], result or name + "_result")
        assert message[7] == self.request_id, message
        return message[10]

    def set(self, object_id, name, value):
        self.request("set_object_property", [object_id, name, value])

    def close(self):
        self.running = False
        for connection in self.sockets.values():
            connection.close()
        self.listener.close()


def tree_nodes(flat):
    index = 0
    nodes = {}
    def visit(parent=""):
        nonlocal index
        children, name, _class_name, object_id = flat[index:index + 4]
        index += 4
        path = parent + "/" + name
        nodes[path] = object_id
        for _ in range(children):
            visit(path)
    visit()
    return nodes


def orange_points(path):
    with Image.open(path) as image:
        image = image.convert("RGB")
        return [(x, y) for y in range(image.height) for x in range(image.width)
                if (lambda r, g, b: r > 200 and 95 < g < 195 and 40 < b < 160 and r - g > 55)(*image.getpixel((x, y)))]


def bounds(points):
    assert points, "No native outline pixels found"
    return [min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)]


def expect_bounds(path, expected):
    actual = bounds(orange_points(path))
    assert all(abs(a - b) <= 4 for a, b in zip(actual, expected)), (actual, expected)
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = None
    try:
        client = Client(args.godot.resolve(), output)
        deadline = time.monotonic() + 15
        nodes = {}
        prefix = "/root/RuntimeSelectionFixture"
        while prefix + "/Target" not in nodes and time.monotonic() < deadline:
            nodes = tree_nodes(client.request("scene_snapshot", [])[1])
            time.sleep(0.1)
        root_id = nodes[prefix]
        target = nodes[prefix + "/Target"]

        def capture(name):
            time.sleep(0.12)
            path = output / (name + ".png")
            client.set(root_id, "capture_file", str(path))
            assert path.exists(), path
            return path

        results = {}
        assert not orange_points(capture("baseline"))
        assert client.request("runtime_node_select", [target, True])[1] == "2d"
        results["control_stretch"] = expect_bounds(capture("control"), [40, 60, 240, 140])
        client.set(root_id, "motion", 4)
        client.set(root_id, "rotated", True)
        results["moving_rotated_scaled"] = expect_bounds(capture("transformed"), [80, 60, 120, 360])
        layer = nodes[prefix + "/UILayer/LayerControl"]
        client.request("runtime_node_select", [layer, True])
        results["canvas_layer"] = expect_bounds(capture("layer"), [70, 230, 190, 290])
        sprite = nodes[prefix + "/SpriteTarget"]
        client.request("runtime_node_select", [sprite, True])
        results["sprite"] = expect_bounds(capture("sprite"), [290, 158, 330, 182])
        shape = nodes[prefix + "/Body/ShapeTarget"]
        client.request("runtime_node_select", [shape, True])
        results["collision_shape"] = expect_bounds(capture("shape"), [236, 324, 284, 356])
        nested = nodes[prefix + "/Nested/Viewport/NestedControl"]
        client.request("runtime_node_select", [nested, True])
        nested_capture = capture("nested")
        results["nested_viewport"] = expect_bounds(Path(str(nested_capture) + "-nested.png"), [10, 15, 50, 35])
        cube = nodes[prefix + "/SpatialView/Viewport/CubeTarget"]
        assert client.request("runtime_node_select", [cube, True])[1] == "3d"
        cube_capture = capture("spatial")
        results["spatial_aabb"] = bounds(orange_points(Path(str(cube_capture) + "-3d.png")))
        client.request("runtime_node_select", [cube, False])
        assert not orange_points(capture("disabled"))
        client.request("runtime_node_select", [target, True])
        client.set(root_id, "pause_requested", True)
        stopped = _receive_envelope(client.sockets[0], "stopped")
        assert stopped[8] > 0
        client.request("runtime_node_select", [layer, True])
        results["paused_selection"] = expect_bounds(capture("paused"), [70, 230, 190, 290])
        timeout_capture = output / "heartbeat-timeout.png"
        client.set(root_id, "capture_later", str(timeout_capture))
        client.running = False
        client.heartbeat.join(timeout=1)
        diagnostic = _receive_envelope(client.sockets[0], "diagnostic")
        assert diagnostic[10] == ["control_timeout_auto_continue"]
        deadline = time.monotonic() + 5
        while not timeout_capture.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not orange_points(timeout_capture)
        results["heartbeat_timeout_clear"] = "passed"
        client.running = True
        client.heartbeat = threading.Thread(target=client._heartbeats, daemon=True)
        client.heartbeat.start()
        client.request("runtime_node_select", [target, True])
        client.set(root_id, "delete_target", True)
        assert not orange_points(capture("deleted"))
        client.request("runtime_node_select", [target, True], "request_error")
        client.request("runtime_node_select", [layer, True])
        client.request("runtime_node_select", [0, False])
        assert not orange_points(capture("cleared"))
        client.request("runtime_node_select", [layer, True])
        disconnect_capture = output / "disconnected.png"
        client.set(root_id, "capture_later", str(disconnect_capture))
        client.close()
        deadline = time.monotonic() + 5
        while not disconnect_capture.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not orange_points(disconnect_capture)
        results["clear_disable_delete_disconnect"] = "passed"
        (output / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
        print("Native runtime node selection: PASS")
    finally:
        if client:
            client.close()
            if client.process.poll() is None:
                client.process.terminate()
            client.process.wait(timeout=10)


if __name__ == "__main__":
    main()
