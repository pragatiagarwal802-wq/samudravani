"""Question answering for the app's voice/chat screen ("पूछें").

Answers come only from live data: the point forecast (ForecastService) and the voyage
plan (the agent graph). Two modes:

  rules   (default, free) keyword intents in Hindi / Gujarati / English, answered from
          fixed templates filled with the live numbers.
  claude  (when ANTHROPIC_API_KEY is set and ASK_MODE != "rules") Claude writes a short
          spoken-style answer from the same live data, in the user's language. Any API
          error or refusal falls back to the rules answer, so the app always gets one.

Every answer is built from the data it was given; neither mode invents values.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from models.schemas import ForecastResponse, VoyagePlanResponse

log = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get("ASK_CLAUDE_MODEL", "claude-opus-5")

# --- intents -------------------------------------------------------------------------------

_KEYWORDS: Dict[str, List[str]] = {
    "best_day": ["best day", "which day", "when", "calm", "कब", "कौन सा दिन", "कौनसा दिन", "सबसे अच्छा दिन", "शांत",
                 "ક્યારે", "કયો દિવસ", "સૌથી સારો", "શાંત", "kab", "kaun sa din"],
    "fishing": ["fish", "catch", "zone", "pfz", "मछली", "मछलियां", "क्षेत्र", "जाल", "माछली", "માછલી", "માછીમારી", "વિસ્તાર",
                "machhli", "machli"],
    "route": ["route", "way", "distance", "fuel", "diesel", "how far", "रास्ता", "मार्ग", "दूरी", "ईंधन", "डीजल", "कितनी दूर",
              "રસ્તો", "માર્ગ", "અંતર", "ઈંધણ", "ડીઝલ", "કેટલું દૂર", "rasta"],
    "safety": ["safe", "danger", "risk", "warning", "alert", "go out", "can i go", "storm", "cyclone", "सुरक्षित", "खतरा",
               "जोखिम", "चेतावनी", "जा सकते", "जाऊं", "जाना", "तूफान", "चक्रवात", "સુરક્ષિત", "જોખમ", "ચેતવણી", "જઈ શક",
               "વાવાઝોડ", "khatra", "toofan"],
    "weather": ["weather", "wind", "wave", "rain", "sea", "मौसम", "हवा", "लहर", "बारिश", "समुद्र", "હવામાન", "પવન", "મોજ",
                "વરસાદ", "દરિયો", "mausam", "hawa", "lehar"],
}
_TOMORROW = ["tomorrow", "कल", "आने वाले कल", "આવતીકાલ", "કાલે", "kal"]


def detect_intent(question: str) -> str:
    q = question.lower()
    scores = {name: sum(1 for k in words if k in q) for name, words in _KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "summary"


def asks_tomorrow(question: str) -> bool:
    q = question.lower()
    return any(k in q for k in _TOMORROW)


# --- language resources --------------------------------------------------------------------

_WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
    "gu": ["સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર", "રવિવાર"],
}
_COMPASS = {
    "en": ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"],
    "hi": ["उत्तर", "उत्तर-पूर्व", "पूर्व", "दक्षिण-पूर्व", "दक्षिण", "दक्षिण-पश्चिम", "पश्चिम", "उत्तर-पश्चिम"],
    "gu": ["ઉત્તર", "ઉત્તર-પૂર્વ", "પૂર્વ", "દક્ષિણ-પૂર્વ", "દક્ષિણ", "દક્ષિણ-પશ્ચિમ", "પશ્ચિમ", "ઉત્તર-પશ્ચિમ"],
}
_VERDICT = {
    "en": {"SAFE": "safe", "CAUTION": "go with caution", "HIGH_RISK": "high risk", "DO_NOT_VENTURE": "do not go out",
           "INSUFFICIENT_DATA": "not enough data"},
    "hi": {"SAFE": "सुरक्षित", "CAUTION": "सावधानी रखें", "HIGH_RISK": "उच्च जोखिम", "DO_NOT_VENTURE": "समुद्र में न जाएं",
           "INSUFFICIENT_DATA": "पर्याप्त डेटा नहीं"},
    "gu": {"SAFE": "સુરક્ષિત", "CAUTION": "સાવચેતી રાખો", "HIGH_RISK": "ઊંચું જોખમ", "DO_NOT_VENTURE": "દરિયામાં ન જશો",
           "INSUFFICIENT_DATA": "પૂરતો ડેટા નથી"},
}
_LEVEL = {
    "en": [(0.7, "high"), (0.5, "medium"), (0.0, "low")],
    "hi": [(0.7, "उच्च"), (0.5, "मध्यम"), (0.0, "कम")],
    "gu": [(0.7, "ઊંચી"), (0.5, "મધ્યમ"), (0.0, "ઓછી")],
}

# Templates: {place}, numbers and names are filled in; nothing else varies.
_T = {
    "weather": {
        "en": "{when} near {place}: wind {wind} km/h (gusts up to {gust} km/h) from the {dir}, waves up to {wave} m, rain {rain} mm. Sea: {verdict}.",
        "hi": "{when} {place} के पास: हवा {wind} km/h ({dir} से, झोंके {gust} km/h तक), लहरें {wave} मीटर तक, बारिश {rain} mm। समुद्र: {verdict}।",
        "gu": "{when} {place} પાસે: પવન {wind} km/h ({dir} થી, ઝાપટાં {gust} km/h સુધી), મોજાં {wave} મીટર સુધી, વરસાદ {rain} mm. દરિયો: {verdict}.",
    },
    "when": {"en": ["Today", "Tomorrow"], "hi": ["आज", "कल"], "gu": ["આજે", "આવતીકાલે"]},
    "best_day": {
        "en": "The calmest of the next {n} days is {day}: waves up to {wave} m and wind up to {wind} km/h ({verdict}).",
        "hi": "अगले {n} दिनों में सबसे शांत दिन {day} है: लहरें {wave} मीटर तक और हवा {wind} km/h तक ({verdict})।",
        "gu": "આગામી {n} દિવસમાં સૌથી શાંત દિવસ {day} છે: મોજાં {wave} મીટર સુધી અને પવન {wind} km/h સુધી ({verdict}).",
    },
    "rough_days": {
        "en": " Take care on {days}.", "hi": " {days} को सावधान रहें।", "gu": " {days} ના દિવસે સાવચેત રહો.",
    },
    "safety_ok": {
        "en": "For the next 24 hours the sea near {place} is {verdict}: waves up to {wave} m, wind up to {wind} km/h.",
        "hi": "अगले 24 घंटे {place} के पास समुद्र {verdict} है: लहरें {wave} मीटर तक, हवा {wind} km/h तक।",
        "gu": "આગામી 24 કલાક {place} પાસે દરિયો {verdict} છે: મોજાં {wave} મીટર સુધી, પવન {wind} km/h સુધી.",
    },
    "safety_warn": {
        "en": "Warning for the next 24 hours near {place}: {verdict}. {reasons}",
        "hi": "{place} के पास अगले 24 घंटे के लिए चेतावनी: {verdict}। {reasons}",
        "gu": "{place} પાસે આગામી 24 કલાક માટે ચેતવણી: {verdict}. {reasons}",
    },
    "fishing": {
        "en": "Fishing chance is {level}. The best zone is {km} km to the {dir} of {place}; I found {n} zones in reach.",
        "hi": "मछली मिलने की संभावना {level} है। सबसे अच्छा क्षेत्र {place} से {km} किमी {dir} दिशा में है; पहुँच में {n} क्षेत्र मिले।",
        "gu": "માછલી મળવાની સંભાવના {level} છે. સૌથી સારો વિસ્તાર {place} થી {km} કિમી {dir} દિશામાં છે; પહોંચમાં {n} વિસ્તાર મળ્યા.",
    },
    "fishing_none": {
        "en": "No fishing zone was found within reach of {place} right now.",
        "hi": "अभी {place} की पहुँच में कोई मछली क्षेत्र नहीं मिला।",
        "gu": "હાલમાં {place} ની પહોંચમાં કોઈ માછીમારી વિસ્તાર મળ્યો નથી.",
    },
    "fishing_unsafe": {
        "en": " But for safety, going out is not advised today.",
        "hi": " लेकिन सुरक्षा के कारण आज समुद्र में जाने की सलाह नहीं है।",
        "gu": " પરંતુ સલામતીના કારણે આજે દરિયામાં જવાની સલાહ નથી.",
    },
    "route": {
        "en": "The safest route to the best zone is {km} km, about {h} hours, using about {fuel} litres of fuel one way ({rt} litres for the round trip).",
        "hi": "सबसे अच्छे क्षेत्र तक सबसे सुरक्षित रास्ता {km} किमी का है, लगभग {h} घंटे, एक तरफ लगभग {fuel} लीटर ईंधन (आना-जाना {rt} लीटर)।",
        "gu": "સૌથી સારા વિસ્તાર સુધીનો સૌથી સુરક્ષિત માર્ગ {km} કિમી છે, આશરે {h} કલાક, એક તરફ આશરે {fuel} લિટર ઈંધણ (આવવા-જવાનું {rt} લિટર).",
    },
    "route_none": {
        "en": "I could not plan a route right now.", "hi": "अभी रास्ता नहीं बन सका।", "gu": "હાલમાં માર્ગ બની શક્યો નથી.",
    },
    "no_data": {
        "en": "I could not get the latest sea data right now. Please try again in a little while.",
        "hi": "अभी समुद्र की ताज़ा जानकारी नहीं मिल सकी। थोड़ी देर बाद फिर पूछें।",
        "gu": "હાલમાં દરિયાની તાજી માહિતી મળી શકી નથી. થોડી વાર પછી ફરી પૂછો.",
    },
}


def _t(key: str, lang: str) -> str:
    return _T[key].get(lang) or _T[key]["en"]


def _kmh(ms: Optional[float]) -> str:
    return "–" if ms is None else str(round(ms * 3.6))


def _m(v: Optional[float]) -> str:
    return "–" if v is None else f"{v:.1f}"


def _compass(deg: float, lang: str) -> str:
    return _COMPASS.get(lang, _COMPASS["en"])[int(((deg % 360) + 22.5) // 45) % 8]


def _day_name(d: date, lang: str) -> str:
    return f"{_WEEKDAYS.get(lang, _WEEKDAYS['en'])[d.weekday()]} {d.day}"


def _verdict(v, lang: str) -> str:
    return _VERDICT.get(lang, _VERDICT["en"]).get(getattr(v, "value", v), str(v))


# --- service --------------------------------------------------------------------------------


@dataclass
class AskAnswer:
    answer: str
    intent: str
    mode: str  # "rules" | "claude"


class AskService:
    def __init__(self, forecast: Callable[[float, float], ForecastResponse],
                 plan: Callable[[float, float, str], VoyagePlanResponse], client=None):
        """`forecast(lat, lon)` and `plan(lat, lon, name)` return live data; `client` is an optional
        Anthropic client (created from the environment when ANTHROPIC_API_KEY is set)."""
        self._forecast, self._plan = forecast, plan
        self._client = client
        if client is None and os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("ASK_MODE", "").lower() != "rules":
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except ImportError:
                log.warning("ANTHROPIC_API_KEY is set but the anthropic package is not installed; using rules mode")

    @property
    def mode(self) -> str:
        return "claude" if self._client is not None else "rules"

    def ask(self, question: str, lang: str, lat: float, lon: float, place: str) -> AskAnswer:
        lang = lang if lang in ("en", "hi", "gu") else "en"
        intent = detect_intent(question)
        tomorrow = asks_tomorrow(question)
        try:
            fc = self._forecast(lat, lon)
        except Exception:
            log.exception("forecast failed")
            fc = None
        needs_plan = self._client is not None or intent in ("fishing", "route", "summary")
        plan = None
        if needs_plan:
            try:
                plan = self._plan(lat, lon, place)
            except Exception:
                log.exception("plan failed")
        rules = self._rules_answer(intent, lang, fc, plan, place, tomorrow, (lat, lon))
        if self._client is not None and (fc is not None or plan is not None):
            text = self._claude_answer(question, lang, fc, plan, place)
            if text:
                return AskAnswer(text, intent, "claude")
        return AskAnswer(rules, intent, "rules")

    # -- rules mode ------------------------------------------------------------------------
    def _rules_answer(self, intent: str, lang: str, fc: Optional[ForecastResponse],
                      plan: Optional[VoyagePlanResponse], place: str, tomorrow: bool, origin) -> str:
        parts: List[str] = []
        if intent in ("weather", "summary", "safety", "best_day") and fc is None and plan is None:
            return _t("no_data", lang)
        if intent == "weather" and fc:
            parts.append(self._weather(fc, lang, place, 1 if tomorrow else 0))
        elif intent == "best_day" and fc:
            parts.append(self._best_day(fc, lang))
        elif intent == "safety":
            parts.append(self._safety(fc, plan, lang, place, 1 if tomorrow else 0))
        elif intent == "fishing":
            parts.append(self._fishing(plan, lang, place, origin))
        elif intent == "route":
            parts.append(self._route(plan, lang))
        else:  # summary
            if fc:
                parts.append(self._weather(fc, lang, place, 0))
            parts.append(self._fishing(plan, lang, place, origin))
        text = " ".join(p for p in parts if p).strip()
        return text or _t("no_data", lang)

    def _weather(self, fc: ForecastResponse, lang: str, place: str, day_idx: int) -> str:
        if not fc.days:
            return _t("no_data", lang)
        d = fc.days[min(day_idx, len(fc.days) - 1)]
        day_hours = [h for h in fc.hours if h.time.replace(tzinfo=timezone.utc).astimezone(
            timezone(timedelta(hours=5, minutes=30))).date().isoformat() == d.date] or fc.hours[:24]
        dirs = [h.wind_from_deg for h in day_hours if h.wind_from_deg is not None]
        direction = _compass(sorted(dirs)[len(dirs) // 2], lang) if dirs else "–"
        return _t("weather", lang).format(
            when=_T["when"].get(lang, _T["when"]["en"])[1 if day_idx else 0], place=place,
            wind=_kmh(d.max_wind_ms), gust=_kmh(d.max_gust_ms), dir=direction, wave=_m(d.max_wave_m),
            rain=_m(d.rain_mm), verdict=_verdict(d.verdict, lang))

    def _best_day(self, fc: ForecastResponse, lang: str) -> str:
        best = next((d for d in fc.days if d.date == fc.best_day), None)
        if best is None:
            return _t("no_data", lang)
        text = _t("best_day", lang).format(n=len(fc.days), day=_day_name(date.fromisoformat(best.date), lang),
                                           wave=_m(best.max_wave_m), wind=_kmh(best.max_wind_ms),
                                           verdict=_verdict(best.verdict, lang))
        rough = [_day_name(date.fromisoformat(d.date), lang) for d in fc.days
                 if getattr(d.verdict, "value", d.verdict) not in ("SAFE", "INSUFFICIENT_DATA")]
        if rough:
            text += _t("rough_days", lang).format(days=", ".join(rough))
        return text

    def _safety(self, fc: Optional[ForecastResponse], plan: Optional[VoyagePlanResponse], lang: str,
                place: str, day_idx: int) -> str:
        day = fc.days[min(day_idx, len(fc.days) - 1)] if fc and fc.days else None
        if day_idx == 0 and plan is not None and plan.plan.risk is not None:
            risk = plan.plan.risk
            verdict = risk.verdict
            reasons = [lt.message for lt in (plan.localized.get(lang).triggered if plan.localized.get(lang) else [])] \
                or [t.message for t in risk.triggered]
        elif day is not None:
            verdict = day.verdict
            reasons = [m.message for m in day.messages.get(lang, [])] or [t.message for t in day.triggered]
        else:
            return _t("no_data", lang)
        v = getattr(verdict, "value", verdict)
        if v == "SAFE" or not reasons:
            return _t("safety_ok", lang).format(place=place, verdict=_verdict(verdict, lang),
                                                wave=_m(day.max_wave_m if day else None),
                                                wind=_kmh(day.max_wind_ms if day else None))
        return _t("safety_warn", lang).format(place=place, verdict=_verdict(verdict, lang), reasons=" ".join(reasons))

    def _fishing(self, plan: Optional[VoyagePlanResponse], lang: str, place: str, origin) -> str:
        if plan is None:
            return _t("no_data", lang)
        zones = plan.fishing_zones
        if not zones:
            return _t("fishing_none", lang).format(place=place)
        best = plan.plan.target_zone or zones[0]
        olat, olon = origin
        km = _haversine_km(olat, olon, best.lat, best.lon)
        level = next(name for lim, name in _LEVEL.get(lang, _LEVEL["en"]) if max(z.score for z in zones) >= lim)
        text = _t("fishing", lang).format(level=level, km=round(km), dir=_compass(_bearing(olat, olon, best.lat, best.lon), lang),
                                          place=place, n=len(zones))
        if plan.plan.status.value in ("DO_NOT_VENTURE", "NOT_RECOMMENDED"):
            text += _t("fishing_unsafe", lang)
        return text

    def _route(self, plan: Optional[VoyagePlanResponse], lang: str) -> str:
        r = plan.plan.route if plan else None
        if r is None or not r.found:
            return _t("route_none", lang)
        return _t("route", lang).format(km=round(r.distance_nm * 1.852), h=f"{r.duration_h:.1f}",
                                        fuel=round(r.fuel_l), rt=round(2 * r.fuel_l))

    # -- claude mode -------------------------------------------------------------------------
    def _claude_answer(self, question: str, lang: str, fc: Optional[ForecastResponse],
                       plan: Optional[VoyagePlanResponse], place: str) -> Optional[str]:
        import anthropic

        language = {"hi": "Hindi (Devanagari script)", "gu": "Gujarati (Gujarati script)", "en": "English"}[lang]
        system = (
            "You are SamudraVani, a marine safety and fishing assistant for small-boat fishers on the Gujarat coast. "
            "Your answer is read aloud by a phone, so reply in 1-3 short, plain sentences with no markdown, lists or emojis. "
            "Use only the live data provided in the user's message; if it does not answer the question, say you do not "
            "have that information. Never invent numbers, places or warnings. Safety comes first: if the data says "
            "DO_NOT_VENTURE or HIGH_RISK, say clearly not to go out. Give wind in km/h, waves in metres, distance in km."
        )
        data = {"place": place, "now_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "forecast": _forecast_digest(fc), "plan": _plan_digest(plan, lang)}
        user = (f"Live data (JSON):\n{json.dumps(data, ensure_ascii=False, sort_keys=True)}\n\n"
                f"Answer in {language}. Question: {question}")
        try:
            response = self._client.beta.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4000,
                output_config={"effort": "low"},  # short spoken answers; keeps latency and cost down
                system=system,
                messages=[{"role": "user", "content": user}],
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # on a safety decline, the API retries on a fallback model
            )
        except anthropic.APIConnectionError:
            log.warning("Claude unreachable; using rules answer")
            return None
        except anthropic.RateLimitError:
            log.warning("Claude rate limited; using rules answer")
            return None
        except anthropic.APIStatusError as e:
            log.warning("Claude API error %s; using rules answer", e.status_code)
            return None
        if response.stop_reason == "refusal":
            return None
        text = " ".join(b.text for b in response.content if b.type == "text").strip()
        return re.sub(r"\s+", " ", text) or None


def _forecast_digest(fc: Optional[ForecastResponse]) -> Optional[dict]:
    if fc is None:
        return None
    return {
        "best_day": fc.best_day,
        "days": [{"date": d.date, "verdict": d.verdict.value, "max_wave_m": d.max_wave_m,
                  "max_wind_kmh": None if d.max_wind_ms is None else round(d.max_wind_ms * 3.6),
                  "max_gust_kmh": None if d.max_gust_ms is None else round(d.max_gust_ms * 3.6),
                  "rain_mm": d.rain_mm, "min_visibility_km": d.min_visibility_km,
                  "warnings": [t.message for t in d.triggered]} for d in fc.days],
        "next_hours": [{"time_utc": h.time.strftime("%m-%d %H:%M"), "wind_kmh": None if h.wind_speed is None else round(h.wind_speed * 3.6),
                        "wind_from_deg": h.wind_from_deg, "wave_m": h.wave_height, "rain_mm": h.rain_mm}
                       for h in fc.hours[:24:3]],
    }


def _plan_digest(plan: Optional[VoyagePlanResponse], lang: str) -> Optional[dict]:
    if plan is None:
        return None
    p = plan.plan
    loc = plan.localized.get(lang)
    r = p.route
    return {
        "status": p.status.value,
        "summary": loc.summary if loc else p.summary,
        "risk": p.risk.verdict.value if p.risk else None,
        "warnings": [t.message for t in (loc.triggered if loc else [])],
        "zones": [{"lat": z.lat, "lon": z.lon, "score": z.score} for z in plan.fishing_zones[:5]],
        "route": None if r is None or not r.found else {
            "distance_km": round(r.distance_nm * 1.852), "hours": round(r.duration_h, 1),
            "fuel_l_one_way": round(r.fuel_l), "max_wave_m": r.max_wave_m},
        "caveats": loc.caveats if loc else p.caveats,
    }


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    import math

    p1, p2 = math.radians(lat1), math.radians(lat2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _bearing(lat1, lon1, lat2, lon2) -> float:
    import math

    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0
