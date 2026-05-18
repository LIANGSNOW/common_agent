#!/usr/bin/env bash

echo "Starting all services..."

# Start open-webui serve in background
echo "Starting open-webui serve..."
nohup open-webui serve > open-webui.log 2>&1 &
OPEN_WEBUI_PID=$!
echo "open-webui started with PID: $OPEN_WEBUI_PID"

# Wait a bit for open-webui to start
sleep 3

# Start ui_pipeline
echo "Starting ui_pipeline..."
cd ui_pipeline
chmod +x start.sh
nohup ./start.sh --mode run > ../ui-pipeline.log 2>&1 &
UI_PIPELINE_PID=$!
cd ..
echo "ui_pipeline started with PID: $UI_PIPELINE_PID"

# Wait a bit for ui_pipeline to start
sleep 3

# Start agent_api
echo "Starting agent_api..."
nohup python agent_api.py > agent-api.log 2>&1 &
AGENT_API_PID=$!
echo "agent_api started with PID: $AGENT_API_PID"

echo ""
echo "All services started!"
echo "Services running:"
echo "  - open-webui: http://localhost:8080 (PID: $OPEN_WEBUI_PID)"
echo "  - ui_pipeline: http://localhost:9099 (PID: $UI_PIPELINE_PID)"
echo "  - agent_api: http://localhost:9000 (PID: $AGENT_API_PID)"
echo ""
echo "Log files:"
echo "  - open-webui.log"
echo "  - ui-pipeline.log"
echo "  - agent-api.log"
echo ""
echo "To stop all services, run: kill $OPEN_WEBUI_PID $UI_PIPELINE_PID $AGENT_API_PID"
echo "Or press Ctrl+C to stop this script"

# Keep the script running and handle Ctrl+C
trap 'echo "Stopping all services..."; kill $OPEN_WEBUI_PID $UI_PIPELINE_PID $AGENT_API_PID 2>/dev/null; echo "All services stopped."; exit 0' INT

# Wait for user to press Ctrl+C
while true; do
    sleep 1
done
