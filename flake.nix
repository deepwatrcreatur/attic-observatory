{
  description = "attic-observatory: lightweight Attic cache dashboard";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems =
        f:
        nixpkgs.lib.genAttrs systems (
          system:
          f {
            pkgs = import nixpkgs { inherit system; };
          }
        );
    in
    {
      packages = forAllSystems (
        { pkgs }:
        {
          default = pkgs.stdenvNoCC.mkDerivation {
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
        }
      );
    };
}
