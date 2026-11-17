"""Launch and orchestrate all QA demo services with uv.
Usage:
    uv run all
    uv run run_all.py
    python run_all.py [--no-stop] [--no-wait]
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def find_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p] + list(p.parents):
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


ROOT = find_root()

SERVICES = [
    {"name": "Portal Dashboard", "dir": "src/portal", "port": 8000},
    {"name": "App 1 - Resume Screener", "dir": "app1_resume_screener", "port": 8001},
    {"name": "App 2 - Document Diff", "dir": "app2_doc_diff", "port": 8002},
    {"name": "App 3 - FAQ Generator", "dir": "app3_faq_generator", "port": 8003},
    {"name": "App 4 - Report Agent", "dir": "app4_report_agent", "port": 8004},
    {"name": "App 5 - Policy Triage", "dir": "app5_policy_triage", "port": 8005},
    {"name": "App 6 - Data Analyst", "dir": "app6_data_analyst", "port": 8006},
]


def kill_processes_on_ports(ports: list[int]):
    """Kill any existing process listening on any of the specified ports."""
    pids = set()
    if sys.platform == "win32":
        try:
            output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], text=True)
            for line in output.splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and parts[3] == "LISTENING":
                    addr = parts[1]
                    if ":" in addr:
                        port_str = addr.rsplit(":", 1)[-1]
                        if port_str.isdigit() and int(port_str) in ports:
                            pid = int(parts[4])
                            if pid != 0 and pid != os.getpid():
                                pids.add(pid)
            for pid in pids:
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                except Exception:
                    pass
        except Exception:
            pass
    else:
        for port in ports:
            try:
                out = subprocess.check_output(["lsof", "-t", f"-i:{port}"], text=True)
                for pid_str in out.split():
                    if pid_str.isdigit():
                        os.kill(int(pid_str), signal.SIGKILL)
            except Exception:
                pass


def check_health(port: int, timeout: float = 3.0) -> bool:
    try:
        url = f"http://127.0.0.1:{port}/"
        req = urllib.request.Request(url, headers={"User-Agent": "health-check"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in (200, 301, 302, 307, 308)
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Run all QA apps concurrently with uv")
    parser.add_argument("--no-stop", action="store_true", help="Do not stop existing listeners on ports 8000-8006")
    parser.add_argument("--no-wait", action="store_true", help="Exit after all services have started")
    args = parser.parse_args()

    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)

    ports = [s["port"] for s in SERVICES]

    if not args.no_stop:
        kill_processes_on_ports(ports)
        time.sleep(1.5)

    uv_path = shutil.which("uv")
    procs: list[tuple[dict, subprocess.Popen, object, object]] = []

    for svc in SERVICES:
        work_dir = ROOT / svc["dir"]
        out_log_path = logs_dir / f"live{svc['port']}.out.log"
        err_log_path = logs_dir / f"live{svc['port']}.err.log"

        out_f = open(out_log_path, "wb")
        err_f = open(err_log_path, "wb")

        if uv_path:
            cmd = [uv_path, "run", "uvicorn", "main:app", "--port", str(svc["port"])]
        else:
            cmd = [sys.executable, "-m", "uvicorn", "main:app", "--port", str(svc["port"])]

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        p = subprocess.Popen(
            cmd,
            cwd=str(work_dir),
            stdout=out_f,
            stderr=err_f,
            creationflags=creationflags,
        )
        procs.append((svc, p, out_f, err_f))
        print(f"\033[96mStarting {svc['name']} on http://localhost:{svc['port']}\033[0m")

    print("\n\033[93mWaiting for services...\033[0m")

    # Poll until ready or timeout (up to 30s)
    max_wait = 30
    start_time = time.time()
    ready = set()

    while time.time() - start_time < max_wait:
        time.sleep(2)
        for svc in SERVICES:
            port = svc["port"]
            if port not in ready:
                if check_health(port, timeout=1.5):
                    ready.add(port)
        if len(ready) == len(SERVICES):
            break

    for svc in SERVICES:
        port = svc["port"]
        if port in ready:
            print(f"\033[92mOK   http://localhost:{port}  {svc['name']}\033[0m")
        else:
            print(f"\033[93mWAIT http://localhost:{port}  {svc['name']} - still starting, check logs/live{port}.err.log\033[0m")

    print("\n\033[92mDashboard: http://localhost:8000\033[0m")
    print("\033[92mAll services are up and running!\033[0m")

    if args.no_wait:
        return

    print("\033[90mKeep this window open to maintain background servers (Press Ctrl+C to stop all servers).\033[0m")
    try:
        while True:
            time.sleep(1)
            for svc, p, _, _ in procs:
                if p.poll() is not None:
                    pass
    except KeyboardInterrupt:
        print("\n\033[93mStopping servers...\033[0m")
    finally:
        for svc, p, out_f, err_f in procs:
            try:
                p.terminate()
            except Exception:
                pass
            try:
                out_f.close()
                err_f.close()
            except Exception:
                pass
        kill_processes_on_ports(ports)
        print("All servers stopped.")


if __name__ == "__main__":
    main()
