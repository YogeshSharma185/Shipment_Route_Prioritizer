"""A visual, non-technical-friendly dashboard for the shipment route pipeline.

This is a thin UI layer on top of the existing project - it does not change
any business logic. It calls the exact same functions main.py uses
(get_travel_matrix -> generate_prioritized_route) and displays the record
data, the travel data, every candidate origin's route, the final selected
route, and a map.

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

from sample_data import AVAILABLE_ORIGINS, SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, geocode_address, get_travel_matrix
from services.route_service import _classify_window, generate_prioritized_route

# folium's default marker icons use Font Awesome 4 names, not "warehouse"/"box" (FA5+).
STOP_ICONS = {"origin": ("green", "home"), "pickup": ("purple", "arrow-up"), "delivery": ("blue", "cube")}
PAGES = ["🏭 Shipments", "📋 Prioritized Route", "📊 Origin Comparison", "🔍 Geoapify Response", "🗺️ Map"]

SHIPMENTS_BY_ID = {shipment["shipment_id"]: shipment for shipment in SAMPLE_SHIPMENTS}
ORIGINS_BY_NAME = {origin["name"]: origin for origin in AVAILABLE_ORIGINS}

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


def _selected_candidate(result):
    return next(candidate for candidate in result["candidates"] if candidate["selected"])


def _stop_key(stop):
    return (stop["type"], stop["shipment_id"])


def _stop_address(stop):
    """The address to physically visit for this stop. Both pickup_address
    and delivery_address are populated on every stop now (see
    route_service._build_routes_output) - "type" says which leg this stop
    actually is, so it's what picks which address applies here, not
    whichever field happens to be non-null.
    """
    return stop["pickup_address"] if stop["type"] == "pickup" else stop["delivery_address"]


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


def build_leg_rows(routes, origin_name, travel):
    """One row per consecutive pair of stops in a route - starting with the
    origin-to-first-stop leg, since the origin isn't part of "routes" itself
    - with the real Geoapify-computed distance/time for that leg. These are
    exactly the numbers that sum to that route's total_miles/total_duration
    (which also includes the origin leg).
    """
    points = [(("origin", origin_name), f"origin {origin_name}")]
    points += [(_stop_key(stop), f"{stop['type']} {stop['shipment_id']}") for stop in routes.values()]

    rows = []
    for (from_key, from_label), (to_key, to_label) in zip(points, points[1:]):
        leg = travel.get((from_key, to_key))
        rows.append(
            {
                "From": from_label,
                "To": to_label,
                "Distance (m)": leg["distance"] if leg else None,
                "Time (s)": leg["time"] if leg else None,
            }
        )
    return rows


def build_priority_reasons(routes, origin_name, shipments_by_id, travel):
    """One reason string per stop, explaining why it landed at that position.
    Starts from the selected origin as the initial "current position"
    (mirrors route_service._prioritize_events, where the very first tie is
    broken by distance from the origin, not an arbitrary ordering). When two
    consecutive stops were genuinely tied on priority (same group/anchor/
    duration), route_service's own tiebreak - real travel distance from
    whichever stop was placed right before it - is what actually broke the
    tie, so that's called out explicitly. UI-only: mirrors
    route_service._classify_window's grouping without duplicating the actual
    sequencing decision.
    """
    reasons = {}
    prev_class, prev_label, prev_key = None, "the selected origin", ("origin", origin_name)
    for stop_key, stop in routes.items():
        event_key = _stop_key(stop)
        shipment = shipments_by_id[stop["shipment_id"]]
        this_class = _classify_window(_stop_priority_window(stop, shipment))
        reason = _describe_event(shipment, stop["type"])

        if this_class == prev_class:
            leg = travel.get((prev_key, event_key))
            distance = f"{leg['distance']}m" if leg else "an unknown distance"
            reason += f" - tied on priority with {prev_label}; {distance} from that stop won the tie"

        reasons[stop_key] = reason
        prev_class, prev_label, prev_key = this_class, f"{stop['shipment_id']} ({stop['type']})", event_key
    return reasons


def render_route_table(routes, origin, shipments_by_id, travel):
    """Renders one route - a leading row for the selected origin (not a
    numbered stop, just where the route starts), then every pickup/delivery
    stop in visiting order - as a table with a Reason column. Shared by the
    Prioritized Route page (the selected route) and every Origin Comparison
    expander (a candidate route), so both stay in perfect sync with no
    duplicated markup.
    """
    reasons = build_priority_reasons(routes, origin["name"], shipments_by_id, travel)
    rows = [
        {
            "Stop #": "Start",
            "Type": "origin",
            "Pickup Address": "—",
            "Delivery Address": "—",
            "Shipment ID": "—",
            "Reason": f"Selected starting warehouse: {origin['name']} ({origin['address']}).",
        }
    ]
    for stop_key, stop in routes.items():
        rows.append(
            {
                "Stop #": stop_key,
                "Type": stop["type"],
                "Pickup Address": stop["pickup_address"] or "—",
                "Delivery Address": stop["delivery_address"] or "—",
                "Shipment ID": stop["shipment_id"],
                "Reason": reasons[stop_key],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Sidebar - the one action in this app
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Run")
    st.caption(
        "Shipment data comes from `sample_data.py`. Edit that file to try different data."
    )
    pickup_count = sum(1 for shipment in SAMPLE_SHIPMENTS if shipment.get("pickup"))
    st.metric("Shipments on record", len(SAMPLE_SHIPMENTS))
    st.caption(
        f"{pickup_count} of these have their own pickup point, and the driver has "
        f"{len(AVAILABLE_ORIGINS)} candidate origins to start from, so the selected route "
        f"will have {len(SAMPLE_SHIPMENTS) + pickup_count} pickup/delivery stops "
        "(one extra per pickup) - plus the selected origin, shown separately above them."
    )
    generate_clicked = st.button("🚀 Generate Prioritized Route", type="primary", use_container_width=True)

    if generate_clicked:
        with st.spinner("Calling the Geoapify Routing Matrix API..."):
            try:
                travel, skipped_keys, raw_response = get_travel_matrix(SAMPLE_SHIPMENTS, AVAILABLE_ORIGINS)
            except GeoapifyError as exc:
                st.session_state["error"] = f"Geoapify request failed: {exc}"
                st.session_state.pop("result", None)
                st.session_state.pop("travel", None)
                st.session_state.pop("raw_response", None)
            else:
                result = generate_prioritized_route(SAMPLE_SHIPMENTS, travel, skipped_keys, AVAILABLE_ORIGINS)
                if "error" in result:
                    st.session_state["error"] = result
                    st.session_state.pop("result", None)
                else:
                    st.session_state["result"] = result
                    st.session_state["travel"] = travel
                    st.session_state["raw_response"] = raw_response
                    st.session_state.pop("error", None)
        # Jump straight to the results page - must be set before the radio
        # widget below is created, since that's what controls its value.
        st.session_state["page"] = "📋 Prioritized Route"

    if st.session_state.get("result"):
        st.success(f"Route ready - selected origin: {st.session_state['result']['selected_origin']}.")
    elif st.session_state.get("error"):
        st.error("Last run failed - see the Prioritized Route page.")
    else:
        st.info("Click **Generate** to run the pipeline.")

    st.divider()
    page = st.radio("View", PAGES, key="page", label_visibility="collapsed")

result = st.session_state.get("result")
travel = st.session_state.get("travel")
raw_response = st.session_state.get("raw_response")
error = st.session_state.get("error")

# ---------------------------------------------------------------------------
# Pages - only the selected one is ever built
# ---------------------------------------------------------------------------

if page == "🏭 Shipments":
    st.subheader("Available origins")
    st.caption(
        "The driver's fixed set of candidate starting warehouses - independent of each "
        "shipment's own pickup point. Every run evaluates all of them and selects the best one."
    )
    origins_df = pd.DataFrame(
        [{"Name": origin["name"], "Address": origin["address"]} for origin in AVAILABLE_ORIGINS]
    )
    st.dataframe(origins_df, use_container_width=True, hide_index=True)

    st.subheader("Shipments")
    pickup_count = sum(1 for shipment in SAMPLE_SHIPMENTS if shipment.get("pickup"))
    st.caption(
        "This is the input data for the run - fixed for this demo, not editable live. "
        f"{len(SAMPLE_SHIPMENTS)} shipments, {pickup_count} with a separate pickup point - "
        f"the selected route will have {len(SAMPLE_SHIPMENTS) + pickup_count} pickup/delivery "
        "stops, since each shipment with its own pickup contributes both a pickup stop and a "
        "delivery stop."
    )
    record_df = pd.DataFrame(
        [
            {
                "Shipment ID": shipment["shipment_id"],
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
        origin = ORIGINS_BY_NAME[_selected_candidate(result)["origin"]]
        col1, col2, col3 = st.columns(3)
        col1.metric("Total distance", f"{result['total_miles']} mi")
        col2.metric("Estimated travel time", result["total_duration"])
        col3.metric("Stops", f"{len(result['routes'])}", help="Pickup/delivery stops only - the selected origin is shown as a separate row above them.")
        st.caption(
            f"Selected origin: **{result['selected_origin']}** (see the Origin Comparison page "
            "for why). "
            f"{len(result['routes'])} stops for {len(SAMPLE_SHIPMENTS)} shipments - shipments with "
            "their own pickup point contribute two stops (pickup + delivery) instead of one."
        )
        render_route_table(result["routes"], origin, SHIPMENTS_BY_ID, travel)

elif page == "📊 Origin Comparison":
    if error:
        message = error if isinstance(error, str) else error.get("error")
        st.error(message)
        if isinstance(error, dict) and "details" in error:
            st.table(pd.DataFrame(error["details"]))
    elif not result:
        st.info("Click **Generate Prioritized Route** in the sidebar to see the origin comparison here.")
    else:
        st.caption(
            "Every available origin is evaluated independently - a full candidate route is "
            "generated starting from each one. The best candidate is then selected by, in "
            "order: fewest time-window violations, fewest constraint violations, lowest total "
            "travel time, lowest total travel distance."
        )
        comparison_rows = [
            {
                "Origin": candidate["origin"],
                "Total Distance": f"{candidate['total_miles']} mi",
                "Total Duration": candidate["total_duration"],
                "Time-Window Violations": candidate["time_window_violations"],
                "Constraint Violations": candidate["constraint_violations"],
                "Score (violations / time / distance)": (
                    f"{candidate['time_window_violations']} / {candidate['constraint_violations']} / "
                    f"{candidate['total_duration']} / {candidate['total_miles']} mi"
                ),
                "Selected": "Yes" if candidate["selected"] else "No",
            }
            for candidate in result["candidates"]
        ]
        st.dataframe(pd.DataFrame(comparison_rows), use_container_width=True, hide_index=True)

        st.subheader("Candidate routes")
        for candidate in result["candidates"]:
            origin = ORIGINS_BY_NAME[candidate["origin"]]
            label = f"{'✅ ' if candidate['selected'] else '⬜ '}{candidate['origin']}"
            with st.expander(label):
                if candidate["violations"]:
                    for violation in candidate["violations"]:
                        st.warning(violation["message"])
                else:
                    st.caption("No time-window violations for this origin.")
                render_route_table(candidate["routes"], origin, SHIPMENTS_BY_ID, travel)

elif page == "🔍 Geoapify Response":
    if not result or not travel:
        st.info("Click **Generate Prioritized Route** in the sidebar to see the Geoapify response here.")
    else:
        st.caption(
            "Real drive distance/time for each leg of the selected route, straight from "
            "Geoapify's Routing Matrix API - the only thing Geoapify is asked to compute. These "
            "numbers sum to the total distance/time shown on the Prioritized Route page."
        )
        selected_origin_name = _selected_candidate(result)["origin"]
        leg_rows = build_leg_rows(result["routes"], selected_origin_name, travel)
        st.dataframe(pd.DataFrame(leg_rows), use_container_width=True, hide_index=True)

        st.subheader("Per-origin processed legs")
        st.caption(
            "One combined Geoapify Matrix API call covers every candidate origin plus every "
            "shipment stop, so the raw response below is genuinely shared across all of them - "
            "each origin's own legs are broken out here instead of repeating that same raw JSON."
        )
        for candidate in result["candidates"]:
            with st.expander(f"{candidate['origin']} - legs"):
                candidate_leg_rows = build_leg_rows(candidate["routes"], candidate["origin"], travel)
                st.dataframe(pd.DataFrame(candidate_leg_rows), use_container_width=True, hide_index=True)

        with st.expander("Raw Geoapify Routing Matrix API response (JSON) - shared across every origin"):
            st.json(raw_response)

elif page == "🗺️ Map":
    if not result:
        st.info("Click **Generate Prioritized Route** in the sidebar to see the map here.")
    else:
        st.caption(
            "🟢 Origin  🟣 Pickup  🔵 Delivery, numbered in visiting order. Lines are straight "
            "connections between stops, not turn-by-turn road geometry - this project no longer "
            "calls Geoapify's Route Planner (which returned real road geometry) now that stop "
            "order and origin selection are decided by its own logic."
        )
        origin_names = [candidate["origin"] for candidate in result["candidates"]]
        default_index = origin_names.index(_selected_candidate(result)["origin"])
        chosen_origin_name = st.selectbox(
            "View route for", origin_names, index=default_index, key="map_origin_choice"
        )
        chosen_candidate = next(
            candidate for candidate in result["candidates"] if candidate["origin"] == chosen_origin_name
        )
        chosen_origin = ORIGINS_BY_NAME[chosen_origin_name]

        try:
            route_map = folium.Map(location=[0, 0], zoom_start=2)
            bounds, path = [], []

            origin_lon, origin_lat = geocode_address(chosen_origin["address"])
            bounds.append((origin_lat, origin_lon))
            path.append((origin_lat, origin_lon))
            color, icon = STOP_ICONS["origin"]
            folium.Marker(
                [origin_lat, origin_lon],
                tooltip=f"Start - origin - {chosen_origin_name}",
                popup=f"<b>Start</b><br>{chosen_origin['address']}",
                icon=folium.Icon(color=color, icon=icon, prefix="fa"),
            ).add_to(route_map)

            for stop_key, stop in chosen_candidate["routes"].items():
                address = _stop_address(stop)
                lon, lat = geocode_address(address)
                bounds.append((lat, lon))
                path.append((lat, lon))
                color, icon = STOP_ICONS.get(stop["type"], ("gray", "info-sign"))
                folium.Marker(
                    [lat, lon],
                    tooltip=f"Stop {stop_key} - {stop['type']} - {stop['shipment_id']}",
                    popup=f"<b>Stop {stop_key}</b><br>{address}",
                    icon=folium.Icon(color=color, icon=icon, prefix="fa"),
                ).add_to(route_map)

            folium.PolyLine(path, color="#1a73e8", weight=4, opacity=0.7).add_to(route_map)
            if bounds:
                route_map.fit_bounds(bounds)

            st_folium(route_map, use_container_width=True, height=520, key="route_map")
        except GeoapifyError as exc:
            st.warning(f"Couldn't render the map - {exc}")
