# Hack the Flow

Real-time warehouse flow optimizer that schedules 32 shuttles to store, retrieve, and relocate boxes efficiently in automated silos.

## Inspiration

We were inspired by automated warehouses and the challenge of keeping thousands of boxes moving without creating bottlenecks. We wanted to optimize how boxes enter and leave a silo using 32 shuttles working at the same time.

## What it does

Hack the Flow simulates an automated warehouse silo with 7,680 positions and 32 shuttles. It decides where to store incoming boxes, which boxes to retrieve, when to relocate blocked boxes, and how to complete pallets efficiently.

It also includes a dashboard to visualize shuttle movement, warehouse metrics, algorithm performance, and an AI assistant that explains what is happening in the simulation.

## How we built it

We built the simulator in Python. The silo is represented as a grid of aisles, sides, X positions, Y levels, and Z depth. We used dictionaries and hash maps to quickly find boxes, free positions, and destinations.

We created algorithms for chaotic storage, greedy retrieval, pallet selection, relocation, and concurrent shuttle scheduling. The dashboard was built with Streamlit and Plotly, and we used the Gemma API to explain simulation decisions.

## Challenges we ran into

The hardest part was handling many operations happening at the same time. Store and retrieve tasks share the same 32 shuttles, so we had to carefully simulate time and shuttle availability.

Another challenge was the Z-depth restriction: if a box is behind another one, the front box must be relocated first. This made the optimization more complex.

## Accomplishments that we're proud of

We are proud of building a working concurrent simulation with real warehouse constraints. We also created several algorithms, benchmarked them, and built an interactive dashboard to visualize the results.

We are especially proud that users can inspect a shuttle or box route and ask the AI assistant why a decision was made.

## What we learned

We learned that warehouse optimization is not only about choosing the shortest path. Good decisions must also consider shuttle workload, destination grouping, pallet completion, relocations, and future congestion.

We also learned how useful visualization is when debugging complex simulations.

## What's next for Hack the Flow

Next, we would improve the algorithms with adaptive strategy switching, better prediction of incoming boxes, and more detailed real-time comparisons between strategies. We would also like to test the system with larger datasets and more realistic warehouse conditions.

## Built With

- Python
- Streamlit
- Plotly
- pandas
- Gemma API
- Google AI Studio
- CSV
- Custom simulation engine
- Hash maps

## Try it out

- GitHub Repo: https://github.com/BestDestro/HackUPC_2026.git

## Run locally

Install the required Python packages, then run:

```bash
streamlit run dashboard.py
```

To enable the AI assistant with Gemma, set your API key before launching Streamlit:

```powershell
$env:MLH_GEMMA_API_KEY="your_api_key"
$env:WAREHOUSE_AI_MODEL="gemma-3-27b-it"
streamlit run dashboard.py
```

You can also paste the API key in the dashboard sidebar. If no API key is available, the chat uses a local fallback explanation based on the simulation metrics and algorithm configuration.

## Benchmark algorithms

Run all algorithms against the initial CSV and generated occupancy states:

```bash
python benchmark_algorithms.py --incoming 1000
```

Run selected algorithms:

```bash
python benchmark_algorithms.py --algorithms baseline nearest_head balanced_ready throughput
```

Results are saved in `benchmark_results/algorithm_benchmark.csv` and `benchmark_results/algorithm_benchmark.md`.

