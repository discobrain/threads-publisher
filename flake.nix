{
  description = "threads-poster — publish approved Discourse drafts to Threads";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: nixpkgs.lib.genAttrs systems (s: f nixpkgs.legacyPackages.${s});
    in
    {
      packages = forAll (pkgs: {
        default = pkgs.python3.pkgs.buildPythonApplication {
          pname = "threads-poster";
          version = "0.1.0";
          pyproject = true;
          src = ./.;
          nativeBuildInputs = [ pkgs.python3.pkgs.setuptools ];
          doCheck = false;
          # Runtime deps: stdlib only (urllib). No external Python packages.
        };
      });

      apps = forAll (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/threads-poster";
        };
        get-token = {
          type = "app";
          program = "${self.packages.${pkgs.system}.default}/bin/get-token";
        };
      });

      devShells = forAll (pkgs:
        let
          get-token = pkgs.writeShellScriptBin "get-token" ''
            exec ${pkgs.python3}/bin/python -m threads_poster.get_token "$@"
          '';
        in
        {
          default = pkgs.mkShell {
            packages = [ pkgs.python3 pkgs.jq get-token ];
            shellHook = ''
              echo "threads-poster dev shell — get-token, or: python -m threads_poster <auth-url|auth|refresh|token>"
            '';
          };
        });
    };
}
