#!/usr/bin/env python3
"""
CloudTrail Ingestion Script v2 - Curso "AWS API Under the Microscope"
Mejoras: logging, metricas, validacion, extraccion de TLS details
"""
import boto3
import mysql.connector
from mysql.connector import Error as MySQLError
import json
import argparse
import traceback
import sys
import logging
import time
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

# ============================================
# CONFIGURACION DE LOGGING
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('cloudtrail_ingest')

# ============================================
# CONFIGURACION DE BASE DE DATOS
# ============================================
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'nivek',
    'password': '1234',
    'database': 'cloudtrail_relational',
    'autocommit': False,
    'buffered': True,
    'connection_timeout': 30,
    'use_pure': False
}

class IngestionMetrics:
    """Metricas de rendimiento de la ingestion"""
    def __init__(self):
        self.start_time = time.time()
        self.events_processed = 0
        self.events_failed = 0
        self.events_skipped = 0
        self.services_seen = set()
        self.errors_seen = set()
    
    @property
    def elapsed_seconds(self):
        return time.time() - self.start_time
    
    @property
    def events_per_second(self):
        elapsed = self.elapsed_seconds
        return self.events_processed / elapsed if elapsed > 0 else 0
    
    def summary(self):
        return (f"\n{'='*50}\n"
                f"RESUMEN DE INGESTION\n"
                f"{'='*50}\n"
                f"Eventos procesados:  {self.events_processed:,}\n"
                f"Eventos fallidos:    {self.events_failed:,}\n"
                f"Eventos omitidos:    {self.events_skipped:,}\n"
                f"Servicios detectados: {len(self.services_seen)}\n"
                f"Errores distintos:   {len(self.errors_seen)}\n"
                f"Tiempo transcurrido: {self.elapsed_seconds:.1f}s\n"
                f"Velocidad:           {self.events_per_second:.1f} evt/s\n"
                f"{'='*50}")


@contextmanager
def managed_db_connection(db_config):
    """Context manager para conexion con reintentos"""
    conn = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            cfg = db_config.copy()
            db_name = cfg.pop('database')
            conn = mysql.connector.connect(**cfg)
            cursor = conn.cursor(buffered=True)
            cursor.execute(f"USE {db_name}")
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute("SET SESSION sql_mode = 'ALLOW_INVALID_DATES'")
            yield conn, cursor
            break
        except MySQLError as e:
            logger.error(f"Intento {attempt + 1}/{max_retries} fallido: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)
    finally:
        if conn and conn.is_connected():
            conn.close()
            logger.debug("Conexion cerrada")


def manage_partitions(cursor, db_name, table, target_date):
    """Estrategia REORGANIZE para permitir ingestas en cualquier orden cronologico"""
    p_name = f"p{target_date.strftime('%Y%m%d')}"
    next_day = target_date + timedelta(days=1)
    limit_ts = int(datetime.combine(next_day, datetime.min.time())
                   .replace(tzinfo=timezone.utc).timestamp())
    
    cursor.execute(
        f"SELECT PARTITION_NAME FROM information_schema.partitions "
        f"WHERE table_name = '{table}' AND table_schema = '{db_name}' LIMIT 1"
    )
    res = cursor.fetchone()
    
    if res and res[0] is None:
        logger.info(f"Inicializando particionamiento en {table}...")
        cursor.execute(
            f"ALTER TABLE {table} PARTITION BY RANGE (UNIX_TIMESTAMP(event_time)) "
            f"(PARTITION p_max VALUES LESS THAN MAXVALUE)"
        )
    
    cursor.execute(
        f"SELECT COUNT(*) FROM information_schema.partitions "
        f"WHERE table_name = '{table}' AND partition_name = '{p_name}' "
        f"AND table_schema = '{db_name}'"
    )
    if cursor.fetchone()[0] == 0:
        logger.info(f"Creando particion {p_name} en {table}...")
        cursor.execute(
            f"ALTER TABLE {table} REORGANIZE PARTITION p_max INTO "
            f"(PARTITION {p_name} VALUES LESS THAN ({limit_ts}), "
            f"PARTITION p_max VALUES LESS THAN MAXVALUE)"
        )


def get_id(cursor, table, unique_col, value):
    """Para tablas maestras de una sola columna"""
    if value is None:
        return None
    cursor.execute(f"INSERT IGNORE INTO {table} ({unique_col}) VALUES (%s)", (value,))
    cursor.execute(f"SELECT id FROM {table} WHERE {unique_col} = %s", (value,))
    result = cursor.fetchone()
    return result[0] if result else None


def get_complex_id(cursor, table, unique_cols, data):
    """Para identidades y emisores con llaves compuestas"""
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    cursor.execute(
        f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
        list(data.values())
    )
    
    where_parts = []
    params = []
    for k in unique_cols:
        val = data.get(k)
        if val is None:
            where_parts.append(f"{k} IS NULL")
        else:
            where_parts.append(f"{k} = %s")
            params.append(val)
    
    where_clause = " AND ".join(where_parts)
    cursor.execute(
        f"SELECT id FROM {table} WHERE {where_clause} LIMIT 1",
        params
    )
    res = cursor.fetchone()
    return res[0] if res else None


def extract_tls_fingerprint(tls_details):
    """Extrae un fingerprint del TLS para identificar clientes"""
    if not tls_details:
        return None
    tls = json.loads(tls_details) if isinstance(tls_details, str) else tls_details
    if not tls:
        return None
    cipher = tls.get('cipherSuite', 'unknown')
    version = tls.get('tlsVersion', 'unknown')
    return f"{version}:{cipher}"


def validate_event(event, ct):
    """Validacion basica de datos antes de procesar"""
    if not event.get('EventId'):
        return False, "EventId faltante"
    if not ct.get('eventTime'):
        return False, "eventTime faltante"
    if not event.get('EventSource'):
        return False, "EventSource faltante"
    return True, None


def process_day(cursor, db_name, client, target_date, max_events, metrics):
    """Procesa un dia completo de eventos CloudTrail"""
    date_str = target_date.strftime('%Y-%m-%d')
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    manage_partitions(cursor, db_name, 'events', target_date)
    manage_partitions(cursor, db_name, 'event_resources', target_date)
    
    paginator = client.get_paginator('lookup_events')
    config = {'MaxItems': max_events} if max_events else {}
    
    batch_insert_resources = []
    count = 0
    
    for page in paginator.paginate(StartTime=start_dt, EndTime=end_dt, PaginationConfig=config):
        for event in page['Events']:
            try:
                ct = json.loads(event.get('CloudTrailEvent') or '{}')
                
                # Validacion
                valid, error = validate_event(event, ct)
                if not valid:
                    logger.debug(f"Evento invalido: {error}")
                    metrics.events_skipped += 1
                    continue
                
                # Limpieza de fechas
                event_time_obj = event.get('EventTime')
                clean_time = str(ct.get('eventTime') or event_time_obj).replace('T', ' ').replace('Z', '')
                epoch_time = int(event_time_obj.timestamp()) if isinstance(event_time_obj, datetime) else None
                
                # Normalizacion de Maestros
                name_id = get_id(cursor, 'event_names', 'name', event.get('EventName'))
                source_id = get_id(cursor, 'event_sources', 'source', event.get('EventSource'))
                region_id = get_id(cursor, 'regions', 'name', ct.get('awsRegion'))
                agent_id = get_id(cursor, 'user_agents', 'agent', ct.get('userAgent'))
                error_id = get_id(cursor, 'error_codes', 'code', ct.get('errorCode'))
                type_id = get_id(cursor, 'event_types', 'name', ct.get('eventType'))
                cat_id = get_id(cursor, 'event_categories', 'name', ct.get('eventCategory'))
                
                ui_raw = ct.get('userIdentity') or {}
                invoker_id = get_id(cursor, 'invocation_sources', 'invoker', ui_raw.get('invokedBy'))
                
                # Identidades
                identity_id = get_complex_id(
                    cursor, 'identities',
                    ['principal_id', 'arn', 'access_key_id'],
                    {
                        'user_name': event.get('Username'),
                        'type': ui_raw.get('type'),
                        'principal_id': ui_raw.get('principalId'),
                        'arn': ui_raw.get('arn'),
                        'account_id': ui_raw.get('accountId'),
                        'access_key_id': event.get('AccessKeyId'),
                        'invoker_id': invoker_id
                    }
                )
                
                # Emisores
                sc = ui_raw.get('sessionContext') or {}
                issuer = sc.get('sessionIssuer') or {}
                issuer_id = None
                if issuer.get('arn') or issuer.get('principalId'):
                    issuer_id = get_complex_id(
                        cursor, 'issuers',
                        ['principal_id', 'arn'],
                        {
                            'type': issuer.get('type'),
                            'principal_id': issuer.get('principalId'),
                            'arn': issuer.get('arn'),
                            'user_name': issuer.get('userName'),
                            'account_id': issuer.get('accountId')
                        }
                    )
                
                # Insercion de Evento
                attr = sc.get('attributes') or {}
                params = ct.get('requestParameters') or {}
                
                # Normalizacion de readOnly (puede venir como string "true" o boolean)
                read_only_val = event.get('ReadOnly')
                read_only = 1 if read_only_val in [True, "true", "True", "TRUE"] else 0
                
                cursor.execute("""
                    INSERT IGNORE INTO events 
                    (event_id, event_time, event_time_epoch, event_name_id, source_id, region_id,
                     identity_id, issuer_id, user_agent_id, error_code_id, type_id,
                     category_id, request_id, shared_event_id, recipient_account_id,
                     source_ip, vpc_endpoint_id, event_version, read_only, management_event,
                     mfa_authenticated, session_creation_date, include_all_instances,
                     request_parameters, response_elements, additional_event_data,
                     service_event_details, tls_details, error_message)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event.get('EventId'), clean_time, epoch_time, name_id, source_id, region_id,
                    identity_id, issuer_id, agent_id, error_id, type_id, cat_id,
                    ct.get('requestID'), ct.get('sharedEventID'), ct.get('recipientAccountId'),
                    ct.get('sourceIPAddress'), ct.get('vpcEndpointId'), ct.get('eventVersion'),
                    read_only,
                    1 if ct.get('managementEvent') is True else 0,
                    1 if attr.get('mfaAuthenticated') == "true" else 0,
                    attr.get('creationDate', '').replace('T', ' ').replace('Z', '') or None,
                    1 if params.get('includeAllInstances') is True else 0,
                    json.dumps(params, ensure_ascii=False),
                    json.dumps(ct.get('responseElements'), ensure_ascii=False),
                    json.dumps(ct.get('additionalEventData'), ensure_ascii=False),
                    json.dumps(ct.get('serviceEventDetails'), ensure_ascii=False),
                    json.dumps(ct.get('tlsDetails'), ensure_ascii=False),
                    ct.get('errorMessage')
                ))
                
                # Recursos (batch insert optimizado)
                all_resources = event.get('Resources') or []
                if 'resources' in ct:
                    all_resources.extend(ct['resources'])
                
                for res in all_resources:
                    batch_insert_resources.append((
                        event.get('EventId'), clean_time,
                        res.get('ResourceType') or res.get('type'),
                        res.get('ResourceName') or res.get('ARN'),
                        res.get('accountId')
                    ))
                
                # Metricas
                metrics.events_processed += 1
                metrics.services_seen.add(event.get('EventSource', 'unknown'))
                if ct.get('errorCode'):
                    metrics.errors_seen.add(ct['errorCode'])
                
                count += 1
                
                # Flush de recursos cada 500 eventos
                if len(batch_insert_resources) >= 500:
                    cursor.executemany("""
                        INSERT IGNORE INTO event_resources 
                        (event_id, event_time, resource_type, resource_name, account_id)
                        VALUES (%s, %s, %s, %s, %s)
                    """, batch_insert_resources)
                    batch_insert_resources = []
                
            except Exception as e:
                metrics.events_failed += 1
                logger.error(f"Error procesando evento {event.get('EventId', 'N/A')}: {e}")
                continue
    
    # Flush final de recursos
    if batch_insert_resources:
        cursor.executemany("""
            INSERT IGNORE INTO event_resources 
            (event_id, event_time, resource_type, resource_name, account_id)
            VALUES (%s, %s, %s, %s, %s)
        """, batch_insert_resources)
    
    # Log de ingestion
    cursor.execute(
        "INSERT INTO ingestion_log (ingested_date, execution_time) VALUES (%s, NOW())",
        (date_str,)
    )
    
    return count


def main():
    parser = argparse.ArgumentParser(description='CloudTrail Ingestion v2 - Curso AWS API')
    parser.add_argument('--days', type=int, default=1, help='Dias hacia atras a procesar')
    parser.add_argument('--max', type=int, default=None, help='Max eventos por dia')
    parser.add_argument('--dry-run', action='store_true', help='Simular sin escribir')
    parser.add_argument('--force', action='store_true', help='Reprocesar sin preguntar')
    args = parser.parse_args()
    
    cfg = DB_CONFIG.copy()
    db_name = cfg.pop('database')
    
    try:
        with managed_db_connection(DB_CONFIG) as (conn, cursor):
            cursor.execute(f"USE {db_name}")
            client = boto3.client('cloudtrail')
            today = datetime.now(timezone.utc).date()
            metrics = IngestionMetrics()
            
            for i in range(args.days, -1, -1):
                target_date = today - timedelta(days=i)
                date_str = target_date.strftime('%Y-%m-%d')
                
                # Verificar si ya fue ingestado
                cursor.execute(
                    "SELECT 1 FROM ingestion_log WHERE ingested_date = %s",
                    (date_str,)
                )
                if cursor.fetchone() and not args.force:
                    logger.warning(f"{date_str} ya existe. Usa --force para reprocesar.")
                    continue
                
                if args.force:
                    p_name = f"p{date_str.replace('-', '')}"
                    try:
                        cursor.execute(f"ALTER TABLE events TRUNCATE PARTITION {p_name}")
                        cursor.execute(f"ALTER TABLE event_resources TRUNCATE PARTITION {p_name}")
                        cursor.execute(
                            "DELETE FROM ingestion_log WHERE ingested_date = %s",
                            (date_str,)
                        )
                        conn.commit()
                    except Exception:
                        cursor.execute(
                            "DELETE FROM ingestion_log WHERE ingested_date = %s",
                            (date_str,)
                        )
                        conn.commit()
                
                logger.info(f"{'='*50}")
                logger.info(f"Procesando {date_str}")
                logger.info(f"{'='*50}")
                
                try:
                    total = process_day(cursor, db_name, client, target_date, args.max, metrics)
                    if not args.dry_run:
                        conn.commit()
                    logger.info(f"Exito: {total:,} eventos procesados.")
                except Exception:
                    conn.rollback()
                    traceback.print_exc()
            
            # Resumen final
            logger.info(metrics.summary())
            
            # Estadisticas adicionales
            cursor.execute("SELECT COUNT(*) FROM events")
            total_db = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT source_id) FROM events")
            total_services = cursor.fetchone()[0]
            logger.info(f"Total en base de datos: {total_db:,} eventos de {total_services} servicios")
    
    except KeyboardInterrupt:
        logger.warning("Interrupcion manual detectada.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

