from __future__ import annotations

import argparse
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
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 5432
DEFAULT_DATABASE_URL = "postgresql+psycopg://fieldline:fieldline@localhost:5432/fieldline"
FRONTEND_REPOSITORY_NAME = "fieldline-crm-frontend"


def log(message: str) -> None:
    print(f"[run.py] {message}", flush=True)


def load_dotenv_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        values[key] = value

    return values


def effective_env(backend_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    dotenv = load_dotenv_values(backend_dir / ".env")
    for key, value in dotenv.items():
        env.setdefault(key, value)
    return env


def port_is_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, process: subprocess.Popen[str] | None, label: str) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"{label} exited before becoming ready (code {process.returncode}).")
        if port_is_open(host, port):
            return
        time.sleep(0.5)

    raise RuntimeError(f"{label} did not open {host}:{port} within 90 seconds.")


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
        executable = shutil.which(command[0])
        if executable is None:
            continue

        try:
            result = subprocess.run(
                [*command, "version"],
                cwd=backend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except OSError:
            continue

        if result.returncode == 0:
            return command

    raise RuntimeError(
        "Docker Compose is required to start the project's local PostgreSQL service. "
        "Install Docker Desktop (or Docker Engine + Compose) and try again."
    )


def frontend_dir_candidates(backend_dir: Path) -> list[Path]:
    parent = backend_dir.parent
    candidates = [
        Path.cwd(),
        parent / FRONTEND_REPOSITORY_NAME,
    ]

    if Path.cwd() != backend_dir:
        candidates.append(Path.cwd() / FRONTEND_REPOSITORY_NAME)

    for base in (Path.cwd(), backend_dir, parent):
        if base.is_dir():
            try:
                candidates.extend(
                    child
                    for child in base.iterdir()
                    if child.is_dir() and child.name != "node_modules"
                )
            except OSError:
                pass

    return candidates


def is_frontend_repository(path: Path) -> bool:
    package_json = path / "package.json"
    next_config = path / "next.config.ts"
    if not package_json.is_file() or not next_config.is_file():
        return False

    try:
        content = package_json.read_text(encoding="utf-8")
    except OSError:
        return False

    return '"name": "fieldline-crm-frontend"' in content


def find_frontend_dir(backend_dir: Path, explicit: str | None) -> Path:
    configured = explicit or os.environ.get("FIELDLINE_FRONTEND_DIR")
    if configured:
        path = Path(configured).expanduser().resolve()
        if not is_frontend_repository(path):
            raise RuntimeError(
                f"FIELDLINE_FRONTEND_DIR does not point to the Fieldline frontend repository: {path}"
            )
        return path

    seen: set[Path] = set()
    for candidate in frontend_dir_candidates(backend_dir):
        try:
            path = candidate.resolve()
        except OSError:
            continue

        if path in seen:
            continue
        seen.add(path)

        if is_frontend_repository(path):
            return path

    raise RuntimeError(
        "The frontend checkout could not be located. Because the application is split across "
        "two independent repositories, set FIELDLINE_FRONTEND_DIR to the frontend repository "
        "or pass --frontend-dir, then run python run.py again."
    )


def configured_database_url(env: dict[str, str]) -> str:
    return env.get("FIELDLINE_DATABASE_URL", DEFAULT_DATABASE_URL)


def should_manage_local_postgres(database_url: str) -> bool:
    parsed = urlparse(database_url)
    host = parsed.hostname or DATABASE_HOST
    port = parsed.port or DATABASE_PORT
    return host in {"localhost", "127.0.0.1"} and port == DATABASE_PORT


def run_checked(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    log("$ " + " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def ensure_database(backend_dir: Path, env: dict[str, str]) -> None:
    database_url = configured_database_url(env)

    if not should_manage_local_postgres(database_url):
        log("Using the configured external PostgreSQL service.")
        return

    if port_is_open(DATABASE_HOST, DATABASE_PORT):
        log(f"PostgreSQL is already listening on {DATABASE_HOST}:{DATABASE_PORT}.")
        return

    compose = compose_command(backend_dir)
    log("Starting PostgreSQL using the repository's existing Docker Compose service.")
    run_checked([*compose, "up", "-d", "postgres"], backend_dir, env)

    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = subprocess.run(
            [*compose, "exec", "-T", "postgres", "pg_isready", "-U", "fieldline", "-d", "fieldline"],
            cwd=backend_dir,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return
        time.sleep(0.5)

    raise RuntimeError("PostgreSQL did not become ready within 90 seconds.")


def process_flags() -> tuple[bool, int]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return False, creationflags
    return True, creationflags


def start_process(
    command: list[str],
    cwd: Path,
    env: dict[str, str],
    label: str,
) -> subprocess.Popen[str]:
    start_new_session, creationflags = process_flags()
    log(f"Starting {label}.")
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        start_new_session=start_new_session,
        creationflags=creationflags,
    )


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the Fieldline CRM local development stack.")
    parser.add_argument(
        "--frontend-dir",
        help="Path to the separately cloned fieldline-crm-frontend repository.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_dir = Path(__file__).resolve().parent
    frontend_dir = find_frontend_dir(backend_dir, args.frontend_dir)
    env = effective_env(backend_dir)

    processes: list[tuple[str, subprocess.Popen[str]]] = []

    try:
        log(f"Backend repository: {backend_dir}")
        log(f"Frontend repository: {frontend_dir}")

        ensure_database(backend_dir, env)

        log("Applying Alembic migrations.")
        run_checked([sys.executable, "-m", "alembic", "upgrade", "head"], backend_dir, env)

        if port_is_open(BACKEND_HOST, BACKEND_PORT):
            wait_for_http(f"http://{BACKEND_HOST}:{BACKEND_PORT}/", None, "Existing backend")
            log(f"Backend is already running at http://{BACKEND_HOST}:{BACKEND_PORT}.")
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
            wait_for_http(
                f"http://{BACKEND_HOST}:{BACKEND_PORT}/",
                backend,
                "Backend",
            )

        frontend_env = env.copy()
        frontend_env.update(
            {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "Path", "PATHEXT", "SYSTEMROOT", "COMSPEC", "HOME", "USERPROFILE"}
            }
        )
        frontend_env.setdefault("BACKEND_URL", f"http://{BACKEND_HOST}:{BACKEND_PORT}")

        if port_is_open(BACKEND_HOST, FRONTEND_PORT):
            wait_for_http(
                f"http://{BACKEND_HOST}:{FRONTEND_PORT}/",
                None,
                "Existing frontend",
            )
            log(f"Frontend is already running at http://{BACKEND_HOST}:{FRONTEND_PORT}.")
        else:
            frontend = start_process(
                ["npm", "run", "dev", "--", "-p", str(FRONTEND_PORT)],
                frontend_dir,
                frontend_env,
                "frontend",
            )
            processes.append(("frontend", frontend))
            wait_for_http(
                f"http://{BACKEND_HOST}:{FRONTEND_PORT}/",
                frontend,
                "Frontend",
            )

        log("")
        log("Fieldline is running:")
        log(f"  Frontend: http://{BACKEND_HOST}:{FRONTEND_PORT}")
        log(f"  Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
        log(f"  API docs: http://{BACKEND_HOST}:{BACKEND_PORT}/api/v1/docs")
        log("Press Ctrl+C to stop the processes started by run.py.")

        while True:
            for label, process in processes:
                returncode = process.poll()
                if returncode is not None:
                    raise RuntimeError(f"{label} exited unexpectedly with code {returncode}.")
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
