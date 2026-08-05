{
  description = "ApplyPilot job-search automation";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      python = pkgs.python312;
      pythonEnv = python.withPackages (
        ps: with ps; [
          pytest
          pyyaml
        ]
      );
      applypilot = python.pkgs.buildPythonApplication {
        pname = "applypilot";
        version = "0.3.0";
        pyproject = true;
        src = ./.;

        build-system = with python.pkgs; [
          hatchling
        ];

        dependencies = with python.pkgs; [
          beautifulsoup4
          httpx
          jobspy
          pandas
          playwright
          pyyaml
          python-dotenv
          rich
          typer
        ];

        nativeBuildInputs = [
          pkgs.makeWrapper
        ];

        postFixup = ''
          wrapProgram "$out/bin/applypilot" \
            --prefix PATH : "${
              pkgs.lib.makeBinPath [
                pkgs.chromium
                pkgs.nodejs
              ]
            }" \
            --set CHROME_PATH "${pkgs.chromium}/bin/chromium" \
            --set PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH "${pkgs.chromium}/bin/chromium" \
            --set PLAYWRIGHT_BROWSERS_PATH "${pkgs.playwright-driver.browsers}" \
            --prefix LD_LIBRARY_PATH : "${
              pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.zlib
              ]
            }"
        '';

        nativeCheckInputs = with python.pkgs; [
          pytest
        ];

        checkPhase = ''
          runHook preCheck
          pytest -q
          runHook postCheck
        '';

        pythonImportsCheck = [
          "applypilot"
        ];
      };
    in
    {
      formatter.${system} = pkgs.writeShellApplication {
        name = "applypilot-format";
        runtimeInputs = [ pkgs.nixfmt-rfc-style ];
        text = ''
          if [ "$#" -eq 0 ]; then
            set -- flake.nix
          fi
          exec nixfmt "$@"
        '';
      };

      packages.${system} = {
        inherit applypilot;
        default = applypilot;
      };

      apps.${system}.default = {
        type = "app";
        program = "${applypilot}/bin/applypilot";
      };

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

        shellHook = ''
          export UV_PROJECT_ENVIRONMENT="$PWD/.venv"
          export PYTHONPATH="$PWD/src:''${PYTHONPATH:-}"
          export CHROME_PATH="${pkgs.chromium}/bin/chromium"
          export PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH="$CHROME_PATH"
          export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
          export LD_LIBRARY_PATH="${
            pkgs.lib.makeLibraryPath [
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
            ]
          }:''${LD_LIBRARY_PATH:-}"

          if [ -f "$PWD/.venv/bin/activate" ]; then
            source "$PWD/.venv/bin/activate"
          fi

          echo "ApplyPilot development shell"
          echo "Python: $(python --version 2>&1)"
          echo "pytest: $(pytest --version 2>&1)"
          echo "Source tree: $PWD/src"
          echo "Run 'uv sync --extra dev' to install the full project into .venv."

          if [ -f "$PWD/.venv/bin/python" ] && ! "$PWD/.venv/bin/python" -c "import jobspy" 2>/dev/null; then
            echo "Installing python-jobspy into .venv (required for LinkedIn/Indeed)..."
            uv pip install --python "$PWD/.venv/bin/python" --no-deps python-jobspy
            uv pip install --python "$PWD/.venv/bin/python" pydantic tls-client requests markdownify regex
          fi
        '';
      };
    };
}
