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
          pydantic
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

      # NixOS module — add to your configuration.nix inputs then:
      #   programs.applypilot.enable = true;
      nixosModules.default =
        { config, lib, ... }:
        {
          options.programs.applypilot.enable = lib.mkEnableOption "ApplyPilot job-search automation";

          config = lib.mkIf config.programs.applypilot.enable {
            environment.systemPackages = [ applypilot ];
          };
        };
    };
}
