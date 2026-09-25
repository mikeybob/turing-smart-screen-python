#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Clock/calendar and red/green service boards for a revision A 3.5" panel.
# Drawing is a short loop around LcdCommRevA. The system-monitor theme stays
# on its own process.

import argparse
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "res" / "fonts" / "roboto" / "Roboto-Bold.ttf"
FONT_REG = ROOT / "res" / "fonts" / "roboto" / "Roboto-Regular.ttf"
BG = (8, 16, 28)
FG = (220, 236, 245)
MUTED = (140, 160, 176)
UP = (40, 200, 90)
DOWN = (220, 50, 50)
WIDTH = 480
HEIGHT = 320


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf8") as stream:
        return yaml.safe_load(stream) or {}


def brightness_from(config_path: Path) -> int:
    try:
        return int(load_yaml(config_path).get("display", {}).get("BRIGHTNESS", 50))
    except (OSError, TypeError, ValueError):
        return 50


def service_targets(screens_path: Path) -> list:
    for screen in load_yaml(screens_path).get("screens") or []:
        if screen.get("kind") == "services":
            return list(screen.get("targets") or [])
    return []


def ping_host(host: str, timeout: float = 1.0) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout + 1,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def probe_targets(targets: list) -> list:
    rows = []
    for target in targets:
        host = str(target.get("host") or "").strip()
        name = str(target.get("name") or host)
        rows.append({"name": name, "host": host, "up": ping_host(host) if host else False})
    return rows


def next_event() -> str:
    """First upcoming event from khal, or a short fallback when it is absent."""
    if shutil.which("khal") is None:
        return "No calendar configured"
    try:
        result = subprocess.run(
            ["khal", "list", "now", "2d"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Calendar unavailable"
    if result.returncode != 0:
        return "Calendar unavailable"
    skip = {"today", "tomorrow", "today:", "tomorrow:"}
    for line in result.stdout.splitlines():
        text = " ".join(line.split())
        if not text or text.lower().rstrip(":") in skip or text.endswith(":"):
            continue
        return text[:42]
    return "Nothing scheduled"


def open_display(port: str, level: int):
    from library.lcd.lcd_comm_rev_a import LcdCommRevA, Orientation

    lcd = LcdCommRevA(com_port=port, display_width=320, display_height=480)
    lcd.InitializeComm()
    lcd.SetBrightness(level=level)
    lcd.SetOrientation(orientation=Orientation.LANDSCAPE)
    lcd.DisplayPILImage(_blank())
    return lcd


def _blank():
    from PIL import Image
    return Image.new("RGB", (WIDTH, HEIGHT), BG)


def _text(lcd, text, x, y, size, color, font=FONT):
    lcd.DisplayText(
        text,
        x,
        y,
        font=str(font),
        font_size=size,
        font_color=color,
        background_color=BG,
    )


def run_calendar(lcd) -> None:
    shown = None
    while True:
        moment = datetime.now()
        _text(lcd, moment.strftime("%H:%M"), 24, 36, 92, FG)
        _text(lcd, moment.strftime("%A %d %B"), 28, 150, 28, MUTED, FONT_REG)
        if shown is None or moment.second == 0:
            shown = next_event()
            _text(lcd, shown, 28, 220, 26, FG, FONT_REG)
        time.sleep(1)


def run_services(lcd, targets: list) -> None:
    while True:
        _text(lcd, "Services", 24, 16, 36, FG)
        rows = probe_targets(targets)
        y = 80
        if not rows:
            _text(lcd, "No targets in screens.yaml", 24, y, 22, MUTED, FONT_REG)
        for row in rows:
            color = UP if row["up"] else DOWN
            state = "UP  " if row["up"] else "DOWN"
            _text(lcd, f"{state}  {row['name']}"[:28], 24, y, 28, color, FONT_REG)
            y += 48
        time.sleep(15)


def main() -> int:
    parser = argparse.ArgumentParser(description="Glance board for one revision A panel")
    parser.add_argument("kind", choices=("calendar", "services"))
    parser.add_argument("--port", required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--screens", type=Path, default=ROOT / "screens.yaml")
    args = parser.parse_args()

    lcd = open_display(args.port, brightness_from(args.config))
    try:
        if args.kind == "calendar":
            run_calendar(lcd)
        else:
            run_services(lcd, service_targets(args.screens))
    except KeyboardInterrupt:
        return 0
    finally:
        lcd.closeSerial()
    return 0


if __name__ == "__main__":
    sys.exit(main())
