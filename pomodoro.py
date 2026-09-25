#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Countdown for one smart screen: a radial gauge and the remaining time.
# Revision, size, and COM port come from config.yaml. One process owns one panel.

from library.pythoncheck import check_python_version
check_python_version()

import argparse
import math
import os
import signal
import sys
import time

from PIL import Image

from library import config
from library.log import logger

DEFAULT_MINUTES = 25
FONT = config.FONTS_DIR + "jetbrains-mono/JetBrainsMono-Bold.ttf"
BACKGROUND = (20, 22, 28)
BAR_COLOR = (46, 204, 113)
TRACK_COLOR = (55, 60, 70)
TEXT_COLOR = (255, 255, 255)

stop = False


def sighandler(signum, frame):
    global stop
    stop = True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Show a pomodoro countdown on one Turing smart screen."
    )
    parser.add_argument(
        "--minutes",
        type=int,
        default=DEFAULT_MINUTES,
        help=f"Countdown length in minutes (default: {DEFAULT_MINUTES})",
    )
    parser.add_argument(
        "--port",
        default=None,
        help="COM port for this panel, overriding COM_PORT in config.yaml "
             "(for example COM5 or /dev/ttyACM0). Run a separate process for each panel.",
    )
    args = parser.parse_args(argv)
    if args.minutes < 1:
        parser.error("--minutes must be >= 1")
    if args.port is not None and not args.port.strip():
        parser.error("--port must not be empty")
    return args


def format_remaining(seconds, total):
    seconds = max(0, int(seconds))
    if total >= 100 * 60:
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    minutes, secs = divmod(seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def gauge_layout(width, height):
    """Place one radial and a fixed text band so both fit the theme size."""
    font_size = max(12, min(48, width // 8))
    text_h = int(font_size * 1.4)
    margin = max(2, min(width, height) // 40)
    avail_h = height - text_h - margin
    radius = min((width // 2) - margin, avail_h // 2)
    if radius < 8:
        return None
    bar_width = max(2, min(radius // 6, 18))
    block_h = (2 * radius) + margin + text_h
    top = max(0, (height - block_h) // 2)
    yc = top + radius
    return {
        "xc": width // 2,
        "yc": yc,
        "radius": radius,
        "bar_width": bar_width,
        "font_size": font_size,
        "text_x": margin,
        "text_y": yc + radius + margin,
        "text_w": width - (2 * margin),
        "text_h": text_h,
    }


def paint(lcd, layout, remaining, total):
    lcd.DisplayRadialProgressBar(
        layout["xc"], layout["yc"], layout["radius"], layout["bar_width"],
        min_value=0,
        max_value=total,
        angle_start=270,
        angle_end=270,
        angle_sep=0,
        clockwise=True,
        value=remaining,
        with_text=False,
        bar_color=BAR_COLOR,
        background_color=BACKGROUND,
        draw_bar_background=True,
        bar_background_color=TRACK_COLOR,
    )
    lcd.DisplayText(
        format_remaining(remaining, total),
        layout["text_x"],
        layout["text_y"],
        width=layout["text_w"],
        height=layout["text_h"],
        font=FONT,
        font_size=layout["font_size"],
        font_color=TEXT_COLOR,
        background_color=BACKGROUND,
        align="center",
        anchor="mm",
    )


def remaining_seconds(deadline, total, now=None):
    if now is None:
        now = time.monotonic()
    left = deadline - now
    if left <= 0:
        return 0
    return min(total, math.ceil(left))


def run_countdown(lcd, total):
    width, height = lcd.get_width(), lcd.get_height()
    layout = gauge_layout(width, height)
    if layout is None:
        logger.error("Display %sx%s is too small for the countdown gauge", width, height)
        return 1

    lcd.DisplayPILImage(Image.new("RGB", (width, height), BACKGROUND), 0, 0)
    deadline = time.monotonic() + total
    while not stop:
        remaining = remaining_seconds(deadline, total)
        paint(lcd, layout, remaining, total)
        if remaining <= 0 or stop:
            break
        delay = (deadline - (remaining - 1)) - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, 1.0))

    if remaining_seconds(deadline, total) <= 0 and not stop:
        logger.info("Countdown finished")
    while not stop:
        time.sleep(0.25)
    return 0


def main(argv=None):
    args = parse_args(argv)

    # simple-program.py writes synchronously because update_queue is None.
    # The display factory reads the queue when it is imported.
    config.update_queue = None
    if args.port:
        config.CONFIG_DATA["config"]["COM_PORT"] = args.port

    from library.display import display

    signal.signal(signal.SIGINT, sighandler)
    signal.signal(signal.SIGTERM, sighandler)
    if os.name == "posix":
        signal.signal(signal.SIGQUIT, sighandler)

    lcd = display.lcd
    if lcd is None:
        logger.error("Display was not created. Check REVISION in config.yaml.")
        return 1

    total = args.minutes * 60
    logger.info(
        "Countdown %s min (%s) on revision %s, COM port %s",
        args.minutes,
        format_remaining(total, total),
        config.CONFIG_DATA["display"]["REVISION"],
        config.CONFIG_DATA["config"]["COM_PORT"],
    )

    try:
        display.initialize_display()
        return run_countdown(lcd, total)
    finally:
        lcd.closeSerial()


if __name__ == "__main__":
    sys.exit(main())
