import math
from decimal import Decimal

import pytest

from identity.clinical_calculators import (
    body_mass_index,
    estimated_gfr,
    macronutrient_energy,
    questionnaire_total,
)


def test_metric_bmi():
    assert body_mass_index(70, 1.75) == pytest.approx(22.857142857142858)
    for weight, height in ((0, 1.7), (60, -1), (math.nan, 1.7), (1, 1e-300)):
        with pytest.raises(ValueError):
            body_mass_index(weight, height)


def test_ckd_epi_2021_examples_at_and_below_kappa():
    assert estimated_gfr(0.9, 60, "male") == pytest.approx(97.775014, abs=0.001)
    assert estimated_gfr(0.7, 60, "female") == pytest.approx(98.948315, abs=0.001)
    assert estimated_gfr(1.5, 60, "male") < estimated_gfr(0.9, 60, "male")
    assert estimated_gfr(0.6, 60, "female") > estimated_gfr(0.7, 60, "female")
    for creatinine, age, sex in (
        (0, 60, "male"),
        (math.inf, 60, "male"),
        (0.9, 17, "male"),
        (0.9, 60, "unknown"),
        (1.79e308, 60, "female"),
    ):
        with pytest.raises(ValueError):
            estimated_gfr(creatinine, age, sex)


def test_macronutrient_energy_preserves_decimal_grams():
    assert macronutrient_energy(Decimal("15.5"), Decimal("20"), Decimal("10")) == Decimal("232.0")
    for invalid in (Decimal("-1"), Decimal("NaN")):
        with pytest.raises(ValueError):
            macronutrient_energy(invalid, Decimal(0), Decimal(0))


def test_full_questionnaire_scores_without_interpretation():
    assert questionnaire_total("PHQ-9", (3,) * 9) == 27
    assert questionnaire_total("GAD-7", (0, 1, 2, 3, 2, 1, 0)) == 9
    for name, scores in (
        ("unknown", (0,) * 7),
        ("PHQ-9", (0,) * 8),
        ("PHQ-9", (0,) * 8 + (4,)),
        ("GAD-7", (0,) * 6 + (True,)),
    ):
        with pytest.raises(ValueError):
            questionnaire_total(name, scores)
