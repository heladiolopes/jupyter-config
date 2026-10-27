import os
import sys
from pathlib import Path

c = get_config()  # noqa: F821
c.ServerApp.ip = "127.0.0.1"
c.ServerApp.open_browser = False
c.ServerApp.port_retries = 0

# The launcher starts the server in its chosen root directory. Use that
# project's .venv for import resolution while keeping LSP in the application.
application_bin = Path(sys.executable).parent
project_venv = Path.cwd() / ".venv"
has_project_venv = (project_venv / "pyvenv.cfg").is_file() and os.access(
    project_venv / "bin/python", os.X_OK
)
python_bin = project_venv / "bin" if has_project_venv else application_bin
c.LanguageServerManager.language_servers = {
    "basedpyright": {
        "version": 2,
        "argv": [str(application_bin / "basedpyright-langserver"), "--stdio"],
        "languages": ["python"],
        "mime_types": ["text/x-python", "text/python"],
        "display_name": "Basedpyright (startup environment)",
        "requires_documents_on_disk": False,
        "env": {
            "PATH": str(python_bin) + os.pathsep + os.environ.get("PATH", ""),
            "VIRTUAL_ENV": str(project_venv) if has_project_venv else sys.prefix,
        },
    }
}
