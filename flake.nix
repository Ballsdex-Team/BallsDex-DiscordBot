{
  description = "Ballsdex Discord bot";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      uv2nix,
      pyproject-nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;

      # Load a uv workspace from the workspace root.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      # Create package overlay from workspace.
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      pkgs = nixpkgs.legacyPackages.x86_64-linux;
      python = pkgs.python313;

      # Construct package set
      pythonSet =
        # Use base package set from pyproject.nix builders
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              overlay
            ]
          );

    in
    {
      # Package a virtual environment as our main application.
      #
      # Enable no optional dependencies for production build.
      packages.x86_64-linux.default = pythonSet.mkVirtualEnv "ballsdex-env" workspace.deps.default;

      # Make ballsdex runnable with `nix run`
      apps.x86_64-linux = {
        default = {
          type = "app";
          program = "${self.packages.x86_64-linux.default}/bin/ballsdex";
        };
      };

      devShells.x86_64-linux.default =
        let
          # Create an overlay enabling editable mode for all local dependencies.
          editableOverlay = workspace.mkEditablePyprojectOverlay {
            root = "$REPO_ROOT";
          };

          # Override previous set with our overrideable overlay.
          editablePythonSet = pythonSet.overrideScope (
            lib.composeManyExtensions [
              editableOverlay

              # Apply fixups for building an editable package of your workspace packages
              (final: prev: {
                ballsdex = prev.ballsdex.overrideAttrs (old: {
                  # It's a good idea to filter the sources going into an editable build
                  # so the editable package doesn't have to be rebuilt on every change.
                  src = lib.fileset.toSource {
                    root = old.src;
                    fileset = lib.fileset.unions [
                      (old.src + "/pyproject.toml")
                      (old.src + "/README.md")
                      #(old.src + "/src/hello_world/__init__.py")
                    ];
                  };

                  # Hatchling (our build system) has a dependency on the `editables` package when building editables.
                  #
                  # In normal Python flows this dependency is dynamically handled, and doesn't need to be explicitly declared.
                  # This behaviour is documented in PEP-660.
                  #
                  # With Nix the dependency needs to be explicitly declared.
                  nativeBuildInputs =
                    old.nativeBuildInputs
                    ++ final.resolveBuildSystem {
                      editables = [ ];
                    };
                });

              })
            ]
          );

          #
          # Enable all optional dependencies for development.
          virtualenv = editablePythonSet.mkVirtualEnv "ballsdex-dev-env" workspace.deps.all;

        in
        pkgs.mkShell {
          packages = [
            virtualenv
            pkgs.uv
          ];

          env = {
            # Don't create venv using uv
            UV_NO_SYNC = "1";

            # Force uv to use Python interpreter from venv
            UV_PYTHON = "${virtualenv}/bin/python";

            # Prevent uv from downloading managed Python's
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = ''
            # Undo dependency propagation by nixpkgs.
            unset PYTHONPATH

            # Get repository root using git. This is expanded at runtime by the editable `.pth` machinery.
            export REPO_ROOT=$(git rev-parse --show-toplevel)
          '';
        };
    };
}