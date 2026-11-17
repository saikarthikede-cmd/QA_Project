"""Run any of the 6 QA demo apps using uv.
Usage:
    uv run app 3
    uv run run.py 3
    python run.py 3
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def find_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


ROOT = find_root()

APPS = {
    0: {"dir": "src/portal",           "port": 8000, "name": "Portal Dashboard"},
    1: {"dir": "app1_resume_screener", "port": 8001, "name": "Resume Screener"},
    2: {"dir": "app2_doc_diff",        "port": 8002, "name": "Document Diff Analyzer"},
    3: {"dir": "app3_faq_generator",   "port": 8003, "name": "FAQ Generator"},
    4: {"dir": "app4_report_agent",    "port": 8004, "name": "Report Summarizer Agent"},
    5: {"dir": "app5_policy_triage",   "port": 8005, "name": "Policy Triage Agent"},
    6: {"dir": "app6_data_analyst",    "port": 8006, "name": "Data Analyst Agent"},
}


def main():
    parser = argparse.ArgumentParser(description="Run a QA demo app using uv")
    parser.add_argument("app", type=int, nargs="?", default=1, help="App number (1-6, or 0 for Portal, default: 1)")
    parser.add_argument("--port", type=int, default=None, help="Override default port")
    parser.add_argument("--no-reload", action="store_true", help="Disable auto-reload")
    args = parser.parse_args()

    if args.app not in APPS:
        print(f"Error: Unknown app {args.app}. Choose 1-6:")
        for num, info in sorted(APPS.items()):
            print(f"  {num}: {info['name']} (port {info['port']})")
        sys.exit(1)

    cfg = APPS[args.app]
    port = args.port or cfg["port"]
    app_dir = ROOT / cfg["dir"]

    print(f"\033[96mStarting App {args.app} — {cfg['name']} on http://localhost:{port}\033[0m")

    uv_path = shutil.which("uv")
    if uv_path:
        cmd = [uv_path, "run", "uvicorn", "main:app", "--port", str(port)]
    else:
        cmd = [sys.executable, "-m", "uvicorn", "main:app", "--port", str(port)]

    if not args.no_reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=str(app_dir))
    except KeyboardInterrupt:
        print("\nStopping...")


if __name__ == "__main__":
    main()
