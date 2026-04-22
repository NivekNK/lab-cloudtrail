{
  description = "CloudTrail Ingestion con UV y Nix Multiplataforma";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    # Herramienta útil para manejar múltiples sistemas de forma limpia
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    # Esta función genera automáticamente las salidas para cada sistema listado
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = [
            pkgs.python311
            pkgs.uv
            pkgs.awscli2
          ];

          shellHook = ''
            echo "--- Entorno CloudTrail Normalizado ($system) ---"
            
            # Crear venv si no existe
            if [ ! -d ".venv" ]; then
              echo "Creando entorno virtual con uv para $system..."
              uv venv
            fi
            
            # Sincronizar dependencias (uv pip install es muy rápido)
            source .venv/bin/activate
            uv pip install boto3 mysql-connector-python
            
            echo "Listo: Usa 'python ingest_cloudtrail.py --days X'"
          '';
        };
      }
    );
}
