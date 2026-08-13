"""Level arithmetic and display formatting edge cases."""

from __future__ import annotations

import pytest

from printer_monitor import printer_mib as mib
from printer_monitor.models import MediaInput, PrinterReading, Supply


def supply(**kwargs) -> Supply:
    defaults = dict(index=1, description="Cyan", unit_code=19, level_raw=50, max_capacity_raw=100)
    defaults.update(kwargs)
    return Supply(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Percentages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level,capacity,expected",
    [
        (100, 100, 100.0),
        (50, 100, 50.0),
        (0, 100, 0.0),
        (1, 100, 1.0),
        (5425, 7750, 70.0),  # tenths of a millilitre
        (30_000, 200_000, 15.0),  # impressions
        (1, 3, 33.3),
    ],
)
def test_remaining_percent(level, capacity, expected):
    assert supply(level_raw=level, max_capacity_raw=capacity).remaining_percent == expected


@pytest.mark.parametrize("level", [mib.LEVEL_OTHER, mib.LEVEL_UNKNOWN, mib.LEVEL_SOME_REMAINING])
def test_negative_levels_have_no_percentage(level):
    assert supply(level_raw=level).remaining_percent is None


def test_zero_capacity_has_no_percentage():
    """Dividing by a zero or unknown capacity must not blow up."""
    # unit 15 = tenths of a millilitre, so there is no capacity to infer.
    assert supply(unit_code=15, max_capacity_raw=0).remaining_percent is None
    assert supply(unit_code=15, max_capacity_raw=-2).remaining_percent is None


def test_percent_unit_infers_a_capacity_of_100():
    """Level is already a percentage, so an unknown capacity is still usable."""
    assert supply(unit_code=19, max_capacity_raw=-2, level_raw=50).remaining_percent == 50.0
    assert supply(unit_code=19, max_capacity_raw=0, level_raw=12).remaining_percent == 12.0
    # ...but only when the level is a plausible percentage.
    assert supply(unit_code=19, max_capacity_raw=-2, level_raw=4000).remaining_percent is None


def test_level_above_capacity_is_clamped():
    """Some HP firmware reports 105 of 100 just after a swap."""
    assert supply(level_raw=105, max_capacity_raw=100).remaining_percent == 100.0


def test_level_states():
    assert supply(level_raw=50).level_state == "ok"
    assert supply(level_raw=mib.LEVEL_SOME_REMAINING).level_state == "some"
    assert supply(level_raw=mib.LEVEL_UNKNOWN).level_state == "unknown"
    assert supply(level_raw=mib.LEVEL_OTHER).level_state == "unknown"


def test_level_text():
    assert supply(level_raw=42).level_text == "42%"
    assert supply(level_raw=mib.LEVEL_SOME_REMAINING).level_text == "Some remaining"
    assert supply(level_raw=mib.LEVEL_OTHER).level_text == "Present"
    assert supply(level_raw=mib.LEVEL_UNKNOWN).level_text == "Unknown"


# ---------------------------------------------------------------------------
# Waste receptacles
# ---------------------------------------------------------------------------


def test_receptacle_class_inverts_the_level():
    cartridge = supply(class_code=4, level_raw=90, max_capacity_raw=100)
    assert cartridge.is_waste
    assert cartridge.remaining_percent == 10.0


def test_waste_type_inverts_even_when_the_class_is_wrong():
    """Some firmware labels a waste-ink receptacle as class 3; the type decides."""
    for type_code in (4, 8, 14, 24, 26):
        cartridge = supply(type_code=type_code, class_code=3, level_raw=80)
        assert cartridge.is_waste, type_code
        assert cartridge.remaining_percent == 20.0


def test_consumable_is_not_treated_as_waste():
    assert not supply(type_code=6, class_code=3).is_waste
    assert not supply(type_code=21, class_code=3).is_waste  # toner cartridge


# ---------------------------------------------------------------------------
# Capacity formatting
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "unit,capacity,expected",
    [
        (15, 7750, "775 ml"),  # tenths of a millilitre
        (14, 2620, "26.2 fl oz"),  # hundredths of a fluid ounce
        (13, 4500, "450 g"),  # tenths of a gram
        (8, 500, "500 sheets"),
        (7, 200_000, "200,000 impressions"),
        (11, 1500, "1,500 hours"),
        (18, 12, "12 items"),
        (17, 45, "45 m"),
        (19, 100, ""),  # percent needs no capacity label
    ],
)
def test_capacity_text(unit, capacity, expected):
    assert supply(unit_code=unit, max_capacity_raw=capacity).capacity_text == expected


def test_capacity_text_is_blank_when_unknown():
    assert supply(max_capacity_raw=-2).capacity_text == ""


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def test_display_name_prefers_the_printer_description():
    assert supply(description="HP 831 Latex Cyan").display_name == "HP 831 Latex Cyan"


def test_display_name_falls_back_to_type_and_colour():
    nameless = supply(description="", type_code=6)
    assert nameless.display_name == "Ink cartridge #1"


def test_key_is_slugified_and_index_independent():
    assert supply(description="HP 831 Latex Light Cyan").key == "hp-831-latex-light-cyan"
    assert supply(description="  Spaced   Out  ").key == "spaced-out"
    assert supply(description="", index=4).key == "supply-4"


def test_colour_detection_prefers_longer_names():
    assert supply(description="HP Light Cyan").color == "Light Cyan"
    assert supply(description="HP Cyan").color == "Cyan"
    assert supply(description="Photo Black ink").color == "Photo Black"
    assert supply(description="Maintenance Cartridge").color is None


def test_colorant_table_value_is_used_when_present():
    assert supply(description="Cartridge 1", colorant="magenta").color == "Magenta"


def test_supply_type_names():
    assert mib.supply_type_name(3) == "Toner"
    assert mib.supply_type_name(8) == "Waste ink"
    assert mib.supply_type_name(999) == "Type 999"
    assert mib.supply_type_name(None) == "Unknown"


# ---------------------------------------------------------------------------
# Media inputs
# ---------------------------------------------------------------------------


def test_media_input_percent_and_text():
    tray = MediaInput(index=2, name="Tray 2", level_raw=250, max_capacity_raw=500)
    assert tray.remaining_percent == 50.0
    assert tray.level_text == "50%"
    assert not tray.is_empty


def test_empty_tray_reads_as_empty_not_zero_percent():
    tray = MediaInput(index=3, name="Tray 3", level_raw=0, max_capacity_raw=500)
    assert tray.is_empty
    assert tray.level_text == "Empty"


def test_roll_with_unknown_capacity():
    roll = MediaInput(index=1, name="Roll 1", level_raw=-3, max_capacity_raw=-2)
    assert roll.remaining_percent is None
    assert roll.level_text == "Loaded"


def test_media_key_is_namespaced():
    assert MediaInput(index=1, name="Tray 2").key == "tray-tray-2"


# ---------------------------------------------------------------------------
# Detected error bits
# ---------------------------------------------------------------------------


def test_decode_detected_errors_bit_positions():
    assert mib.decode_detected_errors(b"\x80") == ["low paper"]
    assert mib.decode_detected_errors(b"\x40") == ["no paper"]
    assert mib.decode_detected_errors(b"\x20") == ["low toner"]
    assert mib.decode_detected_errors(b"\x04\x00") == ["jammed"]
    # byte 1 bit 5 -> position 13
    assert mib.decode_detected_errors(b"\x00\x04") == ["input tray empty"]


def test_decode_detected_errors_multiple_bits():
    states = mib.decode_detected_errors(b"\x20\x04")
    assert states == ["low toner", "input tray empty"]


def test_decode_detected_errors_handles_empty_and_junk():
    assert mib.decode_detected_errors(b"") == []
    assert mib.decode_detected_errors(b"\x00\x00") == []
    assert mib.decode_detected_errors(None) == []
    assert mib.decode_detected_errors(12.5) == []


def test_decode_detected_errors_ignores_bits_past_the_known_list():
    assert mib.decode_detected_errors(b"\x00\x00\xff") == []


# ---------------------------------------------------------------------------
# Reading summary
# ---------------------------------------------------------------------------


def test_status_text_variants():
    offline = PrinterReading(printer_id="p", printer_name="P", host="h", online=False)
    assert offline.status_text == "Offline"

    idle = PrinterReading(printer_id="p", printer_name="P", host="h", online=True, printer_status_code=3)
    assert idle.status_text == "Idle"

    jammed = PrinterReading(
        printer_id="p",
        printer_name="P",
        host="h",
        online=True,
        printer_status_code=3,
        detected_errors=["jammed", "door open"],
    )
    assert jammed.status_text == "Idle — jammed, door open"
    assert jammed.has_error_state

    bare = PrinterReading(printer_id="p", printer_name="P", host="h", online=True)
    assert bare.status_text == "Online"


def test_supply_lookup_by_key():
    reading = PrinterReading(
        printer_id="p",
        printer_name="P",
        host="h",
        online=True,
        supplies=[supply(description="HP 831 Latex Cyan")],
    )
    assert reading.supply_by_key("hp-831-latex-cyan") is not None
    assert reading.supply_by_key("nope") is None
