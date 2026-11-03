"""Adding many animals, health records or weights at once from a CSV file
The whole file is checked first and if any row has a problem, nothing is saved.
"""
import csv
import io
import re
from datetime import date, datetime

from sqlalchemy.orm import selectinload

from app.farm import tag_in_use
from app.forms import MAX_WEIGHT_KG, normalise_tag
from app.models import HealthRecord, Livestock, WeightRecord
from ml.reference import VACCINES

MAX_BYTES = 1_000_000        # about 1 MB: thousands of rows, far more than one farm adds at once
MAX_ROWS = 2000
ANIMAL_COLUMNS = ["tag_number", "species", "sex", "breed", "date_of_birth", "castrated", "notes"]
ANIMAL_REQUIRED = ["tag_number", "species", "sex"]

SPECIES_WORDS = {"cattle": "CATTLE", "cow": "CATTLE", "goat": "GOAT", "goats": "GOAT",
                 "sheep": "SHEEP", "chicken": "CHICKEN", "chickens": "CHICKEN"}
SEX_WORDS = {"female": "FEMALE", "f": "FEMALE", "male": "MALE", "m": "MALE"}
YES_NO = {"": False, "no": False, "n": False, "yes": True, "y": True}
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")      # 2024-03-01 or 01/03/2024

ANIMAL_TEMPLATE = (
    "tag_number,species,sex,breed,date_of_birth,castrated,notes\n"
    "C101,cattle,female,Boran,2023-05-14,,Bought from a neighbour\n"
    "G045,goat,male,Galla,01/03/2025,yes,\n"
)


def decode(raw):
    """Bytes to text."""
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

def read_rows(raw, columns, required):
    """The shared first step for every kind of file. Returns (rows, problems):
    rows is a list of (row number, {column: text}) with spaces trimmed, and
    problems is a list of (row number, message) for problems with the file
    as a whole. Row numbers count the headings as row 1, as Excel does."""
    if len(raw) > MAX_BYTES:
        return [], [(None, "The file is too big. Split it into smaller files (up to about 1 MB each).")]
    text = decode(raw)
    # Excel in some countries separates columns with ";" instead of ",".
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    headers = [(h or "").strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in required if c not in headers]
    if missing:
        return [], [(1, f"The first row must name the columns. Missing: {', '.join(missing)}. "
                        "Download the template to see the layout.")]
    reader.fieldnames = headers

    rows = []
    for number, row in enumerate(reader, start=2):        # row 1 is the headings
        if number - 1 > MAX_ROWS:
            return [], [(None, f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")]
        value = {key: (row.get(key) or "").strip() for key in columns}
        if any(value.values()):                            # skip empty rows at the end of a spreadsheet
            rows.append((number, value))
    if not rows:
        return [], [(None, "The file has nothing in it, only the headings.")]
    return rows, []


def read_animals(raw, farm_id):
    """Check a CSV file of new animals. Returns (animals, problems): the
    Livestock objects ready to save, and a list of (row number, message).
    Nothing is added to the database here."""
    rows, problems = read_rows(raw, ANIMAL_COLUMNS, ANIMAL_REQUIRED)
    animals, seen = [], {}
    for number, value in rows:


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

    return (animals if not problems else []), problems


# ---------------------------------------------------------------- records
# Health records and weights are about animals already on the farm. Each row
# names its animal by tag number, and the tag is looked up on THIS farm only,
# so a file can never add records to another farm's animals.

def farm_animals_by_tag(farm_id):
    """Every animal on the farm, keyed by tag: one query for the whole file
    instead of one per row. Their deaths and sales are loaded in the same
    go, because left_on() needs them."""
    animals = (Livestock.query.filter_by(farmer_id=farm_id)
               .options(selectinload(Livestock.mortality_record), selectinload(Livestock.commercial_records),
                        selectinload(Livestock.departure)))
    return {animal.tag_number: animal for animal in animals}


def left_on(animal):
    """The day the animal died, was sold or left another way, or None if it
    is still here. Old records can still be added for it, but none dated after it left."""
    if animal.mortality_record is not None:
        return animal.mortality_record.date_of_death
    if animal.departure is not None:
        return animal.departure.date
    sales = [r.date for r in animal.commercial_records if r.transaction_type == "SELL"]
    return min(sales) if sales else None


def check_animal_and_date(value, animals, problem):
    """The two checks every record row needs. Returns (animal, day); either
    is None if that part of the row has a problem (already reported)."""
    tag = normalise_tag(value["tag_number"])
    animal = animals.get(tag)
    if not tag:
        problem("Every row needs the animal's tag number.")
    elif animal is None:
        problem(f"There is no animal with tag {tag} on this farm. Add the animal first.")

    day = None
    if not value["date"]:
        problem("Every row needs a date.")
    else:
        day = parse_date(value["date"])
        if day is None:
            problem(f"Date \"{value['date']}\" isn't a date. Write it as 2024-03-01 or 01/03/2024.")
        elif day > date.today():
            problem("The date can't be in the future.")
        elif animal is not None and animal.date_of_birth and day < animal.date_of_birth:
            problem(f"{tag} was born on {animal.date_of_birth:%d %b %Y}, so the date can't be earlier.")
            day = None
        elif animal is not None and left_on(animal) and day > left_on(animal):
            word = {"DIED": "died", "SOLD": "was sold", "LEFT": "left the farm"}[animal.status]
            problem(f"{tag} {word} on {left_on(animal):%d %b %Y}, so the date can't be later.")
            day = None
    return animal, day


def parse_number(text):
    """"39.5" or "39,5" (Excel in some countries writes a comma) to 39.5; None if it isn't a number."""
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


HEALTH_COLUMNS = ["tag_number", "date", "record_type", "disease", "temperature", "treatment", "dosage", "notes"]
HEALTH_REQUIRED = ["tag_number", "date", "record_type"]
SPECIES_PLURAL = {"CATTLE": "cattle", "GOAT": "goats", "SHEEP": "sheep", "CHICKEN": "chickens"}
RECORD_TYPE_WORDS = {"illness": "ILLNESS", "ill": "ILLNESS", "sick": "ILLNESS",
                     "treatment": "TREATMENT", "follow-up": "TREATMENT", "follow up": "TREATMENT",
                     "vaccination": "VACCINATION", "vaccinated": "VACCINATION", "vaccine": "VACCINATION",
                     "checkup": "CHECKUP", "check-up": "CHECKUP", "check up": "CHECKUP"}

HEALTH_TEMPLATE = (
    "tag_number,date,record_type,disease,temperature,treatment,dosage,notes\n"
    "C101,2025-04-02,illness,East Coast Fever,40.5,Butalex,10 ml,Found lying down in the morning\n"
    "C101,2025-04-05,treatment,East Coast Fever,,Oxytetracycline,20 ml,\n"
    "G045,12/05/2025,vaccination,,,PPR vaccine,,\n"
    "G045,01/06/2025,checkup,,38.9,,,Healthy\n"
)


def read_health(raw, farm_id):
    """Check a CSV file of health records. Returns (records, problems), like
    read_animals. The rules are the same as on the health form, and so is
    how a row is stored, because the illness model reads these rows:
    an illness has its disease filled in, and a vaccination has the vaccine's
    exact name in treatment."""
    rows, problems = read_rows(raw, HEALTH_COLUMNS, HEALTH_REQUIRED)
    animals = farm_animals_by_tag(farm_id) if rows else {}
    # The same animal, day and kind of record twice is almost always the same
    # notebook line typed twice, or the same file uploaded twice.
    existing = {(r.animal_id, r.date, r.record_type) for r in
                HealthRecord.query.join(Livestock).filter(Livestock.farmer_id == farm_id)} if rows else set()
    records, seen = [], {}
    for number, value in rows:
        def problem(message):
            problems.append((number, message))

        animal, day = check_animal_and_date(value, animals, problem)

        kind = RECORD_TYPE_WORDS.get(value["record_type"].lower())
        if kind is None:
            problem(f"Record type \"{value['record_type']}\" should be illness, treatment, vaccination or checkup.")

        disease = value["disease"]
        if kind in ("ILLNESS", "TREATMENT") and not disease:
            problem("An illness or a treatment needs the disease or problem written in.")
        if kind == "CHECKUP":
            disease = ""                     # a check-up isn't about a disease, as on the form

        treatment = value["treatment"]
        if kind == "TREATMENT" and not treatment:
            problem("A treatment needs the medicine that was given.")
        if kind == "VACCINATION":
            # The model and the vaccine plan find vaccines by their exact name,
            # so "ppr vaccine" is stored as "PPR vaccine", and a name the app
            # doesn't know is refused rather than silently ignored later.
            names = {name.lower(): name for name in VACCINES}
            treatment = names.get(treatment.lower())
            if treatment is None:
                problem(f"Vaccine \"{value['treatment']}\" isn't one the app knows. "
                        "Write its name as in the vaccine list, e.g. FMD vaccine.")
            elif animal is not None and animal.species not in VACCINES[treatment]["species"]:
                problem(f"{treatment} isn't given to {SPECIES_PLURAL[animal.species]}.")
            disease = ""

        temperature = None
        if value["temperature"]:
            temperature = parse_number(value["temperature"])
            if temperature is None or not 30 <= temperature <= 46:
                problem(f"Temperature \"{value['temperature']}\" isn't possible. Write °C, like 39.5.")

        for column, longest in (("disease", 100), ("treatment", 100), ("dosage", 50), ("notes", 500)):
            if len(value[column]) > longest:
                problem(f"The {column} is too long ({longest} characters at most).")

        if animal is not None and day is not None and kind is not None:
            key = (animal.animal_id, day, kind)
            if key in existing:
                problem(f"{animal.tag_number} already has a {kind.lower()} record on {day:%d %b %Y}.")
            elif key in seen:
                problem(f"This is the same as row {seen[key]}: same animal, date and record type.")
            else:
                seen[key] = number

        records.append(HealthRecord(animal_id=animal.animal_id if animal else None, date=day, record_type=kind,
                                    disease=disease or None, temperature=temperature,
                                    treatment=treatment or None, dosage=value["dosage"] or None,
                                    description=value["notes"] or None))
    return (records if not problems else []), problems


WEIGHT_COLUMNS = ["tag_number", "date", "weight_kg"]
WEIGHT_TEMPLATE = (
    "tag_number,date,weight_kg\n"
    "C101,2025-04-01,312.5\n"
    "G045,01/04/2025,28\n"
)


def read_weights(raw, farm_id):
    """Check a CSV file of weigh-ins. Returns (records, problems), like read_animals."""
    rows, problems = read_rows(raw, WEIGHT_COLUMNS, WEIGHT_COLUMNS)
    animals = farm_animals_by_tag(farm_id) if rows else {}
    existing = {(r.animal_id, r.date) for r in
                WeightRecord.query.join(Livestock).filter(Livestock.farmer_id == farm_id)} if rows else set()
    records, seen = [], {}
    for number, value in rows:
        def problem(message):
            problems.append((number, message))

        animal, day = check_animal_and_date(value, animals, problem)

        weight = parse_number(value["weight_kg"]) if value["weight_kg"] else None
        if weight is None:
            problem(f"Weight \"{value['weight_kg']}\" isn't a number of kg, like 312.5.")
        elif weight <= 0:
            problem("The weight must be more than 0.")
        elif animal is not None and weight > MAX_WEIGHT_KG[animal.species]:
            problem(f"{weight:g} kg is heavier than any {animal.species.lower()} "
                    f"({MAX_WEIGHT_KG[animal.species]} kg). Check the reading.")

        if animal is not None and day is not None:
            key = (animal.animal_id, day)
            if key in existing:
                problem(f"{animal.tag_number} already has a weight on {day:%d %b %Y}.")
            elif key in seen:
                problem(f"{animal.tag_number} is weighed on {day:%d %b %Y} on row {seen[key]} too.")
            else:
                seen[key] = number

        records.append(WeightRecord(animal_id=animal.animal_id if animal else None, date=day, weight=weight))
    return (records if not problems else []), problems


# What the import page needs for each kind of file. The route and the page
# are shared; only these details differ.
KINDS = {
    "animals": {
        "read": read_animals, "template": ANIMAL_TEMPLATE, "noun": "animal",
        "title": "animals", "intro": "One animal per row. Each tag must be new on this farm.",
        "columns": [
            ("tag_number", True, "Letters, numbers and hyphens, e.g. C101. Must be new on this farm."),
            ("species", True, "cattle, goat, sheep or chicken"),
            ("sex", True, "female or male (or F / M)"),
            ("breed", False, "e.g. Boran"),
            ("date_of_birth", False, "2024-03-01 or 01/03/2024"),
            ("castrated", False, "yes for a castrated male; otherwise leave empty"),
            ("notes", False, "Anything else, up to 500 characters"),
        ],
    },
    "health": {
        "read": read_health, "template": HEALTH_TEMPLATE, "noun": "health record",
        "title": "health records",
        "intro": "One illness, treatment, vaccination or check-up per row, for animals already on this farm.",
        "columns": [
            ("tag_number", True, "The animal's tag, e.g. C101. The animal must already be on this farm."),
            ("date", True, "2024-03-01 or 01/03/2024. Not before the animal was born, or after it died or was sold."),
            ("record_type", True, "illness, treatment, vaccination or checkup"),
            ("disease", False, "Needed for an illness or a treatment, e.g. East Coast Fever"),
            ("temperature", False, "In °C, e.g. 39.5"),
            ("treatment", False, "The medicine given (needed for a treatment). For a vaccination, the vaccine's name, e.g. FMD vaccine"),
            ("dosage", False, "e.g. 10 ml"),
            ("notes", False, "Anything else, up to 500 characters"),
        ],
    },
    "weights": {
        "read": read_weights, "template": WEIGHT_TEMPLATE, "noun": "weight",
        "title": "weights", "intro": "One weigh-in per row, for animals already on this farm.",
        "columns": [
            ("tag_number", True, "The animal's tag, e.g. C101. The animal must already be on this farm."),
            ("date", True, "2024-03-01 or 01/03/2024"),
            ("weight_kg", True, "The weight in kg, e.g. 312.5"),
        ],
    },
}