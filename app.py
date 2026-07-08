"""A visual, non-technical-friendly dashboard for the shipment route pipeline.

This is a thin UI layer on top of the existing project - it does not change
any business logic. It calls the exact same functions main.py uses
(get_geoapify_route -> generate_prioritized_route) and displays the record
data, the raw Geoapify response, the final prioritized route, and a map.

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

from sample_data import SAMPLE_ORIGIN_ADDRESS, SAMPLE_SHIPMENTS
from services.geoapify_service import GeoapifyError, get_geoapify_route
from services.route_service import _classify, _extract_job_distances, generate_prioritized_route

# folium's default marker icons use Font Awesome 4 names, not "warehouse"/"box" (FA5+).
STOP_ICONS = {"origin": ("green", "home"), "drop": ("blue", "cube"), "end": ("red", "home")}
PAGES = ["🏭 Warehouse & Deliveries", "📋 Prioritized Route", "🔍 Geoapify Response", "🗺️ Map"]

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


def format_time_window(shipment):
    time_window = shipment.get("time_window")
    if not time_window:
        return "No constraint"
    start, end = time_window.get("start", "—"), time_window.get("end", "—")
    return f"{start} - {end}"


def extract_job_times(geoapify_response):
    """Map each job's id to its arrival time (seconds since route start), read
    directly off its action - Geoapify already computes this per job, no
    summation needed (unlike distance, which only has per-leg values).
    UI-only helper, kept here rather than in route_service.py.
    """
    times = {}
    try:
        actions = geoapify_response["features"][0]["properties"].get("actions", [])
        for action in actions:
            if action.get("type") == "job" and "job_id" in action:
                times[action["job_id"]] = action.get("start_time", 0)
    except (KeyError, IndexError, TypeError):
        pass
    return times


def _describe_shipment(shipment):
    time_window = shipment.get("time_window") or {}
    start, end = time_window.get("start"), time_window.get("end")
    if start and end:
        return f"Strict window {start}-{end}"
    if end:
        return f"Deadline {end}"
    if start:
        return f"Start-only {start} (no deadline, can go any time after)"
    return "No time constraint"


def build_priority_reasons(sorted_shipments, job_distances):
    """One reason string per shipment, in sorted order, explaining why it
    landed at that position. When two consecutive shipments were genuinely
    tied on time (same group/anchor/duration), the Geoapify distance is what
    actually broke the tie - so that's called out explicitly.
    """
    reasons = {}
    prev_key, prev_id = None, None
    for shipment in sorted_shipments:
        key = _classify(shipment)
        reason = _describe_shipment(shipment)
        if key == prev_key:
            distance = job_distances.get(shipment["shipment_id"], 0)
            prev_distance = job_distances.get(prev_id, 0)
            comparison = "closer" if distance < prev_distance else "farther"
            reason += f" - same as {prev_id}, {comparison} stop wins the tie"
        reasons[shipment["shipment_id"]] = reason
        prev_key, prev_id = key, shipment["shipment_id"]
    return reasons


# ---------------------------------------------------------------------------
# Sidebar - the one action in this app
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Run")
    st.caption(
        "Warehouse and shipment data come from `sample_data.py`. Edit that file to try different data."
    )
    st.metric("Shipments on record", len(SAMPLE_SHIPMENTS))
    generate_clicked = st.button("🚀 Generate Prioritized Route", type="primary", use_container_width=True)

    if generate_clicked:
        with st.spinner("Calling Geoapify Route Planner..."):
            try:
                geoapify_response = get_geoapify_route(SAMPLE_ORIGIN_ADDRESS, SAMPLE_SHIPMENTS)
            except GeoapifyError as exc:
                st.session_state["error"] = f"Geoapify request failed: {exc}"
                st.session_state.pop("result", None)
                st.session_state.pop("geoapify_response", None)
            else:
                result = generate_prioritized_route(SAMPLE_SHIPMENTS, geoapify_response, SAMPLE_ORIGIN_ADDRESS)
                if "error" in result:
                    st.session_state["error"] = result
                    st.session_state.pop("result", None)
                else:
                    st.session_state["result"] = result
                    st.session_state["geoapify_response"] = geoapify_response
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
geoapify_response = st.session_state.get("geoapify_response")
error = st.session_state.get("error")

# ---------------------------------------------------------------------------
# Pages - only the selected one is ever built
# ---------------------------------------------------------------------------

if page == "🏭 Warehouse & Deliveries":
    st.caption("This is the input data for the run - fixed for this demo, not editable live.")
    st.subheader("Warehouse (origin & return point)")
    st.write(SAMPLE_ORIGIN_ADDRESS)

    st.subheader("Deliveries")
    record_df = pd.DataFrame(
        [
            {
                "Shipment ID": s["shipment_id"],
                "Address": s["address"],
                "Time Window": format_time_window(s),
            }
            for s in SAMPLE_SHIPMENTS
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

        shipments_by_id = {s["shipment_id"]: s for s in SAMPLE_SHIPMENTS}
        sorted_shipments = [
            shipments_by_id[stop["shipment_id"]] for stop in result["routes"].values() if stop["type"] == "drop"
        ]
        job_distances = _extract_job_distances(geoapify_response)
        reasons = build_priority_reasons(sorted_shipments, job_distances)

        priority = 0
        rows = []
        for stop_key, stop in result["routes"].items():
            if stop["type"] == "drop":
                priority += 1
                rows.append(
                    {
                        "Stop #": stop_key,
                        "Priority": str(priority),
                        "Address": stop["address"],
                        "Shipment ID": stop["shipment_id"],
                        "Type": stop["type"],
                        "Reason": reasons[stop["shipment_id"]],
                    }
                )
            else:
                rows.append(
                    {
                        "Stop #": stop_key,
                        "Priority": "-",
                        "Address": stop["address"],
                        "Shipment ID": stop["shipment_id"] or "-",
                        "Type": stop["type"],
                        "Reason": "Warehouse (route start)" if stop["type"] == "origin" else "Warehouse (route end)",
                    }
                )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

elif page == "🔍 Geoapify Response":
    if not geoapify_response:
        st.info("Click **Generate Prioritized Route** in the sidebar to see Geoapify's response here.")
    else:
        st.caption("Distance and time exactly as Geoapify's Route Planner returned them, per shipment.")
        job_distances = _extract_job_distances(geoapify_response)
        job_times = extract_job_times(geoapify_response)
        detail_rows = []
        for shipment in SAMPLE_SHIPMENTS:
            detail_rows.append(
                {
                    "Shipment ID": shipment["shipment_id"],
                    "Address": shipment["address"],
                    "Distance (m)": job_distances.get(shipment["shipment_id"]),
                    "Time (s)": job_times.get(shipment["shipment_id"]),
                }
            )
        st.dataframe(pd.DataFrame(detail_rows), use_container_width=True, hide_index=True)

        with st.expander("Raw Geoapify Route Planner JSON response"):
            st.json(geoapify_response)

elif page == "🗺️ Map":
    if not (result and geoapify_response):
        st.info("Click **Generate Prioritized Route** in the sidebar to see the map here.")
    else:
        st.caption("🟢 Warehouse (start)  🔵 Delivery stop, numbered in priority order  🔴 Warehouse (end)")
        try:
            properties = geoapify_response["features"][0]["properties"]
            geometry = geoapify_response["features"][0]["geometry"]
            waypoints = properties.get("waypoints", [])
            actions = properties.get("actions", [])

            # Map each job_id (and the start) to its real geocoded location, reusing
            # the coordinates Geoapify already resolved - no extra API calls needed.
            # Note: the "end" action has no waypoint_index of its own, so it's
            # skipped here and handled below by reusing the origin's location.
            location_by_job_id = {}
            origin_location = None
            for action in actions:
                waypoint_index = action.get("waypoint_index")
                if waypoint_index is None:
                    continue
                waypoint = waypoints[waypoint_index]
                if action.get("type") == "start":
                    origin_location = waypoint["location"]
                elif action.get("type") == "job" and "job_id" in action:
                    location_by_job_id[action["job_id"]] = waypoint["location"]

            route_map = folium.Map(location=[0, 0], zoom_start=2)
            bounds = []

            for line in geometry.get("coordinates", []):
                path = [(lat, lon) for lon, lat in line]
                bounds.extend(path)
                folium.PolyLine(path, color="#1a73e8", weight=5, opacity=0.8).add_to(route_map)

            for stop_key, stop in result["routes"].items():
                location = location_by_job_id.get(stop["shipment_id"]) if stop["type"] == "drop" else origin_location
                if not location:
                    continue
                lon, lat = location
                bounds.append((lat, lon))
                color, icon = STOP_ICONS.get(stop["type"], ("gray", "info-sign"))
                label = stop["shipment_id"] or "Warehouse"
                folium.Marker(
                    [lat, lon],
                    tooltip=f"Stop {stop_key} - {stop['type']} - {label}",
                    popup=f"<b>Stop {stop_key}</b><br>{stop['address']}",
                    icon=folium.Icon(color=color, icon=icon, prefix="fa"),
                ).add_to(route_map)

            if bounds:
                route_map.fit_bounds(bounds)

            st_folium(route_map, use_container_width=True, height=520, key="route_map")
        except (KeyError, IndexError, TypeError) as exc:
            st.warning(f"Couldn't render the map - unexpected Geoapify response shape ({exc}).")
