"""
Tests for Task 12: thanas, wards, police stations and the "where is this point?" lookup.
They load the real data file (api/data/dhaka_areas.geojson) into the test database.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import shape

from app.db import database_status, get_db
from app.main import app
from app.modules.areas.service import find_area_ids, load_area_file
from app.setup_db import apply_schema

pytestmark = pytest.mark.skipif(
    not database_status()["ok"],
    reason="Database not running. Start it: Terminal -> Run Task -> 'SafeZone: start database'",
)
DATA = json.loads((Path(__file__).parent.parent / "data" / "dhaka_areas.geojson").read_text(encoding="utf-8"))
client = TestClient(app)


def inside_point(code: str) -> tuple[float, float]:
    """A point that is surely inside the area with this code: (lat, lng)."""
    feature = next(f for f in DATA["features"] if f["properties"]["code"] == code)
    point = shape(feature["geometry"]).representative_point()
    return point.y, point.x


@pytest.fixture(scope="module", autouse=True)
def db():
    database = get_db()
    assert database.name == "safezone_test"
    database.client.drop_database(database.name)
    apply_schema(database)
    load_area_file(database)
    yield database
    database.client.drop_database(database.name)


def test_the_data_file_has_all_of_dhaka():
    kinds = [f["properties"].get("type", f["properties"]["kind"]) for f in DATA["features"]]
    assert kinds.count("thana") == 41
    assert kinds.count("ward") == 92
    assert kinds.count("police_station") >= 30
    for f in DATA["features"]:
        assert f["properties"]["name_bn"], f"{f['properties']['code']} has no Bangla name"


def test_loading_twice_does_not_double_anything(db):
    load_area_file(db)
    assert db.areas.count_documents({"type": "thana"}) == 41
    assert db.areas.count_documents({"type": "ward"}) == 92
    assert db.police_stations.count_documents({}) == len([f for f in DATA["features"]
                                                          if f["properties"]["kind"] == "police_station"])


def test_wards_know_their_thanas(db):
    ward = db.areas.find_one({"code": "dcc-w06"})
    pallabi = db.areas.find_one({"code": "pallabi"})
    assert pallabi["_id"] in ward["thana_ids"]
    assert all(w["thana_ids"] for w in db.areas.find({"type": "ward"}))  # every ward overlaps some thana


def test_lookup_finds_thana_ward_and_police():
    lat, lng = inside_point("mirpur")
    answer = client.get("/api/v1/areas/lookup", params={"lat": lat, "lng": lng})
    assert answer.status_code == 200
    body = answer.json()
    assert body["inside_dhaka"] is True
    assert body["thana"]["code"] == "mirpur" and body["thana"]["name_bn"] == "মিরপুর"
    assert body["ward"]["type"] == "ward"
    stations = body["nearest_police_stations"]
    assert len(stations) == 3
    assert stations[0]["distance_m"] <= stations[1]["distance_m"] <= stations[2]["distance_m"]


def test_lookup_in_ramna_finds_ramna_police_nearby():
    body = client.get("/api/v1/areas/lookup", params={"lat": 23.7457, "lng": 90.4047}).json()
    assert body["thana"]["code"] == "ramna"
    assert body["nearest_police_stations"][0]["code"] == "ramna-model-ps"
    assert body["nearest_police_stations"][0]["distance_m"] < 100


def test_lookup_outside_dhaka_says_so():
    body = client.get("/api/v1/areas/lookup", params={"lat": 22.3569, "lng": 91.7832}).json()  # Chattogram
    assert body["inside_dhaka"] is False
    assert body["thana"] is None and body["ward"] is None
    assert body["nearest_police_stations"] == []


def test_lookup_refuses_points_outside_bangladesh():
    answer = client.get("/api/v1/areas/lookup", params={"lat": 51.5, "lng": -0.12})  # London
    assert answer.status_code == 422
    assert set(answer.json()["error"]["fields"]) == {"lat", "lng"}


def test_list_and_search():
    thanas = client.get("/api/v1/areas", params={"type": "thana"}).json()["areas"]
    assert len(thanas) == 41 and "geom" not in thanas[0]
    found = client.get("/api/v1/areas", params={"q": "dhan"}).json()["areas"]
    assert [a["code"] for a in found] == ["dhanmondi"]
    in_bangla = client.get("/api/v1/areas", params={"q": "গুলশান"}).json()["areas"]
    assert [a["code"] for a in in_bangla] == ["gulshan"]
    wards = client.get("/api/v1/areas", params={"type": "ward"}).json()["areas"]
    assert [w["name_en"] for w in wards[:3]] == ["Ward 1", "Ward 2", "Ward 3"]  # 1, 2, 3 ... not 1, 10, 11


def test_search_with_strange_characters_is_safe():
    answer = client.get("/api/v1/areas", params={"q": ".*(["})
    assert answer.status_code == 200 and answer.json()["areas"] == []


def test_shapes_for_the_map():
    answer = client.get("/api/v1/areas/shapes", params={"type": "thana"})
    assert answer.status_code == 200
    assert "max-age" in answer.headers["cache-control"]
    body = answer.json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 41
    assert body["features"][0]["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_one_area_with_its_wards_and_police():
    body = client.get("/api/v1/areas/ramna").json()
    assert body["type"] == "thana" and body["wards"] and body["police_stations"]
    assert body["geom"]["type"] in ("Polygon", "MultiPolygon")
    ward = client.get("/api/v1/areas/dcc-w06").json()
    assert [t["code"] for t in ward["thanas"]] == ["pallabi"]


def test_unknown_area():
    answer = client.get("/api/v1/areas/atlantis")
    assert answer.status_code == 404 and answer.json()["error"]["code"] == "area_not_found"


def test_nearest_police_stations():
    body = client.get("/api/v1/police-stations/nearest", params={"lat": 23.7457, "lng": 90.4047, "limit": 5}).json()
    assert len(body["police_stations"]) == 5


def test_find_area_ids_for_reports(db):
    lat, lng = inside_point("gulshan")
    ids = find_area_ids(lat, lng)
    assert ids["thana_id"] == db.areas.find_one({"code": "gulshan"})["_id"]
    assert find_area_ids(22.3569, 91.7832) == {"thana_id": None, "ward_id": None}


# ---------------------------------------------------------------- Task 13: the city outline
def test_city_outline_for_the_map_picker():
    answer = client.get("/api/v1/areas/outline")
    assert answer.status_code == 200
    body = answer.json()
    assert body["outline"]["type"] in ("Polygon", "MultiPolygon")
    box = body["bounds"]
    assert 23.6 < box["south"] < box["north"] < 24.0 and 90.2 < box["west"] < box["east"] < 90.6
    assert box["south"] < body["center"]["lat"] < box["north"]


def test_outline_contains_every_police_station(db):
    from shapely.geometry import Point, shape
    city = shape(client.get("/api/v1/areas/outline").json()["outline"]).buffer(0.01)  # ~1 km of tolerance
    for station in db.police_stations.find():
        lng, lat = station["location"]["coordinates"]
        assert city.contains(Point(lng, lat)), station["name_en"]
