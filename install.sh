#!/usr/bin/env bash
# install.sh — One-line install for agent-team protocol
# curl -fsSL https://raw.githubusercontent.com/<user>/agent-team-protocol/main/install.sh | bash

set -e

REPO_URL="${AGENT_TEAM_REPO:-https://github.com/obra/agent-team-protocol.git}"
INSTALL_DIR="${HOME}/.agent-team-protocol"
BIN_LINK="${HOME}/.local/bin/agent-team"
BIN_LINK_ALT="/usr/local/bin/agent-team"

echo "=== Agent Team Protocol Installer ==="
echo ""

# Clone or update
if [ -d "$INSTALL_DIR/.git" ]; then
  echo "→ Updating existing installation..."
  cd "$INSTALL_DIR"
  git pull --ff-only 2>/dev/null || echo "   (update skipped — local changes may exist)"
  cd - >/dev/null
else
  echo "→ Cloning to $INSTALL_DIR..."
  if [ -d "$INSTALL_DIR" ]; then
    echo "   (directory exists but is not a git clone, removing...)"
    rm -rf "$INSTALL_DIR"
  fi
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

# Ensure executable
chmod +x "$INSTALL_DIR/agent-team.sh"

# Create symlink (try user-local first, then system)
mkdir -p "${HOME}/.local/bin"
ln -sf "$INSTALL_DIR/agent-team.sh" "$BIN_LINK" 2>/dev/null || true

# Try system bin if user-local not in PATH
if ! echo "$PATH" | grep -q "${HOME}/.local/bin"; then
  # Fall back to /usr/local/bin if we have write access
  if [ -w "/usr/local/bin" ]; then
    ln -sf "$INSTALL_DIR/agent-team.sh" "$BIN_LINK_ALT" 2>/dev/null || true
  fi
fi

# Add to PATH if needed
PATH_ENTRY='export PATH="$HOME/.local/bin:$PATH"'
if [ -f "${HOME}/.bashrc" ]; then
  if ! grep -q ".local/bin" "${HOME}/.bashrc" 2>/dev/null; then
    echo "$PATH_ENTRY" >> "${HOME}/.bashrc"
    echo "→ Added ~/.local/bin to ~/.bashrc"
  fi
else
  echo "$PATH_ENTRY" > "${HOME}/.bashrc"
  echo "→ Created ~/.bashrc with PATH"
fi

echo ""
echo "=== Installation complete ==="
echo ""
echo "To start using:"
echo "  source ~/.bashrc          # (or restart terminal)"
echo "  agent-team init my-team"
echo ""
echo "For documentation: $INSTALL_DIR/PROTOCOL.md"
