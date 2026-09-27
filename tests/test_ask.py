"""AskService: intents in three languages, answers built from live data, Claude mode fallbacks."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import anthropic
import pytest

from main import _localizer
from models.schemas import VoyagePlanResponse
from services.ask_service import AskService, detect_intent
from services.forecast_service import ForecastService
from services.risk_service import RiskService
from tests.test_forecast import fake_fetch
from tests.test_pipeline import VERAVAL, make_service, run


def rough_day_two(t):
    day = (t + timedelta(hours=5, minutes=30)).date() - datetime(2026, 9, 27).date()
    return {1: 3.0, 3: 0.8}.get(day.days, 1.2)


@pytest.fixture(scope="module")
def forecast():
    svc = ForecastService(RiskService(), _localizer, fetch=fake_fetch(rough_day_two))
    return svc.forecast(20.8, 70.25, days=5, now=datetime(2026, 9, 27, 3, 0))


@pytest.fixture(scope="module")
def plan(tmp_path_factory):
    final = run(make_service(tmp_path_factory.mktemp("ask")), origin=VERAVAL)
    return VoyagePlanResponse(plan=final["plan"], fishing_zones=final["fishing"].zones,
                              localized=_localizer.localize_all(final["plan"]))


def service(forecast, plan, client=None):
    return AskService(forecast=lambda lat, lon: forecast, plan=lambda lat, lon, name: plan, client=client)


@pytest.mark.parametrize("q, intent", [
    ("आज मौसम कैसा है?", "weather"), ("aaj hawa kitni tez hai", "weather"), ("આજે પવન કેવો છે?", "weather"),
    ("मछली कहाँ मिलेगी?", "fishing"), ("માછલી ક્યાં મળશે?", "fishing"), ("where can I catch fish", "fishing"),
    ("क्या आज समुद्र में जाना सुरक्षित है?", "safety"), ("is it safe to go out", "safety"),
    ("सबसे अच्छा दिन कौन सा है?", "best_day"), ("દરિયામાં જવા માટે કયો દિવસ સારો?", "best_day"),
    ("कितना ईंधन लगेगा?", "route"), ("how far is the zone and how much fuel", "route"),
    ("नमस्ते", "summary"),
])
def test_intents(q, intent):
    assert detect_intent(q) == intent


def test_weather_answer_uses_live_numbers_in_each_language(forecast, plan):
    svc = service(forecast, plan)
    d = forecast.days[0]
    wind = str(round(d.max_wind_ms * 3.6))
    for lang, word in (("hi", "हवा"), ("gu", "પવન"), ("en", "wind")):
        a = svc.ask("weather / मौसम / હવામાન", lang, 20.8, 70.25, "Veraval")
        assert a.mode == "rules" and a.intent == "weather"
        assert word in a.answer and wind in a.answer and "Veraval" in a.answer


def test_tomorrow_rough_sea_is_reported(forecast, plan):
    a = service(forecast, plan).ask("कल मौसम कैसा रहेगा?", "hi", 20.8, 70.25, "Veraval")
    assert "कल" in a.answer and "3.0" in a.answer and "सावधानी" in a.answer


def test_best_day_names_calm_day_and_warns_about_rough_one(forecast, plan):
    a = service(forecast, plan).ask("which day is best to go out?", "en", 20.8, 70.25, "Veraval")
    assert a.intent == "best_day"
    assert "Wednesday 30" in a.answer and "0.8" in a.answer  # 2026-09-30, calmest
    assert "Take care on Monday 28" in a.answer              # 2026-09-28, rough


def test_fishing_and_route_come_from_the_plan(forecast, plan):
    svc = service(forecast, plan)
    fish = svc.ask("मछली कहाँ मिलेगी?", "hi", VERAVAL.lat, VERAVAL.lon, "Veraval")
    assert "किमी" in fish.answer and str(len(plan.fishing_zones)) in fish.answer
    route = svc.ask("કેટલું ઈંધણ લાગશે?", "gu", VERAVAL.lat, VERAVAL.lon, "Veraval")
    r = plan.plan.route
    assert route.intent == "route" and str(round(r.fuel_l)) in route.answer and "લિટર" in route.answer


def test_no_data_says_so_instead_of_guessing():
    def boom(*a):
        raise RuntimeError("offline")
    a = AskService(forecast=boom, plan=boom).ask("मौसम कैसा है?", "hi", 20.8, 70.25, "Veraval")
    assert "ताज़ा जानकारी नहीं" in a.answer


class FakeClaude:
    """Mimics client.beta.messages.create; records the request."""

    def __init__(self, text="आज समुद्र सुरक्षित है।", stop_reason="end_turn", error=None):
        self.kwargs, self._text, self._stop, self._error = None, text, stop_reason, error
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.kwargs = kwargs
        if self._error:
            raise self._error
        return SimpleNamespace(stop_reason=self._stop, content=[SimpleNamespace(type="text", text=self._text)])


def test_claude_mode_answers_from_live_data(forecast, plan):
    fake = FakeClaude()
    a = service(forecast, plan, client=fake).ask("क्या आज जा सकते हैं?", "hi", 20.8, 70.25, "Veraval")
    assert a.mode == "claude" and a.answer == "आज समुद्र सुरक्षित है।"
    k = fake.kwargs
    assert k["model"] == "claude-opus-5" and k["fallbacks"] == "default"
    prompt = k["messages"][0]["content"]
    assert "Hindi" in prompt and '"best_day": "2026-09-30"' in prompt  # grounded on the forecast


@pytest.mark.parametrize("fake", [
    FakeClaude(stop_reason="refusal", text=""),
    FakeClaude(error=anthropic.APIConnectionError(request=None)),
])
def test_claude_failure_falls_back_to_rules(forecast, plan, fake):
    a = service(forecast, plan, client=fake).ask("आज मौसम कैसा है?", "hi", 20.8, 70.25, "Veraval")
    assert a.mode == "rules" and "हवा" in a.answer
