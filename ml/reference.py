#The disease reference table, written as Python.

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

# Conditions

# Groups:
#   A = vaccine-preventable    B = everyday, treatable
#   M = mortality only (weak newborns)    X = injuries
# A and B are recorded as illnesses; M and X never count as one.
GROUPS = ("A", "B", "M", "X")
RANKS = ("common", "occasional", "rare")

# Words a condition can list under `triggers`. Each one is a reason the
# simulator raises that condition's risk on a given day.
TRIGGERS = (
    "rains",            # rain in the last 30 days: the wetter, the higher the risk
    "rains_onset",      # the rains starting after a dry month (worms hatch in warm, wet weather)
    "heavy_rain",       # very heavy rain (250+ mm in 30 days), as in an El Nino season
    "spray_lapse",      # the herd missed its tick spraying
    "deworm_overdue",   # more than 90 days since deworming
    "vaccine_overdue",  # the animal's vaccine for this disease has run out
    "contagious",       # each recent case in the herd raises everyone's risk
)

# Things about a farm's surroundings that stay the same from year to year,
# so a farm that had many cases of a disease last year tends to have them
# again. Each simulated farm gets its own level of each (1.0 = average).
ENVIRONMENTS = (
    "wet",       # poorly drained, muddy ground: foot rot, worms, liver fluke
    "ticks",     # tick-infested grazing: East Coast Fever, heartwater, dermatophilosis
    "hygiene",   # dirty pens and bedding: scours, coccidiosis, mastitis
)

# Where the facts come from (cited in the report and shown with each alert).
UON = "UoN Faculty of Veterinary Medicine lecture notes"
MERCK = "Merck Veterinary Manual"


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
    min_age_days: int | None = None  # only animals at least this old get it
    max_age_days: int | None = None  # only animals younger than this get it
    after_birth: bool = False        # only in the days after giving birth...
    after_birth_days: int = 3        # ...this many of them
    early_lactation_multiplier: float = 1.0   # extra risk in the 60 days after giving birth
    young_multiplier: float = 1.0    # extra risk for animals under 6 months
    environment: str | None = None   # the farm surroundings (ENVIRONMENTS) that raise it
    vaccine: str | None = None       # the vaccine that prevents it (Group A)
    resistant_breeds: tuple = ()     # breeds that get it less often
    death_chance: float = 0.0        # chance a treated case still dies
    watch_only: bool = False         # rare outbreak disease: alerts mention it, the model doesn't predict it
    advice: str = ""                 # what the farmer should do, shown in the alerts
    source: str = ""                 # where the facts come from


# Shared Group A diseases, defined once and reused by each species that
# gets them (same facts for cattle, goats and sheep). They are rare,
# outbreak diseases, so the model leaves them to the alerts' watch list.
FMD = Condition("Foot and Mouth Disease", "A", "rare",
                "Supportive care + Oxytetracycline LA for secondary infection",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="FMD vaccine", death_chance=0.05, watch_only=True,
                advice="Keep FMD vaccination every 6 months; report suspected cases to the vet.",
                source=MERCK)
RVF = Condition("Rift Valley Fever", "A", "rare", "Supportive care (no treatment)",
                fever=True, triggers=("rains", "heavy_rain", "vaccine_overdue"),
                vaccine="RVF vaccine", death_chance=0.05, watch_only=True,
                advice="In an El Nino year, vaccinate against RVF a month before the rains.",
                source=f"{MERCK}; vet advice on El Nino")
PPR = Condition("PPR", "A", "rare", "Supportive care (no specific treatment)",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="PPR vaccine", death_chance=0.30, watch_only=True,
                advice="Vaccinate goats and sheep; isolate new animals for 2-3 weeks.",
                source=f"{UON}: Food Animal Medicine II")
POX = Condition("Sheep and goat pox", "A", "rare", "Supportive care",
                fever=True, triggers=("contagious", "vaccine_overdue"),
                vaccine="Sheep and goat pox vaccine", death_chance=0.05, watch_only=True,
                advice="Vaccinate yearly; isolate animals with skin nodules.",
                source=f"{UON}: Food Animal Medicine II")
# Orf: kids and lambs are more susceptible than adults and it is worse in goats.
ORF = Condition("Orf", "A", "occasional", "Supportive care (wear gloves)",
                triggers=("contagious", "vaccine_overdue"), vaccine="Orf vaccine",
                young_multiplier=3.0,
                advice="Check kids' and lambs' lips for scabs; isolate cases and wear gloves (it spreads to people).",
                source=f"{UON}: Food Animal Medicine II (contagious ecthyma)")
# Gastrointestinal worms: eggs need warmth and humidity to hatch, the young
# suffer most, and strategic deworming at the start of the rains prevents a
# build-up on pasture.
WORMS_ADVICE = ("Deworm at the start of the rains; watch the young for pale gums, "
                "bottle jaw, diarrhoea and weight loss.")
WORMS_SOURCE = f"{UON}: Gastrointestinal parasitism, fascioliasis and Johne's disease"
FOOT_ROT_ADVICE = ("Keep pens and paths drained and free of stones; use a footbath; "
                   "isolate and treat lame animals early.")
FOOT_ROT_SOURCE = f"{UON}: Foot rot in cattle; vet advice on El Nino"
COCCI_ADVICE = ("Keep pens dry and clean and feed off the ground; watch the young for "
                "bloody, smelly diarrhoea.")
COCCI_SOURCE = f"{UON}: Coccidiosis (Gitau, 2025)"
FLUKE = dict(triggers=("rains",), environment="wet",
             advice="Keep animals off swampy, poorly drained grazing; treat with a flukicide.",
             source=WORMS_SOURCE)

CONDITIONS = {
    "CATTLE": (
        # Brown ear tick; warm, wet zones; breed and age are risk factors.
        Condition("East Coast Fever", "B", "common",
                  "Buparvaquone (Bupalex) + Oxytetracycline 10% LA + Dexa",
                  fever=True, triggers=("rains", "spray_lapse"), environment="ticks",
                  resistant_breeds=("Boran", "Sahiwal"), death_chance=0.10,
                  advice="Spray or dip every week (twice a week in the rains); check ears for "
                         "brown ear ticks; watch for fever and swollen lymph nodes.",
                  source=f"{UON}: East Coast Fever (Gitau, 2022)"),
        # Newborns (12 hours to 14 days), poor hygiene, no colostrum.
        Condition("Calf scours", "B", "common", "Oral rehydration + S-Dime",
                  fever=True, triggers=("contagious",), max_age_days=30,
                  environment="hygiene", death_chance=0.05,
                  advice="Make sure every calf suckles colostrum within 12 hours; keep calf pens clean and dry.",
                  source=f"{UON}: Colibacillosis (Gitau, 2025)"),
        Condition("Coccidiosis", "B", "occasional", "Amprolium",
                  triggers=("rains", "contagious"), max_age_days=365,
                  environment="hygiene", advice=COCCI_ADVICE, source=COCCI_SOURCE),
        Condition("Gastrointestinal worms", "B", "common", "Nilzan drench",
                  triggers=("rains", "rains_onset", "deworm_overdue"),
                  young_multiplier=2.0, environment="wet",
                  advice=WORMS_ADVICE, source=WORMS_SOURCE),
        Condition("Liver fluke", "B", "occasional", "Flukicide (e.g. triclabendazole)", **FLUKE),
        # Most new infections early in lactation; environmental mastitis
        # rises in wet, muddy conditions.
        Condition("Mastitis", "B", "common", "Penstrep", fever=True, sex="FEMALE",
                  triggers=("rains",), early_lactation_multiplier=3.0, environment="hygiene",
                  min_age_days=730,
                  advice="Milk with clean, dry hands and udders; strip-test cows in the first "
                         "two months after calving; keep bedding dry.",
                  source=f"{MERCK}: Mastitis in large animals"),
        Condition("Foot rot", "B", "occasional", "Hoof treatment + Oxytetracycline",
                  triggers=("rains", "heavy_rain"), environment="wet",
                  advice=FOOT_ROT_ADVICE, source=FOOT_ROT_SOURCE),
        # Cows around calving; El Nino years (vet advice).
        Condition("Laminitis", "B", "occasional", "Hoof trimming + NSAIDs + diet change",
                  sex="FEMALE", after_birth=True, after_birth_days=60, triggers=("heavy_rain",),
                  advice="Change cows' diet slowly around calving (no sudden grain); trim hooves; "
                         "avoid hard, rough floors.",
                  source=f"{UON}: Laminitis (founder) in cattle; vet advice on El Nino"),
        # Cattle 6 months to 2 years in good condition, in the wet season.
        Condition("Blackquarter", "A", "occasional", "Penicillin (early) + vet check",
                  fever=True, triggers=("rains", "vaccine_overdue"),
                  min_age_days=180, max_age_days=730, vaccine="Blackquarter vaccine",
                  death_chance=0.50,
                  advice="Vaccinate young stock (6 months to 2 years) twice a year, before the rains.",
                  source=f"{UON}: Blackquarter"),
        # Highest in wet weather, spread by biting flies; heavy in El Nino years.
        Condition("Lumpy skin disease", "A", "occasional", "Supportive care",
                  fever=True, triggers=("rains", "heavy_rain", "vaccine_overdue"),
                  vaccine="Lumpy skin vaccine", death_chance=0.05,
                  advice="Vaccinate every year, a month before the rains in an El Nino year; "
                         "control biting flies.",
                  source=f"{UON}: Lumpy skin disease; vet advice on El Nino"),
        Condition("Retained afterbirth", "B", "occasional", "Antibiotics + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Milk fever", "B", "rare", "Calcium injection by vet",
                  sex="FEMALE", after_birth=True, death_chance=0.05),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        FMD,
        Condition("CBPP", "A", "rare", "Vet treatment",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="CBPP vaccine", death_chance=0.05, watch_only=True,
                  advice="Vaccinate yearly; report coughing cattle to the vet.", source=MERCK),
        RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "occasional", "Warmth + colostrum"),
    ),
    "GOAT": (
        Condition("Pneumonia", "B", "common", "Oxytetracycline 10% LA",
                  fever=True, triggers=("rains", "contagious"), death_chance=0.05,
                  advice="House goats dry and draught-free in the rains; isolate coughing animals.",
                  source=f"{MERCK}: Respiratory diseases of sheep and goats"),
        Condition("Lungworm", "B", "occasional", "Dewormer",
                  triggers=("deworm_overdue",), advice=WORMS_ADVICE, source=WORMS_SOURCE),
        Condition("Gastrointestinal worms", "B", "common", "Nilzan drench",
                  triggers=("rains", "rains_onset", "deworm_overdue"),
                  young_multiplier=2.0, environment="wet",
                  advice=WORMS_ADVICE, source=WORMS_SOURCE),
        Condition("Coccidiosis", "B", "occasional", "Amprolium",
                  triggers=("rains", "contagious"), max_age_days=180,
                  environment="hygiene", advice=COCCI_ADVICE, source=COCCI_SOURCE),
        Condition("Vulval infection", "B", "occasional",
                  "Magadi salt wash + Methoxicash",
                  triggers=("contagious",), sex="FEMALE"),
        Condition("Diarrhoea", "B", "occasional", "Fluids + S-Dime",
                  triggers=("contagious",), max_age_days=180, environment="hygiene",
                  death_chance=0.03,
                  advice="Make sure kids get colostrum early; keep pens clean and dry.",
                  source=f"{UON}: Colibacillosis (Gitau, 2025)"),
        Condition("Mastitis", "B", "occasional", "Antibiotics", fever=True, sex="FEMALE",
                  early_lactation_multiplier=3.0, environment="hygiene", min_age_days=365,
                  advice="Check does' udders for heat and swelling in the first two months after kidding.",
                  source=f"{MERCK}: Mastitis in large animals"),
        Condition("Mange", "B", "occasional", "Acaricide", triggers=("contagious",)),
        # Prolonged wetting of the skin (rain) and ticks.
        Condition("Dermatophilosis", "B", "occasional", "Oxytetracycline LA + dry housing",
                  triggers=("rains", "contagious"), environment="ticks",
                  advice="Give goats dry shelter in the rains and keep up tick control; "
                         "isolate goats with crusty, matted skin.",
                  source=f"{MERCK}: Dermatophilosis; vet advice"),
        Condition("Foot rot", "B", "occasional", "Hoof treatment",
                  triggers=("rains", "heavy_rain"), environment="wet",
                  advice=FOOT_ROT_ADVICE, source=FOOT_ROT_SOURCE),
        Condition("Retained afterbirth", "B", "rare", "S-Dime + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        Condition("CCPP", "A", "rare", "Vet treatment",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="CCPP vaccine", death_chance=0.05, watch_only=True,
                  advice="Keep CCPP vaccination every 6 months; isolate coughing goats.", source=MERCK),
        PPR, POX, ORF, FMD, RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "common", "Warmth + colostrum"),
    ),
    "SHEEP": (
        Condition("Pneumonia", "B", "common", "Oxytetracycline 10% LA + Histacine",
                  fever=True, triggers=("rains", "contagious"), death_chance=0.05,
                  advice="House sheep dry and draught-free in the rains; isolate coughing animals.",
                  source=f"{MERCK}: Respiratory diseases of sheep and goats"),
        Condition("Lungworm", "B", "occasional", "Dewormer",
                  triggers=("deworm_overdue",), advice=WORMS_ADVICE, source=WORMS_SOURCE),
        # Red Maasai sheep resist worms (lecture notes).
        Condition("Gastrointestinal worms", "B", "common", "Dewormer",
                  triggers=("rains", "rains_onset", "deworm_overdue"),
                  young_multiplier=2.0, environment="wet", resistant_breeds=("Red Maasai",),
                  advice=WORMS_ADVICE, source=WORMS_SOURCE),
        Condition("Liver fluke", "B", "occasional", "Flukicide (e.g. triclabendazole)", **FLUKE),
        Condition("Coccidiosis", "B", "occasional", "Amprolium",
                  triggers=("rains", "contagious"), max_age_days=180,
                  environment="hygiene", advice=COCCI_ADVICE, source=COCCI_SOURCE),
        Condition("Foot rot", "B", "occasional", "Hoof treatment",
                  triggers=("rains", "heavy_rain"), environment="wet",
                  advice=FOOT_ROT_ADVICE, source=FOOT_ROT_SOURCE),
        Condition("Mange", "B", "occasional", "Acaricide", triggers=("contagious",)),
        Condition("Diarrhoea", "B", "occasional", "Fluids",
                  triggers=("contagious",), max_age_days=180, environment="hygiene",
                  death_chance=0.03,
                  advice="Make sure lambs get colostrum early; keep pens clean and dry.",
                  source=f"{UON}: Colibacillosis (Gitau, 2025)"),
        Condition("Flystrike", "B", "occasional", "Remove maggots + wound care",
                  triggers=("rains",),
                  advice="Check dirty back ends and wounds daily in warm, wet weather; dag dirty wool.",
                  source=f"{MERCK}: Flystrike in sheep"),
        Condition("Leg paralysis (suspected heartwater)", "B", "rare",
                  "Oxytetracycline", fever=True, triggers=("spray_lapse",),
                  environment="ticks", death_chance=0.50),
        Condition("Retained afterbirth", "B", "rare", "Antibiotics + vet check",
                  fever=True, sex="FEMALE", after_birth=True),
        Condition("Bloat", "B", "rare", "Emergency vet treatment", death_chance=0.05),
        # Spread by Culicoides midges, so seasonal (rains).
        Condition("Bluetongue", "A", "occasional", "Supportive care",
                  fever=True, triggers=("rains", "vaccine_overdue"),
                  vaccine="Bluetongue vaccine", death_chance=0.05,
                  advice="Vaccinate sheep before the rains; house them at dusk and dawn when midges bite.",
                  source=f"{UON}: Food Animal Medicine II"),
        PPR, POX, ORF, FMD, RVF,
        Condition("Injury", "X", "occasional", "Wound care", death_chance=0.02),
        Condition("Weak at birth / starvation", "M", "common", "Warmth + colostrum"),
    ),
    "CHICKEN": (
        # Wet litter in the rains.
        Condition("Coccidiosis", "B", "common", "Amprolium",
                  triggers=("rains", "contagious"), environment="hygiene", death_chance=0.05,
                  advice="Keep litter dry (fix leaking roofs and drinkers); add a coccidiostat "
                         "to water if birds have bloody droppings.",
                  source=f"{UON}: Parasitic diseases of poultry"),
        Condition("Bacterial respiratory disease", "B", "common", "Antibiotics",
                  fever=True, triggers=("rains", "contagious"), death_chance=0.05,
                  advice="Keep the house dry and well aired but draught-free; separate sneezing birds.",
                  source=f"{MERCK}: Mycoplasmosis in poultry"),
        Condition("Gastrointestinal worms", "B", "occasional", "Poultry dewormer",
                  triggers=("deworm_overdue",),
                  advice="Deworm free-range birds every 3 months.",
                  source=f"{UON}: Parasitic diseases of poultry"),
        # Depluming mites worse in warm, wet weather.
        Condition("External parasites", "B", "occasional", "Poultry parasite treatment",
                  triggers=("rains", "contagious"),
                  advice="Check under wings and around the vent for mites and lice; clean perches and nests.",
                  source=f"{UON}: Parasitic diseases of poultry"),
        Condition("Bacterial enteritis", "B", "occasional", "Fluids + medication",
                  death_chance=0.03),
        Condition("Footpad dermatitis", "B", "occasional", "Dry litter + treatment",
                  triggers=("rains",)),
        Condition("Egg binding", "B", "rare", "Vet treatment", sex="FEMALE",
                  death_chance=0.05),
        Condition("Newcastle disease", "A", "occasional", "Supportive care (no treatment)",
                  fever=True, triggers=("contagious", "vaccine_overdue"),
                  vaccine="Newcastle vaccine", death_chance=0.30,
                  advice="Vaccinate against Newcastle; keep visitors, other birds and shared "
                         "egg trays away from the flock.",
                  source=f"{UON}: Viral diseases of poultry (Gitao)"),
        # Spread by mosquitoes, so more in the rains.
        Condition("Fowl pox", "A", "occasional", "Supportive care",
                  triggers=("rains", "contagious", "vaccine_overdue"),
                  vaccine="Fowl pox vaccine", death_chance=0.05,
                  advice="Vaccinate chicks; control mosquitoes around the house in the rains.",
                  source=f"{MERCK}: Fowlpox"),
        Condition("Fowl typhoid", "A", "rare", "Supportive care",
                  fever=True, triggers=("vaccine_overdue",),
                  vaccine="Fowl typhoid vaccine", death_chance=0.30, watch_only=True,
                  advice="Vaccinate growing birds; buy chicks from clean hatcheries.",
                  source=f"{UON}: Bacterial diseases of poultry"),
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
    # Twice a year in endemic areas (UoN notes: Blackquarter); from 6 months old.
    "Blackquarter vaccine": {"species": ("CATTLE",), "first_dose_days": 180, "repeat_days": 182, "doses": None},
}

# Kwetu's vaccination plan (confirmed with the farm): the simulator's
# default. Each simulated farm can be given its own plan instead.
FARM_VACCINES = ("CCPP vaccine", "FMD vaccine", "Lumpy skin vaccine")

# Farm routines based on real farm data
DEWORM_EVERY_DAYS = 90
SPRAYS_PER_WEEK = {"CATTLE": 2, "GOAT": 1, "SHEEP": 1}   # chickens are not sprayed

# Kenya's rains: long rains Mar-May, short rains Oct-Dec. Kwetu is near
# Thika (on the Murang'a-Kiambu border), which has both seasons. The
# simulator and the model use the rain itself (ml/rainfall.py); these months
# only name the season and build the seasonal calendar the model must beat.
LONG_RAINS = (3, 4, 5)
SHORT_RAINS = (10, 11, 12)

# Kenya's rains: long rains Mar-May, short rains Oct-Dec. Kwetu is near
# Thika (on the Murang'a-Kiambu border), which has both seasons. The
# simulator and the model use the rain itself (ml/rainfall.py); these months
# only name the season and build the seasonal calendar the model must beat.
LONG_RAINS = (3, 4, 5)
SHORT_RAINS = (10, 11, 12)

# Products, as named in Kwetu's medicine log.
SPRAY_PRODUCT = "Dip Dominex"
DEWORMER = {"CATTLE": "Nilzan", "GOAT": "Nilzan", "SHEEP": "Nilzan", "CHICKEN": "Poultry dewormer"}

# How often the routine slips (assumptions).
VACCINE_ON_TIME_CHANCE = 0.70       # chance a due vaccine is given on its due day
VACCINE_DELAY_DAYS = (14, 60)       # if not, the farmer tries again this many days later
DEWORM_LATE_CHANCE = 0.20           # chance a group deworming is put off
DEWORM_DELAY_DAYS = (14, 45)
DEWORM_MIN_AGE_DAYS = 30            # very young animals are left out
MISSED_SPRAY_WEEK_CHANCE = 1 / 12   # Kwetu's spray stock ran low in Aug 2026

#The herd
# Starting herd.
# "Young" = under a year old.
START_HERD = {
    "CATTLE": {"adult_male": 34, "adult_female": 58, "young_male": 15, "young_female": 26},
    "GOAT": {"adult_male": 30, "adult_female": 56, "young_male": 6, "young_female": 7},
    "SHEEP": {"adult_male": 14, "adult_female": 95, "young_male": 3, "young_female": 2},
    "CHICKEN": {"adult_male": 5, "adult_female": 45, "young_male": 0, "young_female": 0},
}

# Newborns per adult female per year, from Kwetu's 2024 births
NEWBORNS_PER_FEMALE_PER_YEAR = {"CATTLE": 0.35, "GOAT": 0.95, "SHEEP": 0.55}

# How long a pregnancy lasts, in days (standard figures). A female cannot
# give birth again sooner than this.
GESTATION_DAYS = {"CATTLE": 283, "GOAT": 150, "SHEEP": 147}

# Kwetu sells mostly in December (2024: 22 goats, 18 sheep that month).
SALE_MONTH = 12

# Weights
# Growth: weight at birth and as an adult (kg), and the age (days) by which
# an animal is about 90% grown. Cattle adult weight fits Kwetu's 2025 sale
# weights (270-459 kg); the rest are typical figures for these breeds.
GROWTH = {
    "CATTLE": {"birth": 30.0, "adult": 400.0, "grown_by": 900},
    "GOAT": {"birth": 3.0, "adult": 40.0, "grown_by": 365},
    "SHEEP": {"birth": 3.5, "adult": 45.0, "grown_by": 365},
    "CHICKEN": {"birth": 0.04, "adult": 2.0, "grown_by": 150},
}
# Herd assumptions

AGE_LIMIT_DAYS = {"CATTLE": 10 * 365, "GOAT": 7 * 365, "SHEEP": 7 * 365, "CHICKEN": 3 * 365}
FIRST_BIRTH_AGE_DAYS = {"CATTLE": 900, "GOAT": 365, "SHEEP": 420}
TWIN_CHANCE = {"CATTLE": 0.02, "GOAT": 0.30, "SHEEP": 0.15}
NEWBORN_DEATH_CHANCE = {"CATTLE": 0.05, "GOAT": 0.08, "SHEEP": 0.08}  # weak at birth, first 2 weeks
WEAK_NEWBORN_MULTIPLIER = 1.5     # for twins, and again for a first-time mother
SALE_AGE_DAYS = {"CATTLE": 2 * 365, "GOAT": 365, "SHEEP": 365}
DECEMBER_SALE_SHARE = {"CATTLE": 0.25, "GOAT": 0.60, "SHEEP": 0.60}   # of males old enough
# Price in KES. 
SALE_PRICE_KES = {"CATTLE": (150_000, 200_000), "GOAT": (7_000, 12_000), "SHEEP": (7_000, 12_000)}

# ASSUMPTIONS
# Chance an unprotected animal gets the condition in a year. For conditions
# limited to young animals or to the days after giving birth, it is the
# chance over that whole window instead (e.g. per calf, per birth).
YEARLY_CHANCE = {"common": 0.20, "occasional": 0.05, "rare": 0.01}
# How rain raises rain-driven disease. The simulator reads each farm's real
# daily rainfall (Thika's, 1981-2026) and looks at the last 30 days:
RAIN_EFFECT = 0.5                   # a wet month (RAIN_SCALE_MM in 30 days) raises risk by half...
RAIN_SCALE_MM = 200                 # ...Thika's April, its wettest month, averages about 197 mm
RAIN_CAP_MM = 500                   # beyond this, more rain adds nothing
RAINS_ONSET_MULTIPLIER = 1.5        # worms: extra when the rains start after a dry month
ONSET_WET_MM = 60                   # ...60+ mm in the last 30 days...
ONSET_DRY_MM = 40                   # ...after under 40 mm in the 30 days before
HEAVY_RAIN_MM = 250                 # very heavy rain: 250+ mm in 30 days (3.5% of days since 1981)
HEAVY_RAIN_MULTIPLIER = 2.0         # extra risk of the heavy-rain diseases
EARLY_LACTATION_DAYS = 60           # "early lactation" for mastitis
YOUNG_DAYS = 180                    # "young" for young_multiplier
ENVIRONMENT_SPREAD = 0.6            # how much farms differ in their surroundings (lognormal sigma)
SPRAY_LAPSE_MULTIPLIER = 3.0        # ECF / heartwater risk after a missed spray week...
SPRAY_LAPSE_WINDOW_DAYS = (7, 21)   # ...7-21 days later (the 1-3 week incubation)
DEWORM_OVERDUE_MULTIPLIER = 2.0
# Vaccine-preventable (Group A): the base chance is for an UNPROTECTED animal.
# Up to date cuts it to 5%; overdue or not in the farm's plan leaves it as is.
VACCINE_UP_TO_DATE_MULTIPLIER = 0.05
OUTBREAK_BOOST_PER_CASE = 0.25      # +25% risk per recent case of the same condition...
OUTBREAK_DAYS = 14                  # ...in the same species, in the last 14 days
OUTBREAK_MAX_MULTIPLIER = 3.0       # stops one outbreak from growing without limit
RESISTANT_BREED_MULTIPLIER = 0.5    # e.g. zebu cattle and ECF
ILLNESS_RECOVERY_DAYS = 21          # no new illness while still recovering
FEVER_RISE = (1.0, 2.5)             # degC above normal when a fever is present
REPEAT_TREATMENT_CHANCES = (0.25, 0.35, 0.20, 0.12, 0.08)   # 0, 1, 2, 3 or 4 follow-ups
FRAILTY_SPREAD = 0.8                # some animals are simply more illness-prone
WEIGH_DAYS_PER_YEAR = 2             # Kwetu rarely weighs: a couple of herd weigh days a year
MISSED_WEIGH_CHANCE = 0.10          # animals not caught on a weigh day
ILLNESS_WEIGHT_DROP = (0.05, 0.10)  # weight lost when weighed within 30 days of falling ill

def daily_chance(rank):
    #Turn a yearly chance into the chance on any single day.
    yearly = YEARLY_CHANCE[rank]
    return 1 - (1 - yearly) ** (1 / 365)


def conditions_for(species, groups=("A", "B")):
    """The conditions a species can get, filtered by group. By default only
    the ones recorded as illnesses (A and B)."""
    return [c for c in CONDITIONS[species] if c.group in groups]


def predicted_conditions(species):
    """The diseases the model predicts: common and occasional illnesses,
    not the rare outbreak diseases left to the watch list."""
    return [c for c in conditions_for(species) if c.rank != "rare" and not c.watch_only]
