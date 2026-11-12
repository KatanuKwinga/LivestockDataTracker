"""Read a farm's Excel workbook into the same tables the simulator makes,
so the model can be tested on it.

Two workbooks are supported:
- the demo farm (seeds/data/Demo_Farm_Records.xlsx), the farm loaded into the app;
- Kwetu's real records (seeds/data/Kwetu_Animals_and_Records.xlsx).
The animal's tag is used as its id.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEMO_WORKBOOK = ROOT / "seeds" / "data" / "Demo_Farm_Records.xlsx"
KWETU_WORKBOOK = ROOT / "seeds" / "data" / "Kwetu_Animals_and_Records.xlsx"

ACTIVITY = {"Tick spraying": "TICK_SPRAY", "Dipping": "TICK_SPRAY", "Deworming": "DEWORMING",
            "Deworming (injection)": "DEWORMING", "Vaccination": "VACCINATION",
            "Group treatment": "TREATMENT", "Group treatment (vet)": "TREATMENT",
            "Supplement": "SUPPLEMENT"}


def _animals(a, joined):
    return pd.DataFrame({"animal_id": a["Tag"], "species": a["Species"].str.upper(),
                         "gender": a["Sex"].str.upper(), "breed": a["Breed"],
                         "date_of_birth": pd.to_datetime(a["Date of birth"]), "joined": joined})


def demo_farm(path=DEMO_WORKBOOK):
    """The demo farm (Kilima Farm), two years of records to 31 Oct 2026."""
    sheets = pd.read_excel(path, sheet_name=None)
    a = sheets["Animals"]
    trade = sheets["Purchases and sales"]
    bought = trade[trade["Type"] == "Bought"].groupby("Tag")["Date"].min()
    births = sheets["Breeding"]
    births = births[births["Status"] == "Gave birth"]
    h = sheets["Health records"]
    g = sheets["Group treatments"]
    return {
        "livestock": _animals(a, pd.to_datetime(a["Tag"].map(bought)).fillna(pd.to_datetime(a["Date of birth"]))),
        "breeding": pd.DataFrame({"animal_id": births["Mother (tag)"],
                                  "actual_delivery_date": pd.to_datetime(births["Birth or loss date"])}),
        "health": pd.DataFrame({"animal_id": h["Tag"], "date": pd.to_datetime(h["Date"]),
                                "record_type": h["Record type"], "disease": h["Disease"],
                                "treatment": h["Treatment"], "description": h["Notes"]}),
        "mortality": pd.DataFrame({"animal_id": sheets["Deaths"]["Tag"],
                                   "date_of_death": pd.to_datetime(sheets["Deaths"]["Date"])}),
        "commercial": pd.DataFrame({"animal_id": trade["Tag"], "date": pd.to_datetime(trade["Date"]),
                                    "transaction_type": trade["Type"].map({"Sold": "SELL", "Bought": "BUY"})}),
        "departures": pd.DataFrame({"animal_id": sheets["Left the farm"]["Tag"],
                                    "date": pd.to_datetime(sheets["Left the farm"]["Date"])}),
        "herd_activities": pd.DataFrame({"date": pd.to_datetime(g["Date"]), "species": g["Species"].str.upper(),
                                         "activity": g["Activity"].map(ACTIVITY)}),
    }


# Kwetu's illnesses are written in the farm's own words. These are the
# ones that match a disease the model predicts; the rest are left out.
KWETU_DISEASES = {
    "East Coast Fever": "East Coast Fever",
    "Scouring (diarrhoea)": "Calf scours",
    "Orf": "Orf",
    "Lung problem": "Pneumonia",
    "Vulva infection": "Vulval infection",
}
KWETU_GROUP_SPECIES = {"Cattle": ["CATTLE"], "Goat": ["GOAT"], "Sheep": ["SHEEP"],
                       "Sheep, goats, calves": ["SHEEP", "GOAT", "CATTLE"], "Not stated": []}


def kwetu_disease(text):
    """The model's name for one of Kwetu's illness descriptions, or None."""
    if not isinstance(text, str):
        return None
    for start, name in KWETU_DISEASES.items():
        if text.startswith(start):
            return name
    return None


def kwetu(path=KWETU_WORKBOOK):
    """Kwetu Farm's real records. Health records only start in March 2026."""
    sheets = pd.read_excel(path, sheet_name=None)
    a = sheets["Animals"].dropna(subset=["Tag"])
    h = sheets["Health records"].dropna(subset=["Tag"])
    d = sheets["Deaths"].dropna(subset=["Tag"])
    s = sheets["Sales & exits"].dropna(subset=["Tag"])          # sold, given away, lost, missing
    b = sheets["Births"].dropna(subset=["Mother (tag)"])
    g = sheets["Group treatments"].dropna(subset=["Species"])
    groups = pd.DataFrame({"date": pd.to_datetime(g["Date"]), "species": g["Species"].map(KWETU_GROUP_SPECIES),
                           "activity": g["Activity"].map(ACTIVITY)}).explode("species").dropna(subset=["species"])
    return {
        "livestock": _animals(a, pd.to_datetime(a["Joined the records"])),
        "breeding": pd.DataFrame({"animal_id": b["Mother (tag)"], "actual_delivery_date": pd.to_datetime(b["Date"])}),
        "health": pd.DataFrame({"animal_id": h["Tag"], "date": pd.to_datetime(h["Date"]),
                                "record_type": h["Record type"], "disease": h["Illness / problem"].map(kwetu_disease),
                                "treatment": h["Medicine"], "description": h["Notes"]}),
        "mortality": pd.DataFrame({"animal_id": d["Tag"], "date_of_death": pd.to_datetime(d["Date"])}),
        "commercial": pd.DataFrame({"animal_id": s["Tag"], "date": pd.to_datetime(s["Date"]),
                                    "transaction_type": "SELL"}),
        "herd_activities": groups,
    }