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
from pathlib import Path

from models import Box
from silo import Silo
from shuttle import ShuttleManager
from concurrent_sim import (
    ConcurrentManager,
    available_algorithm_configs,
    build_algorithms,
)
from csv_loader import load_silo_from_csv
from warehouse_chatbot import (
    DEFAULT_MODEL,
    ask_gemma,
    build_warehouse_context,
    fallback_answer,
)

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hack the Flow - Silo Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }
    .main-title {
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0;
    }
    .subtitle {
        text-align: center;
        color: #888;
        font-size: 1rem;
        margin-top: -10px;
        margin-bottom: 20px;
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid #333;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3);
    }
    div[data-testid="stMetric"] label {
        color: #aaa !important;
        font-size: 0.85rem !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    .phase-badge-input {
        background: linear-gradient(135deg, #00b894, #00cec9);
        padding: 4px 12px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 600; color: #fff;
        display: inline-block;
    }
    .phase-badge-output {
        background: linear-gradient(135deg, #e17055, #d63031);
        padding: 4px 12px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 600; color: #fff;
        display: inline-block;
    }
    .phase-badge-concurrent {
        background: linear-gradient(135deg, #667eea, #764ba2);
        padding: 4px 12px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 600; color: #fff;
        display: inline-block;
    }
    .stSidebar [data-testid="stSidebarContent"] {
        background: linear-gradient(180deg, #0f0c29, #302b63, #24243e);
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION RUNNER (cached)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Running simulation...")
def run_simulation(csv_path, num_incoming, num_destinations, seed, algorithm_config):
    """Run the concurrent simulation and return snapshots."""
    random.seed(seed)
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    storage_alg, pallet_alg, retrieval_alg = build_algorithms(algorithm_config)
    manager = ConcurrentManager(
        silo,
        shuttle_mgr,
        storage_algorithm=storage_alg,
        pallet_algorithm=pallet_alg,
        retrieval_algorithm=retrieval_alg,
    )

    # Load CSV
    result = load_silo_from_csv(csv_path, silo)
    all_boxes = result["all_boxes"]
    stats = result["stats"]
    manager.all_boxes.update(all_boxes)
    manager.boxes_stored = stats["loaded"]
    manager.record_initial_state(all_boxes)

    # Get existing destinations
    existing_dests = sorted(set(b.destination for b in all_boxes.values()))

    # Generate incoming boxes
    incoming = []
    source = "3055769"
    for i in range(num_incoming):
        dest = random.choice(existing_dests[:num_destinations])
        bulk = 90000 + i
        box_id = f"{source}{dest}{bulk:05d}"
        incoming.append(Box.from_id(box_id))

    # Run
    metrics = manager.run(incoming, verbose=False)
    return metrics


TRACE_COLORS = {
    "INITIAL": "#95a5a6",
    "STORE": "#00b894",
    "RETRIEVE": "#e17055",
    "RELOCATE": "#a29bfe",
    "RETRIEVE_BLOCKER": "#fdcb6e",
}

PROJECT_STORY_PATH = Path(__file__).with_name("PROJECT_STORY.md")


def load_project_story():
    """Load the shared project documentation used by Streamlit and Devpost."""
    if PROJECT_STORY_PATH.exists():
        return PROJECT_STORY_PATH.read_text(encoding="utf-8")
    return (
        "# Hack the Flow\n\n"
        "Real-time warehouse flow optimizer that schedules 32 shuttles to store, "
        "retrieve, and relocate boxes efficiently in automated silos."
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHART BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
DARK_BG = "#0e1117"
GRID_COLOR = "#1e2130"
COLORS = {
    'stored': '#00b894',
    'retrieved': '#e17055',
    'occupancy': '#667eea',
    'pallets': '#fdcb6e',
    'pending': '#ff7675',
    'relocations': '#a29bfe',
    'aisle1': '#00cec9',
    'aisle2': '#6c5ce7',
    'aisle3': '#fd79a8',
    'aisle4': '#ffeaa7',
    'busy': '#e17055',
    'idle': '#00b894',
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
        line=dict(color=COLORS['pending'], width=2),
        fill='tozeroy', fillcolor='rgba(255,118,117,0.15)'))
    fig.add_trace(go.Scatter(
        x=df['time_min'], y=df['relocations'], name='Relocations (cumul)',
        line=dict(color=COLORS['relocations'], width=1.5, dash='dot'),
        yaxis='y2'))
    chart_layout(fig, "Input Queue & Relocations")
    fig.update_layout(
        yaxis2=dict(title="Relocations", overlaying='y', side='right',
                    gridcolor=GRID_COLOR, color='#a29bfe'))
    return fig


def build_trace_timeline_chart(trace_df, mode, selected_id, current_time):
    id_col = "box_id" if mode == "Box" else "shuttle_id"
    x_from_col = "box_from_x" if mode == "Box" else "shuttle_from_x"
    x_to_col = "box_to_x" if mode == "Box" else "shuttle_to_x"
    focus = trace_df[trace_df[id_col] == selected_id].sort_values("start_time")

    fig = go.Figure()
    for _, event in focus.iterrows():
        color = TRACE_COLORS.get(event["event_type"], "#667eea")
        name = event["event_type"]
        if event["event_type"] == "INITIAL":
            fig.add_trace(go.Scatter(
                x=[event["start_min"]],
                y=[event[x_to_col]],
                mode="markers",
                marker=dict(color=color, size=9),
                name=name,
                text=[event["decision"]],
                hovertemplate="t=%{x:.2f} min<br>X=%{y}<br>%{text}<extra></extra>",
                showlegend=False,
            ))
            continue

        fig.add_trace(go.Scatter(
            x=[event["start_min"], event["end_min"]],
            y=[event[x_from_col], event[x_to_col]],
            mode="lines+markers",
            line=dict(color=color, width=4),
            marker=dict(color=color, size=7),
            name=name,
            text=[event["reason"], event["decision"]],
            hovertemplate="t=%{x:.2f} min<br>X=%{y}<br>%{text}<extra></extra>",
            showlegend=False,
        ))

    if not focus.empty:
        fig.add_vline(
            x=current_time / 60.0,
            line_dash="dot",
            line_color="#ffffff",
            annotation_text="now",
            annotation_position="top",
        )

    chart_layout(fig, f"{mode} route over time: {selected_id}", height=330)
    fig.update_yaxes(title="X coordinate", range=[-2, 62])
    return fig


def build_trace_lane_chart(trace_df, mode, selected_id, current_time):
    id_col = "box_id" if mode == "Box" else "shuttle_id"
    x_from_col = "box_from_x" if mode == "Box" else "shuttle_from_x"
    x_to_col = "box_to_x" if mode == "Box" else "shuttle_to_x"
    focus = trace_df[trace_df[id_col] == selected_id].sort_values("start_time")

    fig = go.Figure()
    tick_values = []
    tick_text = []
    for _, event in focus.iterrows():
        lane = (int(event["aisle"]) - 1) * 8 + int(event["y"])
        lane_label = f"A{int(event['aisle'])}-Y{int(event['y'])}"
        if lane not in tick_values:
            tick_values.append(lane)
            tick_text.append(lane_label)
        color = TRACE_COLORS.get(event["event_type"], "#667eea")
        fig.add_trace(go.Scatter(
            x=[event[x_from_col], event[x_to_col]],
            y=[lane, lane],
            mode="lines+markers",
            line=dict(color=color, width=5),
            marker=dict(color=color, size=8),
            text=[event["from_position"], event["to_position"]],
            hovertemplate="X=%{x}<br>Lane=%{y}<br>%{text}<extra></extra>",
            showlegend=False,
        ))

    active = focus[
        (focus["start_time"] <= current_time) &
        (focus["end_time"] >= current_time) &
        (focus["duration"] > 0)
    ]
    if not active.empty:
        event = active.iloc[-1]
        progress = (current_time - event["start_time"]) / max(event["duration"], 0.001)
        x_now = event[x_from_col] + (event[x_to_col] - event[x_from_col]) * progress
        lane = (int(event["aisle"]) - 1) * 8 + int(event["y"])
        fig.add_trace(go.Scatter(
            x=[x_now],
            y=[lane],
            mode="markers",
            marker=dict(color="#ffffff", size=16, symbol="diamond"),
            name="current",
            hovertemplate="Current X=%{x:.1f}<extra></extra>",
            showlegend=False,
        ))

    chart_layout(fig, f"Lane zoom: {selected_id}", height=330)
    fig.update_xaxes(title="X coordinate", range=[-2, 62])
    fig.update_yaxes(title="Lane", tickmode="array", tickvals=tick_values, ticktext=tick_text)
    return fig


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
            state = "next scheduled/known movement"

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
    """Interpolate every shuttle position at the selected simulation time."""
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
                decision = "Shuttle esperando en cabecera."
                reason = "Aun no tiene movimientos asignados en este instante."
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

    chart_layout(fig, "Live Shuttle Map - click a shuttle to pause and inspect", height=520)
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
    """Read selected shuttle id from Streamlit Plotly selection state."""
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


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Simulation Parameters")

    csv_path = st.text_input("CSV File", value="silo-semi-empty.csv")
    num_incoming = st.slider("Incoming Boxes", 200, 5000, 1000, step=100)
    num_destinations = st.slider("Destinations", 5, 80, 20)
    algorithm_config = st.selectbox(
        "Algorithm",
        available_algorithm_configs(),
        index=available_algorithm_configs().index("nearest_head"),
    )
    seed = st.number_input("Random Seed", value=42, step=1)
    playback_speed = st.slider("Playback Speed", 1, 50, 10,
                                help="Snapshots per second during playback")

    st.markdown("---")
    run_btn = st.button("Run Simulation", type="primary", use_container_width=True)

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
    st.markdown("---")
    st.markdown("""
    **Algorithms:**
    - Input: Selected strategy
    - Output: Dynamic pallet priority
    - Z-Relocation: Opportunistic when useful
    - State: Hash Maps (O(1))
    """)
    st.markdown("---")
    with st.expander("About Hack the Flow", expanded=False):
        st.markdown(load_project_story())


# ─────────────────────────────────────────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-title">Hack the Flow - Silo Dashboard</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Real-time visualization of the logistics simulation</p>',
            unsafe_allow_html=True)

# Check if CSV exists
if not os.path.exists(csv_path):
    st.error(f"CSV file not found: {csv_path}")
    st.stop()

# Run or use cached simulation
if run_btn or 'sim_result' not in st.session_state:
    with st.spinner("Running concurrent simulation..."):
        result = run_simulation(
            csv_path,
            num_incoming,
            num_destinations,
            seed,
            algorithm_config,
        )
        st.session_state.sim_result = result
        st.session_state.algorithm_config = algorithm_config
        st.session_state.playback_idx = 0
        st.session_state.chat_messages = []
else:
    result = st.session_state.sim_result
    algorithm_config = st.session_state.get("algorithm_config", algorithm_config)

snapshots = result.get('snapshots', [])
if not snapshots:
    st.warning("No snapshots collected. Run the simulation first.")
    st.stop()

df = pd.DataFrame(snapshots)

# ─── LIVE PLAYBACK ──────────────────────────────────────────────────────────
st.markdown("---")

# Playback controls
if "playing" not in st.session_state:
    st.session_state.playing = False
if "playback_idx" not in st.session_state:
    st.session_state.playback_idx = 0

col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4 = st.columns([1, 1, 4, 1])
with col_ctrl1:
    play_label = "Pause" if st.session_state.playing else "Play"
    if st.button(play_label, use_container_width=True):
        st.session_state.playing = not st.session_state.playing
        st.rerun()
with col_ctrl2:
    if st.button("Step", use_container_width=True):
        st.session_state.playing = False
        st.session_state.playback_idx = min(st.session_state.playback_idx + 1, len(df) - 1)
        st.rerun()
with col_ctrl3:
    frame_idx = st.slider(
        "Timeline",
        0,
        len(df) - 1,
        min(st.session_state.get('playback_idx', 0), len(df) - 1),
    )
    if frame_idx != st.session_state.playback_idx:
        st.session_state.playback_idx = frame_idx
        st.session_state.playing = False
with col_ctrl4:
    reset_btn = st.button("Reset", use_container_width=True)


if reset_btn:
    st.session_state.playing = False
    st.session_state.playback_idx = 0
    st.rerun()

# Get current frame data
frame_idx = st.session_state.playback_idx
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

# ─── KPI ROW ────────────────────────────────────────────────────────────────
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

# LIVE SHUTTLE MAP
st.markdown("---")
st.markdown("### Live Shuttle Movement")
st.caption("Each point is one shuttle. Moving shuttles are highlighted; click one to pause playback and inspect its route.")

if trace_df.empty:
    st.info("Run the simulation again to collect detailed shuttle movements.")
else:
    selected_shuttle_for_map = st.session_state.get("selected_shuttle_id")
    shuttle_map, shuttle_frame = build_live_shuttle_map(
        trace_df,
        float(current["time"]),
        selected_shuttle_for_map,
    )
    shuttle_state = st.plotly_chart(
        shuttle_map,
        width="stretch",
        key="live_shuttle_map",
        on_select="rerun",
        selection_mode="points",
    )
    clicked_shuttle = extract_selected_shuttle(shuttle_state)
    if clicked_shuttle:
        st.session_state.selected_shuttle_id = clicked_shuttle
        st.session_state.trace_mode = "Shuttle"
        st.session_state.trace_mode_radio = "Shuttle"
        st.session_state.playing = False
        selected_shuttle_for_map = clicked_shuttle

    if selected_shuttle_for_map:
        selected_row = shuttle_frame[shuttle_frame["shuttle_id"] == selected_shuttle_for_map]
        if not selected_row.empty:
            row = selected_row.iloc[0]
            info_cols = st.columns(5)
            info_cols[0].metric("Selected Shuttle", row["shuttle_id"])
            info_cols[1].metric("State", row["state"])
            info_cols[2].metric("X", f"{row['x']:.1f}")
            info_cols[3].metric("Box", row["box_id"] or "None")
            info_cols[4].metric("Destination", row["destination"] or "None")
            st.markdown(f"**Decision:** {row['decision']}")

# ─── CHARTS ─────────────────────────────────────────────────────────────────
st.markdown("---")

col1, col2 = st.columns(2)
with col1:
    st.plotly_chart(build_throughput_chart(df_up_to), use_container_width=True)
with col2:
    st.plotly_chart(build_occupancy_chart(df_up_to), use_container_width=True)

col3, col4 = st.columns(2)
with col3:
    st.plotly_chart(build_pallets_chart(df_up_to), use_container_width=True)
with col4:
    st.plotly_chart(build_aisle_chart(df_up_to), use_container_width=True)

col5, col6 = st.columns(2)
with col5:
    st.plotly_chart(build_shuttle_chart(df_up_to), use_container_width=True)
with col6:
    st.plotly_chart(build_pending_chart(df_up_to), use_container_width=True)


# ROUTE ZOOM
st.markdown("---")
st.markdown("### Route Zoom")
st.caption("Search a box or shuttle, or click a shuttle in the live map. The white marker shows the selected route at the timeline time.")

if trace_df.empty:
    st.info("Run the simulation again to collect detailed route events.")
else:
    current_time = float(current["time"])

    zoom_col1, zoom_col2, zoom_col3 = st.columns([1, 2, 2])
    with zoom_col1:
        default_mode = st.session_state.get("trace_mode", "Shuttle")
        trace_mode = st.radio(
            "Track",
            ["Box", "Shuttle"],
            horizontal=True,
            index=0 if default_mode == "Box" else 1,
            key="trace_mode_radio",
        )
        st.session_state.trace_mode = trace_mode

    if trace_mode == "Box":
        moving = trace_df[
            (trace_df["start_time"] <= current_time) &
            (trace_df["end_time"] >= current_time) &
            (trace_df["event_type"] != "INITIAL")
        ]
        box_options = sorted(trace_df["box_id"].dropna().unique())
        if st.session_state.get("selected_box_id") in box_options:
            default_box = st.session_state.selected_box_id
        else:
            default_box = moving["box_id"].iloc[0] if not moving.empty else box_options[0]
        with zoom_col2:
            box_search = st.text_input(
                "Search box",
                value=st.session_state.get("box_search", ""),
                placeholder="Type box id or destination...",
            ).strip()
            st.session_state.box_search = box_search
            if box_search:
                filtered_boxes = [
                    bid for bid in box_options
                    if box_search.lower() in bid.lower()
                    or box_search.lower() in str(
                        trace_df.loc[trace_df["box_id"] == bid, "destination"].iloc[0]
                    ).lower()
                ][:200]
            else:
                filtered_boxes = box_options[:200]
                if default_box not in filtered_boxes:
                    filtered_boxes = [default_box] + filtered_boxes[:199]
            if not filtered_boxes:
                st.warning("No matching boxes.")
                filtered_boxes = [default_box]
            default_index = filtered_boxes.index(default_box) if default_box in filtered_boxes else 0
            selected_trace_id = st.selectbox(
                "Matching boxes",
                filtered_boxes,
                index=default_index,
            )
            st.session_state.selected_box_id = selected_trace_id
    else:
        shuttle_options = sorted(trace_df["shuttle_id"].dropna().unique())
        busy = trace_df[
            (trace_df["start_time"] <= current_time) &
            (trace_df["end_time"] >= current_time) &
            (trace_df["event_type"] != "INITIAL")
        ]
        if st.session_state.get("selected_shuttle_id") in shuttle_options:
            default_shuttle = st.session_state.selected_shuttle_id
        else:
            default_shuttle = busy["shuttle_id"].iloc[0] if not busy.empty else shuttle_options[0]
        with zoom_col2:
            shuttle_search = st.text_input(
                "Search shuttle",
                value=st.session_state.get("shuttle_search", ""),
                placeholder="Example: A2_Y5",
            ).strip()
            st.session_state.shuttle_search = shuttle_search
            if shuttle_search:
                filtered_shuttles = [
                    sid for sid in shuttle_options
                    if shuttle_search.lower() in sid.lower()
                ]
            else:
                filtered_shuttles = shuttle_options
            if default_shuttle not in filtered_shuttles:
                filtered_shuttles = [default_shuttle] + filtered_shuttles
            default_index = filtered_shuttles.index(default_shuttle) if default_shuttle in filtered_shuttles else 0
            selected_trace_id = st.selectbox(
                "Matching shuttles",
                filtered_shuttles,
                index=default_index,
            )
            st.session_state.selected_shuttle_id = selected_trace_id

    selected_trace_context = build_trace_context(
        trace_df,
        trace_mode,
        selected_trace_id,
        current_time,
    )
    with zoom_col3:
        if selected_trace_context:
            compact_context = selected_trace_context.replace("\n", "  \n")
            st.markdown(compact_context)

    route_col1, route_col2 = st.columns(2)
    with route_col1:
        st.plotly_chart(
            build_trace_timeline_chart(trace_df, trace_mode, selected_trace_id, current_time),
            use_container_width=True,
        )
    with route_col2:
        st.plotly_chart(
            build_trace_lane_chart(trace_df, trace_mode, selected_trace_id, current_time),
            use_container_width=True,
        )

    selected_events = trace_df[
        trace_df["box_id" if trace_mode == "Box" else "shuttle_id"] == selected_trace_id
    ].sort_values("start_time")
    with st.expander("Movement log for selected route", expanded=False):
        st.dataframe(
            selected_events[[
                "event_type",
                "start_min",
                "end_min",
                "box_id",
                "destination",
                "shuttle_id",
                "from_position",
                "to_position",
                "reason",
            ]].tail(20),
            use_container_width=True,
            hide_index=True,
        )

# ─── FINAL SUMMARY ─────────────────────────────────────────────────────────
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


# CHATBOT
st.markdown("---")
st.markdown("### Talk to the warehouse")
st.caption("Ask why the system is prioritizing a pallet, what causes relocations, or how the current algorithm thinks.")

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

operator_question = st.chat_input("Ask the silo what it is doing...")
if operator_question:
    st.session_state.chat_messages.append({"role": "user", "content": operator_question})
    with st.chat_message("user"):
        st.markdown(operator_question)

    current_context = build_warehouse_context(
        result,
        current.to_dict(),
        algorithm_config,
        focus_context=selected_trace_context,
    )
    api_key = (
        api_key_input
        or os.getenv("MLH_GEMMA_API_KEY")
        or os.getenv("GEMINI_API_KEY")
    )

    with st.chat_message("assistant"):
        with st.spinner("The warehouse is thinking..."):
            try:
                answer = ask_gemma(
                    operator_question,
                    current_context,
                    api_key=api_key,
                    model=ai_model or DEFAULT_MODEL,
                )
            except Exception as exc:
                answer = fallback_answer(operator_question, current_context, algorithm_config)
                answer += f"\n\n_API unavailable, using local explanation. Detail: {exc}_"
            st.markdown(answer)

    st.session_state.chat_messages.append({"role": "assistant", "content": answer})


# Real-time playback: render one frame per rerun so charts and shuttle map move.
if st.session_state.get("playing", False):
    if st.session_state.playback_idx < len(df) - 1:
        time.sleep(1.0 / max(playback_speed, 1))
        st.session_state.playback_idx += 1
        st.rerun()
    else:
        st.session_state.playing = False
