from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_PORT = 3000
POSTGRES_PORT = 5432
DEFAULT_DATABASE_URL = "postgresql+psycopg://fieldline:fieldline@localhost:5432/fieldline"
FRONTEND_PACKAGE_NAME = "fieldline-crm-frontend"


def log(message: str) -> None:
    print(f"[run.py] {message}", flush=True)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def build_env(backend_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in load_env_file(backend_dir / ".env").items():
        env.setdefault(key, value)
    return env


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for_http(
    url: str,
    process: subprocess.Popen[str] | None,
    label: str,
    timeout: float = 90,
) -> None:
    deadline = time.monotonic() + timeout
    last_error = "no response"

    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"{label} exited before becoming ready (code {process.returncode}).")
        try:
            with urlopen(url, timeout=2) as response:
                if 200 <= response.status < 300:
                    return
                last_error = f"HTTP {response.status}"
        except (OSError, URLError) as exc:
            last_error = str(exc)
        time.sleep(0.5)

    raise RuntimeError(f"{label} did not become ready within {timeout:.0f} seconds ({last_error}).")


def compose_command(backend_dir: Path) -> list[str]:
    for command in (["docker", "compose"], ["docker-compose"]):
        if shutil.which(command[0]) is None:
            continue
        result = subprocess.run(
            [*command, "version"],
            cwd=backend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return command
    raise RuntimeError(
        "Docker Compose is required for the local PostgreSQL service. "
        "Install Docker Desktop or Docker Engine + Compose and try again."
    )


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    log("$ " + " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def frontend_repo(path: Path) -> bool:
    package_file = path / "package.json"
    if not package_file.is_file() or not (path / "next.config.ts").is_file():
        return False
    try:
        return json.loads(package_file.read_text(encoding="utf-8")).get("name") == FRONTEND_PACKAGE_NAME
    except (OSError, json.JSONDecodeError):
        return False


def find_frontend(backend_dir: Path, configured: str | None) -> Path:
    value = configured or os.environ.get("FIELDLINE_FRONTEND_DIR")
    if value:
        path = Path(value).expanduser().resolve()
        if frontend_repo(path):
            return path
        raise RuntimeError(f"Frontend path is not a Fieldline frontend repository: {path}")

    cwd = Path.cwd()
    candidates = [cwd, backend_dir.parent / FRONTEND_PACKAGE_NAME]
    if cwd != backend_dir:
        candidates.append(cwd / FRONTEND_PACKAGE_NAME)

    for base in (cwd, backend_dir, backend_dir.parent):
        if not base.is_dir():
            continue
        try:
            candidates.extend(child for child in base.iterdir() if child.is_dir())
        except OSError:
            continue

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            continue
        if path in seen:
            continue
        seen.add(path)
        if frontend_repo(path):
            return path

    raise RuntimeError(
        "The frontend checkout could not be located. Set FIELDLINE_FRONTEND_DIR or "
        "pass --frontend-dir with the path to fieldline-crm-frontend."
    )


def local_postgres_needed(env: dict[str, str]) -> bool:
    parsed = urlparse(env.get("FIELDLINE_DATABASE_URL", DEFAULT_DATABASE_URL))
    return (parsed.hostname or "localhost") in {"localhost", "127.0.0.1"} and (
        parsed.port or POSTGRES_PORT
    ) == POSTGRES_PORT


def ensure_postgres(backend_dir: Path, env: dict[str, str]) -> None:
    if not local_postgres_needed(env):
        log("Using the configured external PostgreSQL service.")
        return

    if port_open(BACKEND_HOST, POSTGRES_PORT):
        log(f"PostgreSQL is already listening on {BACKEND_HOST}:{POSTGRES_PORT}.")
        return

    compose = compose_command(backend_dir)
    run([*compose, "up", "-d", "postgres"], backend_dir, env)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        ready = subprocess.run(
            [*compose, "exec", "-T", "postgres", "pg_isready", "-U", "fieldline", "-d", "fieldline"],
            cwd=backend_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if ready.returncode == 0:
            return
        time.sleep(0.5)

    raise RuntimeError("PostgreSQL did not become ready within 90 seconds.")


def start_process(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> subprocess.Popen[str]:
    log(f"Starting {label}.")
    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, cwd=cwd, env=env, **kwargs)


def stop_process(process: subprocess.Popen[str], label: str) -> None:
    if process.poll() is not None:
        return
    log(f"Stopping {label}.")
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
    except (AttributeError, OSError):
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Fieldline CRM local development stack.")
    parser.add_argument("--frontend-dir", help="Path to the separately cloned frontend repository.")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    frontend_dir = find_frontend(backend_dir, args.frontend_dir)
    env = build_env(backend_dir)
    processes: list[tuple[str, subprocess.Popen[str]]] = []

    try:
        log(f"Backend:  {backend_dir}")
        log(f"Frontend: {frontend_dir}")

        ensure_postgres(backend_dir, env)
        run([sys.executable, "-m", "alembic", "upgrade", "head"], backend_dir, env)

        if port_open(BACKEND_HOST, BACKEND_PORT):
            wait_for_http(f"http://{BACKEND_HOST}:{BACKEND_PORT}/", None, "Existing backend")
            log(f"Backend already running at http://{BACKEND_HOST}:{BACKEND_PORT}.")
        else:
            backend = start_process(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--reload",
                    "--host",
                    BACKEND_HOST,
                    "--port",
                    str(BACKEND_PORT),
                ],
                backend_dir,
                env,
                "backend",
            )
            processes.append(("backend", backend))
            wait_for_http(f"http://{BACKEND_HOST}:{BACKEND_PORT}/", backend, "Backend")

        frontend_env = os.environ.copy()
        frontend_env.setdefault("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

        if port_open(BACKEND_HOST, FRONTEND_PORT):
            wait_for_http(f"http://{BACKEND_HOST}:{FRONTEND_PORT}/", None, "Existing frontend")
            log(f"Frontend already running at http://{BACKEND_HOST}:{FRONTEND_PORT}.")
            wait_for_http(
                f"http://{BACKEND_HOST}:{FRONTEND_PORT}/api/v1/health",
                None,
                "Existing frontend API proxy",
            )
        else:
            frontend = start_process(
                ["npm", "run", "dev", "--", "-p", str(FRONTEND_PORT)],
                frontend_dir,
                frontend_env,
                "frontend",
            )
            processes.append(("frontend", frontend))
            wait_for_http(f"http://{BACKEND_HOST}:{FRONTEND_PORT}/", frontend, "Frontend")
            wait_for_http(
                f"http://{BACKEND_HOST}:{FRONTEND_PORT}/api/v1/health",
                frontend,
                "Frontend API proxy",
            )

        log("")
        log("Fieldline is running:")
        log(f"  Frontend: http://{BACKEND_HOST}:{FRONTEND_PORT}")
        log(f"  Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
        log(f"  API docs: http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/docs")
        log("Press Ctrl+C to stop the processes started by run.py.")

        while True:
            for label, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{label} exited unexpectedly with code {process.returncode}.")
            time.sleep(0.5)

    except KeyboardInterrupt:
        log("Shutdown requested.")
        return 0
    except (RuntimeError, subprocess.CalledProcessError, FileNotFoundError) as exc:
        log(f"ERROR: {exc}")
        return 1
    finally:
        for label, process in reversed(processes):
            stop_process(process, label)


if __name__ == "__main__":
    raise SystemExit(main())
