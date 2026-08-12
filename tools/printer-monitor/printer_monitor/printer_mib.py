"""Printer MIB (RFC 3805) OIDs and textual conventions.

Both target printers implement the standard Printer MIB, so the monitor
discovers whatever supplies each device reports rather than hardcoding a
per-model list. That means the HP Latex 360's inks, printheads and maintenance
cartridge and the LaserJet 4100's toner, fuser and rollers all come through the
same code path.
"""

from __future__ import annotations

# --- System group (RFC 1213) ----------------------------------------------
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_CONTACT = "1.3.6.1.2.1.1.4.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

# --- Host Resources printer status (RFC 2790) -----------------------------
HR_DEVICE_STATUS = "1.3.6.1.2.1.25.3.2.1.5.1"
HR_PRINTER_STATUS = "1.3.6.1.2.1.25.3.5.1.1.1"
HR_PRINTER_DETECTED_ERROR_STATE = "1.3.6.1.2.1.25.3.5.1.2.1"

# --- Printer MIB: general -------------------------------------------------
PRT_GENERAL_PRINTER_NAME = "1.3.6.1.2.1.43.5.1.1.16.1"
PRT_GENERAL_SERIAL_NUMBER = "1.3.6.1.2.1.43.5.1.1.17.1"
PRT_CONSOLE_DISPLAY_BUFFER = "1.3.6.1.2.1.43.16.5.1.2"  # table: .1.<index>

# --- Printer MIB: marker (page counts) ------------------------------------
PRT_MARKER_LIFE_COUNT = "1.3.6.1.2.1.43.10.2.1.4"  # table: .1.<marker>
PRT_MARKER_POWER_ON_COUNT = "1.3.6.1.2.1.43.10.2.1.5"
PRT_MARKER_COUNTER_UNIT = "1.3.6.1.2.1.43.10.2.1.3"

# --- Printer MIB: supplies table (prtMarkerSuppliesEntry) -----------------
PRT_SUPPLIES_CLASS = "1.3.6.1.2.1.43.11.1.1.4"
PRT_SUPPLIES_TYPE = "1.3.6.1.2.1.43.11.1.1.5"
PRT_SUPPLIES_DESCRIPTION = "1.3.6.1.2.1.43.11.1.1.6"
PRT_SUPPLIES_UNIT = "1.3.6.1.2.1.43.11.1.1.7"
PRT_SUPPLIES_MAX_CAPACITY = "1.3.6.1.2.1.43.11.1.1.8"
PRT_SUPPLIES_LEVEL = "1.3.6.1.2.1.43.11.1.1.9"
PRT_SUPPLIES_COLORANT_INDEX = "1.3.6.1.2.1.43.11.1.1.3"

# --- Printer MIB: colorant table ------------------------------------------
PRT_COLORANT_VALUE = "1.3.6.1.2.1.43.12.1.1.4"

# --- Printer MIB: input (paper/substrate) ---------------------------------
PRT_INPUT_TYPE = "1.3.6.1.2.1.43.8.2.1.2"
PRT_INPUT_MAX_CAPACITY = "1.3.6.1.2.1.43.8.2.1.9"
PRT_INPUT_CURRENT_LEVEL = "1.3.6.1.2.1.43.8.2.1.10"
PRT_INPUT_STATUS = "1.3.6.1.2.1.43.8.2.1.11"
PRT_INPUT_MEDIA_NAME = "1.3.6.1.2.1.43.8.2.1.12"
PRT_INPUT_NAME = "1.3.6.1.2.1.43.8.2.1.13"
PRT_INPUT_DESCRIPTION = "1.3.6.1.2.1.43.8.2.1.18"
PRT_INPUT_DIM_UNIT = "1.3.6.1.2.1.43.8.2.1.3"

# --- Printer MIB: output bins ---------------------------------------------
PRT_OUTPUT_MAX_CAPACITY = "1.3.6.1.2.1.43.9.2.1.4"
PRT_OUTPUT_REMAINING_CAPACITY = "1.3.6.1.2.1.43.9.2.1.5"
PRT_OUTPUT_STATUS = "1.3.6.1.2.1.43.9.2.1.6"
PRT_OUTPUT_NAME = "1.3.6.1.2.1.43.9.2.1.7"
PRT_OUTPUT_DESCRIPTION = "1.3.6.1.2.1.43.9.2.1.18"

# --- Printer MIB: alert table --------------------------------------------
PRT_ALERT_SEVERITY = "1.3.6.1.2.1.43.18.1.1.2"
PRT_ALERT_TRAINING_LEVEL = "1.3.6.1.2.1.43.18.1.1.4"
PRT_ALERT_GROUP = "1.3.6.1.2.1.43.18.1.1.5"
PRT_ALERT_LOCATION = "1.3.6.1.2.1.43.18.1.1.6"
PRT_ALERT_CODE = "1.3.6.1.2.1.43.18.1.1.7"
PRT_ALERT_DESCRIPTION = "1.3.6.1.2.1.43.18.1.1.8"
PRT_ALERT_TIME = "1.3.6.1.2.1.43.18.1.1.9"

# ---------------------------------------------------------------------------
# Special level values (prtMarkerSuppliesLevel / prtInputCurrentLevel)
# ---------------------------------------------------------------------------
LEVEL_OTHER = -1  # capacity/level not in the listed units
LEVEL_UNKNOWN = -2  # printer genuinely does not know
LEVEL_SOME_REMAINING = -3  # "some left" but no number (very common on HP)

# ---------------------------------------------------------------------------
# Textual conventions
# ---------------------------------------------------------------------------

SUPPLY_CLASS = {
    1: "other",
    3: "consumed",  # supplyThatIsConsumed  -> level counts down
    4: "receptacle",  # receptacleThatIsFilled -> level counts up (waste)
}

SUPPLY_TYPE = {
    1: "Other",
    2: "Unknown",
    3: "Toner",
    4: "Waste toner",
    5: "Ink",
    6: "Ink cartridge",
    7: "Ink ribbon",
    8: "Waste ink",
    9: "Drum (OPC)",
    10: "Developer",
    11: "Fuser oil",
    12: "Solid wax",
    13: "Ribbon wax",
    14: "Waste wax",
    15: "Fuser",
    16: "Corona wire",
    17: "Fuser oil wick",
    18: "Cleaner unit",
    19: "Fuser cleaning pad",
    20: "Transfer unit",
    21: "Toner cartridge",
    22: "Fuser oiler",
    23: "Water",
    24: "Waste water",
    25: "Glue water additive",
    26: "Waste paper",
    27: "Binding supply",
    28: "Banding supply",
    29: "Stitching wire",
    30: "Shrink wrap",
    31: "Paper wrap",
    32: "Staples",
    33: "Inserts",
    34: "Covers",
}

# Supply types that are waste receptacles no matter what class the firmware
# reports (some HP firmware mislabels these).
WASTE_TYPES = {4, 8, 14, 24, 26}

SUPPLY_UNIT = {
    1: "other",
    2: "unknown",
    3: "ten-thousandths of an inch",
    4: "micrometers",
    7: "impressions",
    8: "sheets",
    11: "hours",
    12: "thousandths of an ounce",
    13: "tenths of a gram",
    14: "hundredths of a fluid ounce",
    15: "tenths of a milliliter",
    16: "feet",
    17: "meters",
    18: "items",
    19: "percent",
}

UNIT_PERCENT = 19

INPUT_STATUS_AVAILABLE = {
    0: "available and idle",
    1: "available and standby",
    2: "available and active",
    3: "available and busy",
    4: "unavailable and on request",
    5: "unavailable because broken",
    6: "unknown",
}

PRINTER_STATUS = {
    1: "other",
    2: "unknown",
    3: "idle",
    4: "printing",
    5: "warming up",
}

DEVICE_STATUS = {
    1: "unknown",
    2: "running",
    3: "warning",
    4: "testing",
    5: "down",
}

# hrPrinterDetectedErrorState is a bit string; bit 0 is the MSB of byte 0.
DETECTED_ERROR_BITS = [
    "low paper",
    "no paper",
    "low toner",
    "no toner",
    "door open",
    "jammed",
    "offline",
    "service requested",
    "input tray missing",
    "output tray missing",
    "marker supply missing",
    "output near full",
    "output full",
    "input tray empty",
    "overdue prevent maintenance",
]

ALERT_SEVERITY = {
    1: "other",
    3: "critical",
    4: "warning",
    5: "warning (binary change)",
}

ALERT_GROUP = {
    1: "other",
    3: "host resources",
    4: "general printer",
    5: "cover",
    6: "localization",
    8: "input tray",
    9: "output tray",
    10: "marker",
    11: "marker supplies",
    12: "marker colorant",
    13: "media path",
    14: "channel",
    15: "interpreter",
    16: "console",
    17: "alert",
    18: "finisher device",
    19: "finisher supply",
    20: "finisher supply media input",
    30: "input",
    31: "output",
}


def decode_detected_errors(value: object) -> list[str]:
    """Turn hrPrinterDetectedErrorState octets into human-readable states."""
    if isinstance(value, str):
        raw = value.encode("latin-1", errors="ignore")
    elif isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, int):
        raw = value.to_bytes(2, "big", signed=False) if value >= 0 else b""
    else:
        return []
    states: list[str] = []
    for byte_index, byte in enumerate(raw):
        for bit in range(8):
            if byte & (0x80 >> bit):
                position = byte_index * 8 + bit
                if position < len(DETECTED_ERROR_BITS):
                    states.append(DETECTED_ERROR_BITS[position])
    return states


def supply_type_name(code: object) -> str:
    if isinstance(code, int):
        return SUPPLY_TYPE.get(code, f"Type {code}")
    return "Unknown"


def is_waste_receptacle(type_code: object, class_code: object) -> bool:
    """True when the reported level means "how full" rather than "how much left"."""
    if isinstance(type_code, int) and type_code in WASTE_TYPES:
        return True
    return class_code == 4


# ---------------------------------------------------------------------------
# Colour naming
# ---------------------------------------------------------------------------

_COLOR_KEYWORDS = [
    ("light cyan", "Light Cyan"),
    ("light magenta", "Light Magenta"),
    ("photo black", "Photo Black"),
    ("matte black", "Matte Black"),
    ("light black", "Light Black"),
    ("light gray", "Light Gray"),
    ("light grey", "Light Gray"),
    ("optimizer", "Optimizer"),
    ("overcoat", "Overcoat"),
    ("gloss", "Gloss Enhancer"),
    ("cyan", "Cyan"),
    ("magenta", "Magenta"),
    ("yellow", "Yellow"),
    ("black", "Black"),
    ("gray", "Gray"),
    ("grey", "Gray"),
    ("orange", "Orange"),
    ("green", "Green"),
    ("violet", "Violet"),
    ("blue", "Blue"),
    ("red", "Red"),
    ("white", "White"),
]

# Hex swatches used by the dashboard.
COLOR_SWATCHES = {
    "Cyan": "#00b7eb",
    "Light Cyan": "#8fdcf3",
    "Magenta": "#e5007e",
    "Light Magenta": "#f49ac1",
    "Yellow": "#ffdd00",
    "Black": "#1a1a1a",
    "Photo Black": "#1a1a1a",
    "Matte Black": "#2b2b2b",
    "Light Black": "#555555",
    "Gray": "#8a8a8a",
    "Light Gray": "#bdbdbd",
    "Optimizer": "#9fd8cb",
    "Overcoat": "#cfe8e2",
    "Gloss Enhancer": "#cfe8e2",
    "Orange": "#ff7a00",
    "Green": "#00a651",
    "Violet": "#6b3fa0",
    "Blue": "#0057b8",
    "Red": "#e03127",
    "White": "#f5f5f5",
}


def guess_color(description: str, colorant: str | None = None) -> str | None:
    """Pull a colour name out of a supply description.

    ``"HP 831 Latex Light Cyan"`` -> ``"Light Cyan"``. Checked longest-first so
    "light cyan" wins over "cyan".
    """
    for source in (colorant or "", description or ""):
        haystack = source.lower()
        for needle, label in _COLOR_KEYWORDS:
            if needle in haystack:
                return label
    return None
