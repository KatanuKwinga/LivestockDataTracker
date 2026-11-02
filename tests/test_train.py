"""Training the illness model"""
from datetime import date

import pandas as pd

from ml.dataset import FEATURES
from ml.train import LABEL, build_table, split_by_time, train


def test_the_split_keeps_the_newest_snapshots_for_testing():
    table = pd.DataFrame({"snapshot": pd.to_datetime(["2026-01-01", "2026-01-15", "2026-01-29", "2026-02-12"]),
                          "x": [1, 2, 3, 4]})
    learn, test = split_by_time(table, test_share=0.25)
    assert learn["snapshot"].max() < test["snapshot"].min()
    assert list(test["x"]) == [4]


def test_the_model_learns_and_gives_a_chance_for_every_animal():
    table = build_table(end=date(2026, 9, 30), years=1, seed=1)
    model, learn, test = train(table)
    chance = model.predict_proba(test[["species"] + FEATURES])[:, 1]
    assert len(chance) == len(test) and ((chance >= 0) & (chance <= 1)).all()
    # Animals that really fell ill should, on average, have been given a higher chance.
    assert chance[test[LABEL].to_numpy() == 1].mean() > chance[test[LABEL].to_numpy() == 0].mean()