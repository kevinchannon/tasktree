{
  description = "Task Tree e2e fixture: a tiny devShell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.05";

  outputs = { self, nixpkgs }:
    let
      forAllSystems = f: nixpkgs.lib.genAttrs
        [ "aarch64-darwin" "x86_64-darwin" "x86_64-linux" "aarch64-linux" ]
        (system: f nixpkgs.legacyPackages.${system});
    in {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShellNoCC {
          packages = [ pkgs.hello ];
          TT_NIX_FIXTURE_VAR = "from-the-flake";
          shellHook = "export TT_NIX_HOOK_VAR=from-the-hook";
        };
      });
    };
}
