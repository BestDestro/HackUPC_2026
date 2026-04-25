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


# ─────────────────────────────────────────────────────────────────────────────
# SIMULATION RUNNER (cached)
# ─────────────────────────────────────────────────────────────────────────────
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



# ─────────────────────────────────────────────────────────────────────────────
# CHART BUILDERS
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
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
        st.markdown("- **Lookahead:** Dynamic (≥8 boxes)\n- **Output:** 32 Shuttles Parallel\n- **Gate:** Competitive\n- **State:** Hash Maps O(1)")
    else:
        st.markdown("- **Lookahead:** Strict (12 boxes)\n- **Output:** Sequential (1 Shuttle max/tick)\n- **Gate:** Occupancy > 50%\n- **State:** Hash Maps O(1)")

    st.markdown("---")
    st.markdown("**🤖 Integración IA (Activa)**")
    st.success("Conectado a Google Gemini")


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

# ─── LIVE PLAYBACK ──────────────────────────────────────────────────────────
st.markdown("---")

# Playback controls
col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 3, 1])
with col_ctrl1:
    play_btn = st.button("▶ Play", width='stretch')
with col_ctrl3:
    reset_btn = st.button("↺ Reset", width='stretch')

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

# ─── GEMINI AI ASSISTANT ───────────────────────────────────────────────────
st.markdown("---")
st.markdown("### 🤖 Habla con el Silo (Gemini AI)")
st.markdown("Pregúntale a la IA sobre su estado actual, qué está haciendo o si detecta algún cuello de botella.")

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# Display chat history
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Pregúntale al Silo (ej: '¿Cómo vas de ocupación?', '¿Hay mucho trabajo pendiente?'):"):
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analizando estado del silo..."):
            try:
                from google import genai
                client = genai.Client(api_key="AIzaSyAjIyY46MQq7yJYtodNIFS2JmZtI8QtW8o")
                
                # Context generation
                context = f"""
                Eres la IA integrada en un Silo Logístico Automatizado avanzado gestionando 32 shuttles robóticos.
                Debes responder a las preguntas del operador de forma profesional, técnica y muy breve (máximo 2-3 frases), hablando en primera persona ("Tengo...", "He almacenado...").
                
                Métricas en tiempo real (Tiempo Simulado: {current['time_min']:.1f} min):
                - Cajas guardadas en total: {int(current['boxes_stored'])}
                - Cajas extraídas en total: {int(current['boxes_retrieved'])}
                - Ocupación física: {current['occupancy_pct']:.1f}% de 7680 slots
                - Cajas pendientes de procesar en entrada: {int(current['pending_input'])}
                - Tareas de reubicación realizadas (desatascos): {int(current['relocations'])}
                - Pallets de salida completados: {int(current['pallets_completed'])}
                - Estrategia algorítmica activa: {algo_mode}
                
                El operador te ha preguntado:
                """
                # Use Gemini to generate response with the new SDK
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=context + prompt
                )
                
                st.markdown(response.text)
                st.session_state.chat_messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error de conexión con la IA: {str(e)}")
