# Local JupyterLab

A shared JupyterLab environment for extensions, shortcuts, and settings. Each project uses its own Python environment as a kernel. Global kernels are also available.

## Install

Requires Linux, Python 3.11+, and [uv](https://docs.astral.sh/uv/).

```sh
./install.sh
```

This creates the application environment and installs `jlab` in `~/.local/bin`. Add that directory to your shell's PATH if needed. Keep this repository in place.

## Run

```sh
cd ~/dev/my-project
jlab start                         # Use the current directory as the root
jlab status
jlab url
jlab logs --follow
jlab restart                       # Keep the previous root and port
jlab restart --root ~/dev/my-project
jlab stop                          # Stop Lab and its running kernels
jlab help                          # Show all commands
```

Open the printed URL in your browser. Lab runs in the background at `127.0.0.1:8888`. Use `--root` or `--port` with `start` or `restart` to change these options.

## Add a project kernel

Run from your project directory:

```sh
uv add --dev ipykernel
jlab kernel add my-project --python .venv/bin/python
jlab kernel list
```

Select **Python (my-project)** in the notebook. Install project libraries in that environment.

```sh
jlab kernel add my-project --python .venv/bin/python --replace
jlab kernel remove my-project
```

Register again if the environment moves. Removal only deletes this instance's registration; global kernels and project environments stay intact. For widget layouts, also install `ipywidgets` in the project.

## Customize

Change shortcuts and preferences in **Settings → Settings Editor**. Settings are saved under `config/lab/user-settings/`; commit them to reuse your setup. Server settings live in `config/jupyter_server_config.py`. Local runtime data stays in ignored `.state/`.

Ruff organizes imports and formats Python cells. Basedpyright uses basic type checking and discovers `.venv` in the startup root. Its environment applies to the whole instance; changing notebook kernels does not change it. Without a project `.venv`, it uses the application environment.

Manage extensions from this repository:

```sh
uv add <extension-package>
uv remove <extension-package>
jlab restart
```

Commit `pyproject.toml` and `uv.lock` after dependency changes. Reload the browser after changing extensions or settings.

## Checks

```sh
.venv/bin/python -m unittest discover -s tests -v
bash -n bin/jlab install.sh
```
