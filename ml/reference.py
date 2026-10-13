#he disease reference table, written as Python.

from dataclasses import dataclass

# The species

# normal_temp: average healthy rectal temperature in degC. A sick animal's recorded temperature is built from this.
SPECIES_INFO = {
    "CATTLE": {"prefix": "C", "normal_temp": 38.5,
               "breeds": ("Friesian", "Ayrshire", "Boran", "Sahiwal")},
    "GOAT": {"prefix": "G", "normal_temp": 39.1,
             "breeds": ("Galla", "Toggenburg", "Saanen", "Small East African")},
    "SHEEP": {"prefix": "S", "normal_temp": 39.1,
              "breeds": ("Dorper", "Red Maasai", "Blackhead Persian")},
    "CHICKEN": {"prefix": "CH", "normal_temp": 41.7,
                "breeds": ("Kienyeji", "Kuroiler", "Kenbro")},
}

# Cnditions

# Groups:
#   A = vaccine-preventable    B = everyday, treatable
#   M = mortality only (weak newborns)    X = injuries
# A and B are what the model predicts; M and X are recorded but never count as a "new illness".
GROUPS = ("A", "B", "M", "X")
RANKS = ("common", "occasional", "rare")

# Words a condition can list under `triggers`. Each one is a reason the
# simulator raises that condition's risk on a given day.
TRIGGERS = (
    "rains",            # long or short rains
    "spray_lapse",      # the herd missed its tick spraying
    "deworm_overdue",   # more than 90 days since deworming
    "vaccine_overdue",  # the animal's vaccine for this disease has run out
    "contagious",       # each recent case in the herd raises everyone's risk
)


@dataclass(frozen=True)
class Condition:
    """
    frozen=True makes each Condition read-only once created, so no part of
    the simulator can change a fact by accident.
    """
    name: str
    group: str                       # one of GROUPS
    rank: str                        # one of RANKS: how common it is
    treatment: str                   # what gets written in health_records.treatment
    fever: bool = False              # does the sick animal run a temperature?
    triggers: tuple = ()             # words from TRIGGERS
    sex: str | None = None           # "FEMALE" if only females get it
    max_age_days: int | None = None  # only animals younger than this get it
    after_birth: bool = False        # only within 3 days of giving birth
    vaccine: str | None = None       # the vaccine that prevents it (Group A)
    resistant_breeds: tuple = ()     # breeds that get it less often
    death_chance: float = 0.0        # chance a treated case still dies


# Shared Group A diseases, defined once and reused by each species that
# gets them (same facts for cattle, goats and sheep).
FMD = Condition("Foot and Mouth Disease", "A", "rare",
                "Supportive care + Oxytetracycline LA for secondary infection",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="FMD vaccine", death_chance=0.05)
RVF = Condition("Rift Valley Fever", "A", "rare", "Supportive care (no treatment)",
                fever=True, triggers=("rains", "vaccine_overdue"),
                vaccine="RVF vaccine", death_chance=0.05)
PPR = Condition("PPR", "A", "rare", "Supportive care (no specific treatment)",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="PPR vaccine", death_chance=0.30)
POX = Condition("Sheep and goat pox", "A", "rare", "Supportive care",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="Sheep and goat pox vaccine", death_chance=0.05)
ORF = Condition("Orf", "A", "occasional", "Supportive care (wear gloves)",
                triggers=("contagious", "vaccine_overdue"), vaccine="Orf vaccine")

CONDITIONS = {
    "CATTLE": (
        Condition("East Coast Fever", "B", "common",
                  "Buparvaquone (Bupalex) + Oxytetracycline 10% LA + Dexa",
                  fever=True, triggers=("rains", "spray_lapse"),
                  resistant_breeds=("Boran", "Sahiwal"), death_chance=0.10),
        Condition("Calf scours", "B", "common", "Oral rehydration + S-Dime",
                  fever=True, triggers=("contagious",), max_age_days=42,
                  death_chance=0.05),
        Condition("Gastrointestinal worms", "B", "common", "Nilzan drench",
                  triggers=("rains", "deworm_overdue")),
        Condition("Mastitis", "B", "common", "Penstrep", fever=True, sex="FEMALE"),
        Condition("Foot rot", "B", "occasional", "Hoof treatment + Oxytetracycline",
                  triggers=("rains",)),
        Condition("Retained afterbirth", "B", "occasional", "Antibiotics + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Milk fever", "B", "rare", "Calcium injection by vet",
                  sex="FEMALE", after_birth=True, death_chance=0.05),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        FMD,
        Condition("Lumpy skin disease", "A", "rare", "Supportive care",
                  fever=True, triggers=("rains", "vaccine_overdue"),
                  vaccine="Lumpy skin vaccine", death_chance=0.05),
        Condition("CBPP", "A", "rare", "Vet treatment",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="CBPP vaccine", death_chance=0.05),
        RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "occasional", "Warmth + colostrum"),
    ),
    "GOAT": (
        Condition("Pneumonia", "B", "common", "Oxytetracycline 10% LA",
                  fever=True, triggers=("rains", "contagious"), death_chance=0.05),
        Condition("Lungworm", "B", "occasional", "Dewormer",
                  triggers=("deworm_overdue",)),
        Condition("Gastrointestinal worms", "B", "common", "Nilzan drench",
                  triggers=("rains", "deworm_overdue")),
        Condition("Vulval infection", "B", "occasional",
                  "Magadi salt wash + Methoxicash",
                  triggers=("contagious",), sex="FEMALE"),
        Condition("Diarrhoea", "B", "occasional", "Fluids + S-Dime",
                  triggers=("contagious",), max_age_days=180, death_chance=0.03),
        Condition("Mastitis", "B", "occasional", "Antibiotics", fever=True, sex="FEMALE"),
        Condition("Mange", "B", "occasional", "Acaricide", triggers=("contagious",)),
        Condition("Foot rot", "B", "occasional", "Hoof treatment", triggers=("rains",)),
        Condition("Retained afterbirth", "B", "rare", "S-Dime + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        Condition("CCPP", "A", "rare", "Vet treatment",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="CCPP vaccine", death_chance=0.05),
        PPR, POX, ORF, FMD, RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "common", "Warmth + colostrum"),
    ),
    "SHEEP": (
        Condition("Pneumonia", "B", "common", "Oxytetracycline 10% LA + Histacine",
                  fever=True, triggers=("rains", "contagious"), death_chance=0.05),
        Condition("Lungworm", "B", "occasional", "Dewormer",
                  triggers=("deworm_overdue",)),
        Condition("Gastrointestinal worms", "B", "common", "Dewormer",
                  triggers=("rains", "deworm_overdue")),
        Condition("Foot rot", "B", "occasional", "Hoof treatment", triggers=("rains",)),
        Condition("Mange", "B", "occasional", "Acaricide", triggers=("contagious",)),
        Condition("Diarrhoea", "B", "occasional", "Fluids",
                  triggers=("contagious",), max_age_days=180, death_chance=0.03),
        Condition("Flystrike", "B", "occasional", "Remove maggots + wound care",
                  triggers=("rains",)),
        Condition("Leg paralysis (suspected heartwater)", "B", "rare",
                  "Oxytetracycline", fever=True, triggers=("spray_lapse",),
                  death_chance=0.50),
        Condition("Retained afterbirth", "B", "rare", "Antibiotics + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        Condition("Bluetongue", "A", "rare", "Supportive care",
                  fever=True, triggers=("rains", "vaccine_overdue"),
                  vaccine="Bluetongue vaccine", death_chance=0.05),
        PPR, POX, ORF, FMD, RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "common", "Warmth + colostrum"),
    ),
    "CHICKEN": (
        Condition("Coccidiosis", "B", "common", "Amprolium",
                  triggers=("rains", "contagious"), death_chance=0.05),
        Condition("Bacterial respiratory disease", "B", "common", "Antibiotics",
                  fever=True, triggers=("contagious",), death_chance=0.05),
        Condition("Gastrointestinal worms", "B", "occasional", "Poultry dewormer",
                  triggers=("deworm_overdue",)),
        Condition("External parasites", "B", "occasional", "Poultry parasite treatment",
                  triggers=("contagious",)),
        Condition("Bacterial enteritis", "B", "occasional", "Fluids + medication",
                  death_chance=0.03),
        Condition("Footpad dermatitis", "B", "occasional", "Dry litter + treatment",
                  triggers=("rains",)),
        Condition("Egg binding", "B", "rare", "Vet treatment", sex="FEMALE",
                  death_chance=0.05),
        Condition("Newcastle disease", "A", "occasional", "Supportive care (no treatment)",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="Newcastle vaccine", death_chance=0.30),
        Condition("Fowl pox", "A", "occasional", "Supportive care",
                  triggers=("contagious", "vaccine_overdue"),
                  vaccine="Fowl pox vaccine", death_chance=0.05),
        Condition("Fowl typhoid", "A", "rare", "Supportive care",
                  fever=True, triggers=("vaccine_overdue",),
                  vaccine="Fowl typhoid vaccine", death_chance=0.30),
        Condition("Wounds and pecking", "X", "occasional", "Separate bird + wound care",
                  death_chance=0.02),
    ),
}

# Vvaccines

# From the KEVEVAPI leaflets. first_dose_days = youngest age for the first
# dose; repeat_days = gap between doses; doses = total doses (None = keep repeating for life).
VACCINES = {
    "FMD vaccine": {"species": ("CATTLE", "GOAT", "SHEEP"), "first_dose_days": 0, "repeat_days": 182, "doses": None},
    "Lumpy skin vaccine": {"species": ("CATTLE",), "first_dose_days": 0, "repeat_days": 365, "doses": None},
    "CBPP vaccine": {"species": ("CATTLE",), "first_dose_days": 182, "repeat_days": 365, "doses": None},
    "RVF vaccine": {"species": ("CATTLE", "GOAT", "SHEEP"), "first_dose_days": 0, "repeat_days": 365, "doses": None},
    "CCPP vaccine": {"species": ("GOAT",), "first_dose_days": 91, "repeat_days": 182, "doses": None},
    "PPR vaccine": {"species": ("GOAT", "SHEEP"), "first_dose_days": 122, "repeat_days": 365, "doses": None},
    "Sheep and goat pox vaccine": {"species": ("GOAT", "SHEEP"), "first_dose_days": 35, "repeat_days": 365, "doses": None},
    "Bluetongue vaccine": {"species": ("SHEEP",), "first_dose_days": 91, "repeat_days": 365, "doses": None},
    "Orf vaccine": {"species": ("GOAT", "SHEEP"), "first_dose_days": 42, "repeat_days": 365, "doses": None},
    "Newcastle vaccine": {"species": ("CHICKEN",), "first_dose_days": 4, "repeat_days": 42, "doses": 2},
    "Fowl pox vaccine": {"species": ("CHICKEN",), "first_dose_days": 28, "repeat_days": None, "doses": 1},
    # The leaflet says "later growing period" without an age: 8 weeks is an assumption.
    "Fowl typhoid vaccine": {"species": ("CHICKEN",), "first_dose_days": 56, "repeat_days": None, "doses": 1},
}

# Farm routines based on real farm data

DEWORM_EVERY_DAYS = 90
SPRAYS_PER_WEEK = {"CATTLE": 2, "GOAT": 1, "SHEEP": 1}   # chickens are not sprayed

# Kenya's rains: long rains Mar-May, short rains Oct-Dec.
LONG_RAINS = (3, 4, 5)
SHORT_RAINS = (10, 11, 12)

# ASSUMPTIONS

YEARLY_CHANCE = {"common": 0.20, "occasional": 0.05, "rare": 0.01}
RAINS_MULTIPLIER = {"long": 1.5, "short": 1.3}
SPRAY_LAPSE_MULTIPLIER = 3.0        # for 1-3 weeks after a missed spray week
DEWORM_OVERDUE_MULTIPLIER = 2.0
VACCINE_OVERDUE_MULTIPLIER = 10.0
VACCINE_UP_TO_DATE_MULTIPLIER = 0.05
OUTBREAK_BOOST_PER_CASE = 0.5       # +50% risk per recent same-species case
OUTBREAK_DAYS = 14


def daily_chance(rank):
    #Turn a yearly chance into the chance on any single day.
    yearly = YEARLY_CHANCE[rank]
    return 1 - (1 - yearly) ** (1 / 365)


def conditions_for(species, groups=("A", "B")):
    """The conditions a species can get, filtered by group. By default only
    the ones the model predicts (A and B)."""
    return [c for c in CONDITIONS[species] if c.group in groups]
