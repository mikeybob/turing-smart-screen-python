#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Start one process per 3.5" panel described in screens.yaml.
# The connected panel is pinned to a fixed COM port. Panels whose
# device node is missing are skipped.

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
RUN_DIR = ROOT / "screens" / "run"


def load_screens(path: Path) -> list:
    with path.open(encoding="utf8") as stream:
        data = yaml.safe_load(stream) or {}
    return list(data.get("screens") or [])


def port_ready(com_port: str) -> bool:
    port = (com_port or "").strip()
    if not port or port.upper() == "AUTO":
        return False
    return Path(port).exists()


def plan_screens(screens: list) -> tuple:
    start = []
    skipped = []
    for screen in screens:
        port = str(screen.get("com_port") or "").strip()
        if port_ready(port):
            start.append(screen)
        else:
            skipped.append(screen)
    return start, skipped


def write_monitor_config(screen: dict, base_config: Path, dest: Path) -> None:
    with base_config.open(encoding="utf8") as stream:
        config = yaml.safe_load(stream)
    config.setdefault("config", {})
    config.setdefault("display", {})
    config["config"]["COM_PORT"] = screen["com_port"]
    config["config"]["THEME"] = screen.get("theme") or "LandscapeMagicBlue"
    # A revision A reset renumerates the COM port and would miss a pinned path.
    config["display"]["RESET_ON_STARTUP"] = False
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf8") as stream:
        yaml.safe_dump(config, stream, sort_keys=False)


def command_for(screen: dict, config_path: Path) -> list:
    kind = screen.get("kind")
    port = screen["com_port"]
    if kind == "monitor":
        return [sys.executable, str(ROOT / "main.py")]
    if kind == "calendar":
        return [sys.executable, str(ROOT / "glance.py"), "calendar", "--port", port,
                "--config", str(config_path)]
    if kind == "services":
        return [sys.executable, str(ROOT / "glance.py"), "services", "--port", port,
                "--config", str(config_path),
                "--screens", str(ROOT / "screens.yaml")]
    raise ValueError(f"Unknown screen kind: {kind}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one job on each connected 3.5\" panel")
    parser.add_argument("--screens", type=Path, default=ROOT / "screens.yaml")
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    screens = load_screens(args.screens)
    start, skipped = plan_screens(screens)
    for screen in skipped:
        port = screen.get("com_port") or "(none)"
        print(f"skip {screen.get('name')}: {port} is not connected")

    if not start:
        print("No panels connected.")
        return 0

    processes = []
    for screen in start:
        generated = RUN_DIR / f"{screen['name']}.yaml"
        cmd = command_for(screen, args.config)
        print(f"start {screen['name']} on {screen['com_port']}: {' '.join(cmd)}")
        if args.dry_run:
            continue
        if screen.get("kind") == "monitor":
            write_monitor_config(screen, args.config, generated)
        env = os.environ.copy()
        env["TSS_CONFIG"] = str(generated if screen.get("kind") == "monitor" else args.config)
        processes.append(subprocess.Popen(cmd, cwd=ROOT, env=env))

    if args.dry_run or not processes:
        return 0

    def stop(_signum, _frame):
        for proc in processes:
            proc.terminate()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    code = 0
    for proc in processes:
        ret = proc.wait()
        if ret not in (0, -signal.SIGTERM, -signal.SIGINT):
            code = ret if isinstance(ret, int) and ret > 0 else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
