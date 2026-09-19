"""SamudraVani dashboard.  Run from the repo root:  streamlit run frontend/app.py

Talks to the API (default http://localhost:8000):  uvicorn main:app
All text about the plan comes from the API's `localized` block, so switching
language never re-plans and never changes a number.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import folium
import requests
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.localization_service import LANG_NAMES, LANGS, UI_LABELS  # noqa: E402

# Offshore approach points (the router needs sea cells; exact port coordinates sit on land).
PRESETS = {
    "Veraval (offshore approach)": (20.80, 70.25),
    "Porbandar (offshore approach)": (21.45, 69.45),
    "Custom": None,
}
STATUS_COLOR = {"PROCEED": "#1a7f37", "PROCEED_WITH_CAUTION": "#9a6700", "NOT_RECOMMENDED": "#bc4c00",
                "DO_NOT_VENTURE": "#cf222e", "REFUSED": "#57606a"}
RISK_COLOR = {"SAFE": "#1a7f37", "CAUTION": "#9a6700", "HIGH_RISK": "#bc4c00", "DO_NOT_VENTURE": "#cf222e",
              "INSUFFICIENT_DATA": "#57606a"}

st.set_page_config(page_title="SamudraVani", layout="wide")

with st.sidebar:
    lang = st.selectbox("Language / भाषा / ભાષા", LANGS, format_func=LANG_NAMES.get)
    L = UI_LABELS[lang]
    api = st.text_input("API URL", os.environ.get("SAMUDRAVANI_API", "http://localhost:8000"))

    def point(label: str, key: str, default: str):
        choice = st.selectbox(label, list(PRESETS), index=list(PRESETS).index(default), key=key + "_p")
        lat, lon = PRESETS[choice] or (21.0, 70.0)
        c1, c2 = st.columns(2)
        return (c1.number_input("lat", -90.0, 90.0, lat, 0.01, format="%.3f", key=key + "_lat"),
                c2.number_input("lon", -180.0, 180.0, lon, 0.01, format="%.3f", key=key + "_lon"))

    origin = point(L["origin"], "o", "Veraval (offshore approach)")
    use_dest = st.checkbox(L["destination"])
    dest = point(L["destination"], "d", "Porbandar (offshore approach)") if use_dest else None
    hours = st.slider("Window (h)", 6, 72, 24, 6)
    radius = st.slider("Search radius (deg)", 0.5, 5.0, 2.0, 0.5)
    candidates = st.slider("Candidate zones", 1, 5, 3)
    budget = st.number_input("Round-trip fuel budget (L, 0 = none)", 0.0, 100000.0, 0.0, 10.0)
    unmasked = st.checkbox("Allow route without land mask (dev only)")
    go = st.button(L["plan_btn"], type="primary", use_container_width=True)

st.title(L["title"])

if go:
    now = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
    payload = {
        "origin": {"lat": origin[0], "lon": origin[1]},
        "window": {"start": now.isoformat(), "end": (now + timedelta(hours=hours)).isoformat()},
        "search_radius_deg": radius, "max_candidates": candidates, "allow_unmasked_route": unmasked,
    }
    if dest:
        payload["destination"] = {"lat": dest[0], "lon": dest[1]}
    if budget > 0:
        payload["fuel_budget_l"] = budget
    with st.spinner("..."):
        try:
            r = requests.post(f"{api.rstrip('/')}/api/v1/voyage/plan", json=payload, timeout=900)
            r.raise_for_status()
            st.session_state["resp"] = r.json()
            st.session_state["origin"] = origin
        except requests.RequestException as exc:
            st.session_state.pop("resp", None)
            st.error(f"API error: {exc}")

resp = st.session_state.get("resp")
if not resp:
    st.info("Choose an origin in the sidebar and press the button.")
    st.stop()

plan, loc = resp["plan"], resp["localized"][lang]
zones = resp.get("fishing_zones", [])
advise_against = plan["status"] in ("DO_NOT_VENTURE", "NOT_RECOMMENDED")


def badge(tag: str, text: str, colors: dict) -> str:
    return (f"<span style='background:{colors.get(tag, '#57606a')};color:#fff;padding:2px 10px;"
            f"border-radius:12px;font-weight:600'>{text}</span>")


st.markdown(badge(loc["status_tag"], loc["status_text"], STATUS_COLOR), unsafe_allow_html=True)
st.subheader(loc["summary"])
if loc["untranslated"]:
    st.caption(f"{L['untranslated']}: {len(loc['untranslated'])}")

left, right = st.columns([3, 2])

with left:
    st.markdown(f"#### {L['map']}")
    o = st.session_state["origin"]
    fmap = folium.Map(location=o, zoom_start=8, tiles="OpenStreetMap")
    points = [o]
    folium.Marker(o, tooltip=L["origin"], icon=folium.Icon(color="green", icon="anchor", prefix="fa")).add_to(fmap)

    route = plan.get("route")
    if route and route["found"]:
        pts = [(w["lat"], w["lon"]) for w in route["waypoints"]]
        folium.PolyLine(pts, color="#0969da", weight=5, tooltip=L["route"]).add_to(fmap)
        points += pts
    for alt in plan.get("alternates", []):
        if alt["route"]["found"]:
            pts = [(w["lat"], w["lon"]) for w in alt["route"]["waypoints"]]
            folium.PolyLine(pts, color="#8c959f", weight=3, dash_array="6", opacity=0.7).add_to(fmap)
    dest_pt = plan.get("destination")
    if dest_pt and route:
        folium.Marker((dest_pt["lat"], dest_pt["lon"]), tooltip=L["destination"],
                      icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(fmap)

    chosen = plan.get("target_zone")
    for z in zones:
        is_target = chosen and (z["lat"], z["lon"]) == (chosen["lat"], chosen["lon"])
        color = "#8c959f" if advise_against else ("#1a7f37" if is_target else "#bf8700")
        folium.CircleMarker(
            (z["lat"], z["lon"]), radius=6 + 12 * z["score"], color=color, fill=True, fill_opacity=0.5,
            tooltip=f"{L['score']}: {z['score']:.2f} ({z['lat']:.3f}, {z['lon']:.3f})",
            popup="<br>".join(z["reasons"]),
        ).add_to(fmap)
        points.append((z["lat"], z["lon"]))
    if len(points) > 1:
        fmap.fit_bounds(points, padding=(30, 30))
    st_folium(fmap, height=520, use_container_width=True, returned_objects=[])

    if not route:
        st.caption(L["no_route"])
    else:
        m1, m2, m3 = st.columns(3)
        m1.metric(L["distance"], f"{route['distance_nm']:.1f} nm")
        m2.metric(L["duration"], f"{route['duration_h']:.1f} h")
        m3.metric(L["fuel"], f"{route['fuel_l']:.0f} L")

with right:
    with st.container(border=True):
        st.markdown(f"#### {L['risk']}")
        if loc["risk_tag"]:
            st.markdown(badge(loc["risk_tag"], loc["risk_text"], RISK_COLOR), unsafe_allow_html=True)
            st.write(loc["risk_explanation"])
            st.markdown(f"**{L['rules']}**")
            if not loc["triggered"]:
                st.caption(L["none_triggered"])
            raw = {t["rule_id"]: t for t in plan["risk"]["triggered"]}
            for t in loc["triggered"]:
                rr = raw[t["rule_id"]]
                st.markdown(
                    f"- {badge(t['verdict'], t['verdict'], RISK_COLOR)} `{t['rule_id']}` "
                    f"`{rr['variable']} = {rr['value']:.2f} {rr['op']} {rr['threshold']}`<br>{t['message']}",
                    unsafe_allow_html=True)

    st.markdown(f"#### {L['pfz']}")
    if advise_against and zones:
        st.warning(L["pfz_warn"])
    if zones:
        st.dataframe(
            [{"#": n + 1, L["score"]: z["score"], "lat": round(z["lat"], 3), "lon": round(z["lon"], 3),
              "why": "; ".join(z["reasons"])} for n, z in enumerate(zones)],
            hide_index=True, use_container_width=True)
    else:
        st.caption(L["no_pfz"])

st.markdown(f"#### {L['why']}")
for line in loc["explanation"]:
    st.write("- " + line)
for title, key in ((L["caveats"], "caveats"), (L["conflicts"], "conflicts_resolved")):
    if loc[key]:
        with st.expander(title, expanded=key == "caveats"):
            for line in loc[key]:
                st.write("- " + line)
with st.expander(L["data"]):
    st.json({"data_status": plan["data_status"], "warnings": resp["warnings"], "trace": resp["trace"]})
