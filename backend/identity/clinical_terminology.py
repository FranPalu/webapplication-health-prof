"""A limited, versioned allow-list for structured report intake."""

PROFILE_VERSION = "claria-lab-1"
UCUM_SYSTEM = "http://unitsofmeasure.org"
LOINC_SYSTEM = "http://loinc.org"

# UCUM case-sensitive codes. A mass concentration code must not accept a
# substance concentration unit even when both observations describe glucose.
REPORT_CODES = frozenset({"11502-2"})
OBSERVATION_UNITS = {"2345-7": "mg/dL", "14749-6": "mmol/L"}
