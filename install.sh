#!/usr/bin/env bash
# install.sh — Install Linux Flow icons and desktop entry so it appears
# in the GNOME app launcher and dock with the correct icon.
#
# Run once after cloning: bash install.sh
# Safe to re-run (idempotent).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"
ICON_SRC="$SCRIPT_DIR/assets/linux-flow-icon.png"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
APPS_DIR="$HOME/.local/share/applications"

# --- Sanity checks ---
if [ ! -f "$VENV_PYTHON" ]; then
    echo "ERROR: venv not found at $VENV_PYTHON"
    echo "Run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# --- Install icon ---
mkdir -p "$ICON_DIR"
cp "$ICON_SRC" "$ICON_DIR/linux-flow.png"
echo "Icon installed to $ICON_DIR/linux-flow.png"

# --- Install desktop entry ---
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/linux-flow.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Linux Flow
GenericName=Voice Dictation
Comment=Voice dictation for Linux powered by Groq AI
Exec=$VENV_PYTHON $SCRIPT_DIR/main.py
Icon=linux-flow
Terminal=false
Categories=Utility;Accessibility;
Keywords=voice;dictation;speech;transcription;ai;groq;
StartupWMClass=linux-flow
EOF
echo "Desktop entry installed to $APPS_DIR/linux-flow.desktop"

# --- Refresh caches ---
if command -v update-desktop-database &>/dev/null; then
    update-desktop-database "$APPS_DIR"
fi
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo ""
echo "Done! Linux Flow will now appear in your app launcher with the correct icon."
echo "Use the 'Launch on Login' toggle in Settings → Advanced to enable autostart."
