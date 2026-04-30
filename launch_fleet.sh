#!/bin/bash

# Kill any existing fleet processes
pkill -f "python" || true
sleep 2

source venv/bin/activate
export PYTHONUNBUFFERED=1

echo "🚀 Launching Tactical Fleet Network..."

# --- ALPHA SQUADRON (1 VTOL + 1 Quad) ---
echo "🛰️  Deploying GCS ALPHA..."
python simulation/vtol_sim.py --port 14550 & # Base
python simulation/quad_sim.py --port 14552 & # Base
export GCS_STATION_ID="truegcs-alpha-tactical-master"
export GCS_STATION_NAME="GCS-ALPHA-MASTER"
python main.py &
sleep 5

# --- BRAVO SQUADRON (1 Tailsitter) ---
echo "🛰️  Deploying GCS BRAVO..."
# Offset Bravo to the North
python simulation/vtol_sim.py --port 14560 &
export GCS_STATION_ID="truegcs-bravo-tactical-master"
export GCS_STATION_NAME="GCS-BRAVO-WING"
python main.py &
sleep 5

# --- CHARLIE SQUADRON (3 Tailsitters) ---
echo "🛰️  Deploying GCS CHARLIE..."
# Stagger Charlie Squadron in a triangle
python simulation/vtol_sim.py --port 14570 &
python simulation/vtol_sim.py --port 14572 &
python simulation/vtol_sim.py --port 14574 &
export GCS_STATION_ID="truegcs-charlie-tactical-master"
export GCS_STATION_NAME="GCS-CHARLIE-SWARM"
python main.py &

echo "✅ Fleet Mobilized with Tactical Offsets."
