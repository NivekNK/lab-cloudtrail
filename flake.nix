{
  description = "CloudTrail Ingestion - Multiplataforma (Linux/Mac)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
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
            
            # 1. Gestión del VENV
            if [ ! -d ".venv" ]; then
              echo "Creando entorno virtual con uv..."
              uv venv
            fi
            source .venv/bin/activate
            
            # 2. Sincronización de dependencias (Aquí integramos todo)
            echo "Sincronizando toolkit de Python y Criptografía..."
            uv pip install \
              boto3 \
              mysql-connector-python \
              python-dotenv \
              awscurl

            echo "--------------------------------------------------"
            echo "Sistema detectado: $system"
            echo "Listo: Usa 'python ingest_cloudtrail.py --days X'"
            echo "Documentación disponible en AWS_HTTP_ANATOMY.md"
            echo "--------------------------------------------------"
          '';
        };
      }
    );
}
