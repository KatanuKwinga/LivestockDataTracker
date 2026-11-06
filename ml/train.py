"""Training the illness model on simulated Kwetu-like farms and save it.
The model learns one weight per clue, adds them up for each
animal, and turns the total into a probability between 0 and 1."""
import pickle
from datetime import date, timedelta
from pathlib import Path

import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ml.dataset import FEATURES, HORIZON_DAYS, features, labels
from ml.synthetic import simulate_farms

END = date(2026, 9, 30)          # fixed, so every run builds the same farms
YEARS = 3
WARM_UP_DAYS = 90                # skip the first months: no earlier records exist yet
TEST_SHARE = 0.25                # the newest quarter of the snapshots is kept for testing
LABEL = "ill_within_30_days"
MODEL_PATH = Path(__file__).parent / "artifacts" / "illness_model.pkl"


def build_table(end=END, years=YEARS, seed=42):
    """Simulate the three farms and turn their history into one row per animal per snapshot, with clues and answer."""
    data = simulate_farms(end=end, years=years, seed=seed)
    start = end - timedelta(days=365 * years) + timedelta(days=WARM_UP_DAYS)
    return features(labels(data, start=start, end=end), data)


def split_by_time(table, test_share=TEST_SHARE):
    """Older snapshots to learn from, newer ones to test on"""
    days = sorted(table["snapshot"].unique())
    cutoff = days[int(len(days) * (1 - test_share))]
    return table[table["snapshot"] < cutoff], table[table["snapshot"] >= cutoff]


def make_model():
    """Species becomes three 0/1 columns; the numbers are put on the same scale;
    then logistic regression."""
    prepare = ColumnTransformer([
        ("species", OneHotEncoder(handle_unknown="ignore"), ["species"]),
        ("numbers", StandardScaler(), FEATURES),
    ])
    return Pipeline([("prepare", prepare), ("model", LogisticRegression(max_iter=1000))])


def train(table):
    """Fit the model on the older snapshots. Returns the model and both halves of the table."""
    learn, test = split_by_time(table)
    model = make_model()
    model.fit(learn[["species"] + FEATURES], learn[LABEL])
    return model, learn, test

def save_bundle(model, metrics=None, path=MODEL_PATH):
    """Save the trained model as ONE pickle file, together with what is
    needed to use it and explain it: the columns it expects, what it
    predicts, how well it did, and when and how it was trained."""
    bundle = {
        "model": model,                              # the fitted Pipeline: call bundle["model"].predict_proba(...)
        "columns": ["species"] + FEATURES,           # the columns it needs, in this order
        "label": LABEL,
        "horizon_days": HORIZON_DAYS,
        "metrics": metrics or {},
        "trained_on": date.today().isoformat(),
        "training_data": f"Simulated Kwetu-like farms, {YEARS} years to {END}",
        "sklearn_version": sklearn.__version__,      # load it with the same version
    }
    path.parent.mkdir(exist_ok=True)
    with open(path, "wb") as f:                      # "wb": write bytes
        pickle.dump(bundle, f)
    return bundle


def load_bundle(path=MODEL_PATH):
    """Read the pickle back. Only ever unpickle files you made yourself:
    loading a pickle can run code hidden inside it."""
    with open(path, "rb") as f:
        return pickle.load(f)

if __name__ == "__main__":
    print("Simulating three farms for three years (about a minute)...")
    table = build_table()
    model, learn, test = train(table)
    print(f"Learned from {len(learn):,} rows ({learn['snapshot'].min():%d/%m/%Y} - {learn['snapshot'].max():%d/%m/%Y})")
    print(f"Kept {len(test):,} rows for testing ({test['snapshot'].min():%d/%m/%Y} - {test['snapshot'].max():%d/%m/%Y})")
    chance = model.predict_proba(test[["species"] + FEATURES])[:, 1]
    test = test.assign(chance=chance)
    print("\nAverage predicted chance, by what really happened (test rows):")
    print(test.groupby(LABEL)["chance"].mean().round(3).to_string())
    save_bundle(model)
    print(f"\nSaved the model to {MODEL_PATH}")