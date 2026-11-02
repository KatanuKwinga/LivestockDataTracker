"""Adding many animals at once from a CSV file (a spreadsheet saved as .csv).
The whole file is checked first and if any row has a problem, nothing is saved.
"""
import csv
import io
import re
from datetime import date, datetime

from app.farm import tag_in_use
from app.forms import normalise_tag
from app.models import Livestock

MAX_BYTES = 1_000_000        # about 1 MB: thousands of animals, far more than one farm adds at once
MAX_ROWS = 2000
COLUMNS = ["tag_number", "species", "sex", "breed", "date_of_birth", "castrated", "notes"]
REQUIRED = ["tag_number", "species", "sex"]

SPECIES_WORDS = {"cattle": "CATTLE", "cow": "CATTLE", "goat": "GOAT", "goats": "GOAT",
                 "sheep": "SHEEP", "chicken": "CHICKEN", "chickens": "CHICKEN"}
SEX_WORDS = {"female": "FEMALE", "f": "FEMALE", "male": "MALE", "m": "MALE"}
YES_NO = {"": False, "no": False, "n": False, "yes": True, "y": True}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")      # 2024-03-01 or 01/03/2024

TEMPLATE = (
    "tag_number,species,sex,breed,date_of_birth,castrated,notes\n"
    "C101,cattle,female,Boran,2023-05-14,,Bought from a neighbour\n"
    "G045,goat,male,Galla,01/03/2025,yes,\n"
)


def decode(raw):
    """Bytes to text. Excel's "CSV UTF-8" starts with a hidden marker (a BOM),
    which utf-8-sig removes; older Excel on Windows saves as cp1252."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def parse_date(text):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def read_animals(raw, farm_id, species_default=None):
    """Check a CSV file's rows. Returns (animals, problems): the Livestock
    objects ready to save, and a list of (row number, message). Nothing is
    added to the database here."""
    if len(raw) > MAX_BYTES:
        return [], [(None, "The file is too big. Split it into smaller files (up to about 1 MB each).")]
    text = decode(raw)
    # Excel in some countries separates columns with ";" instead of ",".
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        return [], [(1, f"The first row must name the columns. Missing: {', '.join(missing)}. "
                        "Download the template to see the layout.")]
    reader.fieldnames = headers

    animals, problems, seen = [], [], {}
    for number, row in enumerate(reader, start=2):        # row 1 is the headings
        if number - 1 > MAX_ROWS:
            return [], [(None, f"The file has more than {MAX_ROWS} animals. Split it into smaller files.")]
        value = {key: (row.get(key) or "").strip() for key in COLUMNS}
        if not any(value.values()):
            continue                                       # skip empty rows at the end of a spreadsheet

        def problem(message):
            problems.append((number, message))

        tag = normalise_tag(value["tag_number"])
        if not tag:
            problem("Every animal needs a tag number.")
        elif len(tag) > 20 or not re.fullmatch(r"[A-Z0-9-]+", tag):
            problem(f"Tag \"{value['tag_number']}\": use only letters, numbers and hyphens (up to 20).")
        elif tag in seen:
            problem(f"Tag {tag} is also on row {seen[tag]}: each animal needs its own tag.")
        elif tag_in_use(farm_id, tag):
            problem(f"Tag {tag} is already used by an animal on this farm.")
        else:
            seen[tag] = number

        species = SPECIES_WORDS.get(value["species"].lower())
        if species is None:
            problem(f"Species \"{value['species']}\" isn't one of: cattle, goat, sheep, chicken.")

        sex = SEX_WORDS.get(value["sex"].lower())
        if sex is None:
            problem(f"Sex \"{value['sex']}\" should be female or male (or F / M).")

        born = None
        if value["date_of_birth"]:
            born = parse_date(value["date_of_birth"])
            if born is None:
                problem(f"Date of birth \"{value['date_of_birth']}\" isn't a date. Write it as 2024-03-01 or 01/03/2024.")
            elif born > date.today():
                problem("The date of birth can't be in the future.")

        castrated = YES_NO.get(value["castrated"].lower())
        if castrated is None:
            problem(f"Castrated \"{value['castrated']}\" should be yes, no or empty.")
        elif castrated and sex == "FEMALE":
            problem("Only a male can be castrated.")

        if len(value["breed"]) > 50:
            problem("The breed is too long (50 characters at most).")
        if len(value["notes"]) > 500:
            problem("The notes are too long (500 characters at most).")

        animals.append(Livestock(farmer_id=farm_id, tag_number=tag, species=species, gender=sex,
                                 breed=value["breed"] or None, date_of_birth=born, castrated=bool(castrated),
                                 description=value["notes"] or None))

    if not animals and not problems:
        problems.append((None, "The file has no animals in it, only the headings."))
    return (animals if not problems else []), problems