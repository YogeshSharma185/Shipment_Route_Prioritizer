"""A visual, non-technical-friendly dashboard for the shipment route pipeline.

This is a thin UI layer on top of the existing project - it does not change
any business logic. It calls the exact same functions main.py uses
(get_travel_matrix -> generate_prioritized_route) and displays the record
data, the travel data, the final prioritized route, and a map.

Navigation is a radio-button page switch rather than st.tabs on purpose:
st.tabs renders every tab's content on every run (just hides the inactive
ones with CSS), so a map built inside a hidden tab gets initialized at
zero size and stays blank forever. A radio switch only ever builds the
page that's actually visible.

Run with: streamlit run app.py
"""
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from sample_data import SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, geocode_address, get_travel_matrix
from services.route_service import _classify_window, generate_prioritized_route

# folium's default marker icons use Font Awesome 4 names, not "warehouse"/"box" (FA5+).
STOP_ICONS = {"pickup": ("purple", "arrow-up"), "delivery": ("blue", "cube")}
PAGES = ["🏭 Shipments", "📋 Prioritized Route", "🔍 Travel Matrix", "🗺️ Map"]

st.set_page_config(page_title="Shipment Route Prioritizer", page_icon="📦", layout="wide")

st.markdown(
    """
    <style>
    .app-hero {
        padding: 1.2rem 2rem;
        border-radius: 14px;
        background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%);
        color: white;
        margin-bottom: 1.5rem;
    }
    .app-hero h1 { margin: 0; font-size: 1.6rem; }
    </style>
    <div class="app-hero">
        <h1>📦 Shipment Route Prioritizer</h1>
    </div>
    """,
    unsafe_allow_html=True,
)


def format_time_window(time_window):
    if not time_window:
        return "No constraint"
    start, end = time_window.get("start", "—"), time_window.get("end", "—")
    return f"{start} - {end}"


def _describe_event(shipment, kind):
    time_window = (shipment["pickup"].get("time_window") if kind == "pickup" else shipment["delivery"].get("time_window")) or {}
    start, end = time_window.get("start"), time_window.get("end")
    label = "Pickup" if kind == "pickup" else "Delivery"
    if start and end:
        return f"{label}: strict window {start}-{end}"
    if end:
        return f"{label}: deadline {end}"
    if start:
        return f"{label}: start-only {start} (no deadline, can go any time after)"
    return f"{label}: no time constraint"


def _stop_priority_window(stop, shipment):
    """The window actually used to classify this stop's priority - matches
    route_service._expand_events: a pickup with no window of its own
    inherits its delivery's window, since it has to happen early enough for
    that deadline to be reachable.
    """
    if stop["type"] == "pickup":
        return shipment["pickup"].get("time_window") or shipment["delivery"].get("time_window")
    return shipment["delivery"].get("time_window")


def build_priority_reasons(ordered_stops, travel):
    """One reason string per stop (keyed by stop_key, since a shipment can
    contribute both a pickup and a delivery stop), explaining why it landed
    at that position. When two consecutive stops were genuinely tied on
    priority (same group/anchor/duration), route_service's own tiebreak -
    real travel distance from whichever stop was placed right before it - is
    what actually broke the tie, so that's called out explicitly. UI-only:
    mirrors route_service._classify_window's grouping without duplicating
    the actual sequencing decision.
    """
    reasons = {}
    prev_class, prev_label, prev_key = None, None, None
    for stop_key, stop, shipment in ordered_stops:
        this_class = _classify_window(_stop_priority_window(stop, shipment))
        reason = _describe_event(shipment, stop["type"])
        event_key = (stop["type"], stop["shipment_id"])

        if this_class == prev_class and prev_key is not None:
            leg = travel.get((prev_key, event_key))
            distance = f"{leg['distance']}m" if leg else "an unknown distance"
            reason += f" - tied on priority with {prev_label}; {distance} from that stop won the tie"

        reasons[stop_key] = reason
        prev_class, prev_label, prev_key = this_class, f"{stop['shipment_id']} ({stop['type']})", event_key
    return reasons


# ---------------------------------------------------------------------------
# Sidebar - the one action in this app
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Run")
    st.caption(
        "Shipment data comes from `sample_data.py`. Edit that file to try different data."
    )
    st.metric("Shipments on record", len(SAMPLE_SHIPMENTS))
    generate_clicked = st.button("🚀 Generate Prioritized Route", type="primary", use_container_width=True)

    if generate_clicked:
        with st.spinner("Getting the Geoapify travel matrix..."):
            try:
                travel, skipped_keys = get_travel_matrix(SAMPLE_SHIPMENTS)
            except GeoapifyError as exc:
                st.session_state["error"] = f"Geoapify request failed: {exc}"
                st.session_state.pop("result", None)
                st.session_state.pop("travel", None)
            else:
                result = generate_prioritized_route(SAMPLE_SHIPMENTS, travel, skipped_keys)
                if "error" in result:
                    st.session_state["error"] = result
                    st.session_state.pop("result", None)
                else:
                    st.session_state["result"] = result
                    st.session_state["travel"] = travel
                    st.session_state.pop("error", None)
        # Jump straight to the results page - must be set before the radio
        # widget below is created, since that's what controls its value.
        st.session_state["page"] = "📋 Prioritized Route"

    if st.session_state.get("result"):
        st.success("Route ready.")
    elif st.session_state.get("error"):
        st.error("Last run failed - see the Prioritized Route page.")
    else:
        st.info("Click **Generate** to run the pipeline.")

    st.divider()
    page = st.radio("View", PAGES, key="page", label_visibility="collapsed")

result = st.session_state.get("result")
travel = st.session_state.get("travel")
error = st.session_state.get("error")

# ---------------------------------------------------------------------------
# Pages - only the selected one is ever built
# ---------------------------------------------------------------------------

if page == "🏭 Shipments":
    st.caption("This is the input data for the run - fixed for this demo, not editable live.")
    record_df = pd.DataFrame(
        [
            {
                "Shipment ID": shipment["shipment_id"],
                "Pickup origin": (shipment.get("pickup") or {}).get("origin", "—"),
                "Pickup address": (shipment.get("pickup") or {}).get("address", "—"),
                "Pickup window": format_time_window((shipment.get("pickup") or {}).get("time_window")),
                "Delivery address": shipment["delivery"]["address"],
                "Delivery window": format_time_window(shipment["delivery"].get("time_window")),
            }
            for shipment in SAMPLE_SHIPMENTS
        ]
    )
    st.dataframe(record_df, use_container_width=True, hide_index=True)

elif page == "📋 Prioritized Route":
    if error:
        message = error if isinstance(error, str) else error.get("error")
        st.error(message)
        if isinstance(error, dict) and "details" in error:
            st.table(pd.DataFrame(error["details"]))
    elif not result:
        st.info("Click **Generate Prioritized Route** in the sidebar to see results here.")
    else:
        col1, col2 = st.columns(2)
        col1.metric("Total distance", f"{result['total_miles']} mi")
        col2.metric("Estimated travel time", result["total_duration"])

        shipments_by_id = {shipment["shipment_id"]: shipment for shipment in SAMPLE_SHIPMENTS}
        ordered_stops = [
            (stop_key, stop, shipments_by_id[stop["shipment_id"]]) for stop_key, stop in result["routes"].items()
        ]
        reasons = build_priority_reasons(ordered_stops, travel)

        rows = []
        for priority, (stop_key, stop) in enumerate(result["routes"].items(), start=1):
            rows.append(
                {
                    "Stop #": stop_key,
                    "Priority": str(priority),
                    "Type": stop["type"],
                    "Origin": stop.get("origin", "—"),
                    "Address": stop["address"],
                    "Shipment ID": stop["shipment_id"],
                    "Reason": reasons[stop_key],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

elif page == "🔍 Travel Matrix":
    if not travel:
        st.info("Click **Generate Prioritized Route** in the sidebar to see travel data here.")
    else:
        st.caption(
            "Real drive distance/time between each shipment's own pickup and delivery point - "
            "the only thing Geoapify is asked to compute; the visiting order itself is decided "
            "by this project's own logic, not Geoapify's optimizer."
        )
        rows = []
        for shipment in SAMPLE_SHIPMENTS:
            pickup = shipment.get("pickup")
            if not pickup:
                continue
            leg = travel.get((("pickup", shipment["shipment_id"]), ("delivery", shipment["shipment_id"])))
            rows.append(
                {
                    "Shipment ID": shipment["shipment_id"],
                    "Pickup origin": pickup.get("origin", "—"),
                    "Pickup -> Delivery distance (m)": leg["distance"] if leg else None,
                    "Pickup -> Delivery time (s)": leg["time"] if leg else None,
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No shipments in this run have a separate pickup point.")

elif page == "🗺️ Map":
    if not result:
        st.info("Click **Generate Prioritized Route** in the sidebar to see the map here.")
    else:
        st.caption(
            "🟣 Pickup  🔵 Delivery, numbered in visiting order. Lines are straight connections "
            "between stops, not turn-by-turn road geometry - this project no longer calls "
            "Geoapify's Route Planner (which returned real road geometry) now that stop order is "
            "decided by its own logic."
        )
        try:
            route_map = folium.Map(location=[0, 0], zoom_start=2)
            bounds, path = [], []
            for stop_key, stop in result["routes"].items():
                location = geocode_address(stop["address"])
                lon, lat = location
                bounds.append((lat, lon))
                path.append((lat, lon))
                color, icon = STOP_ICONS.get(stop["type"], ("gray", "info-sign"))
                folium.Marker(
                    [lat, lon],
                    tooltip=f"Stop {stop_key} - {stop['type']} - {stop['shipment_id']}",
                    popup=f"<b>Stop {stop_key}</b><br>{stop['address']}",
                    icon=folium.Icon(color=color, icon=icon, prefix="fa"),
                ).add_to(route_map)

            folium.PolyLine(path, color="#1a73e8", weight=4, opacity=0.7).add_to(route_map)
            if bounds:
                route_map.fit_bounds(bounds)

            st_folium(route_map, use_container_width=True, height=520, key="route_map")
        except GeoapifyError as exc:
            st.warning(f"Couldn't render the map - {exc}")
