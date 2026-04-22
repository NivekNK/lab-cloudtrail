DROP DATABASE IF EXISTS cloudtrail_relational;
CREATE DATABASE IF NOT EXISTS cloudtrail_relational;
USE cloudtrail_relational;

-- --- 1. TABLAS MAESTRAS ---

CREATE TABLE IF NOT EXISTS event_names (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL -- $.EventName / $.CloudTrailEvent.eventName [cite: 1, 3]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS event_sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source VARCHAR(255) UNIQUE NOT NULL -- $.EventSource / $.CloudTrailEvent.eventSource [cite: 1, 3]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_agents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    agent TEXT NOT NULL -- $.CloudTrailEvent.userAgent [cite: 3, 5]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS regions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL -- $.CloudTrailEvent.awsRegion [cite: 3]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS event_types (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL -- $.CloudTrailEvent.eventType [cite: 3, 8]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS event_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL -- $.CloudTrailEvent.eventCategory [cite: 3, 8]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS error_codes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    code VARCHAR(255) UNIQUE NOT NULL -- $.CloudTrailEvent.errorCode [cite: 107, 124]
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS invocation_sources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    invoker VARCHAR(255) UNIQUE NOT NULL -- $.CloudTrailEvent.userIdentity.invokedBy [cite: 13, 14]
) ENGINE=InnoDB;


-- --- 2. ENTIDADES (DEDUPLICACIÓN) ---

CREATE TABLE IF NOT EXISTS identities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_name VARCHAR(255),       -- $.Username [cite: 2, 4]
    type VARCHAR(100),            -- $.CloudTrailEvent.userIdentity.type [cite: 2, 8]
    principal_id VARCHAR(200),    -- $.CloudTrailEvent.userIdentity.principalId [cite: 2]
    arn VARCHAR(400),              -- $.CloudTrailEvent.userIdentity.arn [cite: 2]
    account_id VARCHAR(100),       -- $.CloudTrailEvent.userIdentity.accountId [cite: 2, 8]
    access_key_id VARCHAR(64),     -- $.AccessKeyId / $.CloudTrailEvent.userIdentity.accessKeyId [cite: 1, 2]
    invoker_id INT,                -- FK -> invocation_sources.id [cite: 13]
    UNIQUE KEY unq_identity (principal_id, arn, access_key_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS issuers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type VARCHAR(100),            -- $.CloudTrailEvent.userIdentity.sessionContext.sessionIssuer.type [cite: 2, 4]
    principal_id VARCHAR(200),    -- $.CloudTrailEvent.userIdentity.sessionContext.sessionIssuer.principalId [cite: 2, 4]
    arn VARCHAR(400),              -- $.CloudTrailEvent.userIdentity.sessionContext.sessionIssuer.arn [cite: 2, 4]
    user_name VARCHAR(255),       -- $.CloudTrailEvent.userIdentity.sessionContext.sessionIssuer.userName [cite: 2, 4]
    account_id VARCHAR(100),       -- $.CloudTrailEvent.userIdentity.sessionContext.sessionIssuer.accountId [cite: 2, 4]
    UNIQUE KEY unq_issuer (principal_id, arn)
) ENGINE=InnoDB;


-- --- 3. TABLA DE EVENTOS (HECHOS) ---

CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR(255) NOT NULL,        -- $.EventId / $.CloudTrailEvent.eventID [cite: 1, 3]
    event_time TIMESTAMP NOT NULL,         -- $.CloudTrailEvent.eventTime [cite: 3]
    event_time_epoch BIGINT,               -- $.EventTime (Formato epoch) [cite: 1]
    
    -- Relaciones (IDs)
    event_name_id INT NOT NULL,
    source_id INT NOT NULL,
    region_id INT NOT NULL,
    identity_id INT NOT NULL,
    issuer_id INT,
    user_agent_id INT,
    error_code_id INT,
    type_id INT,                           -- CORREGIDO: Columna faltante
    category_id INT,                       -- CORREGIDO: Columna faltante
    
    -- Metadata técnica
    request_id VARCHAR(255),               -- $.CloudTrailEvent.requestID [cite: 3, 5]
    shared_event_id VARCHAR(255),          -- $.CloudTrailEvent.sharedEventID [cite: 8, 13]
    recipient_account_id VARCHAR(100),     -- $.CloudTrailEvent.recipientAccountId [cite: 3, 8]
    source_ip VARCHAR(100),                -- $.CloudTrailEvent.sourceIPAddress [cite: 3, 8]
    vpc_endpoint_id VARCHAR(255),          -- $.CloudTrailEvent.vpcEndpointId [cite: 73]
    event_version VARCHAR(10),             -- $.CloudTrailEvent.eventVersion [cite: 2, 13]
    
    -- Flags y Seguridad
    read_only TINYINT(1) DEFAULT 0,        -- $.ReadOnly [cite: 1, 3]
    management_event TINYINT(1) DEFAULT 0, -- $.CloudTrailEvent.managementEvent [cite: 3, 8]
    mfa_authenticated TINYINT(1) DEFAULT 0,-- $.CloudTrailEvent.userIdentity.sessionContext.attributes.mfaAuthenticated [cite: 2]
    session_creation_date DATETIME,        -- $.CloudTrailEvent.userIdentity.sessionContext.attributes.creationDate [cite: 2]
    include_all_instances TINYINT(1) DEFAULT 0, -- $.CloudTrailEvent.requestParameters.includeAllInstances [cite: 72]
    
    -- Campos Dinámicos JSON
    request_parameters JSON,               -- $.CloudTrailEvent.requestParameters [cite: 3, 5]
    response_elements JSON,                -- $.CloudTrailEvent.responseElements [cite: 3, 13]
    additional_event_data JSON,            -- $.CloudTrailEvent.additionalEventData [cite: 13, 94]
    service_event_details JSON,            -- $.CloudTrailEvent.serviceEventDetails [cite: 8, 48]
    tls_details JSON,                      -- $.CloudTrailEvent.tlsDetails [cite: 3, 5]
    error_message TEXT,                    -- $.CloudTrailEvent.errorMessage [cite: 107, 124]

    PRIMARY KEY (event_id, event_time)
) ENGINE=InnoDB;


-- --- 4. DETALLE DE RECURSOS ---

CREATE TABLE IF NOT EXISTS event_resources (
    id INT AUTO_INCREMENT,
    event_id VARCHAR(255) NOT NULL,
    event_time TIMESTAMP NOT NULL,
    resource_type VARCHAR(255),            -- $.Resources[].ResourceType [cite: 9, 29]
    resource_name VARCHAR(1000),           -- $.Resources[].ResourceName [cite: 9, 29]
    account_id VARCHAR(100),               -- $.CloudTrailEvent.resources[].accountId [cite: 8, 13]
    PRIMARY KEY (id, event_time)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ingestion_log (
    ingested_date DATE PRIMARY KEY,
    execution_time DATETIME NOT NULL
) ENGINE=InnoDB;

-- ============================================
-- TABLA DE CALENDARIO (opcional, para analisis temporal avanzado)
-- Facilita queries por dia de semana, hora habil, etc.
-- ============================================

CREATE TABLE IF NOT EXISTS calendar (
    calendar_date DATE PRIMARY KEY,
    year_num INT,
    month_num INT,
    day_num INT,
    day_of_week INT,        -- 1=Domingo, 7=Sabado
    day_name VARCHAR(10),
    is_weekend TINYINT(1),
    is_business_hours TINYINT(1),  -- 9-18, L-V
    hour_block VARCHAR(20),        -- 'Madrugada', 'Manana', 'Tarde', 'Noche'
    week_of_year INT,
    month_name VARCHAR(20)
) ENGINE=InnoDB;

-- 1. Indice compuesto para trazabilidad de requests (el mas importante)
ALTER TABLE events ADD INDEX idx_request_trace (request_id, event_time);

-- 2. Indice para analisis temporal por servicio
ALTER TABLE events ADD INDEX idx_time_service (event_time, source_id);

-- 3. Indice para analisis de identidades
ALTER TABLE events ADD INDEX idx_identity_time (identity_id, event_time);

-- 4. Indice para busqueda de errores
ALTER TABLE events ADD INDEX idx_errors (error_code_id, event_time);

-- 5. Indice para analisis de IPs
ALTER TABLE events ADD INDEX idx_source_ip (source_ip, event_time);

-- 6. Indice para eventos de escritura (filtrado rapido read_only)
ALTER TABLE events ADD INDEX idx_write_events (read_only, source_id, event_name_id);

-- 7. Indice en event_resources para busqueda por recurso
ALTER TABLE event_resources ADD INDEX idx_resource (resource_name, event_time);


-- ============================================
-- VISTAS ANALITICAS (crear despues de los indices)
-- Estas vistas simplifican TODAS las queries del curso
-- ============================================

-- VISTA 1: events_enriched - El microscopio principal
-- Une todos los maestros en una sola vista analitica
CREATE OR REPLACE VIEW events_enriched AS
SELECT
    e.event_id,
    e.event_time,
    e.event_time_epoch,
    n.name AS event_name,
    s.source AS event_source,
    r.name AS region,
    i.user_name,
    i.type AS identity_type,
    i.principal_id,
    i.arn AS identity_arn,
    i.account_id AS identity_account,
    i.access_key_id,
    inv.invoker AS invoked_by,
    iss.user_name AS issuer_name,
    iss.arn AS issuer_arn,
    iss.type AS issuer_type,
    ua.agent AS user_agent,
    ec.code AS error_code,
    e.error_message,
    et.name AS event_type,
    ec2.name AS event_category,
    e.request_id,
    e.shared_event_id,
    e.recipient_account_id,
    e.source_ip,
    e.vpc_endpoint_id,
    e.event_version,
    e.read_only,
    e.management_event,
    e.mfa_authenticated,
    e.session_creation_date,
    e.request_parameters,
    e.response_elements,
    e.additional_event_data,
    e.service_event_details,
    e.tls_details
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN regions r ON e.region_id = r.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id
LEFT JOIN error_codes ec ON e.error_code_id = ec.id
LEFT JOIN event_types et ON e.type_id = et.id
LEFT JOIN event_categories ec2 ON e.category_id = ec2.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id;

-- VISTA 2: service_interactions - El mapa de dependencias
-- Muestra que servicios llaman a que otros servicios
CREATE OR REPLACE VIEW service_interactions AS
SELECT
    inv.invoker AS caller_service,
    s.source AS target_service,
    n.name AS action,
    COUNT(*) AS interaction_count
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
JOIN invocation_sources inv ON i.invoker_id = inv.id
WHERE inv.invoker IS NOT NULL
GROUP BY inv.invoker, s.source, n.name;

-- VISTA 3: human_activity - Actividad humana filtrada
-- Pre-filtrada para acciones humanas reales
CREATE OR REPLACE VIEW human_activity AS
SELECT *
FROM events_enriched
WHERE identity_type IN ('IAMUser', 'AssumedRole', 'SAMLUser', 'WebIdentityUser')
  AND (user_agent LIKE '%Mozilla%'
       OR user_agent LIKE '%Safari%'
       OR user_agent LIKE '%Chrome%'
       OR user_agent LIKE '%Firefox%')
  AND user_name NOT LIKE '%service%'
  AND user_name NOT LIKE '%Service%'
  AND user_name NOT LIKE '%aws-service%'
  AND event_name NOT IN ('ConsoleLogin', 'CheckMfa');

-- VISTA 4: credential_analysis - Analisis de credenciales
CREATE OR REPLACE VIEW credential_analysis AS
SELECT
    e.event_time,
    e.event_id,
    CASE
        WHEN i.type = 'IAMUser' THEN 'Credenciales Largas (Access Key)'
        WHEN n.name = 'AssumeRole' AND i.type = 'IAMUser' THEN 'Usuario asume Rol'
        WHEN n.name = 'AssumeRole' AND i.type = 'AWSService' THEN 'Servicio asume Rol'
        WHEN i.principal_id LIKE 'AROA%' AND n.name != 'AssumeRole' THEN 'STS Session (Rol ya asumido)'
        WHEN inv.invoker IS NOT NULL THEN 'Service Principal'
        WHEN i.type = 'AWSService' THEN 'Servicio AWS Interno'
        WHEN e.mfa_authenticated = 1 THEN 'MFA + STS'
        WHEN ua.agent LIKE '%botocore%' THEN 'CLI/SDK Session'
        WHEN ua.agent LIKE '%aws-cli%' THEN 'AWS CLI'
        ELSE 'Otro'
    END AS credential_source,
    i.type AS identity_type,
    i.principal_id,
    i.arn AS identity_arn,
    inv.invoker,
    n.name,
    s.source AS event_source,
    e.mfa_authenticated,
    e.session_creation_date
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id;

-- VISTA 5: service_classification - Clasificador automatico de servicios
CREATE OR REPLACE VIEW service_classification AS
SELECT
    s.source AS event_source,
    COUNT(DISTINCT n.name) AS total_operations,
    SUM(CASE WHEN n.name REGEXP '^(Create|Put|Update|Delete|Register|Add|Remove|Modify|Attach|Detach)'
             THEN 1 ELSE 0 END) AS write_operations,
    SUM(CASE WHEN n.name REGEXP '^(Get|List|Describe|Query|Scan|Search|Fetch|View)'
             THEN 1 ELSE 0 END) AS read_operations,
    SUM(CASE WHEN n.name LIKE '%Invoke%'
              OR n.name LIKE '%Send%'
              OR n.name LIKE '%Publish%'
              OR n.name LIKE '%Process%'
             THEN 1 ELSE 0 END) AS action_operations,
    CASE
        WHEN SUM(CASE WHEN n.name REGEXP '^(Create|Put|Update|Delete|Register|Add|Remove|Modify)'
                      THEN 1 ELSE 0 END) = 0 THEN 'ReadOnly'
        WHEN SUM(CASE WHEN n.name REGEXP '^(Get|List|Describe|Query|Scan|Search|Fetch|View)'
                      THEN 1 ELSE 0 END) = 0 THEN 'WriteOnly'
        WHEN SUM(CASE WHEN n.name LIKE '%Invoke%'
                       OR n.name LIKE '%Send%'
                       OR n.name LIKE '%Publish%'
                      THEN 1 ELSE 0 END) > 0 THEN 'ActionBased'
        ELSE 'CRUD'
    END AS service_pattern,
    CASE
        WHEN SUM(CASE WHEN n.name LIKE '%Invoke%' THEN 1 ELSE 0 END) > 0
            THEN 'Compute/Orchestration'
        WHEN s.source LIKE '%s3%' OR s.source LIKE '%dynamodb%'
             OR s.source LIKE '%rds%' THEN 'DataStorage'
        WHEN s.source LIKE '%sns%' OR s.source LIKE '%sqs%'
             OR s.source LIKE '%eventbridge%' THEN 'Messaging'
        WHEN s.source LIKE '%iam%' OR s.source LIKE '%kms%'
             OR s.source LIKE '%secretsmanager%' THEN 'Security'
        WHEN s.source LIKE '%cloudwatch%' OR s.source LIKE '%logs%'
             OR s.source LIKE '%xray%' THEN 'Observability'
        WHEN s.source LIKE '%ec2%' OR s.source LIKE '%ecs%'
             OR s.source LIKE '%eks%' THEN 'Compute'
        WHEN s.source LIKE '%cloudformation%' OR s.source LIKE '%terraform%'
             OR s.source LIKE '%cloudcontrol%' THEN 'Infrastructure'
        ELSE 'Other'
    END AS service_domain,
    COUNT(*) AS total_calls
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
GROUP BY s.source;

