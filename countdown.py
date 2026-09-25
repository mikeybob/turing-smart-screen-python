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

# Countdown / pomodoro. Owns the panel while it runs; do not start it beside main.py.

from library.pythoncheck import check_python_version
check_python_version()

import argparse
import math
import os
import signal
import sys
import time

from library.lcd.lcd_comm import Orientation
from library.log import logger

# Same pair simple-program.py draws in its refresh loop: a clock string and one radial gauge.
_TEXT_XY = (160, 2)
_RADIAL = (98, 260, 25, 4)  # xc, yc, radius, bar width
_FONT = "res/fonts/roboto/Roboto-Bold.ttf"
_FONT_SIZE = 20
DEFAULT_MINUTES = 25

stop = False


def _sighandler(signum, frame):
    global stop
    stop = True


def parse_minutes(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Countdown / pomodoro for a Turing smart screen. "
                    "Uses the display revision from config.yaml (REVISION: SIMU writes screencap.png)."
    )
    parser.add_argument(
        "minutes",
        nargs="?",
        type=int,
        default=DEFAULT_MINUTES,
        help=f"Countdown length in minutes (default: {DEFAULT_MINUTES})",
    )
    args = parser.parse_args(argv)
    if args.minutes < 0:
        parser.error("minutes must be a non-negative integer")
    return args.minutes


def format_remaining(seconds: int) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{secs:02d}"


def _place(lcd):
    """Keep the simple-program.py coordinates when they fit; otherwise center the same pair."""
    width, height = lcd.get_width(), lcd.get_height()
    text_x, text_y = _TEXT_XY
    xc, yc, radius, bar_width = _RADIAL
    text_w, text_h = 8 * _FONT_SIZE, _FONT_SIZE + 8
    if (xc - radius < 0 or yc - radius < 0 or xc + radius > width or yc + radius > height
            or text_x + text_w > width or text_y + text_h > height):
        radius = max(8, min(radius, width // 2 - 1, height // 2 - 1))
        bar_width = max(1, min(bar_width, radius))
        xc = width // 2
        yc = height // 2
        text_x = max(0, min(text_x, width - text_w))
        text_y = max(0, min(text_y, yc - radius - text_h))
    return text_x, text_y, text_w, text_h, xc, yc, radius, bar_width


def draw(lcd, background, remaining_s: int, total_s: int):
    # The ring fills with elapsed time, so 00:00 is a full gauge.
    if total_s <= 0:
        gauge_max, gauge_value = 1, 1
    else:
        gauge_max = total_s
        gauge_value = total_s - remaining_s

    text_x, text_y, text_w, text_h, xc, yc, radius, bar_width = _place(lcd)
    lcd.DisplayText(
        format_remaining(remaining_s),
        text_x, text_y,
        width=text_w,
        height=text_h,
        font=_FONT,
        font_size=_FONT_SIZE,
        font_color=(255, 0, 0),
        background_color=(255, 255, 255),
        background_image=background,
        align="left",
    )
    lcd.DisplayRadialProgressBar(
        xc, yc, radius, bar_width,
        min_value=0,
        max_value=gauge_max,
        value=gauge_value,
        angle_sep=0,
        bar_color=(0, 255, 0),
        font_color=(255, 255, 255),
        background_color=(255, 255, 255),
        background_image=background,
        with_text=False,
        draw_bar_background=True,
        bar_background_color=(180, 180, 180),
    )


def _background_for(lcd):
    background = f"res/backgrounds/example_{lcd.get_width()}x{lcd.get_height()}.png"
    if os.path.isfile(background):
        lcd.DisplayBitmap(background)
        return background
    return None


def run(lcd_display, minutes: int):
    if lcd_display.lcd is None:
        logger.error("Display was not created. Check display.REVISION in config.yaml.")
        sys.exit(1)

    # This process owns the panel. Write in order here instead of queueing for main.py's scheduler.
    lcd_display.lcd.update_queue = None
    lcd_display.initialize_display()
    lcd = lcd_display.lcd
    lcd.SetOrientation(orientation=Orientation.LANDSCAPE)

    total_s = minutes * 60
    deadline = time.monotonic() + total_s
    background = _background_for(lcd)
    shown = None

    while not stop:
        remaining = deadline - time.monotonic()
        remaining_s = math.ceil(remaining) if remaining > 0 else 0
        if remaining_s != shown:
            draw(lcd, background, remaining_s, total_s)
            shown = remaining_s
            if remaining_s == 0:
                logger.info("Countdown finished (00:00, gauge full)")
        time.sleep(0.2)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)
    if os.name == "posix":
        signal.signal(signal.SIGQUIT, _sighandler)

    minutes = parse_minutes()
    # Open the display only after the CLI is accepted. Importing the factory
    # selects the driver from config.yaml (including REVISION: SIMU).
    from library.display import display

    logger.info("Countdown %s (%d minute%s). Stop with Ctrl+C.",
                format_remaining(minutes * 60), minutes, "" if minutes == 1 else "s")
    try:
        run(display, minutes)
    finally:
        if display.lcd is not None:
            display.lcd.closeSerial()
