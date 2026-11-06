"""Versioned calculations for verification only, with no diagnostic interpretation."""

import math
from decimal import Decimal
from typing import Literal

BMI_VERSION = "cdc-metric-v1"
EGFR_VERSION = "ckd-epi-creatinine-2021"
MACROS_VERSION = "eu-1169-2011-annex-xiv"
SCALE_VERSIONS = {"PHQ-9": "kroenke-2001", "GAD-7": "spitzer-2006"}


def body_mass_index(weight_kg: float, height_m: float) -> float:
    if not all(math.isfinite(value) and value > 0 for value in (weight_kg, height_m)):
        raise ValueError("Positive, finite kg and m are required.")
    # Sequential division avoids underflow while squaring a very small height.
    result = weight_kg / height_m / height_m
    if not math.isfinite(result) or result <= 0:
        raise ValueError("BMI is outside the representable range.")
    return result


def estimated_gfr(
    creatinine_mg_dl: float, age_years: int, equation_sex: Literal["female", "male"]
) -> float:
    if not math.isfinite(creatinine_mg_dl) or creatinine_mg_dl <= 0:
        raise ValueError("Positive, finite creatinine in mg/dL is required.")
    if type(age_years) is not int or not 18 <= age_years <= 130:
        raise ValueError("An adult age in whole years is required.")
    if equation_sex not in ("female", "male"):
        raise ValueError("The equation sex coefficient must be explicitly selected.")
    kappa, alpha, factor = (0.7, -0.241, 1.012) if equation_sex == "female" else (0.9, -0.302, 1)
    ratio = creatinine_mg_dl / kappa
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError("Creatinine is outside the representable range.")
    return 142 * min(ratio, 1) ** alpha * max(ratio, 1) ** -1.200 * 0.9938**age_years * factor


def macronutrient_energy(protein_g: Decimal, carbohydrate_g: Decimal, fat_g: Decimal) -> Decimal:
    if not all(value.is_finite() and value >= 0 for value in (protein_g, carbohydrate_g, fat_g)):
        raise ValueError("Finite, nonnegative grams are required.")
    return 4 * protein_g + 4 * carbohydrate_g + 9 * fat_g


def questionnaire_total(instrument: str, responses: tuple[int, ...]) -> int:
    count = {"PHQ-9": 9, "GAD-7": 7}.get(instrument)
    if count is None or len(responses) != count:
        raise ValueError("The full supported instrument is required.")
    if any(type(score) is not int or not 0 <= score <= 3 for score in responses):
        raise ValueError("Each response must be a whole number from 0 to 3.")
    return sum(responses)
