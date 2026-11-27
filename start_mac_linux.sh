#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
visualpfd_python=python3
if [[ -x .venv/bin/python ]]; then
    visualpfd_python=.venv/bin/python
fi
exec "$visualpfd_python" -m streamlit run app.py --server.address=127.0.0.1 --browser.gatherUsageStats=false --client.toolbarMode=minimal
