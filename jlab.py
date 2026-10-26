"""Manage this checkout's JupyterLab without activating its environment."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = Path(__file__).resolve().parent
STATE = REPO / ".state"
PRIVATE_DATA = STATE / "share" / "jupyter"
META = STATE / "server.json"
LOG = STATE / "server.log"


def prepare():
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    STATE.chmod(0o700)


def environment():
    env = os.environ.copy()
    env.update(
        JUPYTER_CONFIG_DIR=str(REPO / "config"),
        JUPYTERLAB_SETTINGS_DIR=str(REPO / "config/lab/user-settings"),
        JUPYTERLAB_WORKSPACES_DIR=str(STATE / "workspaces"),
        JUPYTER_RUNTIME_DIR=str(STATE / "runtime"),
        JUPYTER_PATH=os.pathsep.join(
            [str(PRIVATE_DATA)] + ([env["JUPYTER_PATH"]] if env.get("JUPYTER_PATH") else [])
        ),
    )
    return env


def read_meta():
    try:
        return json.loads(META.read_text())
    except FileNotFoundError:
        return None


def write_meta(meta):
    temporary = META.with_suffix(".tmp")
    temporary.write_text(json.dumps(meta, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(META)


def process_stamp(pid):
    """Linux boot ID and process start ticks protect against PID reuse."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return f"{boot}:{stat[19]}"
    except (FileNotFoundError, ProcessLookupError):
        return None


def alive(meta):
    return bool(meta and meta.get("stamp") and process_stamp(meta["pid"]) == meta["stamp"])


def request(meta, endpoint, *, shutdown=False):
    req = urllib.request.Request(
        f"http://127.0.0.1:{meta['port']}{endpoint}",
        data=b"" if shutdown else None,
        headers={"Authorization": f"token {meta['token']}"},
        method="POST" if shutdown else "GET",
    )
    # Loopback traffic must not be sent through inherited HTTP proxies.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=2) as response:
        return response.read()


def ready(meta):
    if not alive(meta):
        return False
    try:
        request(meta, "/api/kernelspecs")
        return True
    except (OSError, urllib.error.URLError):
        return False


def print_instance(meta):
    print(f"http://127.0.0.1:{meta['port']}/lab?token={meta['token']}")
    print(f"Root: {meta['root']}")


def wait_stopped(meta, timeout):
    deadline = time.monotonic() + timeout
    while alive(meta) and time.monotonic() < deadline:
        time.sleep(0.1)
    return not alive(meta)


def stop(meta):
    if not alive(meta):
        print("JupyterLab is stopped.")
        return
    try:
        request(meta, "/api/shutdown", shutdown=True)
    except (OSError, urllib.error.URLError):
        pass
    for sig in (signal.SIGTERM, signal.SIGKILL):
        if wait_stopped(meta, 10):
            break
        # Verify identity again immediately before signaling.
        if alive(meta):
            with contextlib.suppress(ProcessLookupError):
                os.kill(meta["pid"], sig)
    if not wait_stopped(meta, 5):
        raise RuntimeError("Server did not stop; inspect the log before retrying.")
    print("JupyterLab stopped.")


def start(root, port):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Root is not a directory: {root}")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    token = secrets.token_urlsafe(32)
    env = environment()
    env["JUPYTER_TOKEN"] = token
    with LOG.open("ab") as log:
        log.write(f"\n--- Starting {time.ctime()} root={root} port={port} ---\n".encode())
        log.flush()
        child = subprocess.Popen(
            [sys.executable, "-m", "jupyterlab", "--no-browser", "--ServerApp.ip=127.0.0.1",
             f"--ServerApp.port={port}", "--ServerApp.port_retries=0", f"--ServerApp.root_dir={root}"],
            cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            start_new_session=True,
        )
    meta = dict(pid=child.pid, stamp=process_stamp(child.pid), root=str(root), port=port,
                token=token, phase="starting")
    write_meta(meta)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"Startup failed (exit {child.returncode}). See {LOG}")
            if ready(meta):
                meta["phase"] = "running"
                write_meta(meta)
                print_instance(meta)
                return
            time.sleep(0.2)
        raise RuntimeError(f"Startup timed out. See {LOG}")
    except BaseException:
        stop(meta)
        raise


def kernel_manager():
    # This environment is also passed unchanged to the Lab server.
    os.environ.update(environment())
    from jupyter_client.kernelspec import KernelSpecManager
    from traitlets.config.loader import PyFileConfigLoader

    # Load the same Jupyter configuration as the server for discovery settings.
    config = PyFileConfigLoader("jupyter_server_config.py", path=str(REPO / "config")).load_config()
    return KernelSpecManager(config=config)


def scope(path):
    path = Path(path).resolve()
    if path.is_relative_to(PRIVATE_DATA):
        return "private"
    if path.is_relative_to(Path(sys.prefix)):
        return "environment"
    from jupyter_core.paths import jupyter_data_dir
    if path.is_relative_to(Path(jupyter_data_dir()).resolve()):
        return "user"
    if any(path.is_relative_to(Path(p)) for p in ("/usr/share/jupyter", "/usr/local/share/jupyter")):
        return "system"
    return "external"


def kernels(args):
    manager = kernel_manager()
    found = manager.find_kernel_specs()
    if args.action == "list":
        rows = [("NAME", "DISPLAY NAME", "SCOPE", "DIRECTORY")]
        for name, spec in sorted(manager.get_all_specs().items()):
            path = spec["resource_dir"]
            rows.append((name, spec["spec"]["display_name"], scope(path), path))
        widths = [max(len(row[column]) for row in rows) for column in range(3)]
        for row in rows:
            print("  ".join(value.ljust(width) for value, width in zip(row[:3], widths))
                  + "  " + row[3])
        return
    name = args.name.lower()
    import re
    if name in (".", "..") or not re.fullmatch(r"[a-z0-9._-]+", name):
        raise ValueError("Kernel names must contain only ASCII letters, digits, '.', '_', or '-'.")
    destination = PRIVATE_DATA / "kernels" / name
    if args.action == "remove":
        if not destination.is_dir():
            if name in found:
                raise ValueError(f"Kernel is not private; leaving registration at {found[name]} unchanged.")
            raise ValueError(f"Unknown private kernel: {name}")
        import shutil
        shutil.rmtree(destination)
        print(f"Removed private kernel {name}.")
        return
    if name in found and not args.replace:
        raise ValueError(f"Kernel {name} already exists at {found[name]}; use --replace to create a private override.")
    # Preserve a venv's bin/python path: resolving its symlink would select base Python.
    python = os.path.abspath(os.path.expanduser(args.python))
    check = subprocess.run([python, "-c", "import ipykernel"], capture_output=True, text=True)
    if check.returncode:
        raise ValueError(f"ipykernel is unavailable in {python}. Install it in that project environment first "
                         "(for example: uv add --dev ipykernel).")
    subprocess.run(
        [python, "-m", "ipykernel", "install", "--prefix", str(STATE), "--name", name,
         "--display-name", args.display_name or f"Python ({name})"],
        env=environment(), check=True,
    )


def parser():
    cli = argparse.ArgumentParser(prog="jlab", description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    help_command = commands.add_parser("help", help="Show help for all commands or a specific command")
    help_command.add_argument("topic", nargs="*", metavar="COMMAND", help="For example: kernel add")
    for command in ("start", "restart"):
        sub = commands.add_parser(command, help=f"{command.capitalize()} the background JupyterLab instance")
        sub.add_argument("--root", help="File browser root (start default: current directory)")
        sub.add_argument("--port", type=int, help="Listen port (start default: 8888)")
    for command, description in (("stop", "Stop the server and its kernels"),
                                 ("status", "Show server status, URL, and root"),
                                 ("url", "Print the authenticated Lab URL and root")):
        commands.add_parser(command, help=description)
    log = commands.add_parser("logs", help="Show the server log")
    log.add_argument("--follow", action="store_true")
    kernel = commands.add_parser("kernel", help="List kernels or manage private registrations").add_subparsers(dest="action", required=True)
    kernel.add_parser("list", help="List private, environment, user, and system kernels")
    add = kernel.add_parser("add", help="Register a project environment as a private kernel")
    add.add_argument("name")
    add.add_argument("--python", required=True, help="Project environment's Python executable")
    add.add_argument("--display-name")
    add.add_argument("--replace", action="store_true")
    kernel.add_parser("remove", help="Remove a private kernel registration").add_argument("name")
    return cli


def main():
    arguments = sys.argv[1:]
    if arguments[:1] == ["help"]:
        arguments = arguments[1:] + ["--help"]
    args = parser().parse_args(arguments)
    prepare()
    if args.command == "logs":
        if not LOG.exists():
            raise ValueError("No server log yet.")
        os.execvp("tail", ["tail", "-n", "100"] + (["-F"] if args.follow else []) + [str(LOG)])
    if args.command in ("status", "url"):
        meta = read_meta()
        if ready(meta):
            if args.command == "status":
                print(f"JupyterLab running (PID {meta['pid']}).")
            print_instance(meta)
            return 0
        state = "stopped"
        if alive(meta):
            state = "starting" if meta.get("phase") == "starting" else "unhealthy"
        print(f"JupyterLab is {state}.")
        return 1
    with (STATE / "lifecycle.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.command == "kernel":
            kernels(args)
            return 0
        meta = read_meta()
        if args.command == "stop":
            stop(meta)
        elif args.command == "restart":
            root = args.root if args.root is not None else (meta["root"] if meta else os.getcwd())
            port = args.port if args.port is not None else (meta["port"] if meta else 8888)
            # Validate before disrupting a running instance.
            if not Path(root).expanduser().is_dir() or not 1 <= port <= 65535:
                raise ValueError("Restart requires an existing root directory and a port between 1 and 65535.")
            stop(meta)
            start(root, port)
        elif alive(meta):
            if ((args.root is not None and str(Path(args.root).expanduser().resolve()) != meta["root"])
                    or (args.port is not None and args.port != meta["port"])):
                raise ValueError("Instance already running with different options. Use jlab restart to change them.")
            if not ready(meta):
                raise RuntimeError(f"Instance is unhealthy. Inspect {LOG} or run jlab restart.")
            print("JupyterLab is already running.")
            print_instance(meta)
        else:
            start(args.root if args.root is not None else os.getcwd(), args.port if args.port is not None else 8888)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f"jlab: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
