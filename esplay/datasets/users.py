"""UsersDataset — the default seed dataset.

Loads documents from esplay/datasets/data/users.json so the data is easy
to swap or extend without touching any Python code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from esplay.datasets.base import DatasetProvider

_DATA_FILE = Path(__file__).parent / "data" / "users.json"


class UsersDataset(DatasetProvider):
    """Realistic user records designed to demonstrate core ES query patterns:
    - Full-text search (match, multi_match)
    - Term / terms filters
    - Range queries (age, salary, dates)
    - Bool compound queries
    - Aggregations (terms, date_histogram, avg/min/max metrics)
    - Sorting and pagination
    """

    def index_name(self) -> str:
        return "users"

    def mapping(self) -> dict[str, Any]:
        return {
            "mappings": {
                "properties": {
                    "id":           {"type": "keyword"},
                    "first_name":   {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "last_name":    {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword", "ignore_above": 256}},
                    },
                    "email":        {"type": "keyword"},
                    "age":          {"type": "integer"},
                    "gender":       {"type": "keyword"},
                    "city":         {"type": "keyword"},
                    "country":      {"type": "keyword"},
                    "role":         {"type": "keyword"},
                    "department":   {"type": "keyword"},
                    "salary":       {"type": "integer"},
                    "is_active":    {"type": "boolean"},
                    "signup_date":  {"type": "date", "format": "yyyy-MM-dd"},
                    "last_login":   {"type": "date", "format": "yyyy-MM-dd"},
                    "interests":    {"type": "keyword"},
                }
            }
        }

    def documents(self) -> list[dict[str, Any]]:
        return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
