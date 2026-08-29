#!/usr/bin/env python3
"""Run every Godot 3 debugger protocol-v2 correctness and latency gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ("handshake", "control", "timeout", "reconnect", "data_disconnect", "lazy", "backpressure")


def print_output(output: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    sys.stdout.buffer.write((output + "\n").encode(encoding, errors="replace"))
    sys.stdout.buffer.flush()


def run(name: str, command: list[str], cwd: Path, timeout: int = 180) -> dict[str, object]:
    started = time.perf_counter()
    completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    print(f"[{name}] {elapsed_ms:.0f} ms")
    if output:
        print_output(output)
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")
    return {"name": name, "duration_ms": round(elapsed_ms, 3), "output": output}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", type=Path, required=True)
    parser.add_argument("--plugin", type=Path, default=Path(r"D:\work_mine\godot\GodotTools-debug-v2"))
    parser.add_argument("--skip-editor", action="store_true")
    parser.add_argument("--skip-vscode", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    godot = args.godot.resolve()
    if not godot.is_file():
        parser.error(f"Godot binary does not exist: {godot}")
    results: list[dict[str, object]] = []
    python = sys.executable
    results.append(run("protocol-model", [python, "misc/debugger_v2/test_protocol_model.py"], ROOT))
    results.append(run("session-model", [python, "misc/debugger_v2/test_debug_session_model.py"], ROOT))
    for scenario in SCENARIOS:
        results.append(run(scenario, [python, "misc/debugger_v2/fake_debug_server.py", "--godot", str(godot), "--scenario", scenario], ROOT))
    if not args.skip_editor:
        results.append(run("godot-editor", [python, "misc/debugger_v2/test_editor_frontend.py", "--godot", str(godot)], ROOT))
    if not args.skip_vscode:
        plugin = args.plugin.resolve()
        if not (plugin / "package.json").is_file():
            parser.error(f"GodotTools checkout does not exist: {plugin}")
        npm = "npm.cmd" if os.name == "nt" else "npm"
        results.append(run("vscode-unit", [npm, "run", "test:debugger-v2"], plugin))
        env = os.environ.copy()
        env["GODOT3_V2_PATH"] = str(godot)
        started = time.perf_counter()
        completed = subprocess.run([npm, "run", "test:debugger-v2:integration"], cwd=plugin, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=env, check=False)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
        print(f"[vscode-integration] {elapsed_ms:.0f} ms")
        print_output(output)
        if completed.returncode != 0:
            raise RuntimeError(f"vscode-integration failed with exit code {completed.returncode}")
        results.append({"name": "vscode-integration", "duration_ms": round(elapsed_ms, 3), "output": output})

    report = {"godot": str(godot), "plugin": str(args.plugin.resolve()), "tests": results}
    if args.report:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report: {report_path}")
    print(f"Debugger protocol v2 integration suite: PASS ({len(results)} gates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
