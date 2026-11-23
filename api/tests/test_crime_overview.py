"""
Tests for Task 28: the danger score per km², relative levels and the top 10 (FR-23, R6).
"""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import load_area_file
from app.modules.crime.admin import seed_categories
from app.modules.crime.overview import level_for
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
visitor = TestClient(app)


def month_ago(n: int) -> datetime:
    now = datetime.now(timezone.utc)
    year, month = now.year, now.month - n
    while month <= 0:
        month += 12
        year -= 1
    return datetime(year, month, 1, tzinfo=timezone.utc)


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    seed_categories(database)
    yield database
    database.client.drop_database(database.name)


@pytest.fixture(autouse=True)
def clean(db):
    db.crime_stats.delete_many({})


def figure(db, area_code, category_key, count, months_ago=1, source="Test source"):
    area = db.areas.find_one({"code": area_code})
    cat = db.crime_categories.find_one({"key": category_key})
    db.crime_stats.insert_one({"area_id": area["_id"], "category_id": cat["_id"], "month": month_ago(months_ago),
                               "count": count, "source": source})


def test_levels_are_relative_ranks():
    # 10 areas with figures: 1 very high, 2 high, 3 medium, 4 low
    assert [level_for(r, 10) for r in range(10)] == ["very_high", "high", "high", "medium", "medium", "medium",
                                                       "low", "low", "low", "low"]
    assert level_for(0, 1) == "very_high"


def test_score_is_weighted_and_per_km2(db):
    figure(db, "ramna", "robbery", 2)  # 2 x weight 6 = 12
    figure(db, "ramna", "snatching", 3)  # 3 x weight 4 = 12  -> 24 in total
    figure(db, "uttara", "snatching", 3)  # 12, but Uttara is much bigger
    body = visitor.get("/api/v1/public/crime/overview", params={"months": 3}).json()
    ramna = next(a for a in body["areas"] if a["code"] == "ramna")
    size = db.areas.find_one({"code": "ramna"})["size_km2"]
    assert ramna["score"] == round(24 / size, 2) and ramna["total"] == 5 and ramna["top_category"] == "snatching"
    assert [a["code"] for a in body["top10"]] == ["ramna", "uttara"]
    assert body["sources"] == ["Test source"]

    total_mode = visitor.get("/api/v1/public/crime/overview", params={"months": 3, "mode": "total"}).json()
    assert next(a for a in total_mode["areas"] if a["code"] == "ramna")["score"] == 24


def test_areas_without_figures_have_no_data(db):
    figure(db, "ramna", "murder", 1)
    body = visitor.get("/api/v1/public/crime/overview", params={"months": 1}).json()
    levels = {a["code"]: a["level"] for a in body["areas"]}
    assert levels["ramna"] == "very_high" and levels["gulshan"] == "no_data"
    assert len(body["areas"]) == 41 and body["areas_with_data"] == 1


def test_period_category_and_level(db):
    figure(db, "ramna", "robbery", 5, months_ago=1)
    figure(db, "gulshan", "burglary", 9, months_ago=5)  # only in the 6- and 12-month views
    assert visitor.get("/api/v1/public/crime/overview", params={"months": 3}).json()["areas_with_data"] == 1
    assert visitor.get("/api/v1/public/crime/overview", params={"months": 6}).json()["areas_with_data"] == 2
    only_burglary = visitor.get("/api/v1/public/crime/overview", params={"months": 12, "category": "burglary"}).json()
    assert [a["code"] for a in only_burglary["top10"]] == ["gulshan"]
    assert only_burglary["by_category"] == [{"key": "burglary", "name_en": "Burglary", "name_bn": "সিঁধেল চুরি", "count": 9}]
    # Wards are ranked on their own (no figures for wards here)
    assert visitor.get("/api/v1/public/crime/overview", params={"months": 12, "level": "ward"}).json()["top10"] == []
    assert visitor.get("/api/v1/public/crime/overview", params={"months": 2}).status_code == 422
    assert visitor.get("/api/v1/public/crime/overview", params={"category": "aliens"}).status_code == 422


def test_this_months_figures_are_not_counted_yet(db):
    figure(db, "ramna", "robbery", 5, months_ago=0)  # this month: not finished, not counted
    assert visitor.get("/api/v1/public/crime/overview", params={"months": 1}).json()["areas_with_data"] == 0
