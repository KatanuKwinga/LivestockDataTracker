import numpy as np

from ml.test import flag_riskiest, measure


def test_the_riskiest_fifth_is_flagged():
    chance = np.array([0.9, 0.3, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    assert list(flag_riskiest(chance)) == [1, 0, 1, 0, 0, 0, 0, 0, 0, 0]


def test_measures_worked_out_by_hand():
    # Ten animals: the first two fell ill. The model flags animals 1 and 3 (the two riskiest).
    truth = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    chance = np.array([0.9, 0.3, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    result = measure(truth, chance)
    assert result["accuracy_if_always_no"] == 0.8     # 8 of 10 didn't fall ill
    assert result["precision_of_flagged"] == 0.5      # of the 2 flagged, 1 fell ill
    assert result["recall_of_flagged"] == 0.5         # of the 2 that fell ill, 1 was flagged
    assert result["roc_auc"] == 0.938                 # 15 of the 16 ill/healthy pairs ranked the right way