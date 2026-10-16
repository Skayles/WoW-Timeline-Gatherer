"""Shared test helpers: recorded WCL fixtures and an offline fake of the WCL API."""

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from wcl_notes.api.auth import TOKEN_URL
from wcl_notes.api.client import WclClient
from wcl_notes.api.credentials import Credentials
from wcl_notes.api.models import ReportQueryModel
from wcl_notes.api.reports import parse_cast_events, report_from_model
from wcl_notes.domain.models import Report, Track, TrackRef
from wcl_notes.services.report_navigation import resolve_fight
from wcl_notes.services.timeline import build_casts

# UI tests never open real windows.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"

REPORT_CODE = "cmw7ZBvfaJV6DyKQ"
FIGHT_7_START = 3182734
MAGE_ID = 118  # "Givrâme", 341 casts over 4 pages (recorded with limit=100)
ROGUE_ID = 126  # "Vénéfique", Assassination, includes fake Mutilate casts
SHAMAN_ID = 117  # owner of the Primal Fire Elemental (pet 134)
FIRE_ELEMENTAL_ID = 134
ABSENT_PLAYER_ID = 3  # in the report, not in fight 7


def load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def read_golden(name: str) -> str:
    return (GOLDEN / name).read_text(encoding="utf-8")


def load_report() -> Report:
    model = ReportQueryModel.model_validate(load_json("report_cmw7.json")["data"])
    assert model.report_data.report is not None
    return report_from_model(model.report_data.report)


@pytest.fixture
def report() -> Report:
    return load_report()


def _events(body: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = body["data"]["reportData"]["report"]["events"]["data"]
    return events


def fixture_track(report: Report, source_id: int) -> Track:
    """Fight 7 track of the rogue or the mage, built from the recorded casts."""
    if source_id == ROGUE_ID:
        raw = _events(load_json("casts_cmw7_f7_s126.json"))
    else:
        raw = [e for page in load_json("casts_cmw7_f7_s118_pages.json") for e in _events(page)]
    fight = resolve_fight(report, 7)
    casts = build_casts(parse_cast_events(raw), fight)
    return Track(TrackRef(REPORT_CODE, 7, source_id), report.actors[source_id], fight, casts)


@pytest.fixture
def rogue_track(report: Report) -> Track:
    return fixture_track(report, ROGUE_ID)


@pytest.fixture
def mage_track(report: Report) -> Track:
    return fixture_track(report, MAGE_ID)


Handler = Callable[[dict[str, Any]], httpx.Response]


def _empty_events() -> httpx.Response:
    events: dict[str, Any] = {"data": [], "nextPageTimestamp": None}
    return httpx.Response(200, json={"data": {"reportData": {"report": {"events": events}}}})


class FakeWcl:
    """Serves recorded responses, keyed by GraphQL operation name."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.token_requests = 0
        self.handlers: dict[str, Handler] = {
            "Report": lambda _: httpx.Response(200, json=load_json("report_cmw7.json")),
            "PlayerCasts": self._player_casts,
            "PetCasts": self._pet_casts,
            "PlayerDetails": lambda _: httpx.Response(
                200, json=load_json("player_details_cmw7_f7.json")
            ),
        }
        pages = load_json("casts_cmw7_f7_s118_pages.json")
        starts = [FIGHT_7_START] + [
            p["data"]["reportData"]["report"]["events"]["nextPageTimestamp"] for p in pages[:-1]
        ]
        self._mage_pages = dict(zip(starts, pages, strict=True))

    def handle(self, request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            self.token_requests += 1
            return httpx.Response(200, json={"access_token": "test", "expires_in": 3600})
        body = json.loads(request.content)
        match = re.search(r"query\s+(\w+)", body["query"])
        assert match, "every query must be named"
        self.calls.append((match.group(1), body["variables"]))
        return self.handlers[match.group(1)](body["variables"])

    def client(self) -> WclClient:
        http = httpx.Client(transport=httpx.MockTransport(self.handle))
        return WclClient(Credentials("test-id", "test-secret"), http=http)

    def _player_casts(self, variables: dict[str, Any]) -> httpx.Response:
        if variables["sourceID"] == MAGE_ID:
            return httpx.Response(200, json=self._mage_pages[variables["startTime"]])
        if variables["sourceID"] == ROGUE_ID:
            return httpx.Response(200, json=load_json("casts_cmw7_f7_s126.json"))
        return _empty_events()

    def _pet_casts(self, variables: dict[str, Any]) -> httpx.Response:
        if variables["sourceID"] == FIRE_ELEMENTAL_ID:
            return httpx.Response(200, json=load_json("pet_casts_cmw7_f7_s134.json"))
        return _empty_events()


@pytest.fixture
def fake_wcl() -> FakeWcl:
    return FakeWcl()
