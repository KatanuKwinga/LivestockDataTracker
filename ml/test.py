"""Figuring out how good the model is"""
import json

import numpy as np
from sklearn.metrics import roc_auc_score

from ml.dataset import FEATURES
from ml.train import LABEL, MODEL_PATH, build_table, train

FLAG_SHARE = 0.20      # the farmer checks the riskiest fifth of the herd


def flag_riskiest(chance, share=FLAG_SHARE):
    """1 for the riskiest `share` of animals, 0 for the rest."""
    cutoff = np.quantile(chance, 1 - share)
    return (chance >= cutoff).astype(int)


def measure(truth, chance):
    """The numbers that matter for a yes/no prediction where 'yes' is rare."""
    flagged = flag_riskiest(chance)
    fell_ill = truth == 1
    return {
        "test_rows": int(len(truth)),
        "share_that_fell_ill": round(float(fell_ill.mean()), 3),
        "accuracy_if_always_no": round(float((~fell_ill).mean()), 3),
        "roc_auc": round(float(roc_auc_score(truth, chance)), 3),
        "precision_of_flagged": round(float(fell_ill[flagged == 1].mean()), 3),
        "recall_of_flagged": round(float(flagged[fell_ill].mean()), 3),
    }


def weights(model):
    """What each clue does to the odds of falling ill, for one 'typical step' up in that clue."""
    names = model.named_steps["prepare"].get_feature_names_out()
    coefs = model.named_steps["model"].coef_[0]
    return {name.split("__")[1]: round(float(np.exp(c)), 2) for name, c in zip(names, coefs)}


if __name__ == "__main__":
    print("Simulating and training (about a minute)...")
    model, learn, test = train(build_table())
    chance = model.predict_proba(test[["species"] + FEATURES])[:, 1]
    result = measure(test[LABEL].to_numpy(), chance)
    result["odds_multipliers"] = weights(model)

    for key, value in result.items():
        if key != "odds_multipliers":
            print(f"  {key:24} {value}")
    print("\n  What each clue does to the odds (1.00 = nothing, above 1 = riskier):")
    for name, value in result["odds_multipliers"].items():
        print(f"    {name:24} x {value}")

    MODEL_PATH.parent.mkdir(exist_ok=True)
    with open(MODEL_PATH.with_name("illness_model_metrics.json"), "w") as f:
        json.dump(result, f, indent=2)