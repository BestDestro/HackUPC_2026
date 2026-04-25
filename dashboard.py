"""
dashboard.py - Streamlit live dashboard for the logistics simulation.

Run: streamlit run dashboard.py
"""

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import time
import random
import os

from models import Box
from silo import Silo
from shuttle import ShuttleManager
from concurrent_sim import ConcurrentManager, BOX_INTERVAL, run_continuous
from csv_loader import load_silo_from_csv
from warehouse_chatbot import (
    DEFAULT_MODEL,
    ask_gemma,
    build_warehouse_context,
    fallback_answer,
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PAGE CONFIG
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.set_page_config(
    page_title="Hack the Flow - Silo Dashboard",
    page_icon="ðŸ“¦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CUSTOM CSS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
        background-color: #050505;
    }
    .main-title {
        text-align: left;
        color: #ffffff;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 2.2rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        text-transform: uppercase;
        margin-bottom: 0;
        border-bottom: 1px solid #333;
        padding-bottom: 10px;
    }
    .subtitle {
        text-align: left;
        color: #888;
        font-family: 'Inter', sans-serif;
        font-size: 0.9rem;
        letter-spacing: 0.05em;
        margin-top: 10px;
        margin-bottom: 30px;
        text-transform: uppercase;
    }
    div[data-testid="stMetric"] {
        background: #0A0A0A;
        border: 1px solid #222;
        border-radius: 0px;
        padding: 16px;
        box-shadow: none;
    }
    div[data-testid="stMetric"] label {
        color: #777 !important;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: #fff !important;
        font-size: 1.8rem !important;
        font-weight: 400 !important;
        font-family: 'Space Grotesk', sans-serif;
    }
    .phase-badge-input {
        background: transparent;
        border: 1px solid #fff;
        padding: 2px 8px; border-radius: 0px;
        font-size: 0.65rem; font-weight: 500; color: #fff;
        display: inline-block;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .phase-badge-output {
        background: #fff;
        border: 1px solid #fff;
        padding: 2px 8px; border-radius: 0px;
        font-size: 0.65rem; font-weight: 500; color: #000;
        display: inline-block;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .phase-badge-concurrent {
        background: transparent;
        border: 1px solid #888;
        padding: 2px 8px; border-radius: 0px;
        font-size: 0.65rem; font-weight: 500; color: #888;
        display: inline-block;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .stSidebar [data-testid="stSidebarContent"] {
        background: #000000;
        border-right: 1px solid #111;
    }
    hr {
        border-top: 1px solid #222;
    }
</style>
""", unsafe_allow_html=True)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SIMULATION RUNNER (cached)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
@st.cache_data(show_spinner="Running simulation...")
def run_simulation(mode, csv_path, num_incoming, num_destinations, duration_hours, arrival_rate, seed, algo_mode):
    """Run the selected simulation mode and return snapshots."""
    if mode == "Continuous":
        return run_continuous(csv_path, num_destinations=num_destinations,
                              duration_hours=duration_hours, arrival_rate=arrival_rate, verbose=True, algo_mode=algo_mode)
    else:
        random.seed(seed)
        silo = Silo()
        shuttle_mgr = ShuttleManager()
        manager = ConcurrentManager(silo, shuttle_mgr)

        result = load_silo_from_csv(csv_path, silo)
        all_boxes = result["all_boxes"]
        stats = result["stats"]
        manager.all_boxes.update(all_boxes)
        manager.boxes_stored = stats["loaded"]
        if hasattr(manager, "record_initial_state"):
            manager.record_initial_state(all_boxes)

        existing_dests = list(set(b.destination for b in all_boxes.values()))

        incoming = []
        source = "3055769"
        for i in range(num_incoming):
            dest = random.choice(existing_dests[:num_destinations])
            bulk = 90000 + i
            box_id = f"{source}{dest}{bulk:05d}"
            incoming.append(Box.from_id(box_id))

        metrics = manager.run(incoming, verbose=False)
        return metrics



# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CHART BUILDERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DARK_BG = "#050505"
GRID_COLOR = "#1a1a1a"
COLORS = {
    'stored': '#ffffff',
    'retrieved': '#888888',
    'occupancy': '#cccccc',
    'pallets': '#aaaaaa',
    'pending': '#555555',
    'relocations': '#333333',
    'aisle1': '#ffffff',
    'aisle2': '#bbbbbb',
    'aisle3': '#777777',
    'aisle4': '#333333',
    'busy': '#ffffff',
    'idle': '#222222',
}


def chart_layout(fig, title="", height=350):
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#ccc")),
        template="plotly_dark",
        paper_bgcolor=DARK_BG,
        plot_bgcolor=DARK_BG,
        height=height,
        margin=dict(l=50, r=20, t=40, b=40),
        font=dict(family="Inter", color="#aaa"),
        xaxis=dict(gridcolor=GRID_COLOR, title="Time (min)"),
        yaxis=dict(gridcolor=GRID_COLOR),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def build_throughput_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['boxes_stored'], name='Stored',
        line=dict(color=COLORS['stored'], width=2),
        fill='tozeroy', fillcolor='rgba(0,184,148,0.1)'))
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['boxes_retrieved'], name='Retrieved',
        line=dict(color=COLORS['retrieved'], width=2),
        fill='tozeroy', fillcolor='rgba(225,112,85,0.1)'))
    return chart_layout(fig, "Throughput: Boxes Stored vs Retrieved")


def build_occupancy_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['occupancy_pct'], name='Occupancy %',
        line=dict(color=COLORS['occupancy'], width=3),
        fill='tozeroy', fillcolor='rgba(102,126,234,0.15)'))
    chart_layout(fig, "Silo Occupancy (%)")
    fig.update_yaxes(title="Occupancy %")
    return fig


def build_pallets_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['pallets_completed'], name='Completed',
        line=dict(color=COLORS['pallets'], width=2.5)))
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['active_pallets'], name='Active (in progress)',
        line=dict(color='#e17055', width=1.5, dash='dot')))
    return chart_layout(fig, "Pallet Completion Over Time")


def build_aisle_chart(df):
    fig = go.Figure()
    for i, color_key in enumerate(['aisle1', 'aisle2', 'aisle3', 'aisle4'], 1):
        fig.add_trace(go.Scatter(
            x=df['time_min'], y=df[f'aisle_{i}'], name=f'Aisle {i}',
            line=dict(color=COLORS[color_key], width=2),
            stackgroup='one'))
    return chart_layout(fig, "Per-Aisle Box Distribution (Stacked)")


def build_shuttle_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['shuttles_busy'], name='Busy',
        line=dict(color=COLORS['busy'], width=2),
        fill='tozeroy', fillcolor='rgba(225,112,85,0.2)'))
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['shuttles_idle'], name='Idle',
        line=dict(color=COLORS['idle'], width=2),
        fill='tozeroy', fillcolor='rgba(0,184,148,0.1)'))
    chart_layout(fig, "Shuttle Utilization (Busy vs Idle)")
    fig.update_yaxes(title="# Shuttles", range=[0, 34])
    return fig


def build_pending_chart(df):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['pending_input'], name='Pending',
        line=dict(color=COLORS['pending'], width=1),
        fill='tozeroy', fillcolor='rgba(255,255,255,0.05)'))
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['relocations'], name='Relocations (cumul)',
        line=dict(color=COLORS['relocations'], width=1, dash='dot'),
        yaxis='y2'))
    chart_layout(fig, "Input Queue & Relocations")
    fig.update_layout(
        yaxis2=dict(title="Relocations", overlaying='y', side='right',
                    gridcolor=GRID_COLOR, color='#888'))
    return fig


TRACE_COLORS = {
    "INITIAL": "#95a5a6",
    "STORE": "#00b894",
    "RETRIEVE": "#e17055",
    "RELOCATE": "#a29bfe",
    "RETRIEVE_BLOCKER": "#fdcb6e",
}


def build_trace_context(trace_df, mode, selected_id, current_time):
    id_col = "box_id" if mode == "Box" else "shuttle_id"
    focus = trace_df[trace_df[id_col] == selected_id].sort_values("start_time")
    if focus.empty:
        return ""

    active = focus[
        (focus["start_time"] <= current_time) &
        (focus["end_time"] >= current_time) &
        (focus["duration"] > 0)
    ]
    if not active.empty:
        event = active.iloc[-1]
        state = "currently moving"
    else:
        past = focus[focus["end_time"] <= current_time]
        if not past.empty:
            event = past.iloc[-1]
            state = "last completed movement"
        else:
            event = focus.iloc[0]
            state = "next scheduled movement"

    return (
        f"- Focus mode: {mode}\n"
        f"- Selected id: {selected_id}\n"
        f"- Route state: {state}\n"
        f"- Event type: {event['event_type']}\n"
        f"- Box id: {event['box_id']}\n"
        f"- Destination: {event['destination']}\n"
        f"- Shuttle: {event['shuttle_id']}\n"
        f"- From: {event['from_position']} to {event['to_position']}\n"
        f"- X route box: {event['box_from_x']} -> {event['box_to_x']}\n"
        f"- X route shuttle: {event['shuttle_from_x']} -> {event['shuttle_to_x']}\n"
        f"- Time window: {event['start_min']:.2f} to {event['end_min']:.2f} min\n"
        f"- Reason: {event['reason']}\n"
        f"- Decision: {event['decision']}"
    )


def get_shuttle_frame(trace_df, current_time):
    rows = []
    for aisle in range(1, 5):
        for y in range(1, 9):
            shuttle_id = f"A{aisle}_Y{y}"
            events = trace_df[
                (trace_df["shuttle_id"] == shuttle_id) &
                (trace_df["event_type"] != "INITIAL")
            ].sort_values("start_time")

            active = events[
                (events["start_time"] <= current_time) &
                (events["end_time"] >= current_time) &
                (events["duration"] > 0)
            ]
            if not active.empty:
                event = active.iloc[-1]
                progress = (current_time - event["start_time"]) / max(event["duration"], 0.001)
                x = event["shuttle_from_x"] + (event["shuttle_to_x"] - event["shuttle_from_x"]) * progress
                state = "MOVING"
            else:
                past = events[events["end_time"] <= current_time]
                if not past.empty:
                    event = past.iloc[-1]
                    x = event["shuttle_to_x"]
                else:
                    event = None
                    x = 0
                state = "IDLE"

            lane = (aisle - 1) * 8 + y
            if event is None:
                event_type = "IDLE"
                box_id = ""
                destination = ""
                decision = "Shuttle waiting at the head."
                reason = "No movement is assigned at the current simulation time."
            else:
                event_type = event["event_type"]
                box_id = event["box_id"]
                destination = event["destination"]
                decision = event["decision"]
                reason = event["reason"]

            rows.append({
                "shuttle_id": shuttle_id,
                "aisle": aisle,
                "y": y,
                "lane": lane,
                "lane_label": f"A{aisle}-Y{y}",
                "x": x,
                "state": state,
                "event_type": event_type,
                "box_id": box_id,
                "destination": destination,
                "decision": decision,
                "reason": reason,
            })
    return pd.DataFrame(rows)


def build_live_shuttle_map(trace_df, current_time, selected_shuttle=None):
    shuttle_df = get_shuttle_frame(trace_df, current_time)
    marker_colors = shuttle_df["state"].map({
        "MOVING": "#00cec9",
        "IDLE": "#636e72",
    }).fillna("#667eea")
    marker_sizes = [
        20 if sid == selected_shuttle else (15 if state == "MOVING" else 11)
        for sid, state in zip(shuttle_df["shuttle_id"], shuttle_df["state"])
    ]
    marker_symbols = [
        "diamond" if sid == selected_shuttle else "circle"
        for sid in shuttle_df["shuttle_id"]
    ]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=shuttle_df["x"],
        y=shuttle_df["lane"],
        mode="markers+text",
        marker=dict(
            color=marker_colors,
            size=marker_sizes,
            symbol=marker_symbols,
            line=dict(color="#ffffff", width=1),
        ),
        text=shuttle_df["shuttle_id"],
        textposition="top center",
        customdata=shuttle_df[[
            "shuttle_id",
            "state",
            "event_type",
            "box_id",
            "destination",
            "decision",
        ]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "X=%{x:.1f}<br>"
            "State=%{customdata[1]}<br>"
            "Event=%{customdata[2]}<br>"
            "Box=%{customdata[3]}<br>"
            "Dest=%{customdata[4]}<br>"
            "%{customdata[5]}<extra></extra>"
        ),
        selected=dict(marker=dict(size=22, color="#fdcb6e")),
        unselected=dict(marker=dict(opacity=0.75)),
    ))

    for aisle in range(1, 5):
        fig.add_hrect(
            y0=(aisle - 1) * 8 + 0.5,
            y1=aisle * 8 + 0.5,
            fillcolor="rgba(102,126,234,0.06)" if aisle % 2 else "rgba(0,206,201,0.04)",
            line_width=0,
            layer="below",
        )
        fig.add_annotation(
            x=61,
            y=(aisle - 1) * 8 + 4.5,
            text=f"Aisle {aisle}",
            showarrow=False,
            font=dict(color="#aaa", size=11),
        )

    chart_layout(fig, "Live Shuttle Map - click a shuttle to inspect it", height=520)
    fig.update_xaxes(title="X coordinate", range=[-2, 64], dtick=5)
    fig.update_yaxes(
        title="Shuttle lane",
        tickmode="array",
        tickvals=shuttle_df["lane"].tolist(),
        ticktext=shuttle_df["lane_label"].tolist(),
        autorange="reversed",
    )
    fig.update_layout(clickmode="event+select", showlegend=False)
    return fig, shuttle_df


def extract_selected_shuttle(plotly_state):
    try:
        selection = plotly_state.get("selection", {})
    except AttributeError:
        selection = getattr(plotly_state, "selection", {})
    points = selection.get("points", []) if selection else []
    if not points:
        return None
    customdata = points[0].get("customdata")
    if isinstance(customdata, (list, tuple)) and customdata:
        return customdata[0]
    return None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SIDEBAR
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
with st.sidebar:
    st.markdown("### Simulation Parameters")

    sim_mode = st.radio("Operation Mode", ["Concurrent (Finite)", "Continuous (Infinite Flow)"])
    algo_mode = st.radio("Algorithm Strategy", ["Optimized (Parallel + Lookahead)", "Naive (Legacy)"])

    csv_path = st.text_input("CSV File", value="silo-semi-empty.csv")
    num_destinations = st.slider("Destinations", 5, 80, 20)

    if sim_mode == "Concurrent (Finite)":
        num_incoming = st.slider("Incoming Boxes", 200, 5000, 1000, step=100)
        duration_hours = 0.0
        arrival_rate = 0
    else:
        num_incoming = 0
        duration_hours = st.slider("Duration (Hours)", 0.5, 8.0, 2.0, step=0.5)
        arrival_rate = st.slider("Arrival Rate (boxes/h)", 500, 3000, 1000, step=100)

    seed = st.number_input("Random Seed", value=42, step=1)
    playback_speed = st.slider("Playback Speed", 1, 50, 10, help="Snapshots per second during playback")

    st.markdown("---")
    run_btn = st.button("Run Simulation", type="primary", width='stretch')
    st.markdown("---")
    
    st.markdown("**Algorithms Info:**")
    if "Optimized" in algo_mode:
        st.markdown("- **Lookahead:** Dynamic (â‰¥8 boxes)\n- **Output:** 32 Shuttles Parallel\n- **Gate:** Competitive\n- **State:** Hash Maps O(1)")
    else:
        st.markdown("- **Lookahead:** Strict (12 boxes)\n- **Output:** Sequential (1 Shuttle max/tick)\n- **Gate:** Occupancy > 50%\n- **State:** Hash Maps O(1)")

    st.markdown("---")
    st.markdown("### Warehouse Chat")
    ai_model = st.text_input("Model", value=DEFAULT_MODEL)
    api_key_input = st.text_input(
        "API key",
        value="",
        type="password",
        help="Uses MLH_GEMMA_API_KEY or GEMINI_API_KEY if left empty.",
    )
    detected_api_key = bool(
        api_key_input
        or os.getenv("MLH_GEMMA_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )
    if detected_api_key:
        st.success("API key detected")
    else:
        st.warning("No API key detected")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MAIN DASHBOARD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown('<h1 class="main-title">Hack the Flow - Silo Dashboard</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Real-time visualization of the logistics simulation</p>',
            unsafe_allow_html=True)

# Check if CSV exists
if not os.path.exists(csv_path):
    st.error(f"CSV file not found: {csv_path}")
    st.stop()

# Run or use cached simulation
if run_btn or 'sim_result' not in st.session_state:
    with st.spinner(f"Running {sim_mode}..."):
        mode_str = "Continuous" if "Continuous" in sim_mode else "Concurrent"
        algo_str = "Naive" if "Naive" in algo_mode else "Optimized"
        result = run_simulation(mode_str, csv_path, num_incoming, num_destinations, duration_hours, arrival_rate, seed, algo_str)
        st.session_state.sim_result = result
        st.session_state.playback_idx = 0
else:
    result = st.session_state.sim_result

snapshots = result.get('snapshots', [])
if not snapshots:
    st.warning("No snapshots collected. Run the simulation first.")
    st.stop()

df = pd.DataFrame(snapshots)

# â”€â”€â”€ LIVE PLAYBACK â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("---")

# Playback controls
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 3, 1])
with col_ctrl1:
    play_btn = st.button("â–¶ Play", width='stretch')
with col_ctrl3:
    reset_btn = st.button("â†º Reset", width='stretch')

with col_ctrl2:
    frame_idx = st.slider("Timeline", 0, len(df) - 1,
                           st.session_state.get('playback_idx', len(df) - 1),
                           key="timeline_slider")

if reset_btn:
    st.session_state.playback_idx = 0
    st.rerun()

# Get current frame data
current = df.iloc[frame_idx]
df_up_to = df.iloc[:frame_idx + 1]

# Phase badge
t = current['time']
has_pending = current['pending_input'] > 0
has_retrievals = current['boxes_retrieved'] > 0
if has_pending and has_retrievals:
    phase_html = '<span class="phase-badge-concurrent">CONCURRENT I/O</span>'
elif has_pending or current['boxes_stored'] < result.get('boxes_arrived', 0):
    phase_html = '<span class="phase-badge-input">INPUT PHASE</span>'
else:
    phase_html = '<span class="phase-badge-output">OUTPUT ONLY</span>'

# â”€â”€â”€ KPI ROW â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown(f"#### Sim Time: **{current['time_min']:.1f} min** &nbsp; {phase_html}",
            unsafe_allow_html=True)

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Boxes Stored", f"{int(current['boxes_stored']):,}")
k2.metric("Boxes Retrieved", f"{int(current['boxes_retrieved']):,}")
k3.metric("Pallets Done", int(current['pallets_completed']))
k4.metric("Occupancy", f"{current['occupancy_pct']:.1f}%")
k5.metric("Pending Input", int(current['pending_input']))
k6.metric("Relocations", int(current['relocations']))

trace_events = result.get("trace_events", [])
trace_df = pd.DataFrame(trace_events) if trace_events else pd.DataFrame()
selected_trace_context = ""

st.markdown("---")
st.markdown("### Live Shuttle Movement")

if trace_df.empty:
    st.info("This run does not expose live shuttle traces yet.")
else:
    current_time = float(current["time"])

    if "selected_shuttle_id" not in st.session_state:
        st.session_state.selected_shuttle_id = "None"
    if "selected_box_id" not in st.session_state:
        st.session_state.selected_box_id = "None"

    live_col, focus_col = st.columns([3, 2])

    with live_col:
        focused_shuttle = st.session_state.get("selected_shuttle_id")
        if focused_shuttle == "None":
            focused_shuttle = None

        shuttle_map, shuttle_frame = build_live_shuttle_map(
            trace_df,
            current_time,
            selected_shuttle=focused_shuttle,
        )
        plotly_state = st.plotly_chart(
            shuttle_map,
            width='stretch',
            key="live_shuttle_map",
            on_select="rerun",
            selection_mode="points",
        )
        clicked_shuttle = extract_selected_shuttle(plotly_state)
        if clicked_shuttle and clicked_shuttle != st.session_state.get("selected_shuttle_id"):
            st.session_state.selected_shuttle_id = clicked_shuttle
            st.rerun()

    with focus_col:
        shuttle_options = ["None"] + sorted(shuttle_frame["shuttle_id"].tolist())
        current_shuttle_value = st.session_state.get("selected_shuttle_id", "None")
        if current_shuttle_value not in shuttle_options:
            current_shuttle_value = "None"
        selected_shuttle_value = st.selectbox(
            "Focus shuttle for chat",
            shuttle_options,
            index=shuttle_options.index(current_shuttle_value),
            key="selected_shuttle_id",
            help="Search or choose a shuttle. Clicking the map also updates this focus.",
        )

        box_candidates = sorted(
            box_id
            for box_id in trace_df.loc[trace_df["event_type"] != "INITIAL", "box_id"].dropna().unique().tolist()
            if box_id
        )
        box_options = ["None"] + box_candidates
        current_box_value = st.session_state.get("selected_box_id", "None")
        if current_box_value not in box_options:
            current_box_value = "None"
        selected_box_value = st.selectbox(
            "Focus box for chat",
            box_options,
            index=box_options.index(current_box_value),
            key="selected_box_id",
            help="Search or choose a box to ask why it moved or where it is going.",
        )

        if selected_shuttle_value != "None":
            shuttle_row = shuttle_frame[shuttle_frame["shuttle_id"] == selected_shuttle_value]
            if not shuttle_row.empty:
                shuttle_info = shuttle_row.iloc[0]
                st.caption("Current shuttle focus")
                st.write(f"- Shuttle: `{shuttle_info['shuttle_id']}`")
                st.write(f"- State: `{shuttle_info['state']}`")
                st.write(f"- X position: `{shuttle_info['x']:.1f}`")
                if shuttle_info["box_id"]:
                    st.write(f"- Box: `{shuttle_info['box_id']}`")
                if shuttle_info["destination"]:
                    st.write(f"- Destination: `{shuttle_info['destination']}`")

    focus_parts = []
    if selected_shuttle_value != "None":
        shuttle_context = build_trace_context(
            trace_df,
            "Shuttle",
            selected_shuttle_value,
            current_time,
        )
        if shuttle_context:
            focus_parts.append(shuttle_context)
    if selected_box_value != "None":
        box_context = build_trace_context(
            trace_df,
            "Box",
            selected_box_value,
            current_time,
        )
        if box_context:
            focus_parts.append(box_context)

    selected_trace_context = "\n\n".join(focus_parts)
    if selected_trace_context:
        with st.expander("Selected live movement context", expanded=False):
            st.code(selected_trace_context)

# â”€â”€â”€ CHARTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(build_throughput_chart(df_up_to), width='stretch')
with col2:
    st.plotly_chart(build_occupancy_chart(df_up_to), width='stretch')

col3, col4 = st.columns(2)
with col3:
    st.plotly_chart(build_pallets_chart(df_up_to), width='stretch')
with col4:
    st.plotly_chart(build_aisle_chart(df_up_to), width='stretch')

col5, col6 = st.columns(2)
with col5:
    st.plotly_chart(build_shuttle_chart(df_up_to), width='stretch')
with col6:
    st.plotly_chart(build_pending_chart(df_up_to), width='stretch')

# â”€â”€â”€ LIVE PLAYBACK LOOP â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
if play_btn:
    start_idx = st.session_state.get('playback_idx', 0)
    kpi_placeholder = st.empty()
    chart_placeholder = st.empty()
    progress_bar = st.progress(start_idx / len(df))

    for i in range(start_idx, len(df)):
        st.session_state.playback_idx = i
        progress_bar.progress(i / (len(df) - 1))
        time.sleep(1.0 / playback_speed)

    st.session_state.playback_idx = len(df) - 1
    st.rerun()

# â”€â”€â”€ FINAL SUMMARY â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
st.markdown("---")
with st.expander("Final Simulation Summary", expanded=False):
    summary_cols = st.columns(3)
    with summary_cols[0]:
        st.markdown("**Throughput**")
        st.write(f"- Boxes arrived: {result.get('boxes_arrived', 'N/A')}")
        st.write(f"- Boxes stored: {result.get('boxes_stored', 'N/A')}")
        st.write(f"- Boxes retrieved: {result.get('boxes_retrieved', 'N/A')}")
    with summary_cols[1]:
        st.markdown("**Pallets**")
        st.write(f"- Completed: {result.get('pallets_completed', 'N/A')}")
        st.write(f"- Full pallet %: {result.get('full_pallet_pct', 'N/A')}")
        st.write(f"- Avg time/pallet: {result.get('avg_time_per_pallet', 'N/A')}")
    with summary_cols[2]:
        st.markdown("**System**")
        st.write(f"- Relocations: {result.get('total_relocations', 'N/A')}")
        st.write(f"- Remaining in silo: {result.get('remaining_in_silo', 'N/A')}")
        st.write(f"- Shuttle max time: {result.get('shuttle_max_time', 'N/A')}")

# Warehouse chat
st.markdown("---")
st.markdown("### Warehouse Chat")
st.markdown("Ask about the warehouse state, a shuttle, or a box you have selected above.")

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about the warehouse, a shuttle, or a box."):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking through the warehouse state..."):
            algorithm_name = "Naive" if "Naive" in algo_mode else "Optimized"
            api_key = (
                api_key_input
                or os.getenv("MLH_GEMMA_API_KEY")
                or os.getenv("GEMINI_API_KEY")
            )
            context = build_warehouse_context(
                result,
                current.to_dict(),
                algorithm_name,
                focus_context=selected_trace_context,
            )
            try:
                answer = ask_gemma(prompt, context, api_key, model=ai_model)
            except Exception as exc:
                fallback = fallback_answer(prompt, context, algorithm_name)
                answer = (
                    f"_API unavailable, using local explanation. Detail: {exc}_\n\n"
                    f"{fallback}"
                )

            st.markdown(answer)
            st.session_state.chat_messages.append({"role": "assistant", "content": answer})
