"""AeroNav AI — Streamlit Dashboard (Gemini API)"""

import json
import math
import os
import random
from dataclasses import dataclass
from typing import List

import plotly.graph_objects as go
import streamlit as st


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AeroNav AI",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark theme CSS ───────────────────────────────────────────────────────────
st.markdown(
    """
<style>
  body, .stApp { background:#050a12; color:#c8dff0; }
  .stMetric label { color:#4a6a8a !important; }
  .stMetric .metric-value { color:#00d4ff !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Data Models ──────────────────────────────────────────────────────────────
@dataclass
class Airport:
    code: str
    name: str
    lon: float
    lat: float


@dataclass
class Aircraft:
    code: str
    name: str
    burn_rate_kg_per_hr: float
    max_payload_kg: float


@dataclass
class Waypoint:
    name: str
    lat: float
    lon: float
    altitude_fl: int
    wind_kt: int


@dataclass
class RouteOption:
    label: str
    total_fuel_kg: float
    total_co2_kg: float
    flight_time_min: int
    distance_nm: float
    is_eco: bool = False


@dataclass
class FlightAnalysis:
    origin: Airport
    destination: Airport
    aircraft: Aircraft
    priority: str
    cruise_fl: int
    distance_nm: float
    eco_route: RouteOption
    standard_route: RouteOption
    fuel_saved_kg: float
    co2_saved_kg: float
    time_delta_min: int
    wind_profile: List[float]
    emission_breakdown: dict
    waypoints: List[Waypoint]
    ai_insight: str = ""


# ── Databases ────────────────────────────────────────────────────────────────
AIRPORTS = {
    "KJFK": Airport("KJFK", "New York JFK", -73.78, 40.63),
    "EGLL": Airport("EGLL", "London Heathrow", -0.46, 51.47),
    "KLAX": Airport("KLAX", "Los Angeles LAX", -118.40, 33.94),
    "EDDF": Airport("EDDF", "Frankfurt FRA", 8.57, 50.03),
    "RJTT": Airport("RJTT", "Tokyo Haneda", 139.78, 35.55),
    "OMDB": Airport("OMDB", "Dubai DXB", 55.36, 25.25),
    "YSSY": Airport("YSSY", "Sydney SYD", 151.18, -33.94),
    "SBGR": Airport("SBGR", "Sao Paulo GRU", -46.47, -23.43),
    "ZBAA": Airport("ZBAA", "Beijing Capital", 116.58, 40.08),
    "LFPG": Airport("LFPG", "Paris CDG", 2.55, 49.01),
}

AIRCRAFT = {
    "B737": Aircraft("B737", "Boeing 737-800", 2400, 65000),
    "B777": Aircraft("B777", "Boeing 777-300ER", 6800, 145700),
    "A320": Aircraft("A320", "Airbus A320neo", 2100, 66000),
    "A350": Aircraft("A350", "Airbus A350-900", 5600, 158000),
    "B787": Aircraft("B787", "Boeing 787-9", 5000, 126000),
}

CO2_PER_KG_FUEL = 3.16
CRUISE_SPEED_KT = 480
PRIORITY_FACTOR = {
    "eco": 0.82,
    "fuel": 0.85,
    "time": 0.96,
    "balance": 0.89,
}
WAYPOINT_NAMES = ["RATSU", "MIMKU", "SOMAX", "NATBY", "RESNO", "LIMRI", "DOLIR", "TOPPS"]


# ── Physics Engine ───────────────────────────────────────────────────────────
def haversine_nm(a: Airport, b: Airport) -> float:
    r_nm = 3440.065
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = math.radians(b.lat - a.lat)
    dlon = math.radians(b.lon - a.lon)

    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return r_nm * 2 * math.asin(math.sqrt(h))


def generate_eco_waypoints(origin: Airport, dest: Airport, cruise_fl: int, n: int = 7) -> List[Waypoint]:
    wps = []
    for i in range(1, n):
        t = i / n
        lon = origin.lon + (dest.lon - origin.lon) * t
        lat = (
            origin.lat
            + (dest.lat - origin.lat) * t
            + math.sin(t * math.pi) * 6
            + random.uniform(-1, 1)
        )
        wind = round(math.sin(t * math.pi) * 30 + random.uniform(-15, 15))
        wps.append(
            Waypoint(
                WAYPOINT_NAMES[i % len(WAYPOINT_NAMES)],
                round(lat, 2),
                round(lon, 2),
                cruise_fl,
                wind,
            )
        )
    return wps


def generate_wind_profile(n: int = 20) -> List[float]:
    return [
        round(math.sin(i / (n - 1) * math.pi) * 30 + random.uniform(-15, 15), 1)
        for i in range(n)
    ]


def compute_emission_breakdown(co2_kg: float) -> dict:
    return {
        "Cruise": round(co2_kg * 0.68),
        "Climb/Descent": round(co2_kg * 0.18),
        "Ground/Taxi": round(co2_kg * 0.07),
        "Contrail Effect": round(co2_kg * 0.07),
    }


def compute_route(origin: Airport, dest: Airport, aircraft: Aircraft, priority: str = "eco", cruise_fl: int = 370) -> FlightAnalysis:
    dist_nm = haversine_nm(origin, dest)
    flight_hrs = dist_nm / CRUISE_SPEED_KT
    base_fuel = aircraft.burn_rate_kg_per_hr * flight_hrs

    factor = PRIORITY_FACTOR.get(priority, 0.86)

    # Slight extra variation so dashboard does not feel too static
    wind_bonus_factor = 1 - (0.01 if priority in ("eco", "fuel") else 0.0)
    altitude_factor = 1 - ((cruise_fl - 330) / 10000.0)
    adjusted_factor = max(0.78, min(0.98, factor * wind_bonus_factor * altitude_factor))

    eco_fuel = base_fuel * adjusted_factor
    eco_co2 = eco_fuel * CO2_PER_KG_FUEL
    base_min = round(flight_hrs * 60)
    time_delta = round(base_min * (1 - adjusted_factor))

    eco_route = RouteOption(
        "ECO OPTIMAL",
        round(eco_fuel),
        round(eco_co2),
        base_min + time_delta,
        round(dist_nm),
        is_eco=True,
    )

    standard_route = RouteOption(
        "STANDARD",
        round(base_fuel),
        round(base_fuel * CO2_PER_KG_FUEL),
        base_min,
        round(dist_nm),
    )

    return FlightAnalysis(
        origin=origin,
        destination=dest,
        aircraft=aircraft,
        priority=priority,
        cruise_fl=cruise_fl,
        distance_nm=round(dist_nm, 1),
        eco_route=eco_route,
        standard_route=standard_route,
        fuel_saved_kg=round(base_fuel - eco_fuel),
        co2_saved_kg=round((base_fuel - eco_fuel) * CO2_PER_KG_FUEL),
        time_delta_min=time_delta,
        wind_profile=generate_wind_profile(),
        emission_breakdown=compute_emission_breakdown(round(eco_co2)),
        waypoints=generate_eco_waypoints(origin, dest, cruise_fl),
    )


def all_alternatives(origin: Airport, dest: Airport, aircraft: Aircraft, cruise_fl: int):
    dist = haversine_nm(origin, dest)
    hrs = dist / CRUISE_SPEED_KT
    bf = aircraft.burn_rate_kg_per_hr * hrs
    bm = round(hrs * 60)

    return [
        RouteOption("ECO OPTIMAL", round(bf * 0.82), round(bf * 0.82 * CO2_PER_KG_FUEL), bm + 18, round(dist), True),
        RouteOption("BALANCED", round(bf * 0.89), round(bf * 0.89 * CO2_PER_KG_FUEL), bm + 8, round(dist)),
        RouteOption("MIN TIME", round(bf * 0.96), round(bf * 0.96 * CO2_PER_KG_FUEL), bm, round(dist)),
        RouteOption("STANDARD", round(bf), round(bf * CO2_PER_KG_FUEL), bm, round(dist)),
    ]


# ── Gemini AI ────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_ai_insight(
    origin_code,
    dest_code,
    aircraft_name,
    priority,
    cruise_fl,
    distance_nm,
    fuel_saved_kg,
    co2_saved_kg,
    time_delta_min,
    api_key,
):
    prompt = f"""You are AeroNav AI, an expert aviation fuel efficiency system.
Give a concise technical pilot briefing (2-3 sentences) for this flight:
Route: {origin_code} → {dest_code}
Aircraft: {aircraft_name} | Priority: {priority}
Cruise FL{cruise_fl} | Distance: {distance_nm:,.0f} NM
Fuel saved vs standard: {fuel_saved_kg:,} kg
CO2 avoided: {co2_saved_kg:,} kg
Time delta: {'+' if time_delta_min >= 0 else ''}{time_delta_min} min
Mention jet streams, altitude optimization, or contrail avoidance as relevant.
Be direct and technical. No bullet points."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        return model.generate_content(prompt).text.strip()
    except Exception as e:
        return (
            f"Eco route {origin_code}–{dest_code}: FL{cruise_fl} cruise with "
            f"jet-stream alignment yields {fuel_saved_kg:,} kg fuel reduction. "
            f"[Gemini error: {e}]"
        )


# ── Plotly map helpers ───────────────────────────────────────────────────────
def gc_latlons(lon1, lat1, lon2, lat2, n=80):
    lo1, la1, lo2, la2 = map(math.radians, [lon1, lat1, lon2, lat2])
    pts = []
    d = math.acos(
        max(
            -1,
            min(
                1,
                math.sin(la1) * math.sin(la2)
                + math.cos(la1) * math.cos(la2) * math.cos(lo2 - lo1),
            ),
        )
    )
    sd = math.sin(d) if math.sin(d) != 0 else 1e-12
    for i in range(n + 1):
        t = i / n
        a = math.sin((1 - t) * d) / sd
        b = math.sin(t * d) / sd
        x = a * math.cos(la1) * math.cos(lo1) + b * math.cos(la2) * math.cos(lo2)
        y = a * math.cos(la1) * math.sin(lo1) + b * math.cos(la2) * math.sin(lo2)
        z = a * math.sin(la1) + b * math.sin(la2)
        lat_d = math.degrees(math.atan2(z, math.sqrt(x**2 + y**2)))
        lon_d = math.degrees(math.atan2(y, x))
        pts.append([lat_d, lon_d])
    return pts


def build_route_map_plotly(origin, dest, analysis, aircraft, airports):
    std_path = gc_latlons(origin.lon, origin.lat, dest.lon, dest.lat)
    std_lats = [p[0] for p in std_path]
    std_lons = [p[1] for p in std_path]

    eco_path = [[origin.lat, origin.lon]] + [[w.lat, w.lon] for w in analysis.waypoints] + [[dest.lat, dest.lon]]
    eco_lats = [p[0] for p in eco_path]
    eco_lons = [p[1] for p in eco_path]

    fig = go.Figure()

    fig.add_trace(
        go.Scattergeo(
            lat=std_lats,
            lon=std_lons,
            mode="lines",
            name="Standard Route",
            line=dict(width=2, color="#ff6b35", dash="dash"),
            opacity=0.55,
            hoverinfo="text",
            text=["Standard Great-Circle Route"] * len(std_lats),
        )
    )

    fig.add_trace(
        go.Scattergeo(
            lat=eco_lats,
            lon=eco_lons,
            mode="lines+markers",
            name="Eco Route",
            line=dict(width=4, color="#00d4ff"),
            marker=dict(size=5, color="#00d4ff"),
            opacity=0.9,
            hoverinfo="text",
            text=["Eco Optimal Route"] * len(eco_lats),
        )
    )

    if analysis.waypoints:
        wp_text = []
        for wp in analysis.waypoints:
            wind_sign = "+" if wp.wind_kt >= 0 else ""
            wp_text.append(
                f"<b>{wp.name}</b><br>"
                f"Lat: {wp.lat:.2f}° | Lon: {wp.lon:.2f}°<br>"
                f"Altitude: FL{wp.altitude_fl}<br>"
                f"Wind: {wind_sign}{wp.wind_kt} kt"
            )

        fig.add_trace(
            go.Scattergeo(
                lat=[wp.lat for wp in analysis.waypoints],
                lon=[wp.lon for wp in analysis.waypoints],
                mode="markers+text",
                name="Waypoints",
                marker=dict(size=8, color="#00d4ff", line=dict(width=1, color="white")),
                text=[wp.name for wp in analysis.waypoints],
                textposition="top center",
                hoverinfo="text",
                hovertext=wp_text,
            )
        )

    fig.add_trace(
        go.Scattergeo(
            lat=[origin.lat],
            lon=[origin.lon],
            mode="markers+text",
            name="Origin",
            marker=dict(size=14, color="#00ff9d", symbol="triangle-up", line=dict(width=1, color="white")),
            text=[origin.code],
            textposition="top center",
            hoverinfo="text",
            hovertext=f"<b>✈ ORIGIN</b><br><b>{origin.code}</b> — {origin.name}",
        )
    )

    fig.add_trace(
        go.Scattergeo(
            lat=[dest.lat],
            lon=[dest.lon],
            mode="markers+text",
            name="Destination",
            marker=dict(size=14, color="#00d4ff", symbol="triangle-down", line=dict(width=1, color="white")),
            text=[dest.code],
            textposition="top center",
            hoverinfo="text",
            hovertext=f"<b>🛬 DESTINATION</b><br><b>{dest.code}</b> — {dest.name}",
        )
    )

    other_airports = [ap for code, ap in airports.items() if code not in (origin.code, dest.code)]
    if other_airports:
        fig.add_trace(
            go.Scattergeo(
                lat=[ap.lat for ap in other_airports],
                lon=[ap.lon for ap in other_airports],
                mode="markers",
                name="Other Airports",
                marker=dict(size=6, color="#1a3a5c", line=dict(width=0.5, color="#2a4a6a")),
                hoverinfo="text",
                hovertext=[f"{ap.code} — {ap.name}" for ap in other_airports],
                opacity=0.8,
            )
        )

    fig.update_layout(
        title=(
            f"✈ {origin.code} → {dest.code} | {aircraft.name} | "
            f"{analysis.distance_nm:,.0f} NM | "
            f"⬇ {analysis.fuel_saved_kg:,} kg fuel saved | "
            f"⬇ {analysis.co2_saved_kg:,} kg CO₂ avoided"
        ),
        height=650,
        paper_bgcolor="#050a12",
        plot_bgcolor="#050a12",
        font=dict(color="#c8dff0", family="monospace", size=12),
        legend=dict(bgcolor="rgba(5,10,18,0.85)", bordercolor="#0d2545", borderwidth=1, x=0.01, y=0.01),
        margin=dict(l=20, r=20, t=70, b=20),
        geo=dict(
            projection_type="equirectangular",
            showland=True,
            landcolor="#0d2240",
            showocean=True,
            oceancolor="#030810",
            showlakes=True,
            lakecolor="#030810",
            showcountries=True,
            countrycolor="#1a3a5c",
            coastlinecolor="#1a3a5c",
            showframe=False,
            bgcolor="#050a12",
            lataxis=dict(showgrid=True, gridcolor="#0a1e35", dtick=30),
            lonaxis=dict(showgrid=True, gridcolor="#0a1e35", dtick=30),
        ),
    )
    return fig


def draw_eco_dashboard(analysis: FlightAnalysis):
    labels = ["Eco Fuel", "Std Fuel", "Eco CO₂", "Std CO₂"]
    values = [
        analysis.eco_route.total_fuel_kg,
        analysis.standard_route.total_fuel_kg,
        analysis.eco_route.total_co2_kg,
        analysis.standard_route.total_co2_kg,
    ]
    colors = ["#00d4ff", "#ff6b35", "#00ff9d", "#ffcc00"]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=values,
            marker_color=colors,
            text=[f"{v:,}" for v in values],
            textposition="outside",
        )
    )

    fig.update_layout(
        title="Eco Metrics Dashboard",
        height=420,
        paper_bgcolor="#050a12",
        plot_bgcolor="#050a12",
        font=dict(color="#c8dff0", family="monospace"),
        xaxis=dict(title="", showgrid=False),
        yaxis=dict(title="kg", gridcolor="#0a1e35"),
        margin=dict(l=30, r=30, t=60, b=30),
    )
    return fig


# ── Sidebar controls ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🎛️ Flight Parameters")

    airport_labels = {code: f"{code} — {ap.name}" for code, ap in AIRPORTS.items()}
    origin_code = st.selectbox(
        "Origin",
        list(AIRPORTS.keys()),
        format_func=lambda c: airport_labels[c],
        index=0,
    )
    dest_code = st.selectbox(
        "Destination",
        list(AIRPORTS.keys()),
        format_func=lambda c: airport_labels[c],
        index=1,
    )

    if origin_code == dest_code:
        st.warning("Origin and destination must differ.")

    aircraft_labels = {code: f"{code} ({ac.name})" for code, ac in AIRCRAFT.items()}
    aircraft_code = st.selectbox(
        "Aircraft",
        list(AIRCRAFT.keys()),
        format_func=lambda c: aircraft_labels[c],
        index=1,
    )

    priority = st.radio(
        "Routing Strategy",
        ["eco", "fuel", "time", "balance"],
        format_func=str.upper,
        horizontal=True,
        index=0,
    )

    cruise_fl = st.select_slider(
        "Cruise Flight Level",
        [330, 350, 370, 390, 410],
        value=370,
    )

    st.divider()

    gemini_key = st.text_input(
        "🔑 Gemini API Key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        help="Get a free key at aistudio.google.com",
    )

    compute_btn = st.button(
        "🚀 Compute Route",
        type="primary",
        use_container_width=True,
    )


# ── Main panel ───────────────────────────────────────────────────────────────
if compute_btn and origin_code != dest_code:
    origin = AIRPORTS[origin_code]
    dest = AIRPORTS[dest_code]
    aircraft = AIRCRAFT[aircraft_code]

    with st.spinner("⟳ Computing eco route..."):
        analysis = compute_route(origin, dest, aircraft, priority, cruise_fl)

    if gemini_key:
        with st.spinner("🤖 Consulting Gemini AI..."):
            analysis.ai_insight = fetch_ai_insight(
                origin.code,
                dest.code,
                aircraft.name,
                priority,
                cruise_fl,
                analysis.distance_nm,
                analysis.fuel_saved_kg,
                analysis.co2_saved_kg,
                analysis.time_delta_min,
                gemini_key,
            )

    pct = round((analysis.fuel_saved_kg / analysis.standard_route.total_fuel_kg) * 100) if analysis.standard_route.total_fuel_kg else 0
    fmt = lambda m: f"{m//60}h {m%60:02d}m"

    st.subheader("📊 Eco Metrics")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Distance", f"{analysis.distance_nm:,.0f} NM")
    c2.metric("⬇ Fuel Saved", f"{analysis.fuel_saved_kg:,} kg", f"-{pct}% vs std")
    c3.metric("⬇ CO₂ Avoided", f"{analysis.co2_saved_kg:,} kg", f"-{pct}% vs std")
    c4.metric("⏱ Time Delta", f"{analysis.time_delta_min:+} min")
    c5.metric("Eco Flight Time", fmt(analysis.eco_route.flight_time_min))

    if analysis.ai_insight:
        st.subheader("🤖 AI Insight (Gemini)")
        st.info(analysis.ai_insight)

    st.subheader("🌍 World Route Map")
    fig_map = build_route_map_plotly(origin, dest, analysis, aircraft, AIRPORTS)
    st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})

    st.subheader("📈 Eco Metrics Dashboard")
    fig_dash = draw_eco_dashboard(analysis)
    st.plotly_chart(fig_dash, use_container_width=True, config={"displayModeBar": False})

    st.subheader("📍 Waypoint Table")
    wp_data = [
        {
            "Waypoint": wp.name,
            "Lat": f"{wp.lat:.2f}°",
            "Lon": f"{wp.lon:.2f}°",
            "Altitude": f"FL{wp.altitude_fl}",
            "Wind": f"{'+' if wp.wind_kt >= 0 else ''}{wp.wind_kt} kt",
        }
        for wp in analysis.waypoints
    ]
    st.dataframe(wp_data, use_container_width=True)

    st.subheader("💾 Export Analysis")
    export = {
        "flight": {
            "origin": origin_code,
            "dest": dest_code,
            "aircraft": aircraft_code,
            "priority": priority,
            "cruise_fl": cruise_fl,
        },
        "eco_metrics": {
            "fuel_saved_kg": analysis.fuel_saved_kg,
            "co2_saved_kg": analysis.co2_saved_kg,
            "time_delta_min": analysis.time_delta_min,
        },
        "ai_insight": analysis.ai_insight,
    }

    st.download_button(
        "⬇ Download JSON",
        json.dumps(export, indent=2),
        file_name=f"aeronav_{origin_code}_{dest_code}.json",
        mime="application/json",
    )
else:
    st.info("← Configure your flight in the sidebar and click **Compute Route**.")
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Boeing_787-8_Dreamliner_N787BX.jpg/1280px-Boeing_787-8_Dreamliner_N787BX.jpg",
        caption="Boeing 787 Dreamliner — one of the most fuel-efficient wide-body aircraft",
        width="stretch",
    )
