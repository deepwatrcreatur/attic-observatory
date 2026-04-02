{
  description = "attic-observatory: lightweight Attic cache dashboard";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachSystem
      [
        "x86_64-linux"
        "aarch64-linux"
      ]
      (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          attic-observatory = pkgs.stdenvNoCC.mkDerivation {
            pname = "attic-observatory";
            version = "0.1.0";
            src = ./.;

            installPhase = ''
              runHook preInstall
              mkdir -p $out/bin $out/share/attic-observatory
              cp app.py $out/share/attic-observatory/app.py
              cp README.md $out/share/attic-observatory/README.md
              cat > $out/bin/attic-observatory <<EOF
              #!${pkgs.runtimeShell}
              exec ${pkgs.python3}/bin/python3 $out/share/attic-observatory/app.py "\$@"
              EOF
              chmod +x $out/bin/attic-observatory
              runHook postInstall
            '';
          };
        in
        {
          packages.default = attic-observatory;

          apps.default = {
            type = "app";
            program = "${attic-observatory}/bin/attic-observatory";
            meta.description = "Run the attic-observatory dashboard";
          };

          checks.unit-tests =
            pkgs.runCommand "attic-observatory-unit-tests" { nativeBuildInputs = [ pkgs.python3 ]; }
              ''
                cd ${self}
                python3 -m unittest -v test_app.py
                touch $out
              '';

          devShells.default = pkgs.mkShell {
            buildInputs = [
              pkgs.python3
              pkgs.sqlite
            ];
          };

          formatter = pkgs.nixfmt-rfc-style;
        }
      );
}
