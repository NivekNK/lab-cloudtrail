{
  description = "CloudTrail Ingestion con UV y Nix - Mac Intel";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }: 
    let
      system = "x86_64-darwin"; 
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.python311
          pkgs.uv
          pkgs.awscli2
        ];

        shellHook = ''
          echo "--- Entorno CloudTrail Normalizado (Mac Intel) ---"
          if [ ! -d ".venv" ]; then
            echo "Creando entorno virtual con uv..."
            uv venv
          fi
          source .venv/bin/activate
          
          echo "Sincronizando dependencias (incluyendo awscurl)..."
          uv pip install boto3 mysql-connector-python python-dotenv awscurl
          
          echo "--------------------------------------------------"
          echo "Listo: Usa 'python ingest_cloudtrail.py --days X'"
          echo "awscurl instalado vía uv correctamente."
          echo "--------------------------------------------------"
        '';
      };
    };
}
