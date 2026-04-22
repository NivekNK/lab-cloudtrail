# AWS CloudTrail Analysis Lab 🚀

Este laboratorio está diseñado para la ingesta, normalización y análisis técnico de eventos de **AWS CloudTrail** en una base de datos relacional (MySQL). El objetivo es transformar el JSON crudo de AWS en un esquema optimizado para auditoría, seguridad y análisis de costos.

## 📌 Requisitos Previos

Antes de comenzar, asegúrate de contar con lo siguiente:
* **Nix Package Manager**: Para la gestión de dependencias deterministas.
* **AWS CLI**: Configurado con credenciales válidas (o un archivo `.env` con las mismas).
* **MySQL Server 8.0+**: Corriendo localmente o en un contenedor.
* **Uv**: El gestor de paquetes de Python (instalado automáticamente vía Nix).

---

## 🛠️ Configuración del Entorno

### 1. Levantar el Shell de Nix
El proyecto utiliza un archivo `flake.nix` para garantizar que todos tengamos las mismas versiones de Python, AWS CLI y librerías.

```bash
nix develop
```
*Esto creará un `.venv`, instalará `boto3`, `mysql-connector-python`, `python-dotenv` y te dejará listo para operar.*

### 2. Configuración de Variables de Entorno
Copia el archivo de ejemplo y completa tus credenciales:

```bash
cp .env.example .env
```

**Campos requeridos en el `.env`:**
* `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
* `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (si aplica)
* `AWS_REGION` (por defecto `us-east-1`)

---

## 🗄️ Preparación de la Base de Datos

El script de ingesta **no crea la base de datos por ti**. Debes preparar el esquema manualmente para asegurar que los índices y particiones estén correctamente configurados.

1.  **Crear la DB**:
    ```sql
    CREATE DATABASE cloudtrail_relational;
    ```
2.  **Importar el Esquema**:
    ```bash
    mysql -u tu_usuario -p cloudtrail_relational < cloudtrail_schema.sql
    ```

---

## 🚀 Ejecución de la Ingesta

Una vez que la DB está lista y el entorno activo, puedes comenzar a poblar los datos:

### Comandos básicos:
```bash
# Ingestar los últimos 7 días
python ingest_cloudtrail.py --days 7

# Ingestar un máximo de 500 eventos (para pruebas rápidas)
python ingest_cloudtrail.py --days 1 --max 500

# Forzar reprocesamiento de un día específico
python ingest_cloudtrail.py --days 2 --force
```

### ¿Qué hace el script bajo el capó?
1.  **Auth Check**: Valida que tus credenciales de AWS no hayan expirado.
2.  **Partition Management**: Crea particiones automáticas en MySQL basadas en la fecha de los eventos (`event_time`).
3.  **Normalización**: Descompone el evento en tablas maestras (`identities`, `issuers`, `user_agents`) para evitar redundancia de datos.
4.  **Batch Insert**: Los recursos asociados se insertan en lotes de 500 para maximizar el throughput.

---

## 📂 Estructura del Proyecto

* `ingest_cloudtrail.py`: El core engine de ingesta y lógica de negocio.
* `cloudtrail_schema.sql`: Definición DDL optimizada (con soporte para tipos complejos y auditoría).
* `flake.nix`: Definición de la infraestructura como código para el entorno de desarrollo.
* `.env`: (Ignorado por Git) Tus secretos y configuración local.

---

## ⚠️ Troubleshooting Común

* **Error de Credenciales**: Si recibes un `CRITICAL | ❌ Error de Credenciales`, ejecuta `aws sso login` o actualiza tus variables en el `.env`.
* **MySQL Header Error**: Asegúrate de que el motor sea InnoDB, necesario para las llaves foráneas y el particionamiento.
* **Nix Slowdown**: La primera vez que ejecutas `nix develop` puede tardar unos minutos mientras descarga el toolchain de Python.

---

> **Propósito Académico**: Este laboratorio es una pieza de ingeniería de datos para entender la interconectividad de dominios: Infraestructura (AWS), Código (Python) y Persistencia (SQL).
