# Local JupyterLab

One application environment for JupyterLab, extensions, keyboard shortcuts, and settings. Each project supplies its own Python environment as a kernel. Existing user and system kernels remain available.

## Install

Requires Linux, Python 3.11 or newer, and [uv](https://docs.astral.sh/uv/).

```sh
cd /path/to/jupyterlab-config
./install.sh
```

The installer runs `uv sync --locked` and links `~/.local/bin/jlab` to this checkout. Keep the checkout in place. If needed, add `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc`, then open a new shell. The application never needs its environment activated.

To use the repository script without installing a shortcut, run `/path/to/jupyterlab-config/bin/jlab` directly after `uv sync --locked`.

## Run

```sh
cd ~/dev/my-project
jlab start                         # File browser root: current directory
jlab start --root ~/dev --port 8889 # For a stopped instance, expose multiple projects
jlab status
jlab url
jlab logs
jlab logs --follow
jlab restart                       # Retain last root and port
jlab restart --root ~/dev           # Change root explicitly
jlab stop                          # Also shuts down its running kernels
```

One background instance runs per checkout. It survives closing the terminal, listens only on `127.0.0.1`, and uses token authentication. Open the printed URL manually; no browser opens automatically. Port 8888 is the default, and an occupied port causes an error rather than silently choosing another port.

Repeated `start` calls report the existing instance, even when invoked from another directory. Explicitly conflicting root or port options require `restart`. Status and URL commands exit with status 1 when the server is unavailable. A restart of a stopped instance retains its last root and port when metadata is available.

Logs, authentication tokens, runtime files, process metadata, and workspace layouts live under ignored `.state/`. Treat this directory and printed authenticated URLs as private. Stop the instance before moving or deleting the checkout. `jlab stop` terminates notebook computations; save work first. There is no automatic startup at login.

## Project kernels

For a uv-managed project:

```sh
cd ~/dev/my-project
uv add --dev ipykernel
jlab kernel add my-project --python .venv/bin/python --display-name 'Python (my-project)'
jlab kernel list
jlab start
```

Select **Python (my-project)** in the notebook kernel picker. The notebook runs in that project's environment; install its libraries with that project's dependency manager. For an existing non-uv environment, install `ipykernel` using that environment's Python, then pass its `bin/python` path to the same registration command.

```sh
jlab kernel add my-project --python .venv/bin/python --replace
jlab kernel remove my-project
```

Registration saves an absolute interpreter path. Register again after moving or rebuilding an environment. Removing a registration does not delete the environment or stop an already running kernel.

Lab and `jlab kernel list` use the same search paths: this checkout's private registrations, inherited `JUPYTER_PATH`, and Jupyter's normal environment, user, and system paths. The CLI shows the effective name, display name, scope, and resource directory. It does not scan arbitrary unregistered virtual environments.

Private registrations take priority on duplicate names; the remaining paths follow Jupyter's normal precedence. `--replace` can create a private override of a global kernel without modifying it. Removing the override reveals the global registration again. Removal refuses to delete global-only registrations. Use the same environment variables when invoking lifecycle and kernel commands if you customize Jupyter search paths; restart after changing those variables.

## Settings and extensions

Edit shortcuts and other preferences in JupyterLab's **Settings → Settings Editor**. Changes are written into `config/lab/user-settings/`; review and commit these files to reuse them. Server options live in `config/jupyter_server_config.py`. The launcher enforces loopback binding, the chosen root and port, no port fallback, and no automatic browser launch. Keep secrets out of tracked configuration.

Install prebuilt Python extensions from this application repository:

```sh
cd /path/to/jupyterlab-config
uv add jupyterlab-git                 # Example; no extensions are installed initially
jlab restart
```

To remove one, use `uv remove jupyterlab-git` and restart. Commit `pyproject.toml` and `uv.lock` after dependency changes. Prefer this workflow to installing through Lab's extension UI, so the environment remains reproducible. Notebook `%pip` commands affect the selected kernel, not the application's dependencies.

To rebuild the application environment, stop Lab, recreate `.venv` using `uv sync --locked`, and start again. Configuration and private kernel registrations live outside `.venv` and survive rebuilding it. UI workspace layouts are local state and are not committed.

## Checks

```sh
.venv/bin/python -m unittest discover -s tests -v
bash -n bin/jlab install.sh
```

Integration tests run real servers in temporary checkouts, use private fixture registrations, and stop their servers during cleanup. They require permission to bind loopback ports; they do not modify your global kernels or running application instance.
