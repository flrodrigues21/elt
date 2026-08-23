#!/bin/bash
set -e

# ------------------------------------------------------------------
# JupyterLab entrypoint for ELT Lab
# Validates required env vars, generates password hash, sets up
# directories, and starts JupyterLab — never runs as root.
# ------------------------------------------------------------------

echo "=== ELT Lab — JupyterLab ==="

# --- Validate required variables ---
: "${JUPYTER_PASSWORD:?ERROR: JUPYTER_PASSWORD is not set. Add it to .env}"

# JUPYTER_USERNAME is optional (defaults to jovyan for container identity)
JUPYTER_USERNAME="${JUPYTER_USERNAME:-jovyan}"
export JUPYTER_USERNAME

# --- Generate password hash (bcrypt via jupyter_server.auth) ---
HASH=$(python3 -c "
from jupyter_server.auth import passwd
import os
pw = os.environ['JUPYTER_PASSWORD']
print(passwd(pw, algorithm='sha256'))
")

# --- Write jupyter_server_config.py at runtime ---
JUPYTER_CONFIG_DIR="${HOME}/.jupyter"
mkdir -p "${JUPYTER_CONFIG_DIR}"

cat > "${JUPYTER_CONFIG_DIR}/jupyter_server_config.py" <<JUPYTERCONF
c = get_config()
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = 8888
c.ServerApp.open_browser = False
c.ServerApp.allow_root = False
c.ServerApp.password = '${HASH}'
c.ServerApp.terminado_settings = {'shell_command': ['/bin/bash']}
c.ServerApp.extra_static_paths = []
c.ServerApp.notebook_dir = '/home/jovyan/work'
JUPYTERCONF

# --- Ensure correct permissions ---
chown -R "${NB_UID}:${NB_GID}" "${JUPYTER_CONFIG_DIR}" 2>/dev/null || true
chmod 600 "${JUPYTER_CONFIG_DIR}/jupyter_server_config.py"

# --- Ensure work directories exist ---
mkdir -p /home/jovyan/work/ELT /home/jovyan/work/Data\ Lab/datasets
chown -R "${NB_UID}:${NB_GID}" /home/jovyan/work

echo "User: ${JUPYTER_USERNAME}"
echo "URL:  http://localhost:${JUPYTER_PORT:-8888}"
echo "Dir:  /home/jovyan/work"
echo "Note: the JupyterLab login screen requires ONLY the password."

exec start-notebook.py \
    --NotebookApp.notebook_dir='/home/jovyan/work' \
    --ServerApp.terminado_settings='{"shell_command": ["/bin/bash"]}'
