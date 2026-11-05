import csv
import io
import json
from collections import defaultdict

import pyarrow as pa
import pyarrow.parquet as pq

from identity.research_archive import DATASET

FIELDS = ("year", "code", "accounts")


def encode_export(rows, format_name):
    if format_name == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(FIELDS)
        writer.writerows(rows)
        return output.getvalue().encode(), "text/csv", "csv"
    if format_name == "parquet":
        table = pa.table(
            {
                "year": pa.array([row[0] for row in rows], type=pa.int32()),
                "code": pa.array([row[1] for row in rows], type=pa.string()),
                "accounts": pa.array([row[2] for row in rows], type=pa.int64()),
            }
        )
        data = io.BytesIO()
        pq.write_table(table, data)
        return data.getvalue(), "application/vnd.apache.parquet", "parquet"
    years: dict[int, list[dict]] = defaultdict(list)
    for year, code, accounts in rows:
        years[year].append(
            {
                "code": {"coding": [{"system": "http://loinc.org", "code": code}]},
                "population": [
                    {
                        "code": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/measure-population",
                                    "code": "initial-population",
                                }
                            ]
                        },
                        "count": accounts,
                    }
                ],
            }
        )
    entries = [
        {
            "resource": {
                "resourceType": "MeasureReport",
                "status": "complete",
                "type": "summary",
                "measure": f"urn:claria:research:{DATASET}",
                "period": {"start": f"{year}-01-01", "end": f"{year}-12-31"},
                "group": groups,
            }
        }
        for year, groups in years.items()
    ]
    return (
        json.dumps({"resourceType": "Bundle", "type": "collection", "entry": entries}).encode(),
        "application/fhir+json",
        "json",
    )
