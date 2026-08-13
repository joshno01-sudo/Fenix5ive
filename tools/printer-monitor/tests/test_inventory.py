"""Supply-list behaviour: the +/- buttons, reorder points, seeding, export."""

from __future__ import annotations

import pytest

from printer_monitor import inventory
from printer_monitor.models import SupplyItem
from printer_monitor.storage import Storage

from .fake_agent import FakeAgent
from .mibs import LATEX_360
from .test_poller import printer_for


@pytest.fixture
def storage(tmp_path):
    with Storage(tmp_path / "test.db") as store:
        yield store


def test_add_and_list(storage):
    storage.upsert_item(SupplyItem(name="Cyan ink", printer_id="latex360", quantity=3))
    items = storage.list_items()
    assert len(items) == 1
    assert items[0].name == "Cyan ink"
    assert items[0].quantity == 3
    assert items[0].id is not None


def test_plus_and_minus(storage):
    item = storage.upsert_item(SupplyItem(name="Cyan ink", quantity=2))
    assert item.id is not None

    assert storage.adjust_quantity(item.id, 1).quantity == 3
    assert storage.adjust_quantity(item.id, 1).quantity == 4
    assert storage.adjust_quantity(item.id, -1).quantity == 3
    assert storage.adjust_quantity(item.id, -3).quantity == 0


def test_minus_never_goes_negative(storage):
    """The - button must clamp at zero rather than showing -1 cartridges."""
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=1))
    assert item.id is not None
    assert storage.adjust_quantity(item.id, -1).quantity == 0
    assert storage.adjust_quantity(item.id, -5).quantity == 0


def test_adjustments_are_logged(storage):
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=0))
    assert item.id is not None
    storage.adjust_quantity(item.id, 4, "received shipment")
    storage.adjust_quantity(item.id, -1, "installed in printer")

    log = storage.stock_log(item.id)
    assert [(row["delta"], row["quantity"]) for row in log] == [(-1, 3), (4, 4)]
    assert log[0]["reason"] == "installed in printer"


def test_clamped_adjustment_logs_only_what_applied(storage):
    """Going -5 from 2 records -2, not -5, so the log still reconciles."""
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=2))
    assert item.id is not None
    storage.adjust_quantity(item.id, -5, "used")
    log = storage.stock_log(item.id)
    assert log[0]["delta"] == -2
    assert log[0]["quantity"] == 0


def test_no_op_adjustment_is_not_logged(storage):
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=0))
    assert item.id is not None
    storage.adjust_quantity(item.id, -1, "nothing to take")
    assert storage.stock_log(item.id) == []


def test_set_quantity(storage):
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=2))
    assert item.id is not None
    assert storage.set_quantity(item.id, 9).quantity == 9
    assert storage.stock_log(item.id)[0]["delta"] == 7


def test_needs_reorder_boundary():
    assert SupplyItem(name="a", quantity=0, reorder_at=1, counted=True).needs_reorder
    assert SupplyItem(name="a", quantity=1, reorder_at=1, counted=True).needs_reorder
    assert not SupplyItem(name="a", quantity=2, reorder_at=1, counted=True).needs_reorder
    # reorder_at 0 means "only warn when it's actually gone"
    assert SupplyItem(name="a", quantity=0, reorder_at=0, counted=True).needs_reorder
    assert not SupplyItem(name="a", quantity=1, reorder_at=0, counted=True).needs_reorder


def test_uncounted_item_never_needs_reorder():
    """A row nobody has counted is unknown, not empty — it must stay quiet."""
    assert not SupplyItem(name="a", quantity=0, reorder_at=1, counted=False).needs_reorder


def test_items_needing_reorder(storage):
    storage.upsert_item(SupplyItem(name="Plenty", quantity=10, reorder_at=2))
    storage.upsert_item(SupplyItem(name="Low", quantity=1, reorder_at=2))
    storage.upsert_item(SupplyItem(name="Out", quantity=0, reorder_at=1, counted=True))
    storage.upsert_item(SupplyItem(name="Never counted", quantity=0, reorder_at=1))
    assert sorted(i.name for i in storage.items_needing_reorder()) == ["Low", "Out"]


def test_stock_with_quantity_counts_as_counted(storage):
    """Entering a non-zero count is itself a count, no + press required."""
    item = storage.upsert_item(SupplyItem(name="Cyan", quantity=3))
    assert item.counted
    assert storage.list_items()[0].counted


def test_seeded_items_start_uncounted_and_silent(storage):
    """A fresh starter list must not raise an alert for every row at once."""
    inventory.seed_defaults(storage, "latex360", "hp_latex")
    items = storage.list_items()
    assert items
    assert not any(item.counted for item in items)
    assert storage.items_needing_reorder() == []


def test_first_adjustment_starts_tracking(storage):
    inventory.seed_defaults(storage, "lj4100", "hp_laserjet")
    item = storage.find_item("lj4100", "Transfer roller")
    assert item is not None and item.id is not None
    assert not item.counted

    # Counting up then back to zero leaves it tracked, and now genuinely out.
    storage.adjust_quantity(item.id, 1)
    updated = storage.adjust_quantity(item.id, -1)
    assert updated.counted
    assert updated.quantity == 0
    assert [i.name for i in storage.items_needing_reorder()] == ["Transfer roller"]


def test_counted_flag_survives_a_reload(tmp_path):
    path = tmp_path / "reload.db"
    with Storage(path) as store:
        item = store.upsert_item(SupplyItem(name="Cyan", quantity=2))
        assert item.id is not None
        store.adjust_quantity(item.id, -2)
    with Storage(path) as store:
        reloaded = store.list_items()[0]
        assert reloaded.counted
        assert reloaded.quantity == 0
        assert reloaded.needs_reorder


def test_migration_adds_the_counted_column(tmp_path):
    """A database created before `counted` existed must still open."""
    import sqlite3

    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE supply_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            printer_id TEXT NOT NULL DEFAULT '',
            part_number TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Ink',
            quantity INTEGER NOT NULL DEFAULT 0,
            reorder_at INTEGER NOT NULL DEFAULT 1,
            unit TEXT NOT NULL DEFAULT 'each',
            notes TEXT NOT NULL DEFAULT '',
            supply_key TEXT NOT NULL DEFAULT '',
            updated_at REAL NOT NULL
        );
        INSERT INTO supply_items (name, quantity, updated_at) VALUES ('Has stock', 4, 0);
        INSERT INTO supply_items (name, quantity, updated_at) VALUES ('Empty', 0, 0);
        """
    )
    connection.commit()
    connection.close()

    with Storage(path) as store:
        by_name = {item.name: item for item in store.list_items()}
        # Existing stock is treated as already counted; an empty row is not.
        assert by_name["Has stock"].counted
        assert not by_name["Empty"].counted


def test_upsert_by_name_updates_instead_of_duplicating(storage):
    storage.upsert_item(SupplyItem(name="Cyan", printer_id="latex360", quantity=1))
    storage.upsert_item(SupplyItem(name="Cyan", printer_id="latex360", quantity=5))
    items = storage.list_items()
    assert len(items) == 1
    assert items[0].quantity == 5


def test_same_name_on_two_printers_is_allowed(storage):
    storage.upsert_item(SupplyItem(name="Black", printer_id="latex360"))
    storage.upsert_item(SupplyItem(name="Black", printer_id="lj4100"))
    assert len(storage.list_items()) == 2


def test_delete_removes_item_and_history(storage):
    item = storage.upsert_item(SupplyItem(name="Toner", quantity=2))
    assert item.id is not None
    storage.adjust_quantity(item.id, 1)
    storage.delete_item(item.id)
    assert storage.list_items() == []
    assert storage.stock_log(item.id) == []


def test_seed_defaults_is_idempotent(storage):
    first = inventory.seed_defaults(storage, "latex360", "hp_latex")
    second = inventory.seed_defaults(storage, "latex360", "hp_latex")
    assert first > 0
    assert second == 0
    assert len(storage.list_items()) == first


def test_seed_defaults_covers_both_printer_types(storage):
    inventory.seed_defaults(storage, "latex360", "hp_latex")
    inventory.seed_defaults(storage, "lj4100", "hp_laserjet")
    names = [i.name for i in storage.list_items()]
    assert any("Optimizer" in n for n in names)
    assert any("Maintenance cartridge" in n for n in names)
    assert any("toner" in n.lower() for n in names)


def test_seed_from_reading_links_supplies(storage):
    """Polling a printer should populate the shelf list from real descriptions."""
    with FakeAgent(LATEX_360) as agent:
        from printer_monitor.poller import poll_printer

        reading = poll_printer(printer_for(agent, "hp_latex"))

    created = inventory.seed_from_reading(storage, reading)
    assert len(created) == 12
    keys = {item.supply_key for item in storage.list_items(reading.printer_id)}
    assert {s.key for s in reading.supplies} == keys

    # Categories follow the supply type from the MIB.
    by_name = {i.name: i for i in storage.list_items()}
    assert by_name["HP 831 Latex Cyan"].category == "Ink"
    assert by_name["Maintenance Cartridge"].category == "Maintenance"

    # And running it again adds nothing.
    assert inventory.seed_from_reading(storage, reading) == []


def test_on_hand_lookup(storage):
    storage.upsert_item(
        SupplyItem(name="Cyan", printer_id="latex360", supply_key="hp-831-latex-cyan", quantity=4)
    )
    assert inventory.on_hand_for(storage, "latex360", "hp-831-latex-cyan") == 4
    assert inventory.on_hand_for(storage, "latex360", "nope") is None


def test_consume_and_receive(storage):
    item = storage.upsert_item(SupplyItem(name="Cyan", quantity=2))
    assert item.id is not None
    assert inventory.consume_one(storage, item.id).quantity == 1
    assert inventory.receive(storage, item.id, 3).quantity == 4


def test_summarize(storage):
    storage.upsert_item(SupplyItem(name="A", quantity=5, reorder_at=1))
    storage.upsert_item(SupplyItem(name="B", quantity=0, reorder_at=1, counted=True))
    stats = inventory.summarize(storage.list_items())
    assert stats == {
        "total_rows": 2,
        "total_units": 5,
        "needs_reorder": 1,
        "out_of_stock": 1,
    }


def test_csv_export_round_trips(storage):
    storage.upsert_item(
        SupplyItem(name="Cyan ink", part_number="X1", printer_id="latex360", quantity=2)
    )
    text = inventory.to_csv(storage.list_items())
    lines = text.strip().splitlines()
    assert lines[0].startswith("Printer,Category,Item,Part number,On hand")
    assert "Cyan ink" in lines[1]
    assert "X1" in lines[1]


def test_supply_key_is_stable_across_index_changes():
    """HP firmware renumbers the supplies table after a swap; keys must not move."""
    from printer_monitor.models import Supply

    first = Supply(index=3, description="HP 831 Latex Cyan")
    later = Supply(index=7, description="HP 831 Latex Cyan")
    assert first.key == later.key == "hp-831-latex-cyan"
