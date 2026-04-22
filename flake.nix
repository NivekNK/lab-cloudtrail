{
  description = "CloudTrail Ingestion con UV y Nix";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }: 
    let
      system = "x86_64-linux"; # Cámbialo si usas ARM/Mac
      pkgs = import nixpkgs { inherit system; };
    in {
      devShells.${system}.default = pkgs.mkShell {
        buildInputs = [
          pkgs.python311
          pkgs.uv         # El gestor ultra-rápido de Python
          pkgs.awscli2
        ];

		shellHook = ''
          echo "--- Entorno CloudTrail Normalizado ---"
          if [ ! -d ".venv" ]; then
            echo "Creando entorno virtual con uv..."
            uv venv
          fi
          source .venv/bin/activate
          
          # Añadimos la nueva dependencia aquí
          echo "Sincronizando dependencias..."
          uv pip install boto3 mysql-connector-python python-dotenv
          
          echo "Listo: Usa 'python ingest_cloudtrail.py --days X'"
        '';
      };
    };
}
