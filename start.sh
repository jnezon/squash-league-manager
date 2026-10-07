#!/bin/bash
# Start the league manager. Open http://127.0.0.1:8501 if the browser doesn't open itself.
# Add  --server.address 0.0.0.0  to let phones on the same wifi connect (http://<laptop-ip>:8501).
cd "$(dirname "$0")" && exec python3 -m streamlit run app.py --server.port 8501
