{ pkgs, lib, ... }:

let
  playwrightLibs = lib.makeLibraryPath [
    pkgs.stdenv.cc.cc.lib
    pkgs.zlib
    pkgs.glib
    pkgs.nss
    pkgs.nspr
    pkgs.atk
    pkgs.at-spi2-atk
    pkgs.cups
    pkgs.dbus
    pkgs.expat
    pkgs.libdrm
    pkgs.libxkbcommon
    pkgs.mesa
    pkgs.pango
    pkgs.cairo
    pkgs.alsa-lib
    pkgs.gtk3
    pkgs.libgbm
    pkgs.xorg.libX11
    pkgs.xorg.libXcomposite
    pkgs.xorg.libXdamage
    pkgs.xorg.libXext
    pkgs.xorg.libXfixes
    pkgs.xorg.libXrandr
  ];
in
{
  packages = with pkgs; [
    uv
    ruff
    pyright
    just
    git
    chromium
    playwright-driver
    pkg-config
    gcc
    zlib
    stdenv.cc.cc.lib
    glib
    nss
    nspr
    atk
    at-spi2-atk
    cups
    dbus
    expat
    libdrm
    libxkbcommon
    mesa
    pango
    cairo
    alsa-lib
    gtk3
    libgbm
    xorg.libX11
    xorg.libXcomposite
    xorg.libXdamage
    xorg.libXext
    xorg.libXfixes
    xorg.libXrandr
  ];

  env = {
    CHROME_PATH = "${pkgs.chromium}/bin/chromium";
    PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = "${pkgs.chromium}/bin/chromium";
    PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.browsers}";
  };

  enterShell = ''
    export UV_PROJECT_ENVIRONMENT="$DEVENV_ROOT/.venv"
    export PYTHONPATH="$DEVENV_ROOT/src:''${PYTHONPATH:-}"
    export LD_LIBRARY_PATH="${playwrightLibs}:''${LD_LIBRARY_PATH:-}"

    if [ -f "$DEVENV_ROOT/.venv/bin/activate" ]; then
      source "$DEVENV_ROOT/.venv/bin/activate"
    fi

    echo "ApplyPilot development shell"
    echo "Python: $(python --version 2>&1)"
    echo "Source tree: $DEVENV_ROOT/src"
    echo "Run 'uv sync --extra dev' to install the full project into .venv."

    if [ -f "$DEVENV_ROOT/.venv/bin/python" ] && ! "$DEVENV_ROOT/.venv/bin/python" -c "import jobspy" 2>/dev/null; then
      echo "Installing python-jobspy into .venv (required for LinkedIn/Indeed)..."
      uv pip install --python "$DEVENV_ROOT/.venv/bin/python" --no-deps python-jobspy
      uv pip install --python "$DEVENV_ROOT/.venv/bin/python" pydantic tls-client requests markdownify regex
    fi
  '';
}
