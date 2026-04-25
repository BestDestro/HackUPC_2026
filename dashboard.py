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
import shutil
from pathlib import Path

DATA_DIR = Path("data")
OUTPUTS_DIR = Path("outputs")
CURRENT_CSV_PATH = OUTPUTS_DIR / "current_silo.csv"

INITIAL_SCENARIOS = {
    "original": {
        "label": "Original - semi-empty",
        "path": DATA_DIR / "silo-semi-empty.csv",
    },
    "medium": {
        "label": "Medium - half full",
        "path": DATA_DIR / "silo-medium.csv",
    },
    "nearly_full": {
        "label": "Nearly full",
        "path": DATA_DIR / "silo-nearly-full.csv",
    },
}

from models import Box
from silo import Silo
from shuttle import ShuttleManager
from concurrent_sim import ConcurrentManager, BOX_INTERVAL
from csv_loader import load_silo_from_csv

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




def prepare_current_csv(scenario_key: str, force_reset: bool = False) -> Path:
    """
    Crea outputs/current_silo.csv copiando el CSV inicial elegido.
    El original de data/ nunca se modifica.
    """
    scenario = INITIAL_SCENARIOS[scenario_key]
    source_csv = scenario["path"]

    if not source_csv.exists():
        st.error(f"No existe el CSV del escenario: {source_csv}")
        st.stop()

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if force_reset or not CURRENT_CSV_PATH.exists():
        shutil.copyfile(source_csv, CURRENT_CSV_PATH)

    return CURRENT_CSV_PATH


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION RUNNER (cached)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Running simulation...")
def run_simulation(csv_path, csv_version, num_incoming, num_destinations, seed):
    """Run the concurrent simulation and return snapshots."""
    random.seed(seed)
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    manager = ConcurrentManager(silo, shuttle_mgr)

    # Load CSV
    result = load_silo_from_csv(csv_path, silo)
    all_boxes = result["all_boxes"]
    stats = result["stats"]
    manager.all_boxes.update(all_boxes)
    manager.boxes_stored = stats["loaded"]

    # Get existing destinations
    existing_dests = list(set(b.destination for b in all_boxes.values()))

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

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Initial State")

    scenario_key = st.selectbox(
        "Initial CSV scenario",
        options=list(INITIAL_SCENARIOS.keys()),
        format_func=lambda key: INITIAL_SCENARIOS[key]["label"],
    )

    scenario_changed = st.session_state.get("scenario_key") != scenario_key

    reset_current_state = st.button(
        "Reset current state from selected CSV",
        use_container_width=True,
    )

    if scenario_changed or reset_current_state:
        prepare_current_csv(scenario_key, force_reset=True)

        st.session_state["scenario_key"] = scenario_key

        for key in [
            "sim_result",
            "csv_signature",
            "playback_idx",
            "timeline_slider",
        ]:
            if key in st.session_state:
                del st.session_state[key]

        st.cache_data.clear()
        st.rerun()

    # Esto tiene que estar FUERA del if anterior
    csv_path = prepare_current_csv(scenario_key)

    st.caption(f"Initial CSV: `{INITIAL_SCENARIOS[scenario_key]['path']}`")
    st.caption(f"Current CSV: `{csv_path}`")

    csv_stat_sidebar = Path(csv_path).stat()
    st.caption(f"CSV version: `{csv_stat_sidebar.st_mtime_ns}-{csv_stat_sidebar.st_size}`")

    st.markdown("---")
    st.markdown("### Simulation Parameters")

    num_incoming = st.slider("Incoming Boxes", 200, 5000, 1000, step=100)
    num_destinations = st.slider("Destinations", 5, 80, 20)
    seed = st.number_input("Random Seed", value=42, step=1)

    playback_speed = st.slider(
        "Playback Speed",
        1,
        50,
        10,
        help="Snapshots per second during playback",
    )

    st.markdown("---")
    run_btn = st.button("Run Simulation", type="primary", use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('<h1 class="main-title">Hack the Flow - Silo Dashboard</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Real-time visualization of the logistics simulation</p>',
            unsafe_allow_html=True)

# Check if CSV exists
if not Path(csv_path).exists():
    st.error(f"CSV file not found: {csv_path}")
    st.stop()


csv_stat = Path(csv_path).stat()
csv_version = f"{csv_stat.st_mtime_ns}-{csv_stat.st_size}"

csv_signature = (
    scenario_key,
    str(csv_path),
    csv_version,
    num_incoming,
    num_destinations,
    int(seed),
)


previous_signature = st.session_state.get("csv_signature")
scenario_has_changed = previous_signature != csv_signature

# Run or use cached simulation
if run_btn or "sim_result" not in st.session_state or scenario_has_changed:
    with st.spinner("Running concurrent simulation..."):
        csv_stat = Path(csv_path).stat()
        csv_version = f"{csv_stat.st_mtime_ns}-{csv_stat.st_size}"

        result = run_simulation(
            str(csv_path),
            csv_version,
            num_incoming,
            num_destinations,
            int(seed),
        )

        st.session_state.sim_result = result
        st.session_state.csv_signature = csv_signature
        st.session_state.playback_idx = 0
else:
    result = st.session_state.sim_result

snapshots = result.get('snapshots', [])
if not snapshots:
    st.warning("No snapshots collected. Run the simulation first.")
    st.stop()

df = pd.DataFrame(snapshots)

# ─── LIVE PLAYBACK ──────────────────────────────────────────────────────────
st.markdown("---")

# Playback controls
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 3, 1])
with col_ctrl1:
    play_btn = st.button("▶ Play", use_container_width=True)
with col_ctrl3:
    reset_btn = st.button("↺ Reset", use_container_width=True)

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

# ─── LIVE PLAYBACK LOOP ────────────────────────────────────────────────────
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
