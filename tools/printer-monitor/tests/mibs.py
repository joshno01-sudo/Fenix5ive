"""Canned MIBs shaped like the two printers this tool was built for."""

from __future__ import annotations

# --- HP Latex 360 ---------------------------------------------------------
# Inks report volume in tenths of a millilitre (775 ml cartridges); the
# maintenance cartridge is a receptacle that fills up; printheads report percent.

LATEX_360: dict[str, object] = {
    "1.3.6.1.2.1.1.1.0": "HP Latex 360 Printer",
    "1.3.6.1.2.1.1.3.0": 918273,
    "1.3.6.1.2.1.1.5.0": "HPLATEX360",
    "1.3.6.1.2.1.43.5.1.1.16.1": "HP Latex 360",
    "1.3.6.1.2.1.43.5.1.1.17.1": "MY7BD1802X",
    "1.3.6.1.2.1.25.3.5.1.1.1": 3,  # idle
    "1.3.6.1.2.1.25.3.2.1.5.1": 2,  # running
    "1.3.6.1.2.1.25.3.5.1.2.1": b"\x00\x00",
    "1.3.6.1.2.1.43.16.5.1.2.1.1": "Ready to print",
    "1.3.6.1.2.1.43.10.2.1.4.1.1": 148_205,
    # -- supplies: description / class / type / unit / max / level
    **{
        f"1.3.6.1.2.1.43.11.1.1.6.1.{index}": description
        for index, description in enumerate(
            [
                "HP 831 Latex Cyan",
                "HP 831 Latex Magenta",
                "HP 831 Latex Yellow",
                "HP 831 Latex Black",
                "HP 831 Latex Light Cyan",
                "HP 831 Latex Light Magenta",
                "HP 831 Latex Optimizer",
                "Printhead Cyan/Black",
                "Printhead Yellow/Magenta",
                "Printhead Light Cyan/Light Magenta",
                "Printhead Optimizer",
                "Maintenance Cartridge",
            ],
            start=1,
        )
    },
    # inks 1-7: class 3 (consumed), type 6 (ink cartridge), unit 15 (tenths ml)
    **{f"1.3.6.1.2.1.43.11.1.1.4.1.{i}": 3 for i in range(1, 8)},
    **{f"1.3.6.1.2.1.43.11.1.1.5.1.{i}": 6 for i in range(1, 8)},
    **{f"1.3.6.1.2.1.43.11.1.1.7.1.{i}": 15 for i in range(1, 8)},
    **{f"1.3.6.1.2.1.43.11.1.1.8.1.{i}": 7750 for i in range(1, 8)},
    "1.3.6.1.2.1.43.11.1.1.9.1.1": 5425,  # cyan 70%
    "1.3.6.1.2.1.43.11.1.1.9.1.2": 3100,  # magenta 40%
    "1.3.6.1.2.1.43.11.1.1.9.1.3": 1163,  # yellow 15%  -> warning
    "1.3.6.1.2.1.43.11.1.1.9.1.4": 465,  # black 6%    -> critical
    "1.3.6.1.2.1.43.11.1.1.9.1.5": 7750,  # light cyan 100%
    "1.3.6.1.2.1.43.11.1.1.9.1.6": -3,  # light magenta: "some remaining"
    "1.3.6.1.2.1.43.11.1.1.9.1.7": 6200,  # optimizer 80%
    # printheads 8-11: percent of life left
    **{f"1.3.6.1.2.1.43.11.1.1.4.1.{i}": 3 for i in range(8, 12)},
    **{f"1.3.6.1.2.1.43.11.1.1.5.1.{i}": 1 for i in range(8, 12)},
    **{f"1.3.6.1.2.1.43.11.1.1.7.1.{i}": 19 for i in range(8, 12)},
    **{f"1.3.6.1.2.1.43.11.1.1.8.1.{i}": 100 for i in range(8, 12)},
    "1.3.6.1.2.1.43.11.1.1.9.1.8": 88,
    "1.3.6.1.2.1.43.11.1.1.9.1.9": 64,
    "1.3.6.1.2.1.43.11.1.1.9.1.10": 41,
    "1.3.6.1.2.1.43.11.1.1.9.1.11": 92,
    # maintenance cartridge (12): a receptacle, 82% full -> 18% life left
    "1.3.6.1.2.1.43.11.1.1.4.1.12": 4,
    "1.3.6.1.2.1.43.11.1.1.5.1.12": 8,  # waste ink
    "1.3.6.1.2.1.43.11.1.1.7.1.12": 19,
    "1.3.6.1.2.1.43.11.1.1.8.1.12": 100,
    "1.3.6.1.2.1.43.11.1.1.9.1.12": 82,
    # colorants
    "1.3.6.1.2.1.43.11.1.1.3.1.1": 1,
    "1.3.6.1.2.1.43.12.1.1.4.1.1": "cyan",
    # substrate roll
    "1.3.6.1.2.1.43.8.2.1.13.1.1": "Roll 1",
    "1.3.6.1.2.1.43.8.2.1.18.1.1": "Substrate roll",
    "1.3.6.1.2.1.43.8.2.1.12.1.1": "Cast Vinyl 54in",
    "1.3.6.1.2.1.43.8.2.1.9.1.1": -2,
    "1.3.6.1.2.1.43.8.2.1.10.1.1": -3,
    "1.3.6.1.2.1.43.8.2.1.11.1.1": 0,
}


# --- HP LaserJet 4100 ----------------------------------------------------
# Toner in percent, maintenance kit counted in impressions, three trays with
# one of them empty, and the "low toner" detected-error bit set.

LASERJET_4100: dict[str, object] = {
    "1.3.6.1.2.1.1.1.0": "HP LaserJet 4100 Series; JETDIRECT; FIRMWARE VERSION = G.08.32",
    "1.3.6.1.2.1.1.3.0": 4_501_222,
    "1.3.6.1.2.1.1.5.0": "NPI4100OFFICE",
    "1.3.6.1.2.1.43.5.1.1.16.1": "HP LaserJet 4100 Series",
    "1.3.6.1.2.1.43.5.1.1.17.1": "USBN123456",
    "1.3.6.1.2.1.25.3.5.1.1.1": 3,
    "1.3.6.1.2.1.25.3.2.1.5.1": 3,  # warning
    # byte 0 bit 2 -> "low toner"; bit 13 (byte 1, bit 5) -> "input tray empty"
    "1.3.6.1.2.1.25.3.5.1.2.1": b"\x20\x04",
    "1.3.6.1.2.1.43.16.5.1.2.1.1": "ORDER BLACK CARTRIDGE",
    "1.3.6.1.2.1.43.10.2.1.4.1.1": 612_884,
    # black toner: 7% left -> critical
    "1.3.6.1.2.1.43.11.1.1.6.1.1": "Black Cartridge HP C8061X",
    "1.3.6.1.2.1.43.11.1.1.4.1.1": 3,
    "1.3.6.1.2.1.43.11.1.1.5.1.1": 21,  # toner cartridge
    "1.3.6.1.2.1.43.11.1.1.7.1.1": 19,
    "1.3.6.1.2.1.43.11.1.1.8.1.1": 100,
    "1.3.6.1.2.1.43.11.1.1.9.1.1": 7,
    # maintenance kit: 30k of 200k impressions left -> 15% -> warning
    "1.3.6.1.2.1.43.11.1.1.6.1.2": "Maintenance Kit",
    "1.3.6.1.2.1.43.11.1.1.4.1.2": 3,
    "1.3.6.1.2.1.43.11.1.1.5.1.2": 15,  # fuser
    "1.3.6.1.2.1.43.11.1.1.7.1.2": 7,  # impressions
    "1.3.6.1.2.1.43.11.1.1.8.1.2": 200_000,
    "1.3.6.1.2.1.43.11.1.1.9.1.2": 30_000,
    # trays
    "1.3.6.1.2.1.43.8.2.1.13.1.1": "Tray 1",
    "1.3.6.1.2.1.43.8.2.1.10.1.1": -3,
    "1.3.6.1.2.1.43.8.2.1.9.1.1": 100,
    "1.3.6.1.2.1.43.8.2.1.13.1.2": "Tray 2",
    "1.3.6.1.2.1.43.8.2.1.12.1.2": "Letter",
    "1.3.6.1.2.1.43.8.2.1.10.1.2": 250,
    "1.3.6.1.2.1.43.8.2.1.9.1.2": 500,
    "1.3.6.1.2.1.43.8.2.1.13.1.3": "Tray 3",
    "1.3.6.1.2.1.43.8.2.1.12.1.3": "Letter",
    "1.3.6.1.2.1.43.8.2.1.10.1.3": 0,  # empty
    "1.3.6.1.2.1.43.8.2.1.9.1.3": 500,
    # the printer's own alert table
    "1.3.6.1.2.1.43.18.1.1.2.1": 3,  # critical
    "1.3.6.1.2.1.43.18.1.1.5.1": 8,  # input tray
    "1.3.6.1.2.1.43.18.1.1.7.1": 1_101,
    "1.3.6.1.2.1.43.18.1.1.8.1": "Tray 3 empty",
    "1.3.6.1.2.1.43.18.1.1.2.2": 4,  # warning
    "1.3.6.1.2.1.43.18.1.1.5.2": 11,  # marker supplies
    "1.3.6.1.2.1.43.18.1.1.7.2": 1_102,
    "1.3.6.1.2.1.43.18.1.1.8.2": "Black cartridge low",
}


# --- Other office printers -----------------------------------------------
# Not HP, and shaped the way these vendors actually report: a colour laser with
# CMYK toner plus drums and a waste box, and a mono MFP that gives a bare 0-100
# level with no capacity and no unit.

BROTHER_COLOR_MFP: dict[str, object] = {
    "1.3.6.1.2.1.1.1.0": "Brother MFC-L8900CDW series",
    "1.3.6.1.2.1.1.3.0": 220_115,
    "1.3.6.1.2.1.1.5.0": "BRN30055C123456",
    "1.3.6.1.2.1.43.5.1.1.16.1": "Brother MFC-L8900CDW",
    "1.3.6.1.2.1.43.5.1.1.17.1": "U63878K0N123456",
    "1.3.6.1.2.1.25.3.5.1.1.1": 3,
    "1.3.6.1.2.1.25.3.2.1.5.1": 2,
    "1.3.6.1.2.1.43.10.2.1.4.1.1": 88_412,
    # CMYK toner, reported in percent
    **{
        f"1.3.6.1.2.1.43.11.1.1.6.1.{i}": name
        for i, name in enumerate(
            [
                "Black Toner Cartridge",
                "Cyan Toner Cartridge",
                "Magenta Toner Cartridge",
                "Yellow Toner Cartridge",
                "Drum Unit",
                "Belt Unit",
                "Waste Toner Box",
            ],
            start=1,
        )
    },
    **{f"1.3.6.1.2.1.43.11.1.1.4.1.{i}": 3 for i in range(1, 7)},
    **{f"1.3.6.1.2.1.43.11.1.1.5.1.{i}": 3 for i in range(1, 5)},  # toner
    "1.3.6.1.2.1.43.11.1.1.5.1.5": 9,  # OPC drum
    "1.3.6.1.2.1.43.11.1.1.5.1.6": 20,  # transfer belt
    **{f"1.3.6.1.2.1.43.11.1.1.7.1.{i}": 19 for i in range(1, 7)},
    **{f"1.3.6.1.2.1.43.11.1.1.8.1.{i}": 100 for i in range(1, 7)},
    "1.3.6.1.2.1.43.11.1.1.9.1.1": 62,  # black
    "1.3.6.1.2.1.43.11.1.1.9.1.2": 18,  # cyan     -> warning
    "1.3.6.1.2.1.43.11.1.1.9.1.3": 4,  # magenta  -> critical
    "1.3.6.1.2.1.43.11.1.1.9.1.4": 77,  # yellow
    "1.3.6.1.2.1.43.11.1.1.9.1.5": 45,  # drum
    "1.3.6.1.2.1.43.11.1.1.9.1.6": 90,  # belt
    # waste toner box: a receptacle, 70% full -> 30% life left
    "1.3.6.1.2.1.43.11.1.1.4.1.7": 4,
    "1.3.6.1.2.1.43.11.1.1.5.1.7": 4,  # waste toner
    "1.3.6.1.2.1.43.11.1.1.7.1.7": 19,
    "1.3.6.1.2.1.43.11.1.1.8.1.7": 100,
    "1.3.6.1.2.1.43.11.1.1.9.1.7": 70,
    "1.3.6.1.2.1.43.8.2.1.13.1.1": "Tray 1",
    "1.3.6.1.2.1.43.8.2.1.12.1.1": "Letter",
    "1.3.6.1.2.1.43.8.2.1.10.1.1": 180,
    "1.3.6.1.2.1.43.8.2.1.9.1.1": 250,
}

# A mono MFP that reports level 0-100 with unit "other" and no max capacity —
# common on cheaper office hardware, and unreadable without the percent fallback.
KYOCERA_MONO_MFP: dict[str, object] = {
    "1.3.6.1.2.1.1.1.0": "Kyocera ECOSYS M2540dn",
    "1.3.6.1.2.1.1.3.0": 95_400,
    "1.3.6.1.2.1.1.5.0": "KM7F1234",
    "1.3.6.1.2.1.43.5.1.1.16.1": "ECOSYS M2540dn",
    "1.3.6.1.2.1.25.3.5.1.1.1": 3,
    "1.3.6.1.2.1.43.10.2.1.4.1.1": 41_230,
    "1.3.6.1.2.1.43.11.1.1.6.1.1": "TK-1160 Black Toner",
    "1.3.6.1.2.1.43.11.1.1.4.1.1": 3,
    "1.3.6.1.2.1.43.11.1.1.5.1.1": 21,
    "1.3.6.1.2.1.43.11.1.1.7.1.1": 1,  # unit "other"
    "1.3.6.1.2.1.43.11.1.1.8.1.1": -2,  # capacity unknown
    "1.3.6.1.2.1.43.11.1.1.9.1.1": 11,  # ...but the level is a percentage
    "1.3.6.1.2.1.43.8.2.1.13.1.1": "Cassette 1",
    "1.3.6.1.2.1.43.8.2.1.10.1.1": 300,
    "1.3.6.1.2.1.43.8.2.1.9.1.1": 500,
}

# Answers SNMP but is not a printer — the scan must not offer it.
NETWORK_SWITCH: dict[str, object] = {
    "1.3.6.1.2.1.1.1.0": "24-Port Gigabit Smart Managed Switch",
    "1.3.6.1.2.1.1.3.0": 8_800_100,
    "1.3.6.1.2.1.1.5.0": "office-switch-01",
}
