#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# Devcontainer shell initializer
#   - Prepares persistent Bash and Zsh configs in the mounted cache volume
#   - Ensures history and user tweaks survive container rebuilds
# ------------------------------------------------------------------------------

USERNAME=${USERNAME:-vscode}
DEV_CACHE_DIR=${DEV_CACHE_DIR:-/fred-dev-cache}

# --- Create directories --------------------------------------------------------
sudo mkdir -p ${DEV_CACHE_DIR}/{bash,zsh,commandhistory}
sudo chown -R $(id -u):$(id -g) ${DEV_CACHE_DIR}

# --- Bash persistent config ---------------------------------------------------
if [ ! -f ${DEV_CACHE_DIR}/bash/.bashrc ]; then
  cat > ${DEV_CACHE_DIR}/bash/.bashrc <<'EOF'
# Persistent Bash configuration
export HISTFILE="${DEV_CACHE_DIR}/commandhistory/.bash_history"
export PROMPT_COMMAND="history -a; history -n"
export HISTCONTROL=ignoredups:erasedups
export HISTSIZE=10000
export HISTFILESIZE=20000
EOF
fi

# Ensure main bashrc sources it once
if ! grep -q "source ${DEV_CACHE_DIR}/bash/.bashrc" /home/${USERNAME}/.bashrc; then
  {
    echo ""
    echo "# Load persistent devcontainer Bash config"
    echo "if [ -f ${DEV_CACHE_DIR}/bash/.bashrc ]; then"
    echo "  source ${DEV_CACHE_DIR}/bash/.bashrc"
    echo "fi"
  } | sudo tee -a /home/${USERNAME}/.bashrc > /dev/null
fi

# --- Zsh persistent config ----------------------------------------------------
if [ ! -f ${DEV_CACHE_DIR}/zsh/.zshrc ]; then
  cat > ${DEV_CACHE_DIR}/zsh/.zshrc <<'EOF'
# Persistent Zsh configuration
export HISTFILE="${DEV_CACHE_DIR}/commandhistory/.zsh_history"
setopt hist_ignore_dups hist_reduce_blanks
setopt share_history            # merge histories between terminals
EOF
fi

# Ensure main zshrc sources it once
if ! grep -q "source ${DEV_CACHE_DIR}/zsh/.zshrc" /home/${USERNAME}/.zshrc; then
  {
    echo ""
    echo "# Load persistent devcontainer Zsh config"
    echo "if [ -f ${DEV_CACHE_DIR}/zsh/.zshrc ]; then"
    echo "  source ${DEV_CACHE_DIR}/zsh/.zshrc"
    echo "fi"
  } | sudo tee -a /home/${USERNAME}/.zshrc > /dev/null
fi

echo "✅ Shell initialization complete for user ${USERNAME}"
