import boto3
import mysql.connector
import json
import argparse
import traceback
import sys
from datetime import datetime, timedelta, timezone

# --- CONFIGURACIÓN ---
DB_CONFIG = {
    'host': '127.0.0.1', 
    'user': 'nivek',
    'password': '1234',
    'database': 'cloudtrail_relational'
}

def manage_partitions(cursor, db_name, table, target_date):
    """Estrategia REORGANIZE para permitir ingestas en cualquier orden cronológico"""
    p_name = f"p{target_date.strftime('%Y%m%d')}"
    next_day = target_date + timedelta(days=1)
    limit_ts = int(datetime.combine(next_day, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp())

    cursor.execute(f"SELECT PARTITION_NAME FROM information_schema.partitions WHERE table_name = '{table}' AND table_schema = '{db_name}' LIMIT 1")
    res = cursor.fetchone()
    
    if res and res[0] is None:
        print(f"   [!] Inicializando particionamiento en {table}...")
        cursor.execute(f"ALTER TABLE {table} PARTITION BY RANGE (UNIX_TIMESTAMP(event_time)) (PARTITION p_max VALUES LESS THAN MAXVALUE)")

    cursor.execute(f"SELECT COUNT(*) FROM information_schema.partitions WHERE table_name = '{table}' AND partition_name = '{p_name}' AND table_schema = '{db_name}'")
    if cursor.fetchone()[0] == 0:
        print(f"   [+] Creando partición {p_name} en {table}...")
        cursor.execute(f"ALTER TABLE {table} REORGANIZE PARTITION p_max INTO (PARTITION {p_name} VALUES LESS THAN ({limit_ts}), PARTITION p_max VALUES LESS THAN MAXVALUE)")

def get_id(cursor, table, unique_col, value):
    """Para tablas maestras de una sola columna"""
    if value is None: return None
    cursor.execute(f"INSERT IGNORE INTO {table} ({unique_col}) VALUES (%s)", (value,))
    cursor.execute(f"SELECT id FROM {table} WHERE {unique_col} = %s", (value,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_complex_id(cursor, table, unique_cols, data):
    """Para identidades y emisores con llaves compuestas"""
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["%s"] * len(data))
    cursor.execute(f"INSERT IGNORE INTO {table} ({cols}) VALUES ({placeholders})", list(data.values()))
    
    # Construcción dinámica de la cláusula WHERE para manejar NULLs
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
    cursor.execute(f"SELECT id FROM {table} WHERE {where_clause} LIMIT 1", params)
    res = cursor.fetchone()
    return res[0] if res else None

def process_day(cursor, db_name, client, target_date, max_events):
    date_str = target_date.strftime('%Y-%m-%d')
    start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    manage_partitions(cursor, db_name, 'events', target_date)
    manage_partitions(cursor, db_name, 'event_resources', target_date)

    paginator = client.get_paginator('lookup_events')
    config = {'MaxItems': max_events} if max_events else {}
    
    count = 0
    for page in paginator.paginate(StartTime=start_dt, EndTime=end_dt, PaginationConfig=config):
        for event in page['Events']:
            ct = json.loads(event.get('CloudTrailEvent') or '{}')
            
            # Limpieza de fechas
            event_time_obj = event.get('EventTime')
            clean_time = str(ct.get('eventTime') or event_time_obj).replace('T', ' ').replace('Z', '')
            epoch_time = int(event_time_obj.timestamp()) if isinstance(event_time_obj, datetime) else None

            # 1. Normalización de Maestros
            name_id = get_id(cursor, 'event_names', 'name', event.get('EventName'))
            source_id = get_id(cursor, 'event_sources', 'source', event.get('EventSource'))
            region_id = get_id(cursor, 'regions', 'name', ct.get('awsRegion'))
            agent_id = get_id(cursor, 'user_agents', 'agent', ct.get('userAgent'))
            error_id = get_id(cursor, 'error_codes', 'code', ct.get('errorCode'))
            type_id = get_id(cursor, 'event_types', 'name', ct.get('eventType'))
            cat_id = get_id(cursor, 'event_categories', 'name', ct.get('eventCategory'))
            
            ui_raw = ct.get('userIdentity') or {}
            invoker_id = get_id(cursor, 'invocation_sources', 'invoker', ui_raw.get('invokedBy'))

            # 2. Identidades
            identity_id = get_complex_id(cursor, 'identities', ['principal_id', 'arn', 'access_key_id'], {
                'user_name': event.get('Username'),
                'type': ui_raw.get('type'),
                'principal_id': ui_raw.get('principalId'),
                'arn': ui_raw.get('arn'),
                'account_id': ui_raw.get('accountId'),
                'access_key_id': event.get('AccessKeyId'),
                'invoker_id': invoker_id
            })

            # 3. Emisores
            sc = ui_raw.get('sessionContext') or {}
            issuer = sc.get('sessionIssuer') or {}
            issuer_id = None
            if issuer.get('arn') or issuer.get('principalId'):
                issuer_id = get_complex_id(cursor, 'issuers', ['principal_id', 'arn'], {
                    'type': issuer.get('type'),
                    'principal_id': issuer.get('principalId'),
                    'arn': issuer.get('arn'),
                    'user_name': issuer.get('userName'),
                    'account_id': issuer.get('accountId')
                })

            # 4. Inserción de Evento Central
            attr = sc.get('attributes') or {}
            params = ct.get('requestParameters') or {}
            
            cursor.execute("""
                INSERT IGNORE INTO events 
                (event_id, event_time, event_time_epoch, event_name_id, source_id, region_id, 
                 identity_id, issuer_id, user_agent_id, error_code_id, type_id, 
                 category_id, request_id, shared_event_id, recipient_account_id, 
                 source_ip, vpc_endpoint_id, event_version, read_only, management_event, 
                 mfa_authenticated, session_creation_date, include_all_instances,
                 request_parameters, response_elements, additional_event_data, 
                 service_event_details, tls_details, error_message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                event.get('EventId'), clean_time, epoch_time, name_id, source_id, region_id,
                identity_id, issuer_id, agent_id, error_id, type_id, cat_id,
                ct.get('requestID'), ct.get('sharedEventID'), ct.get('recipientAccountId'),
                ct.get('sourceIPAddress'), ct.get('vpcEndpointId'), ct.get('eventVersion'),
                1 if event.get('ReadOnly') in [True, "true"] else 0,
                1 if ct.get('managementEvent') is True else 0,
                1 if attr.get('mfaAuthenticated') == "true" else 0,
                attr.get('creationDate', '').replace('T', ' ').replace('Z', '') or None,
                1 if params.get('includeAllInstances') is True else 0,
                json.dumps(params), json.dumps(ct.get('responseElements')),
                json.dumps(ct.get('additionalEventData')), json.dumps(ct.get('serviceEventDetails')),
                json.dumps(ct.get('tlsDetails')), ct.get('errorMessage')
            ))

            # 5. Recursos (Detalle)
            all_resources = event.get('Resources') or []
            if 'resources' in ct:
                all_resources.extend(ct['resources'])
            
            for res in all_resources:
                cursor.execute("""
                    INSERT INTO event_resources (event_id, event_time, resource_type, resource_name, account_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    event.get('EventId'), clean_time, 
                    res.get('ResourceType') or res.get('type'),
                    res.get('ResourceName') or res.get('ARN'),
                    res.get('accountId')
                ))
            count += 1
    
    cursor.execute("INSERT INTO ingestion_log (ingested_date, execution_time) VALUES (%s, NOW())", (date_str,))
    return count

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=1)
    parser.add_argument('--max', type=int, default=None)
    args = parser.parse_args()

    cfg = DB_CONFIG.copy()
    db_name = cfg.pop('database')
    
    try:
        conn = mysql.connector.connect(**cfg)
        # CRÍTICO: buffered=True soluciona el error 'Unread result found'
        cursor = conn.cursor(buffered=True)
        
        cursor.execute(f"USE {db_name}")
        cursor.execute("SET time_zone = '+00:00'")
        
        client = boto3.client('cloudtrail')
        today = datetime.now(timezone.utc).date()

        for i in range(args.days, -1, -1):
            target_date = today - timedelta(days=i)
            date_str = target_date.strftime('%Y-%m-%d')

            cursor.execute("SELECT 1 FROM ingestion_log WHERE ingested_date = %s", (date_str,))
            if cursor.fetchone():
                print(f"\n[?] {date_str} ya existe.")
                choice = input("    ¿Reprocesar [r] o Saltar [s]? ").lower()
                if choice == 'r':
                    p_name = f"p{date_str.replace('-', '')}"
                    try:
                        cursor.execute(f"ALTER TABLE events TRUNCATE PARTITION {p_name}")
                        cursor.execute(f"ALTER TABLE event_resources TRUNCATE PARTITION {p_name}")
                        cursor.execute("DELETE FROM ingestion_log WHERE ingested_date = %s", (date_str,))
                        conn.commit()
                    except:
                        cursor.execute("DELETE FROM ingestion_log WHERE ingested_date = %s", (date_str,))
                        conn.commit()
                else:
                    continue

            print(f"--- Procesando {date_str} ---")
            try:
                total = process_day(cursor, db_name, client, target_date, args.max)
                conn.commit()
                print(f"   √ Éxito: {total} eventos.")
            except Exception:
                conn.rollback()
                traceback.print_exc()

    except Exception:
        traceback.print_exc()
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    main()
