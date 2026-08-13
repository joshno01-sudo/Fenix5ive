"""The on-hand supply list — what's on the shelf, tracked with +/- buttons.

Separate from the levels *inside* the printer: the poller reads those, this
tracks spares so you know whether a low cartridge can actually be replaced.
"""

from __future__ import annotations

from typing import Iterable, Optional

from .models import PrinterReading, Supply, SupplyItem
from .storage import Storage

# ---------------------------------------------------------------------------
# Starter lists
# ---------------------------------------------------------------------------
# Part numbers are left blank where they should be confirmed against the
# printer's own supplies page or the label on the box — seeding a wrong P/N is
# worse than seeding none. Once a printer has been polled, seed_from_reading()
# fills the list in using the descriptions the printer itself reports.

LATEX_360_SEED: list[dict[str, object]] = [
    {"name": "Cyan ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Magenta ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Yellow ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Black ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Light Cyan ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Light Magenta ink cartridge (HP 831, 775 ml)", "category": "Ink"},
    {"name": "Optimizer cartridge (HP 831)", "category": "Ink"},
    {"name": "Printhead — Cyan / Black", "category": "Printhead"},
    {"name": "Printhead — Yellow / Magenta", "category": "Printhead"},
    {"name": "Printhead — Light Cyan / Light Magenta", "category": "Printhead"},
    {"name": "Printhead — Optimizer", "category": "Printhead"},
    {"name": "Maintenance cartridge", "category": "Maintenance"},
    {"name": "Printhead cleaning roll", "category": "Maintenance"},
    {"name": "Edge holders", "category": "Parts", "reorder_at": 0},
]

LASERJET_4100_SEED: list[dict[str, object]] = [
    {
        "name": "Black toner cartridge (high yield)",
        "category": "Toner",
        "part_number": "C8061X",
        "notes": "Confirm P/N on the box — C8061X high-yield / C8061A standard.",
    },
    {
        "name": "Maintenance kit (fuser)",
        "category": "Maintenance",
        "notes": "Voltage-specific — confirm the 110V vs 220V P/N before ordering.",
    },
    {"name": "Transfer roller", "category": "Parts", "reorder_at": 0},
    {"name": "Pickup / feed rollers", "category": "Parts", "reorder_at": 0},
]

GENERIC_SEED: list[dict[str, object]] = [
    {"name": "Spare cartridge", "category": "Ink"},
]

SEEDS_BY_PROFILE = {
    "hp_latex": LATEX_360_SEED,
    "hp_laserjet": LASERJET_4100_SEED,
    "generic": GENERIC_SEED,
}

# Supply type code -> supply-list category
CATEGORY_BY_TYPE = {
    3: "Toner",
    4: "Maintenance",
    5: "Ink",
    6: "Ink",
    8: "Maintenance",
    9: "Parts",
    10: "Parts",
    15: "Maintenance",
    18: "Maintenance",
    20: "Parts",
    21: "Toner",
    24: "Maintenance",
    26: "Maintenance",
    32: "Parts",
}


def category_for_supply(supply: Supply) -> str:
    return CATEGORY_BY_TYPE.get(supply.type_code, "Parts")


def seed_defaults(storage: Storage, printer_id: str, profile: str, name_prefix: str = "") -> int:
    """Add the starter rows for a printer profile. Existing rows are left alone."""
    seed = SEEDS_BY_PROFILE.get(profile, GENERIC_SEED)
    added = 0
    for entry in seed:
        name = str(entry["name"])
        if storage.find_item(printer_id, name):
            continue
        storage.upsert_item(
            SupplyItem(
                name=name,
                printer_id=printer_id,
                part_number=str(entry.get("part_number", "")),
                category=str(entry.get("category", "Ink")),
                quantity=int(entry.get("quantity", 0)),
                reorder_at=int(entry.get("reorder_at", 1)),
                unit=str(entry.get("unit", "each")),
                notes=str(entry.get("notes", "")),
            )
        )
        added += 1
    return added


def seed_from_reading(storage: Storage, reading: PrinterReading) -> list[SupplyItem]:
    """Create a shelf row for each supply the printer actually reports.

    Linked back to the supply via ``supply_key``, so the dashboard can show
    "12% left — 2 spares on hand".
    """
    created: list[SupplyItem] = []
    existing_keys = {
        item.supply_key for item in storage.list_items(reading.printer_id) if item.supply_key
    }
    for supply in reading.supplies:
        if supply.key in existing_keys:
            continue
        name = supply.display_name
        if storage.find_item(reading.printer_id, name):
            # Same label already on the shelf — just link it to the supply.
            item = storage.find_item(reading.printer_id, name)
            assert item is not None
            if not item.supply_key:
                item.supply_key = supply.key
                storage.upsert_item(item)
            continue
        item = SupplyItem(
            name=name,
            printer_id=reading.printer_id,
            category=category_for_supply(supply),
            quantity=0,
            reorder_at=1,
            supply_key=supply.key,
            notes=f"Auto-added from {reading.printer_name}. Capacity: {supply.capacity_text or 'n/a'}",
        )
        created.append(storage.upsert_item(item))
    return created


# ---------------------------------------------------------------------------
# Lookups used by the GUI
# ---------------------------------------------------------------------------


def items_by_supply_key(storage: Storage, printer_id: str) -> dict[str, SupplyItem]:
    return {
        item.supply_key: item
        for item in storage.list_items(printer_id)
        if item.supply_key
    }


def on_hand_for(storage: Storage, printer_id: str, supply_key: str) -> Optional[int]:
    for item in storage.list_items(printer_id):
        if item.supply_key == supply_key:
            return item.quantity
    return None


def consume_one(storage: Storage, item_id: int, reason: str = "installed in printer") -> Optional[SupplyItem]:
    return storage.adjust_quantity(item_id, -1, reason)


def receive(storage: Storage, item_id: int, count: int = 1, reason: str = "received") -> Optional[SupplyItem]:
    return storage.adjust_quantity(item_id, abs(int(count)), reason)


def summarize(items: Iterable[SupplyItem]) -> dict[str, int]:
    items = list(items)
    return {
        "total_rows": len(items),
        "total_units": sum(item.quantity for item in items),
        "needs_reorder": sum(1 for item in items if item.needs_reorder),
        "out_of_stock": sum(1 for item in items if item.quantity == 0),
    }


def to_csv(items: Iterable[SupplyItem]) -> str:
    """Export for a purchase order / e-mail to the supplier."""
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Printer", "Category", "Item", "Part number", "On hand", "Reorder at", "Unit", "Notes"]
    )
    for item in items:
        writer.writerow(
            [
                item.printer_id,
                item.category,
                item.name,
                item.part_number,
                item.quantity,
                item.reorder_at,
                item.unit,
                item.notes,
            ]
        )
    return buffer.getvalue()
