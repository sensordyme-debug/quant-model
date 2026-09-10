"""Launch the local Quant dashboard: FastAPI + uvicorn on http://127.0.0.1:8787/.

    python scripts/dashboard.py [--port 8787] [--open] [--no-install]

The server itself lives in scripts/dashboard/ (server.py, sources.py, static/). This
launcher only does the plumbing:

1. refuses to start when 127.0.0.1:<port> is already taken - a second dashboard would also
   collide with the first one's read-only IB Gateway connection (clientId 81);
2. makes sure fastapi and uvicorn import, installing them under the running interpreter
   with pip when they do not (--no-install turns that into a plain failure);
3. puts scripts/ and scripts/dashboard/ on sys.path, sets the working directory to the repo
   root and runs uvicorn programmatically: loopback only, one worker, access log off;
4. with --open, opens the browser once the port answers (skipped when stdin is not a
   terminal; the "Quant Dashboard" scheduled task never passes --open).

The host is fixed to 127.0.0.1 on purpose; there is no flag to expose it. The dashboard is
read-only apart from appending live/state/nav_history.jsonl (see ALLOWED_WRITE in
scripts/dashboard/sources.py). Known limitation: a zombie dashboard process keeps both the
port and clientId 81 and must be killed by hand.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8787
REQUIRED = ("fastapi", "uvicorn")

SCRIPTS_DIR = Path(__file__).resolve().parent
DASHBOARD_DIR = SCRIPTS_DIR / "dashboard"
REPO = SCRIPTS_DIR.parent

EXIT_DEPS = 1     # fastapi/uvicorn missing and could not be installed
EXIT_PORT = 2     # port already bound: another dashboard (or something else) is there
EXIT_IMPORT = 3   # scripts/dashboard/server.py missing or failed to import


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description=f"Serve the Quant dashboard on http://{HOST}:<port>/ (loopback only, read-only).",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"TCP port on {HOST} (default {DEFAULT_PORT})")
    parser.add_argument("--open", action="store_true",
                        help="open the browser once the server answers (interactive terminals only)")
    parser.add_argument("--no-install", action="store_true",
                        help="do not pip install fastapi/uvicorn when they are missing; fail instead")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error(f"--port must be within 1..65535, got {args.port}")
    return args


# --- port -----------------------------------------------------------------------------------

def _listening(port: int, timeout: float = 0.5) -> bool:
    """True when a TCP connection to 127.0.0.1:port is accepted."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((HOST, port)) == 0


def port_in_use(port: int) -> bool:
    """True when something already listens on, or is bound to, 127.0.0.1:port.

    The probe socket deliberately sets no SO_REUSEADDR: on Windows that flag lets a bind
    succeed on top of another process's socket, which is exactly the collision we refuse.
    """
    if _listening(port):
        return True
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((HOST, port))
    except OSError:
        return True
    return False


# --- dependencies ---------------------------------------------------------------------------

def missing_packages() -> list[str]:
    importlib.invalidate_caches()
    return [name for name in REQUIRED if importlib.util.find_spec(name) is None]


def ensure_dependencies(install: bool) -> bool:
    """Return True when fastapi and uvicorn import; try a quiet pip install first if allowed."""
    missing = missing_packages()
    if not missing:
        return True
    names = "/".join(missing)
    if not install:
        print(f"{names} missing under {sys.executable} and --no-install given; "
              f"run: {sys.executable} -m pip install fastapi uvicorn", file=sys.stderr)
        return False
    print(f"installing {names} under {sys.executable} ...", flush=True)
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", *REQUIRED]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=900)
        if proc.returncode != 0:
            for line in (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]:
                print(f"  pip: {line}", file=sys.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  pip: {type(e).__name__}: {e}", file=sys.stderr)
    if not missing_packages():
        return True
    print(f"could not install fastapi/uvicorn under {sys.executable}; try: py -3.11 scripts/dashboard.py",
          file=sys.stderr)
    return False


# --- app import -----------------------------------------------------------------------------

def prepare_sys_path() -> None:
    """scripts/ first (package form: dashboard.server), scripts/dashboard/ second (flat: server)."""
    for index, directory in enumerate((SCRIPTS_DIR, DASHBOARD_DIR)):
        entry = str(directory)
        while entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(index, entry)


def resolve_app() -> str:
    """Return the uvicorn import string for the FastAPI app.

    Prefers the package form "dashboard.server:app" and falls back to the flat form
    "server:app", so server.py may import its siblings either as dashboard.sources or as
    sources. Importing here, before uvicorn, turns a broken server module into a readable
    traceback instead of the one-line "could not import" error uvicorn prints. Module-level
    code in this launcher has no side effects, so an accidental "import dashboard" resolving
    to this file (only possible when scripts/dashboard/__init__.py is missing) is harmless.
    """
    server_py = DASHBOARD_DIR / "server.py"
    if not server_py.is_file():
        raise FileNotFoundError(f"{server_py} not found - the dashboard package is incomplete")
    errors: list[str] = []
    for module_name in ("dashboard.server", "server"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            errors.append(f"--- import {module_name} failed:\n{traceback.format_exc()}")
            continue
        if hasattr(module, "app"):
            return f"{module_name}:app"
        errors.append(f"--- {module_name} has no attribute app")
    raise ImportError("could not import the dashboard app\n" + "\n".join(errors))


# --- browser --------------------------------------------------------------------------------

def _open_when_ready(url: str, port: int, timeout_s: float = 60.0) -> None:
    """Background thread: open the browser once the server accepts connections."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _listening(port):
            try:
                webbrowser.open(url)
            except Exception:
                pass
            return
        time.sleep(0.5)


# --- main -----------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    url = f"http://{HOST}:{args.port}/"

    if port_in_use(args.port):
        print(f"port {args.port} in use - a second dashboard would also collide on IB clientId 81",
              file=sys.stderr)
        return EXIT_PORT

    if not ensure_dependencies(install=not args.no_install):
        return EXIT_DEPS

    os.chdir(REPO)
    prepare_sys_path()
    try:
        target = resolve_app()
    except Exception as e:
        print(f"dashboard: {e}", file=sys.stderr)
        return EXIT_IMPORT

    import uvicorn  # importable: ensure_dependencies passed

    if args.open:
        if sys.stdin is not None and sys.stdin.isatty():
            threading.Thread(target=_open_when_ready, args=(url, args.port),
                             name="open-browser", daemon=True).start()
        else:
            print("--open ignored: stdin is not a terminal", flush=True)

    print(f"Quant dashboard: {url}  (loopback only; read-only except live/state/nav_history.jsonl; "
          "Ctrl+C to stop)", flush=True)
    try:
        uvicorn.run(target, host=HOST, port=args.port, workers=1, log_level="warning", access_log=False)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
