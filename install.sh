#!/usr/bin/env bash
# install.sh — Install hermes-evol plugin into a Hermes Agent profile.
#
# Usage:
#   ./install.sh                           # install into active/default profile
#   ./install.sh conductor                 # install into conductor profile
#   HERMES_HOME=/custom/path ./install.sh  # custom Hermes home
#
# The plugin is loaded by Hermes at gateway startup when the profile's
# config.yaml includes plugins.enabled containing "hermes-evol".

set -euo pipefail

PROFILE="${1:-}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

if [ -n "$PROFILE" ]; then
    PLUGIN_DIR="$HERMES_HOME/profiles/$PROFILE/plugins/hermes-evol"
else
    PLUGIN_DIR="$HERMES_HOME/plugins/hermes-evol"
fi

echo "Installing hermes-evol to: $PLUGIN_DIR"

# Create plugin directory
mkdir -p "$PLUGIN_DIR"

# Copy package
cp -r hermes_evol "$PLUGIN_DIR/"

# Verify critical files exist
if [ ! -f "$PLUGIN_DIR/hermes_evol/plugin.py" ]; then
    echo "ERROR: plugin.py not found — installation incomplete"
    exit 1
fi

if [ ! -f "$PLUGIN_DIR/hermes_evol/engine.py" ]; then
    echo "ERROR: engine.py not found — installation incomplete"
    exit 1
fi

echo "hermes-evol v0.2.0 installed successfully"
echo ""
echo "To enable, add to your profile config.yaml:"
echo "  plugins:"
echo "    enabled:"
echo "      - hermes-evol"
echo ""
echo "Then restart the gateway."
