"""The disease-alert model: training, the simple rules it must beat, and
saving it as one pickle file.

The model is gradient boosting: many small decision trees, each one
correcting the mistakes of the ones before. Trees suit this problem because
a disease's risk depends on combinations (worms x rains x young animals),
which trees pick up without being told. Logistic regression is kept as the
simpler comparison.
"""
import pickle
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

from ml.disease_data import CATEGORIES, FEATURES, HORIZON_DAYS, LABEL, NUMBERS, build_table
from ml.synthetic import simulate_many

END = date(2026, 9, 30)      # fixed, so every run builds the same farms
YEARS = 4                    # the first year only builds up history ("this time last year")
FARMS = 10
TEST_FARMS = 2               # farms kept out of training altogether
TEST_SHARE = 0.25            # the newest quarter of snapshot days is for testing
SEED = 100
MODEL_PATH = Path(__file__).parent / "artifacts" / "disease_model.pkl"


def simulated_table(farms=FARMS, end=END, years=YEARS, seed=SEED):
    """Simulate the farms and turn their history into rows. Snapshots start
    a year in, so every row has a full year of history behind it."""
    tables, about = simulate_many(farms, end, years, seed)
    start = end - timedelta(days=365 * (years - 1))
    return build_table(tables, start, end), about


def split(table, test_farms=TEST_FARMS, test_share=TEST_SHARE):
    """Three parts:
    learn       older 75% of the snapshot days, training farms only
    test_time   newest 25%, the same farms (does it predict the future?)
    test_farms  newest 25%, farms it never saw (does it work on a new farm?)"""
    days = sorted(table["snapshot"].unique())
    cutoff = days[int(len(days) * (1 - test_share))]
    farms = sorted(table["farm"].unique())
    unseen = farms[-test_farms:] if test_farms else []
    old, new = table["snapshot"] < cutoff, table["snapshot"] >= cutoff
    seen = ~table["farm"].isin(unseen)
    return table[old & seen], table[new & seen], table[new & ~seen]


def boosting():
    """Gradient boosting. The four text columns become numbers (codes) and
    are marked as categories, so the trees split on them as groups."""
    prepare = ColumnTransformer([
        ("categories", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), CATEGORIES),
        ("numbers", "passthrough", NUMBERS),
    ])
    model = HistGradientBoostingClassifier(
        categorical_features=list(range(len(CATEGORIES))),
        learning_rate=0.03, max_iter=300, max_leaf_nodes=15, min_samples_leaf=40,   # tuned in the notebook
        l2_regularization=1.0, random_state=SEED)
    return Pipeline([("prepare", prepare), ("model", model)])


def logistic():
    """Logistic regression, for comparison: text columns become 0/1 columns
    and the numbers are put on the same scale."""
    prepare = ColumnTransformer([
        ("categories", OneHotEncoder(handle_unknown="ignore"), CATEGORIES),
        ("numbers", StandardScaler(), NUMBERS),
    ])
    return Pipeline([("prepare", prepare), ("model", LogisticRegression(max_iter=2000))])


# ------------------------------------------------- the rules to beat

def last_year_rule(rows):
    """'Expect what happened at this time last year': the score is last
    year's case count for the same 30 days (ties broken by the whole year)."""
    return rows["cases_this_time_last_year"] + rows["cases_last_year"] / 1000


class SeasonalCalendar:
    """A disease calendar learnt by counting: for each species, group,
    disease and month, the share of training rows that had a case. This is
    what a lookup table (no ML) can do."""

    def fit(self, rows):
        keys = ["species", "group", "disease", "month"]
        self.table = rows.groupby(keys)[LABEL].mean()
        self.fallback = rows.groupby(["species", "group", "disease"])[LABEL].mean()
        self.overall = rows[LABEL].mean()
        return self

    def predict(self, rows):
        keys = pd.MultiIndex.from_frame(rows[["species", "group", "disease", "month"]])
        chance = pd.Series(self.table.reindex(keys).to_numpy(), index=rows.index)
        short = pd.MultiIndex.from_frame(rows[["species", "group", "disease"]])
        chance = chance.fillna(pd.Series(self.fallback.reindex(short).to_numpy(), index=rows.index))
        return chance.fillna(self.overall).to_numpy()


# ------------------------------------------------- saving

def save_bundle(model, metrics=None, path=MODEL_PATH):
    """Save the model with what is needed to use and explain it."""
    bundle = {
        "model": model,                      # bundle["model"].predict_proba(rows[bundle["columns"]])
        "columns": FEATURES,
        "label": LABEL,
        "horizon_days": HORIZON_DAYS,
        "metrics": metrics or {},
        "trained_on": date.today().isoformat(),
        "training_data": f"{FARMS} simulated Kwetu-like farms, {YEARS} years to {END}",
        "sklearn_version": sklearn.__version__,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(bundle, f)
    return bundle


def load_bundle(path=MODEL_PATH):
    """Read the pickle back. Only ever unpickle files you made yourself:
    loading a pickle can run code hidden inside it."""
    with open(path, "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    from sklearn.metrics import roc_auc_score

    print(f"Simulating {FARMS} farms for {YEARS} years (about two minutes)...")
    table, about = simulated_table()
    learn, test_time, test_farms = split(table)
    model = boosting().fit(learn[FEATURES], learn[LABEL])
    for name, part in (("same farms, later", test_time), ("new farms", test_farms)):
        chance = model.predict_proba(part[FEATURES])[:, 1]
        print(f"ROC AUC, {name}: {roc_auc_score(part[LABEL], chance):.3f}")
    final = boosting().fit(table[FEATURES], table[LABEL])
    save_bundle(final)
    print(f"Saved the model to {MODEL_PATH}")