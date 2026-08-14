"""The catalog of file types offered in the middle panel.

Each extension appears in exactly one category, so a checkbox always has a
single unambiguous meaning. Anything the catalog does not know about is not
lost: the scanner reports every extension it actually finds, and unknown ones
are surfaced in their own "Other file types found on this PC" group with real
counts beside them. Between the curated list, the installed-program probe in
``appdetect`` and that discovered group, nothing has to be typed by hand -- but
a free-text box for custom extensions exists as a final escape hatch.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FileType:
    ext: str      # always lowercase, always with the leading dot
    label: str


@dataclass
class Category:
    key: str
    name: str
    blurb: str
    default_on: bool
    types: list[FileType] = field(default_factory=list)

    @property
    def extensions(self) -> list[str]:
        return [t.ext for t in self.types]


def _t(pairs: list[tuple[str, str]]) -> list[FileType]:
    return [FileType(ext.lower(), label) for ext, label in pairs]


# Key used for extensions discovered during a scan that the catalog does not know.
DISCOVERED_KEY = "discovered"

# Key used for extensions the user typed in by hand.
CUSTOM_KEY = "custom"


CATEGORIES: list[Category] = [
    Category(
        key="photos",
        name="Photos & Images",
        blurb="Everything from phone snaps to finished proofs and logos.",
        default_on=True,
        types=_t([
            (".jpg", "JPEG photo"),
            (".jpeg", "JPEG photo"),
            (".jpe", "JPEG photo"),
            (".png", "PNG image"),
            (".gif", "GIF image"),
            (".bmp", "Bitmap image"),
            (".tif", "TIFF image"),
            (".tiff", "TIFF image"),
            (".webp", "WebP image"),
            (".heic", "iPhone photo"),
            (".heif", "High-efficiency photo"),
            (".ico", "Icon"),
            (".jfif", "JPEG photo"),
            (".avif", "AVIF image"),
        ]),
    ),
    Category(
        key="camera_raw",
        name="Camera RAW Originals",
        blurb="Untouched camera files. Large, but they are the negatives.",
        default_on=True,
        types=_t([
            (".raw", "Camera RAW"),
            (".cr2", "Canon RAW"),
            (".cr3", "Canon RAW"),
            (".nef", "Nikon RAW"),
            (".nrw", "Nikon RAW"),
            (".arw", "Sony RAW"),
            (".orf", "Olympus RAW"),
            (".rw2", "Panasonic RAW"),
            (".raf", "Fujifilm RAW"),
            (".pef", "Pentax RAW"),
            (".dng", "Digital Negative"),
            (".srw", "Samsung RAW"),
            (".x3f", "Sigma RAW"),
            (".xmp", "Edit sidecar"),
        ]),
    ),
    Category(
        key="design",
        name="Design & Artwork",
        blurb="Illustrator, Photoshop, CorelDRAW, Affinity and vector art. "
              "Your master artwork lives here.",
        default_on=True,
        types=_t([
            (".ai", "Adobe Illustrator artwork"),
            (".ait", "Illustrator template"),
            (".eps", "Encapsulated PostScript vector"),
            (".svg", "Scalable vector graphic"),
            (".svgz", "Compressed vector graphic"),
            (".psd", "Photoshop document"),
            (".psb", "Photoshop large document"),
            (".pdd", "Photoshop document"),
            (".cdr", "CorelDRAW drawing"),
            (".cdt", "CorelDRAW template"),
            (".cmx", "Corel clipart exchange"),
            (".indd", "InDesign document"),
            (".indt", "InDesign template"),
            (".idml", "InDesign exchange"),
            (".afdesign", "Affinity Designer"),
            (".afphoto", "Affinity Photo"),
            (".afpub", "Affinity Publisher"),
            (".xd", "Adobe XD"),
            (".fig", "Figma file"),
            (".sketch", "Sketch document"),
            (".xcf", "GIMP image"),
            (".kra", "Krita image"),
            (".clip", "Clip Studio Paint"),
            (".procreate", "Procreate artwork"),
            (".pub", "Microsoft Publisher"),
            (".cpt", "Corel PHOTO-PAINT"),
        ]),
    ),
    Category(
        key="vinyl",
        name="Vinyl Cutting & Plotting",
        blurb="Cutter-native files: plotter paths, cut jobs and sign software "
              "documents. (Illustrator and SVG masters sit under Design.)",
        default_on=True,
        types=_t([
            (".plt", "HPGL plotter / cut file"),
            (".hpgl", "HPGL plotter file"),
            (".hpg", "HPGL plotter file"),
            (".cut", "Cut file"),
            (".gsd", "Graphtec Cutting Master"),
            (".gsp", "Graphtec Studio project"),
            (".studio", "Silhouette Studio"),
            (".studio3", "Silhouette Studio"),
            (".studio4", "Silhouette Studio"),
            (".fcm", "Brother ScanNCut"),
            (".scut", "Sure Cuts A Lot"),
            (".scut4", "Sure Cuts A Lot"),
            (".scut5", "Sure Cuts A Lot"),
            (".mtc", "Make The Cut"),
            (".cst", "Roland CutStudio"),
            (".wpl", "Summa WinPlot"),
            (".fs", "FlexiSIGN design"),
            (".flx", "FlexiSIGN design"),
            (".job", "Cut / print job"),
            (".sbp", "ShopBot toolpath"),
            (".nc", "CNC toolpath"),
            (".tap", "CNC toolpath"),
            (".gcode", "G-code toolpath"),
        ]),
    ),
    Category(
        key="print",
        name="Print & RIP Files",
        blurb="Spooled print jobs, PostScript and the colour profiles that keep "
              "your output matching.",
        default_on=True,
        types=_t([
            (".prn", "Print / plotter spool file"),
            (".ps", "PostScript"),
            (".eps2", "PostScript"),
            (".rtl", "Raster print file"),
            (".spl", "Print spool file"),
            (".icc", "Colour profile"),
            (".icm", "Colour profile"),
            (".ppd", "Printer description"),
        ]),
    ),
    Category(
        key="embroidery",
        name="Embroidery & Sewing",
        blurb="Stitch files for embroidery machines and digitising software.",
        default_on=True,
        types=_t([
            (".dst", "Tajima stitch file"),
            (".pes", "Brother stitch file"),
            (".pec", "Brother stitch file"),
            (".jef", "Janome stitch file"),
            (".exp", "Melco stitch file"),
            (".vp3", "Husqvarna stitch file"),
            (".vip", "Husqvarna stitch file"),
            (".hus", "Husqvarna stitch file"),
            (".xxx", "Singer stitch file"),
            (".sew", "Janome stitch file"),
            (".emb", "Wilcom design"),
            (".art", "Bernina design"),
        ]),
    ),
    Category(
        key="cad",
        name="CAD & 3D",
        blurb="Drawings, models and anything headed for a router or 3D printer.",
        default_on=True,
        types=_t([
            (".dwg", "AutoCAD drawing"),
            (".dxf", "CAD exchange / cut path"),
            (".stl", "3D print mesh"),
            (".obj", "3D model"),
            (".3mf", "3D print model"),
            (".step", "STEP model"),
            (".stp", "STEP model"),
            (".iges", "IGES model"),
            (".igs", "IGES model"),
            (".skp", "SketchUp model"),
            (".f3d", "Fusion 360 model"),
            (".blend", "Blender scene"),
            (".fbx", "3D scene"),
            (".sldprt", "SolidWorks part"),
            (".sldasm", "SolidWorks assembly"),
            (".ipt", "Inventor part"),
            (".iam", "Inventor assembly"),
        ]),
    ),
    Category(
        key="documents",
        name="Documents & PDFs",
        blurb="Letters, contracts, quotes, invoices, notes and scans.",
        default_on=True,
        types=_t([
            (".pdf", "PDF document"),
            (".doc", "Word document"),
            (".docx", "Word document"),
            (".docm", "Word document (macros)"),
            (".dot", "Word template"),
            (".dotx", "Word template"),
            (".rtf", "Rich text"),
            (".txt", "Plain text"),
            (".md", "Markdown notes"),
            (".odt", "OpenDocument text"),
            (".pages", "Apple Pages"),
            (".wpd", "WordPerfect"),
            (".tex", "LaTeX document"),
            (".one", "OneNote section"),
            (".xps", "XPS document"),
            (".epub", "eBook"),
            (".mobi", "eBook"),
        ]),
    ),
    Category(
        key="spreadsheets",
        name="Spreadsheets & Accounting",
        blurb="Books, pricing sheets, job lists, tax files and QuickBooks data.",
        default_on=True,
        types=_t([
            (".xls", "Excel workbook"),
            (".xlsx", "Excel workbook"),
            (".xlsm", "Excel workbook (macros)"),
            (".xlsb", "Excel binary workbook"),
            (".xlt", "Excel template"),
            (".xltx", "Excel template"),
            (".csv", "Comma-separated data"),
            (".tsv", "Tab-separated data"),
            (".ods", "OpenDocument sheet"),
            (".numbers", "Apple Numbers"),
            (".qbw", "QuickBooks company file"),
            (".qbb", "QuickBooks backup"),
            (".qbo", "QuickBooks statement"),
            (".qbx", "QuickBooks accountant copy"),
            (".qfx", "Bank statement"),
            (".ofx", "Bank statement"),
            (".qif", "Quicken transactions"),
            (".iif", "QuickBooks import"),
            (".tax", "Tax return"),
        ]),
    ),
    Category(
        key="presentations",
        name="Presentations",
        blurb="Slide decks and pitch material.",
        default_on=True,
        types=_t([
            (".ppt", "PowerPoint deck"),
            (".pptx", "PowerPoint deck"),
            (".pptm", "PowerPoint deck (macros)"),
            (".pot", "PowerPoint template"),
            (".potx", "PowerPoint template"),
            (".odp", "OpenDocument slides"),
            (".key", "Apple Keynote"),
        ]),
    ),
    Category(
        key="email",
        name="Email, Contacts & Calendar",
        blurb="Outlook mailboxes, saved messages, address books and calendars.",
        default_on=True,
        types=_t([
            (".pst", "Outlook mailbox"),
            (".ost", "Outlook offline mailbox"),
            (".msg", "Saved email"),
            (".eml", "Saved email"),
            (".mbox", "Mailbox archive"),
            (".vcf", "Contact card"),
            (".ics", "Calendar"),
            (".nsf", "Notes database"),
        ]),
    ),
    Category(
        key="archives",
        name="Zips & Archives",
        blurb="Compressed bundles, which often hold customer artwork.",
        default_on=True,
        types=_t([
            (".zip", "Zip archive"),
            (".rar", "RAR archive"),
            (".7z", "7-Zip archive"),
            (".tar", "Tar archive"),
            (".gz", "Gzip archive"),
            (".tgz", "Gzip archive"),
            (".bz2", "Bzip2 archive"),
            (".xz", "XZ archive"),
            (".cab", "Cabinet archive"),
        ]),
    ),
    Category(
        key="fonts",
        name="Fonts",
        blurb="Purchased and custom typefaces. Losing these breaks old artwork.",
        default_on=True,
        types=_t([
            (".ttf", "TrueType font"),
            (".otf", "OpenType font"),
            (".ttc", "TrueType collection"),
            (".woff", "Web font"),
            (".woff2", "Web font"),
            (".fon", "Bitmap font"),
            (".pfb", "PostScript font"),
            (".pfm", "PostScript font metrics"),
        ]),
    ),
    Category(
        key="databases",
        name="Business App Data",
        blurb="Databases and program data files that hold customer records.",
        default_on=True,
        types=_t([
            (".mdb", "Access database"),
            (".accdb", "Access database"),
            (".sqlite", "SQLite database"),
            (".sqlite3", "SQLite database"),
            (".db", "Database"),
            (".dbf", "dBase table"),
            (".fdb", "Firebird database"),
            (".bak", "Database backup"),
        ]),
    ),
    Category(
        key="video",
        name="Video",
        blurb="Clips and edits. Usually the biggest thing on a drive -- turn it "
              "on when you have the space.",
        default_on=False,
        types=_t([
            (".mp4", "MP4 video"),
            (".mov", "QuickTime video"),
            (".avi", "AVI video"),
            (".mkv", "Matroska video"),
            (".wmv", "Windows Media video"),
            (".m4v", "MP4 video"),
            (".mpg", "MPEG video"),
            (".mpeg", "MPEG video"),
            (".3gp", "Phone video"),
            (".webm", "WebM video"),
            (".flv", "Flash video"),
            (".mts", "Camcorder video"),
            (".m2ts", "Camcorder video"),
            (".prproj", "Premiere Pro project"),
            (".veg", "Vegas project"),
            (".aep", "After Effects project"),
            (".fcpxml", "Final Cut project"),
            (".drp", "DaVinci Resolve project"),
        ]),
    ),
    Category(
        key="audio",
        name="Music & Audio",
        blurb="Recordings, voiceovers and music libraries.",
        default_on=False,
        types=_t([
            (".mp3", "MP3 audio"),
            (".wav", "WAV audio"),
            (".flac", "FLAC audio"),
            (".aac", "AAC audio"),
            (".m4a", "M4A audio"),
            (".wma", "Windows Media audio"),
            (".ogg", "Ogg audio"),
            (".opus", "Opus audio"),
            (".aif", "AIFF audio"),
            (".aiff", "AIFF audio"),
            (".mid", "MIDI"),
            (".midi", "MIDI"),
        ]),
    ),
    Category(
        key="web",
        name="Web & Code",
        blurb="Website files and scripts.",
        default_on=False,
        types=_t([
            (".html", "Web page"),
            (".htm", "Web page"),
            (".css", "Stylesheet"),
            (".js", "JavaScript"),
            (".ts", "TypeScript"),
            (".json", "JSON data"),
            (".xml", "XML data"),
            (".php", "PHP script"),
            (".py", "Python script"),
            (".ps1", "PowerShell script"),
            (".bat", "Batch script"),
            (".sql", "SQL script"),
            (".yml", "YAML config"),
            (".yaml", "YAML config"),
            (".ini", "Settings file"),
            (".cfg", "Settings file"),
        ]),
    ),
    Category(
        key="keys",
        name="Certificates & Keys",
        blurb="Signing certificates and private keys. Sensitive -- only include "
              "these if the backup drive itself stays secure.",
        default_on=False,
        types=_t([
            (".pfx", "Certificate bundle"),
            (".p12", "Certificate bundle"),
            (".cer", "Certificate"),
            (".crt", "Certificate"),
            (".pem", "Certificate / key"),
            # .key is deliberately absent: it belongs to Keynote above, and
            # sweeping up private keys by accident is the worse mistake.
            (".ppk", "PuTTY private key"),
            (".kdbx", "KeePass password database"),
        ]),
    ),
]


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------

_EXT_TO_CATEGORY: dict[str, str] = {}
_EXT_TO_LABEL: dict[str, str] = {}
for _cat in CATEGORIES:
    for _type in _cat.types:
        _EXT_TO_CATEGORY.setdefault(_type.ext, _cat.key)
        _EXT_TO_LABEL.setdefault(_type.ext, _type.label)


def category_of(ext: str) -> str | None:
    """Category key owning *ext*, or None when the catalog has never seen it."""
    return _EXT_TO_CATEGORY.get(ext.lower())


def label_of(ext: str) -> str:
    return _EXT_TO_LABEL.get(ext.lower(), "File")


def known_extensions() -> set[str]:
    return set(_EXT_TO_CATEGORY)


def category_by_key(key: str) -> Category | None:
    for cat in CATEGORIES:
        if cat.key == key:
            return cat
    return None


def default_extensions() -> set[str]:
    """Extensions selected the first time the program runs."""
    picked: set[str] = set()
    for cat in CATEGORIES:
        if cat.default_on:
            picked.update(cat.extensions)
    return picked


def normalise_ext(text: str) -> str | None:
    """Turn user input such as ``AI``, ``.Ai`` or ``*.ai`` into ``.ai``."""
    cleaned = text.strip().lower().lstrip("*").strip()
    if not cleaned:
        return None
    if not cleaned.startswith("."):
        cleaned = "." + cleaned
    if cleaned == "." or any(ch in cleaned for ch in '\\/:*?"<>| '):
        return None
    return cleaned


# --------------------------------------------------------------------------
# Installed-program hints
# --------------------------------------------------------------------------

# Substrings matched (case-insensitively) against the names of programs found
# installed on the PC. A hit switches its categories on automatically, so a shop
# with CorelDRAW and Silhouette Studio gets those file types ticked without
# having to know which extensions belong to which program.
PROGRAM_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("illustrator", ("design",)),
    ("photoshop", ("design", "photos")),
    ("indesign", ("design",)),
    ("adobe", ("design",)),
    ("coreldraw", ("design", "vinyl")),
    ("corel", ("design",)),
    ("affinity", ("design",)),
    ("inkscape", ("design",)),
    ("gimp", ("design", "photos")),
    ("silhouette", ("vinyl",)),
    ("cricut", ("vinyl",)),
    ("scanncut", ("vinyl",)),
    ("canvas workspace", ("vinyl",)),
    ("sure cuts a lot", ("vinyl",)),
    ("make the cut", ("vinyl",)),
    ("cutting master", ("vinyl",)),
    ("graphtec", ("vinyl",)),
    ("cutstudio", ("vinyl",)),
    ("roland", ("vinyl", "print")),
    ("summa", ("vinyl",)),
    ("signcut", ("vinyl",)),
    ("flexi", ("vinyl", "design")),
    ("signlab", ("vinyl", "design")),
    ("onyx", ("print",)),
    ("versaworks", ("print",)),
    ("caldera", ("print",)),
    ("wasatch", ("print",)),
    ("wilcom", ("embroidery",)),
    ("embird", ("embroidery",)),
    ("hatch", ("embroidery",)),
    ("autocad", ("cad",)),
    ("fusion 360", ("cad",)),
    ("solidworks", ("cad",)),
    ("sketchup", ("cad",)),
    ("inventor", ("cad",)),
    ("vcarve", ("cad", "vinyl")),
    ("aspire", ("cad", "vinyl")),
    ("blender", ("cad",)),
    ("quickbooks", ("spreadsheets", "databases")),
    ("quicken", ("spreadsheets",)),
    ("sage", ("spreadsheets", "databases")),
    ("turbotax", ("spreadsheets",)),
    ("microsoft office", ("documents", "spreadsheets", "presentations")),
    ("microsoft 365", ("documents", "spreadsheets", "presentations")),
    ("libreoffice", ("documents", "spreadsheets", "presentations")),
    ("outlook", ("email",)),
    ("thunderbird", ("email",)),
    ("access", ("databases",)),
    ("premiere", ("video",)),
    ("vegas", ("video",)),
    ("davinci resolve", ("video",)),
    ("after effects", ("video",)),
    ("lightroom", ("photos", "camera_raw")),
    ("capture one", ("photos", "camera_raw")),
    ("audacity", ("audio",)),
]


def categories_for_programs(program_names: list[str]) -> set[str]:
    """Category keys implied by the list of programs installed on this PC."""
    hits: set[str] = set()
    lowered = [name.lower() for name in program_names]
    for needle, keys in PROGRAM_HINTS:
        if any(needle in name for name in lowered):
            hits.update(keys)
    return hits
