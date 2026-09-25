import os
from pathlib import Path

import yaml

from launch_screens import plan_screens, port_ready, write_monitor_config


def test_auto_and_missing_ports_are_not_ready(tmp_path):
    assert port_ready("") is False
    assert port_ready("AUTO") is False
    assert port_ready(str(tmp_path / "missing")) is False


def test_existing_port_is_ready(tmp_path):
    port = tmp_path / "ttyACM2"
    port.write_text("")
    assert port_ready(str(port)) is True


def test_plan_starts_only_connected_panels(tmp_path):
    live = tmp_path / "ttyACM2"
    live.write_text("")
    screens = [
        {"name": "stats", "com_port": str(live)},
        {"name": "calendar", "com_port": ""},
        {"name": "services", "com_port": str(tmp_path / "absent")},
    ]
    start, skipped = plan_screens(screens)
    assert [s["name"] for s in start] == ["stats"]
    assert [s["name"] for s in skipped] == ["calendar", "services"]


def test_monitor_config_pins_port_and_skips_reset(tmp_path):
    base = tmp_path / "config.yaml"
    base.write_text("config:\n  COM_PORT: AUTO\n  THEME: 3.5inchTheme2\ndisplay:\n  BRIGHTNESS: 50\n  RESET_ON_STARTUP: true\n")
    dest = tmp_path / "run" / "stats.yaml"
    write_monitor_config(
        {"com_port": "/dev/ttyACM2", "theme": "LandscapeMagicBlue"},
        base,
        dest,
    )
    data = yaml.safe_load(dest.read_text())
    assert data["config"]["COM_PORT"] == "/dev/ttyACM2"
    assert data["config"]["THEME"] == "LandscapeMagicBlue"
    assert data["display"]["RESET_ON_STARTUP"] is False
    assert data["display"]["BRIGHTNESS"] == 50


def test_repo_screens_pin_the_connected_panel():
    root = Path(__file__).resolve().parents[1]
    data = yaml.safe_load((root / "screens.yaml").read_text())
    by_name = {s["name"]: s for s in data["screens"]}
    assert by_name["stats"]["com_port"] == "/dev/ttyACM2"
    assert by_name["stats"]["theme"] == "LandscapeMagicBlue"
    assert by_name["calendar"]["kind"] == "calendar"
    assert by_name["services"]["targets"][0]["host"] == "8.8.8.8"
    assert os.environ.get("TSS_CONFIG", "") == ""
