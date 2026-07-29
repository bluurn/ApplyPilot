{
  description = "ApplyPilot development shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python312;
      pythonEnv = python.withPackages (ps: with ps; [
        pytest
        pyyaml
      ]);
    in
    {
      devShells.${system}.default = pkgs.mkShell {
        packages = with pkgs; [
          pythonEnv
          uv
          ruff
          pyright
          just
          git
          chromium
          playwright-driver
          pkg-config
          gcc

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

        shellHook = ''
          export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
          export CHROME_PATH="${pkgs.chromium}/bin/chromium"
          export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="$CHROME_PATH"
          export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
          export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
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
          ]}:''${LD_LIBRARY_PATH:-}"

          echo "ApplyPilot development shell"
          echo "Python: $(python --version 2>&1)"
          echo "pytest: $(pytest --version 2>&1)"
          echo "Run 'uv sync --extra dev' to install the full project into .venv."
        '';
      };
    };
}
