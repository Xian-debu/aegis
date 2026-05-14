#!/usr/bin/env bash
# AEGIS Installation Script
# Run: bash install.sh [--prefix ~/.claude]
set -e

AEGIS_HOME="${AEGIS_HOME:-$HOME/.claude}"
PREFIX="${1:-$AEGIS_HOME}"

echo "═══ AEGIS Installer ═══"
echo "Install path: $PREFIX"
echo ""

# Create directories
mkdir -p "$PREFIX/aegis"/{bridges,tests}
mkdir -p "$PREFIX/guardian"

# Copy AEGIS package
cp "$(dirname "$0")"/__init__.py "$PREFIX/aegis/"
cp "$(dirname "$0")"/config.py "$PREFIX/aegis/"
cp "$(dirname "$0")"/cli.py "$PREFIX/aegis/"
cp "$(dirname "$0")"/monitor.py "$PREFIX/aegis/"
cp "$(dirname "$0")"/remediate.py "$PREFIX/aegis/"
cp "$(dirname "$0")"/bridges/*.py "$PREFIX/aegis/bridges/"
cp "$(dirname "$0")"/tests/*.py "$PREFIX/aegis/tests/"

echo "✓ AEGIS Python package installed to $PREFIX/aegis/"

# Copy AEGIS scripts (v2.0.0 guardrail system)
mkdir -p "$PREFIX/scripts"
cp "$(dirname "$0")"/scripts/* "$PREFIX/scripts/"
echo "✓ AEGIS scripts installed to $PREFIX/scripts/"

# Create aegis wrapper script
cat > "$PREFIX/aegis/aegis" << 'WRAPPER'
#!/usr/bin/env python3
import sys; sys.path.insert(0, 'DIR')
from aegis.cli import main; main()
WRAPPER
sed -i "s|DIR|$PREFIX|g" "$PREFIX/aegis/aegis"
chmod +x "$PREFIX/aegis/aegis"

# Symlink to PATH
if [ -w /usr/local/bin ]; then
    ln -sf "$PREFIX/aegis/aegis" /usr/local/bin/aegis
    echo "✓ Symlinked to /usr/local/bin/aegis"
else
    echo "⚠ Cannot write to /usr/local/bin. Add to PATH manually:"
    echo "  export PATH=\"$PREFIX/aegis:\$PATH\""
fi

echo ""
echo "═══ Installation Complete ═══"
echo ""
echo "Next steps:"
echo "  1. Set up environment:"
echo "     export AEGIS_HOME=$AEGIS_HOME"
echo "  2. (Optional) Install Guardian daemon:"
echo "     bash $PREFIX/aegis/install_guardian.sh"
echo "  3. Test:"
echo "     aegis status"
echo ""
echo "Configure by editing $PREFIX/aegis/config.py"
echo "or set environment variables (see config.py for options)."
