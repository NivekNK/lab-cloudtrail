# AWS API Under the Microscope: Aprendiendo AWS a traves de CloudTrail

---

## Modulo 0: Setup del Laboratorio

### Objetivo de Aprendizaje
Verificar que tu laboratorio funciona y comprender la **magnitud de la actividad invisible** que ocurre en tu cuenta AWS.

### Teoria: La Gran Sorpresa

Antes de tocar una sola query, hay que entender algo fundamental: **AWS nunca duerme**. Incluso si tu cuenta parece "inactiva", decenas de servicios estan realizando operaciones de mantenimiento, health checks, replicacion de metadatos y gestion de recursos.

**Ejemplo real del JSON de ejemplo:**
El evento que adjuntaste muestra `AutoScaling` llamando `DescribeInstanceStatus` sobre 4 instancias EC2. Es un evento `ReadOnly`, pero revela que el auto-scaling esta **constantemente sondeando** el estado de tus instancias. Esto ocurre cada minuto, las 24 horas, los 365 dias del ano.

> **Leccion 0:** No hay "silencio" en AWS. Solo hay actividad que tu no iniciaste.

### Laboratorio 0.1: Sanity Check

```sql
-- Verifica que tienes datos y cuantos dias cubren
SELECT
    COUNT(*) AS total_events,
    MIN(event_time) AS primer_log,
    MAX(event_time) AS ultimo_log,
    COUNT(DISTINCT source_id) AS servicios_detectados,
    COUNT(DISTINCT event_name_id) AS operaciones_distintas,
    DATEDIFF(MAX(event_time), MIN(event_time)) AS dias_cubiertos
FROM events;
```

**Preguntas para reflexionar:**
- Si tienes 7 dias de datos, deberias ver actividad cada dia. Si hay dias vacios, ¿por que?
- El numero de servicios detectados suele ser 15-40 en una cuenta tipica. ¿Tienes mas o menos?
- Operaciones distintas: una cuenta basica genera 50-200 operaciones diferentes. Una cuenta enterprise puede llegar a 500+.

### Laboratorio 0.2: Actividad Diaria (El Pulso de tu Cuenta)

```sql
-- El pulso diario: actividad por dia de la semana
SELECT
    DATE(event_time) AS dia,
    COUNT(*) AS total_eventos,
    COUNT(DISTINCT source_id) AS servicios_activos,
    COUNT(DISTINCT identity_id) AS principales_distintos,
    COUNT(DISTINCT request_id) AS requests_unicos,
    SUM(CASE WHEN read_only = 1 THEN 1 ELSE 0 END) AS lecturas,
    SUM(CASE WHEN read_only = 0 THEN 1 ELSE 0 END) AS escrituras,
    ROUND(SUM(CASE WHEN read_only = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS pct_lectura
FROM events
GROUP BY DATE(event_time)
ORDER BY dia DESC
LIMIT 14;
```

**Lo que descubriras:**
- La proporcion lectura/escritura suele ser 80/20 o 90/10. AWS **lee mucho mas de lo que escribe**.
- Los servicios "invisibles" (CloudWatch, SSM, AutoScaling) dominan el volumen.
- Los fines de semana deberian mostrar menos actividad humana pero similar actividad de servicios.

### Laboratorio 0.3: Los Servicios Invisibles

```sql
-- Servicios que operan solos, sin que un humano los toque
SELECT
    s.source AS event_source,
    COUNT(*) AS calls,
    COUNT(DISTINCT n.name) AS operaciones_distintas,
    GROUP_CONCAT(DISTINCT n.name ORDER BY n.name SEPARATOR ', ') AS ejemplos_operaciones
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
WHERE i.type = 'AWSService'
   OR inv.invoker IS NOT NULL
GROUP BY s.source
ORDER BY calls DESC
LIMIT 15;
```

**Descubrimientos tipicos:**
- `cloudwatch.amazonaws.com`: Health checks constantes
- `ssm.amazonaws.com`: Agentes de Systems Manager reportando estado (`UpdateInstanceInformation`)
- `autoscaling.amazonaws.com`: Verificando estado de instancias (`DescribeInstanceStatus`)
- `config.amazonaws.com`: Evaluando reglas de compliance

### Laboratorio 0.4: Tu Huella vs la Huella del Sistema

```sql
-- Comparativa: Humanos vs Servicios
SELECT
    CASE
        WHEN i.type = 'IAMUser' THEN 'IAM User (humano)'
        WHEN i.type = 'AssumedRole' AND ua.agent LIKE '%Mozilla%' THEN 'Humano via Console'
        WHEN i.type = 'AssumedRole' THEN 'Aplicacion/CLI via Rol'
        WHEN i.type = 'AWSService' THEN 'Servicio AWS'
        WHEN inv.invoker IS NOT NULL THEN 'Cross-Service Call'
        ELSE i.type
    END AS tipo_actor,
    COUNT(*) AS eventos,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS porcentaje
FROM events e
JOIN identities i ON e.identity_id = i.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
GROUP BY tipo_actor
ORDER BY eventos DESC;
```

**Expectativa vs Realidad:**
| Expectativa | Realidad |
|---|---|
| "Mi cuenta esta quieta" | 95% de actividad es de servicios autonomos |
| "Yo controlo AWS" | Los servicios se autogestionan constantemente |
| "Los logs son aburridos" | Cada evento cuenta una historia |

### Laboratorio 0.5: Crear Vistas del Curso

```sql
-- Ejecutar TODAS las vistas definidas en la seccion "Mejoras al Esquema SQL"
-- Estas vistas simplificaran todas las queries de los modulos 1-5

-- Verificar que las vistas funcionan:
SELECT COUNT(*) FROM events_enriched;
SELECT COUNT(*) FROM service_interactions;
SELECT COUNT(*) FROM human_activity;
SELECT COUNT(*) FROM credential_analysis;
SELECT * FROM service_classification LIMIT 5;
```

### Ejercicio 0: El Experimento Inicial

Antes de continuar, ejecuta esta query y responde las preguntas:

```sql
-- El experimento inicial
SELECT
    DATE(event_time) AS dia,
    COUNT(*) AS total_eventos,
    COUNT(DISTINCT source_id) AS servicios_usados,
    COUNT(DISTINCT identity_id) AS principales_unicos,
    COUNT(DISTINCT CASE WHEN read_only = 0 THEN request_id END) AS escrituras
FROM events
GROUP BY DATE(event_time)
ORDER BY dia DESC
LIMIT 7;
```

**Preguntas de reflexion:**
1. ¿Hay servicios que aparecen sin que los hayas usado conscientemente?
2. ¿Hay mas o menos actividad de la que esperabas?
3. ¿Quienes son esos principals? ¿Reconoces todos?
4. ¿Cual es la proporcion de lecturas vs escrituras?
5. ¿Hay algun dia con actividad anormalmente alta o baja?

> **Bienvenido a la realidad de AWS.** La que no te muestran en los cursos.

---

## Modulo 1: La AWS API - El Verdadero Plano de Control

**Duracion:** 2 horas teoricas + 2 horas laboratorio  
**Objetivo:** Entender que AWS es una API HTTP y que todo lo demas (CLI, Console, SDKs) son clientes.

### Teoria 1.1: La Gran Mentira de las Abstracciones

Cuando aprendes AWS de forma convencional, te ensenan abstracciones limpias:
- "S3 es almacenamiento de objetos"
- "Lambda ejecuta codigo sin servidores"
- "IAM es un servicio de seguridad"

Pero CloudTrail revela una verdad mas compleja: **cada servicio es una fachada sobre decenas de operaciones CRUD+RPC**.

**Evidencia del ejemplo JSON:**
El evento muestra AutoScaling llamando EC2 con `DescribeInstanceStatus`. No es "Auto Scaling funciona" - es una llamada HTTP con:
- Endpoint: `ec2.amazonaws.com`
- Accion: `DescribeInstanceStatus`
- Parametros: 4 instanceIds
- Autenticacion: STS AssumedRole
- Firma: SigV4 (implicita en el evento)

> **Leccion:** No hay "Auto Scaling" como entidad magica. Hay una serie de llamadas API orquestadas.

### Laboratorio 1.1: Descubrir la API en Accion

```sql
-- Servicios mas "verbosos" (mas operaciones distintas)
SELECT
    s.source AS event_source,
    COUNT(DISTINCT n.name) AS operaciones_unicas,
    COUNT(*) AS llamadas_totales,
    ROUND(COUNT(*) / COUNT(DISTINCT n.name), 1) AS frecuencia_media_por_op
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
GROUP BY s.source
ORDER BY operaciones_unicas DESC
LIMIT 15;
```

**Interpretacion:**
| Servicio | Operaciones | Significado |
|---|---|---|
| ec2.amazonaws.com | 200+ | Servicio mas antiguo y complejo |
| iam.amazonaws.com | 150+ | Cada permiso, rol, politica es una operacion |
| cloudformation.amazonaws.com | 100+ | Orchestrator que llama a todo |
| lambda.amazonaws.com | 80+ | Mucho mas que Invoke |

```sql
-- Operaciones mas frecuentes en tu cuenta (el "latido")
SELECT
    n.name AS operation,
    s.source AS service,
    COUNT(*) AS frecuencia,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct_total,
    MIN(event_time) AS primera_vez,
    MAX(event_time) AS ultima_vez
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
GROUP BY n.name, s.source
ORDER BY frecuencia DESC
LIMIT 20;
```

**Lo que tipicamente descubriras:**
- `DescribeInstanceStatus` (EC2) - el auto-scaling sondeando
- `UpdateInstanceInformation` (SSM) - agentes reportando vida
- `PutMetricData` (CloudWatch) - metricas fluyendo
- `DescribeStacks` (CloudFormation) - verificando estado

> **Pregunta de reflexion:** Las operaciones de lectura (Describe, List, Get) dominan el top 20. ¿Por que crees que AWS necesita leer tanto?

### Laboratorio 1.2: La Capa HTTP (User-Agent Forensics)

```sql
-- fingerprinting de clientes
SELECT
    CASE
        WHEN ua.agent LIKE '%aws-cli%' THEN 'AWS CLI'
        WHEN ua.agent LIKE '%boto3%' THEN 'Boto3 (Python)'
        WHEN ua.agent LIKE '%console%' AND ua.agent LIKE '%Mozilla%' THEN 'AWS Web Console'
        WHEN ua.agent LIKE '%console%' THEN 'AWS Console (otro)'
        WHEN ua.agent LIKE '%terraform%' THEN 'Terraform'
        WHEN ua.agent LIKE '%pulumi%' THEN 'Pulumi'
        WHEN ua.agent LIKE '%kops%' THEN 'Kops'
        WHEN ua.agent LIKE '%eksctl%' THEN 'eksctl'
        WHEN ua.agent LIKE '%CloudFormation%' THEN 'CloudFormation (managed)'
        WHEN ua.agent LIKE '%AWSService%' OR ua.agent = 'autoscaling.amazonaws.com' THEN 'Servicio AWS Interno'
        WHEN ua.agent LIKE '%botocore%' THEN 'Botocore (generico)'
        WHEN ua.agent LIKE '%aws-sdk-%' THEN 'AWS SDK (otro lenguaje)'
        WHEN ua.agent IS NULL THEN 'Sin User-Agent'
        ELSE LEFT(ua.agent, 50)
    END AS client_type,
    COUNT(*) AS llamadas,
    COUNT(DISTINCT s.source) AS servicios_tocados,
    ROUND(AVG(CASE WHEN e.read_only = 1 THEN 1 ELSE 0 END) * 100, 1) AS pct_lecturas
FROM events e
JOIN event_sources s ON e.source_id = s.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id
GROUP BY client_type
ORDER BY llamadas DESC;
```

**Actividad practica (30 min):**

1. Haz tres formas de listar buckets S3:
   ```bash
   aws s3 ls                    # CLI
   ```
   ```python
   import boto3
   boto3.client('s3').list_buckets()  # Python/boto3
   ```
   Y desde la AWS Console (navegador)

2. Encuentra las tres llamadas en CloudTrail:
```sql
SELECT
    e.event_time,
    n.name AS operation,
    s.source,
    CASE
        WHEN ua.agent LIKE '%aws-cli%' THEN 'CLI'
        WHEN ua.agent LIKE '%boto3%' THEN 'Boto3'
        WHEN ua.agent LIKE '%Mozilla%' THEN 'Console'
    END AS client_detected,
    ua.agent AS full_agent,
    e.request_id
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id
WHERE n.name = 'ListBuckets'
  AND e.event_time > NOW() - INTERVAL 2 HOUR
ORDER BY e.event_time DESC
LIMIT 10;
```

**Compara:**
- ¿El eventName es el mismo? (Spoiler: SI, siempre es ListBuckets)
- ¿Cambia el userAgent? (Spoiler: SI, dramaticamente)
- ¿El sourceIPAddress es el mismo? (Spoiler: CLI/SDK = tu IP; Console = IP de AWS)

### Laboratorio 1.3: La Verdad sobre Lambda (y Cualquier Servicio)

```sql
-- Lambda: ¿realmente "ejecuta codigo" o hace mucho mas?
SELECT
    n.name AS operation,
    COUNT(*) AS frecuencia,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct,
    CASE
        WHEN n.name LIKE 'Get%' OR n.name LIKE 'List%' THEN 'ConfigRead'
        WHEN n.name LIKE 'Create%' OR n.name LIKE 'Update%' 
             OR n.name LIKE 'Put%' OR n.name LIKE 'Delete%' THEN 'ConfigWrite'
        WHEN n.name = 'Invoke' OR n.name LIKE '%Invoke%' THEN 'Execution'
        WHEN n.name LIKE '%Permission%' OR n.name LIKE '%Policy%' THEN 'Security'
        WHEN n.name LIKE '%Tag%' THEN 'Tagging'
        ELSE 'Other'
    END AS categoria
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE s.source = 'lambda.amazonaws.com'
GROUP BY n.name
ORDER BY frecuencia DESC;
```

**Descubrimiento tipico:**
| Categoria | % del Total | Leccion |
|---|---|---|
| ConfigRead | 40-50% | Lambda es principalmente un sistema de gestion de config |
| Security | 20-30% | Mucho mas trabajo en permisos que en ejecucion |
| ConfigWrite | 15-20% | Despliegues, actualizaciones |
| Execution | 5-10% | La ejecucion de codigo es la minoria |

> **Leccion profunda:** Lambda es principalmente un **sistema de gestion de configuracion que ocasionalmente ejecuta codigo**. El 90% de su actividad es administrar versiones, etiquetas, politicas y permisos. Esto cambia TODO sobre como deberias disenar, optimizar costos y asegurar Lambda.

### Laboratorio 1.4: Servicios Globales vs Regionales

```sql
-- IAM es "global" pero... ¿realmente?
SELECT
    s.source AS service,
    r.name AS region,
    COUNT(*) AS calls,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY s.source), 1) AS pct
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN regions r ON e.region_id = r.id
WHERE s.source IN ('iam.amazonaws.com', 'cloudfront.amazonaws.com', 
                   'route53.amazonaws.com', 's3.amazonaws.com',
                   'organizations.amazonaws.com')
GROUP BY s.source, r.name
ORDER BY s.source, calls DESC;
```

**Descubrimiento:** IAM aparece casi siempre en `us-east-1` incluso si tu region es otra. ¿Por que? **El endpoint global de IAM fisicamente esta en us-east-1**. La "globalidad" es una abstraccion - fisicamente hay un cluster atendiendo todo.

### Ejercicio del Modulo 1: El Cliente Oculto

Busca en tus logs un evento que no reconozcas y traza quien lo origino:

```sql
-- Encuentra la llamada mas "extrana" de hoy
SELECT
    e.event_time,
    n.name AS operation,
    s.source,
    i.type AS identity_type,
    i.user_name,
    inv.invoker as invoked_by,
    iss.user_name AS assumed_role,
    ua.agent,
    e.source_ip,
    JSON_PRETTY(e.request_parameters) AS params
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
LEFT JOIN user_agents ua ON e.user_agent_id = ua.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
WHERE e.event_time > NOW() - INTERVAL 24 HOUR
  AND i.type != 'IAMUser'
  AND (inv.invoker IS NOT NULL OR iss.user_name LIKE '%Service%')
ORDER BY RAND()
LIMIT 5;
```

**Tarea:** Para cada evento encontrado, responde:
1. ¿Que servicio origino la llamada? (invokedBy)
2. ¿Que rol asumio? (issuer)
3. ¿A que servicio llamo? (event_source)
4. ¿Con que parametros? (request_parameters)
5. ¿Por que crees que ese servicio necesita hacer esa llamada?

---

## Modulo 2: Anatomia de una Request API

**Duracion:** 2.5 horas teoricas + 2.5 horas laboratorio  
**Objetivo:** Entender el flujo completo: Cliente → Autenticacion → Autorizacion → Ejecucion → Registro.

### Teoria 2.1: El Viaje de 7 Pasos

Cada llamada a AWS sigue exactamente este camino:

```
CLIENTE
   |
   v
1. Firma de Request (SigV4: headers Authorization + X-Amz-Date)
   |
   v
2. DNS → Endpoint Regional (ec2.us-east-1.amazonaws.com)
   |
   v
3. API Gateway del Servicio (no es API Gateway el servicio, es el "front door" de cada servicio)
   |
   v
4. AUTENTICACION: ¿Quien eres? (verifica firma, validez de credenciales)
   |
   v
5. AUTORIZACION: ¿Puedes hacer esto? (evalua politicas IAM)
   |
   v
6. EJECUCION: La operacion se realiza
   |
   v
7. REGISTRO: CloudTrail captura el evento + RESPONSE al cliente
```

**Cada uno de estos pasos deja huella en CloudTrail.**

Del ejemplo JSON podemos reconstruir:
- Paso 4 (Autenticacion): `userIdentity.type = "AssumedRole"` → STS ya verifico credenciales
- Paso 5 (Autorizacion): No hay `errorCode` → la autorizacion paso
- Paso 6 (Ejecucion): `responseElements = null` → es una lectura, no hay elemento de respuesta
- Paso 7 (Registro): `requestID = "f7e76ca0-..."` → el ID de traza

### Laboratorio 2.1: Trazar una Request Completa

```sql
-- Paso 1: Encontrar requestIDs con multiples eventos (cadenas de llamadas)
SELECT
    e.request_id,
    COUNT(*) AS eventos_en_cadena,
    COUNT(DISTINCT s.source) AS servicios_involucrados,
    GROUP_CONCAT(DISTINCT n.name ORDER BY e.event_time SEPARATOR ' → ') AS secuencia,
    MIN(e.event_time) AS inicio,
    MAX(e.event_time) AS fin,
    TIMESTAMPDIFF(MICROSECOND, MIN(e.event_time), MAX(e.event_time)) / 1000.0 AS duracion_ms
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE e.request_id IS NOT NULL
GROUP BY e.request_id
HAVING eventos_en_cadena > 1
ORDER BY eventos_en_cadena DESC
LIMIT 10;
```

> **Leccion:** Un solo `request_id` puede tener multiples eventos cuando hay retries automaticos, cross-service calls, o cuando un servicio llama a otro en cadena.

### Laboratorio 2.2: Reconstruir la Secuencia Completa

```sql
-- Paso 2: Escoge un request_id del resultado anterior y reconstruye todo
SELECT
    e.event_time,
    s.source AS servicio,
    n.name AS operacion,
    i.type AS tipo_autenticacion,
    CASE
        WHEN e.error_code_id IS NULL THEN '✓ EXITO'
        ELSE CONCAT('✗ ', ec.code)
    END AS estado,
    CASE
        WHEN e.read_only = 1 THEN 'Lectura'
        ELSE 'Escritura'
    END AS tipo_operacion,
    i.user_name AS actor,
    iss.user_name AS rol_asumido,
    e.source_ip
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
LEFT JOIN error_codes ec ON e.error_code_id = ec.id
WHERE e.request_id = 'REEMPLAZA_CON_REQUEST_ID_AQUI'
ORDER BY e.event_time;
```

**Analisis de la cadena:**
- Mira la columna `estado` → si hay errores intermedios pero la cadena continua, ¿que paso?
- Mira `tipo_autenticacion` → ¿cambia a lo largo de la cadena?
- Mira `rol_asumido` → ¿asume un rol intermedio?

### Laboratorio 2.3: El Contexto Temporal de una Operacion

```sql
-- ¿Que mas hizo el mismo caller 5 segundos antes y despues?
WITH target_event AS (
    SELECT event_time, identity_id, request_id
    FROM events
    WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID_AQUI'
    LIMIT 1
)
SELECT
    e.event_time,
    TIMESTAMPDIFF(MICROSECOND, te.event_time, e.event_time) / 1000000.0 AS segundos_delta,
    n.name AS operacion,
    s.source AS servicio,
    CASE WHEN e.error_code_id IS NULL THEN 'OK' ELSE 'ERROR' END AS estado,
    e.request_id
FROM events e
CROSS JOIN target_event te
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE e.identity_id = te.identity_id
  AND ABS(TIMESTAMPDIFF(MICROSECOND, te.event_time, e.event_time)) <= 5000000  -- 5 segundos
ORDER BY e.event_time;
```

### Laboratorio 2.4: Camino de Autorizacion (Errores AccessDenied)

```sql
-- Analizar errores de autorizacion (que revelan que permiso faltaba)
SELECT
    e.event_time,
    n.name AS operacion_intentada,
    s.source AS servicio,
    i.type AS tipo_identidad,
    i.arn AS identity_arn,
    ec.code AS error,
    e.error_message,
    e.request_parameters->>"$.roleArn" AS rol_solicitado,
    e.request_parameters->>"$.policyArn" AS policy_solicitada,
    e.source_ip
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
JOIN error_codes ec ON e.error_code_id = ec.id
WHERE ec.code LIKE 'AccessDenied%'
   OR ec.code LIKE 'Unauthorized%'
   OR ec.code LIKE 'Forbidden%'
ORDER BY e.event_time DESC
LIMIT 20;
```

**Analisis de errores:**
| errorMessage | Leccion |
|---|---|
| "User is not authorized to perform iam:PassRole" | El rol necesita permiso para "pasar" otro rol |
| "Access Denied for bucket 'xyz'" | Falta permiso S3 especifico para ese recurso |
| "User is not authorized to perform lambda:InvokeFunction" | La policy no incluye la ARN de la funcion |

### Laboratorio 2.5: Servicios que se Autogestionan

```sql
-- AutoScaling: un ejemplo perfecto de servicio autonomo
SELECT
    e.event_time,
    n.name AS operacion,
    s.source AS servicio_target,
    i.type,
    i.user_name,
    iss.user_name AS rol_base,
    inv.invoker AS invocado_por,
    e.request_parameters->>"$.instancesSet.items[0].instanceId" AS instancia,
    e.request_parameters->>"$.includeAllInstances" AS todas_las_instancias,
    CASE WHEN e.error_code_id IS NULL THEN 'OK' ELSE 'FALLO' END AS resultado
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
WHERE inv.invoker = 'autoscaling.amazonaws.com'
   OR iss.user_name LIKE '%AutoScaling%'
ORDER BY e.event_time DESC
LIMIT 20;
```

**Lo que veras:** AutoScaling constantemente llama a EC2 para verificar estado de instancias. No hay humano detras - es un **loop de control automatico**.

### Laboratorio 2.6: Proyecto Parcial - Trazar una Request Fallida

```sql
-- "El Detective de APIs": Request fallida
-- Paso 1: Encontrar requests fallidos recientes
SELECT
    e.request_id,
    e.event_time,
    n.name AS operacion,
    s.source,
    ec.code AS error,
    e.error_message,
    i.arn AS identity,
    iss.user_name AS rol
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
JOIN error_codes ec ON e.error_code_id = ec.id
WHERE e.request_id IS NOT NULL
ORDER BY e.event_time DESC
LIMIT 5;

-- Paso 2: Para un request_id especifico, ver TODA la cadena
-- (usar la query del Laboratorio 2.2 con ese request_id)
```

**Responder:**
1. ¿Que operacion fallo?
2. ¿Que credenciales se usaron? (identity_arn, tipo, rol)
3. ¿Habia operaciones exitosas antes en la misma sesion?
4. ¿El error es de autenticacion (firma invalida), autorizacion (AccessDenied) o del servicio (500, Throttling)?

---

## Modulo 3: IAM en Accion - Credenciales y Autorizacion

**Duracion:** 3 horas teoricas + 3 horas laboratorio  
**Objetivo:** Entender los 4 mecanismos de autenticacion y como fluye la autorizacion.

### Teoria 3.1: Los 4 Mecanismos de Autenticacion

CloudTrail registra exactamente 4 formas de autenticarse en AWS:

| Mecanismo | Identificacion en CloudTrail | Revela |
|---|---|---|
| **IAM User** | `identity_type = 'IAMUser'` | Acceso humano directo (mala practica en prod) |
| **AssumedRole** | `identity_type = 'AssumedRole'` + sessionContext | Como las apps se autentican (buena practica) |
| **Service Principal** | `invoked_by` no nulo | Servicios que actuan por si mismos |
| **STS Session** | `principalId LIKE 'AROA%'` | Credenciales temporales |

Del ejemplo JSON:
```json
"userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROA6NVW7XE743JRJFCRC:AutoScaling",
    "arn": "arn:aws:sts::991447464255:assumed-role/AWSServiceRoleForAutoScaling/AutoScaling",
    "invokedBy": "autoscaling.amazonaws.com"
}
```
Esto es un **Service Principal** (AutoScaling) que ha **asumido un rol** (AWSServiceRoleForAutoScaling) para obtener credenciales temporales. Es el mecanismo 3 generando el mecanismo 2.

### Laboratorio 3.1: Mapear Tipos de Identidad en tu Cuenta

```sql
-- Distribucion de tipos de identidad
SELECT
    i.type AS identity_type,
    COUNT(*) AS api_calls,
    COUNT(DISTINCT s.source) AS servicios_accedidos,
    COUNT(DISTINCT n.name) AS operaciones_distintas,
    COUNT(DISTINCT i.principal_id) AS identidades_unicas,
    MIN(e.event_time) AS primera_aparicion,
    MAX(e.event_time) AS ultima_aparicion
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
GROUP BY i.type
ORDER BY api_calls DESC;
```

**Interpretacion:**
| identity_type | Significado | Recomendacion |
|---|---|---|
| `AssumedRole` | Roles asumidos (apps, servicios) | ✓ Buena practica |
| `IAMUser` | Usuarios con credenciales largas | ⚠ Minimizar en prod |
| `AWSService` | Servicios AWS internos | Normal, no controlable |
| `SAMLUser` | SSO (Single Sign-On) | ✓ Buena practica para humanos |
| `WebIdentityUser` | Cognito, OIDC | ✓ Para apps web/mobile |

### Laboratorio 3.2: Roles Asumidos en Accion

```sql
-- Paso 1: Encontrar asunciones de rol (AssumeRole events)
SELECT
    e.event_time,
    n.name AS tipo_asuncion,  -- AssumeRole, AssumeRoleWithSAML, AssumeRoleWithWebIdentity
    i.arn AS quien_solicita,
    i.type AS tipo_solicitante,
    e.request_parameters->>"$.roleArn" AS rol_solicitado,
    e.request_parameters->>"$.roleSessionName" AS nombre_sesion,
    e.response_elements->>"$.credentials.accessKeyId" AS access_key_temporal,
    e.response_elements->>"$.credentials.expiration" AS expiracion,
    iss.user_name AS issuer_original,
    e.source_ip
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
WHERE n.name LIKE 'AssumeRole%'
ORDER BY e.event_time DESC
LIMIT 10;
```

**Analisis de credenciales temporales:**
- `accessKeyId` empieza con `ASIA` (temporal) vs `AKIA` (larga duracion)
- La expiracion suele ser 1 hora despues de la asuncion
- `roleSessionName` identifica la sesion (ej: "AutoScaling")

```sql
-- Paso 2: Seguir el rastro de esas credenciales temporales
-- Busca llamadas con el mismo roleSessionName despues de la asuncion
SELECT
    e.event_time,
    n.name AS operacion,
    s.source AS servicio,
    i.principal_id,  -- AROA...:roleSessionName
    e.request_id,
    CASE WHEN e.error_code_id IS NULL THEN 'OK' ELSE 'ERROR' END AS estado
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
WHERE i.principal_id LIKE '%:AutoScaling%'  -- Reemplaza con el session name
   AND e.event_time > '2026-04-21 16:30:00'  -- Fecha de la asuncion
ORDER BY e.event_time
LIMIT 20;
```

### Laboratorio 3.3: Anomalias de IAM (Security)

```sql
-- Detectar uso directo de Access Keys (mala practica)
SELECT
    i.user_name,
    i.arn,
    i.access_key_id,
    COUNT(*) AS llamadas_directas,
    COUNT(DISTINCT s.source) AS servicios_tocados,
    GROUP_CONCAT(DISTINCT s.source ORDER BY s.source) AS lista_servicios,
    MIN(e.event_time) AS primera_llamada,
    MAX(e.event_time) AS ultima_llamada
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_sources s ON e.source_id = s.id
WHERE i.type = 'IAMUser'
  AND i.access_key_id IS NOT NULL
GROUP BY i.user_name, i.arn, i.access_key_id
ORDER BY llamadas_directas DESC;
```

```sql
-- Roles que nunca se asumen (potencialmente muertos)
SELECT DISTINCT
    e.request_parameters->>"$.roleArn" AS rol_creado_o_referenciado,
    COUNT(*) AS referencias,
    MAX(e.event_time) AS ultima_referencia
FROM events e
JOIN event_names n ON e.event_name_id = n.id
WHERE e.request_parameters->>"$.roleArn" IS NOT NULL
GROUP BY rol_creado_o_referenciado
ORDER BY ultima_referencia ASC
LIMIT 20;
```

```sql
-- Cross-account access: ¿Alguien esta accediendo desde otra cuenta?
SELECT
    e.event_time,
    i.arn AS identity,
    i.account_id AS cuenta_origen,
    e.recipient_account_id AS cuenta_destino,
    n.name AS operacion,
    s.source AS servicio,
    CASE 
        WHEN i.account_id != e.recipient_account_id THEN '⚠ CROSS-ACCOUNT'
        ELSE 'Misma cuenta'
    END AS tipo_acceso
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE i.account_id != e.recipient_account_id
ORDER BY e.event_time DESC
LIMIT 10;
```

### Laboratorio 3.4: MFA en Accion

```sql
-- Operaciones con y sin MFA
SELECT
    CASE
        WHEN e.mfa_authenticated = 1 THEN '✓ Con MFA'
        ELSE '✗ Sin MFA'
    END AS estado_mfa,
    i.type AS identity_type,
    COUNT(*) AS operaciones,
    COUNT(DISTINCT n.name) AS tipos_de_operacion,
    MIN(e.event_time) AS primera_op,
    MAX(e.event_time) AS ultima_op
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
WHERE i.type IN ('IAMUser', 'AssumedRole')
GROUP BY estado_mfa, i.type
ORDER BY identity_type, estado_mfa;
```

```sql
-- Acciones sensibles SIN MFA (alerta de seguridad)
SELECT
    e.event_time,
    i.user_name,
    n.name AS operacion_critica,
    s.source AS servicio,
    e.source_ip,
    e.request_parameters->>"$.roleArn" AS rol_afectado,
    e.request_parameters->>"$.policyArn" AS policy_afectada
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE e.mfa_authenticated = 0
  AND i.type = 'IAMUser'
  AND n.name REGEXP '(Create|Delete|Put|Attach|Detach)'
  AND n.name REGEXP '(Role|Policy|User|Group|AccessKey)'
ORDER BY e.event_time DESC
LIMIT 15;
```

### Ejercicio Hands-on del Modulo 3: "Crea y Rastrea un Rol"

1. **Crea un rol** con trust policy a tu usuario:
   ```bash
   aws iam create-role --role-name CursoDebugRol --assume-role-policy-document file://trust.json
   ```

2. **Asumelo** y captura las credenciales:
   ```bash
   aws sts assume-role --role-arn arn:aws:iam::TU_CUENTA:role/CursoDebugRol --role-session-name CursoSession
   ```

3. **Usa las credenciales temporales** para hacer 3 operaciones:
   ```bash
   export AWS_ACCESS_KEY_ID=...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_SESSION_TOKEN=...
   aws s3 ls
   aws ec2 describe-instances
   aws lambda list-functions
   ```

4. **Encuentra TODO en CloudTrail:**
```sql
-- La asuncion
SELECT * FROM events_enriched
WHERE event_name LIKE 'AssumeRole%'
  AND identity_arn LIKE '%CursoDebugRol%'
  AND event_time > NOW() - INTERVAL 1 HOUR;

-- Las llamadas subsecuentes (usa el principalId de la asuncion)
SELECT * FROM events_enriched
WHERE principal_id LIKE '%CursoSession%'
  AND event_time > NOW() - INTERVAL 1 HOUR;
```

5. **Dibuja el flujo:**
   ```
   Usuario(IAM) → STS AssumeRole → Credenciales Temp(ASIA...) → S3 ListBuckets → CloudTrail(registra)
                                    → EC2 DescribeInstances → CloudTrail(registra)
                                    → Lambda ListFunctions → CloudTrail(registra)
   ```

---

## Modulo 4: Condiciones y Parametros - El Filtro Fino

**Duracion:** 2 horas teoricas + 2 horas laboratorio  
**Objetivo:** Entender que las politicas IAM evaluan condiciones sobre parametros de la request, y que esos parametros estan visibles en CloudTrail.

### Teoria 4.1: El Modelo de Autorizacion Completo

La autorizacion en AWS evalua:
```
Solicitud API
    |
    +-- Principal (quien) → userIdentity.*
    +-- Accion (que) → eventName + eventSource
    +-- Recurso (sobre que) → requestParameters.*
    +-- Condiciones (contexto) → sourceIPAddress, userAgent, hora, tags, etc.
    |
    v
Evaluar TODAS las polelevantes (IAM, Resource, SCP)
    |
    v
Decision: Allow / Deny / Implicit Deny
```

### Laboratorio 4.1: Parametros Reales en tus Logs

```sql
-- Que parametros se usan en operaciones de escritura?
SELECT
    n.name AS operacion,
    s.source AS servicio,
    e.request_parameters->>"$.instanceType" AS instance_type,
    e.request_parameters->>"$.bucketName" AS bucket,
    e.request_parameters->>"$.functionName" AS lambda_function,
    e.request_parameters->>"$.repositoryName" AS repo,
    e.request_parameters->>"$.tagSpecificationSet" AS tags,
    COUNT(*) AS frecuencia
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE e.read_only = 0
  AND e.request_parameters IS NOT NULL
GROUP BY n.name, s.source, 
         e.request_parameters->>"$.instanceType",
         e.request_parameters->>"$.bucketName",
         e.request_parameters->>"$.functionName",
         e.request_parameters->>"$.repositoryName",
         e.request_parameters->>"$.tagSpecificationSet"
HAVING frecuencia > 1
ORDER BY frecuencia DESC
LIMIT 20;
```

### Laboratorio 4.2: Condicion sourceIPAddress

```sql
-- IPs que acceden a tu cuenta
SELECT
    e.source_ip,
    COUNT(*) AS llamadas,
    COUNT(DISTINCT s.source) AS servicios_tocados,
    COUNT(DISTINCT i.principal_id) AS identidades_distintas,
    MIN(e.event_time) AS primera_aparicion,
    MAX(e.event_time) AS ultima_aparicion,
    GROUP_CONCAT(DISTINCT i.type ORDER BY i.type) AS tipos_de_identity
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
WHERE e.source_ip IS NOT NULL
GROUP BY e.source_ip
ORDER BY llamadas DESC
LIMIT 15;
```

```sql
-- IPs con errores de autorizacion (posible ataque)
SELECT
    e.source_ip,
    COUNT(DISTINCT i.arn) AS usuarios_intentados,
    COUNT(*) AS intentos_fallidos,
    COUNT(DISTINCT s.source) AS servicios_probed,
    GROUP_CONCAT(DISTINCT n.name ORDER BY n.name) AS operaciones_intentadas,
    MIN(e.event_time) AS primer_intento,
    MAX(e.event_time) AS ultimo_intento,
    TIMESTAMPDIFF(MINUTE, MIN(e.event_time), MAX(e.event_time)) AS ventana_minutos
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
JOIN error_codes ec ON e.error_code_id = ec.id
WHERE ec.code LIKE 'AccessDenied%'
GROUP BY e.source_ip
HAVING intentos_fallidos > 5
ORDER BY intentos_fallidos DESC;
```

### Laboratorio 4.3: Condicion de Tags

```sql
-- Operaciones que usan tags (input para politicas basadas en tags)
SELECT
    n.name AS operacion,
    s.source AS servicio,
    e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].key" AS tag_key_1,
    e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].value" AS tag_value_1,
    e.request_parameters->>"$.tags[0].key" AS tag_key_2,
    e.request_parameters->>"$.tags[0].value" AS tag_value_2,
    COUNT(*) AS veces_usado
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE e.request_parameters IS NOT NULL
  AND (e.request_parameters->>"$.tagSpecificationSet" IS NOT NULL
       OR e.request_parameters->>"$.tags" IS NOT NULL)
GROUP BY n.name, s.source,
         e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].key",
         e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].value",
         e.request_parameters->>"$.tags[0].key",
         e.request_parameters->>"$.tags[0].value"
ORDER BY veces_usado DESC
LIMIT 15;
```

### Laboratorio 4.4: Condicion de Tiempo (Fuera de Horario)

```sql
-- Usando la vista calendar (si la creaste) o directamente
SELECT
    i.arn AS identity,
    n.name AS operacion,
    s.source AS servicio,
    HOUR(e.event_time) AS hora_del_dia,
    DAYNAME(e.event_time) AS dia_semana,
    e.source_ip,
    CASE
        WHEN HOUR(e.event_time) BETWEEN 9 AND 18 
             AND DAYOFWEEK(e.event_time) BETWEEN 2 AND 6 THEN '✓ Horario Laboral'
        ELSE '⚠️ Fuera de horario'
    END AS evaluacion_horario,
    e.request_parameters->>"$.instanceType" AS instance_type, -- Corregido typo y comillas
    e.request_parameters->>"$.bucketName" AS bucket
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE i.type IN ('IAMUser', 'AssumedRole')
  AND e.read_only = 0 
  AND (HOUR(e.event_time) NOT BETWEEN 9 AND 18
       OR DAYOFWEEK(e.event_time) IN (1, 7))
ORDER BY e.event_time DESC
LIMIT 20;
```

### Laboratorio 4.5: Simular una Politica con Condiciones

**Escenario:** Quieres permitir `ec2:RunInstances` solo si:
- instanceType es `t3.micro` o `t3.small`
- Tiene tag `Environment=Production`
- Viene de IP corporativa `192.168.x.x`
- En horario laboral

```sql
-- Encuentra llamadas que CUMPLIRIAN la politica
SELECT
    e.event_time,
    i.arn AS quien,
    n.name AS operacion,
    e.source_ip,
    e.request_parameters->>"$.instanceType" AS instance_type,
    e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].key" AS tag_key,
    e.request_parameters->>"$.tagSpecificationSet.items[0].tags[0].value" AS tag_value,
    HOUR(e.event_time) AS hora,
    DAYNAME(e.event_time) AS dia
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
WHERE n.name = 'RunInstances'
  AND e.request_parameters->>"$.instanceType" IN ('t3.micro', 't3.small')
  AND e.source_ip LIKE '192.168.%'
  AND HOUR(e.event_time) BETWEEN 9 AND 18
  AND DAYOFWEEK(e.event_time) BETWEEN 2 AND 6
ORDER BY e.event_time DESC;

-- Encuentra llamadas que NO CUMPLIRIAN (serian denegadas)
SELECT
    e.event_time,
    i.arn AS quien,
    n.name AS operacion,
    e.source_ip,
    e.request_parameters->>"$.instanceType" AS instance_type,
    HOUR(e.event_time) AS hora,
    CONCAT(
        CASE WHEN e.request_parameters->>"$.instanceType" NOT IN ('t3.micro', 't3.small') 
             THEN 'instanceType invalido; ' ELSE '' END,
        CASE WHEN e.source_ip NOT LIKE '192.168.%' 
             THEN 'IP no corporativa; ' ELSE '' END,
        CASE WHEN HOUR(e.event_time) NOT BETWEEN 9 AND 18 
             THEN 'Fuera de horario; ' ELSE '' END
    ) AS razones_denegacion
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
WHERE n.name = 'RunInstances'
  AND (
      e.request_parameters->>"$.instanceType" NOT IN ('t3.micro', 't3.small')
      OR e.source_ip NOT LIKE '192.168.%'
      OR HOUR(e.event_time) NOT BETWEEN 9 AND 18
  )
ORDER BY e.event_time DESC;
```

---

## Modulo 5: Tipos de Servicios y Patrones de API

**Duracion:** 2.5 horas teoricas + 2.5 horas laboratorio  
**Objetivo:** Clasificar servicios por comportamiento y detectar patrones de API.

### Teoria 5.1: Clasificacion de Servicios

Basandonos en sus operaciones CloudTrail, los servicios se clasifican en:

| Patron | Caracteristicas | Ejemplos |
|---|---|---|
| **CRUD** | Balance de lecturas/escrituras | DynamoDB, S3, RDS |
| **Action/RPC** | Dominado por Invoke/Send/Process | Lambda, SQS, SNS |
| **Orchestrator** | Muchas operaciones, llama a otros | CloudFormation, StepFunctions |
| **ReadOnly** | Solo Describe/List/Get | CloudTrail, algunas partes de Config |
| **WriteOnly** | Solo Create/Update/Delete (raro) | Algunos servicios de provisioning |

### Laboratorio 5.1: Clasificador Automatico

```sql
-- Usando la vista service_classification (ya creada)
SELECT
    event_source,
    total_operations,
    write_operations,
    read_operations,
    action_operations,
    service_pattern,
    service_domain,
    total_calls,
    ROUND(write_operations * 100.0 / NULLIF(total_calls, 0), 1) AS pct_write,
    ROUND(read_operations * 100.0 / NULLIF(total_calls, 0), 1) AS pct_read,
    ROUND(action_operations * 100.0 / NULLIF(total_calls, 0), 1) AS pct_action
FROM service_classification
ORDER BY total_calls DESC;
```

**Interpretacion de patrones:**
| service_pattern | Significado |
|---|---|
| `CRUD` | Servicio de datos tradicional. Leer y escribir con similar frecuencia. |
| `ReadOnly` | Servicio de observabilidad o catalogo. Solo consultas. |
| `ActionBased` | Servicio de computo o mensajeria. La accion principal no es CRUD. |
| `WriteOnly` | Servicio de provisionamiento. Crear recursos es lo unico que hace. |

### Laboratorio 5.2: Patrones de Consistencia Eventual

```sql
-- Operaciones que fallan temporalmente (eventual consistency)
SELECT
    n.name AS operacion,
    ec.code AS error,
    e.error_message,
    COUNT(*) AS fallos,
    MIN(e.event_time) AS primer_fallo,
    MAX(e.event_time) AS ultimo_fallo,
    TIMESTAMPDIFF(SECOND, MIN(e.event_time), MAX(e.event_time)) AS ventana_segundos
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN error_codes ec ON e.error_code_id = ec.id
WHERE ec.code REGEXP 'NotYet|NotFound|Throttl|Conflict| propagat'
   OR e.error_message REGEXP 'not yet|not found|still propagat|eventual|retry'
GROUP BY n.name, ec.code, e.error_message
ORDER BY fallos DESC;
```

```sql
-- Caso especifico: creacion + fallo posterior por "no existe"
-- (indica consistencia eventual)
WITH creations AS (
    SELECT
        e.request_parameters->>"$.bucketName" AS resource,
        e.event_time AS created_at
    FROM events e
    JOIN event_names n ON e.event_name_id = n.id
    WHERE n.name LIKE '%Create%'
      AND e.error_code_id IS NULL
),
failures AS (
    SELECT
        e.request_parameters->>"$.bucketName" AS resource,
        e.event_time AS failed_at,
        ec.code AS error
    FROM events e
    JOIN event_names n ON e.event_name_id = n.id
    JOIN error_codes ec ON e.error_code_id = ec.id
    WHERE ec.code REGEXP 'NotFound|NoSuch'
)
SELECT
    c.resource,
    c.created_at,
    f.failed_at,
    TIMESTAMPDIFF(SECOND, c.created_at, f.failed_at) AS segundos_hasta_fallo,
    f.error
FROM creations c
JOIN failures f ON c.resource = f.resource
WHERE f.failed_at > c.created_at
  AND TIMESTAMPDIFF(SECOND, c.created_at, f.failed_at) < 60  -- Dentro de 1 minuto
ORDER BY segundos_hasta_fallo;
```

### Laboratorio 5.3: Paginacion

```sql
-- ¿Quien usa paginacion correctamente? (NextToken en request)
SELECT
    i.arn AS caller,
    COUNT(*) AS total_calls,
    SUM(CASE WHEN e.request_parameters->>"$.NextToken" IS NOT NULL  -- Corregido e.request
              OR e.request_parameters->>"$.nextToken" IS NOT NULL
             THEN 1 ELSE 0 END) AS calls_paginadas,
    SUM(CASE WHEN e.request_parameters->>"$.MaxResults" IS NOT NULL 
              OR e.request_parameters->>"$.maxResults" IS NOT NULL
             THEN 1 ELSE 0 END) AS calls_con_limite,
    ROUND(
        SUM(CASE WHEN e.request_parameters->>"$.NextToken" IS NOT NULL THEN 1 ELSE 0 END) 
        * 100.0 / COUNT(*), 1
    ) AS pct_paginado
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
WHERE n.name REGEXP 'List|Describe|Get.*Page|Query|Scan'
GROUP BY i.arn
HAVING total_calls > 5
ORDER BY pct_paginado ASC;
```

### Laboratorio 5.4: Idempotencia

```sql
-- Buscar clientToken (mecanismo de idempotencia de AWS)
SELECT
    n.name AS operacion,
    e.request_parameters->>"$.clientToken" AS token,
    COUNT(*) AS veces_enviado,
    MIN(e.event_time) AS primera_vez,
    MAX(e.event_time) AS ultima_vez,
    CASE 
        WHEN COUNT(*) = 1 THEN 'Unico (idempotente o no necesario)'
        WHEN COUNT(DISTINCT e.error_code_id) = 0 THEN 'Repetido, todos OK'
        ELSE 'Repetido, algun fallo'
    END AS comportamiento
FROM events e
JOIN event_names n ON e.event_name_id = n.id
WHERE e.request_parameters->>"$.clientToken" IS NOT NULL
GROUP BY n.name, e.request_parameters->>"$.clientToken"
HAVING veces_enviado > 1
ORDER BY veces_enviado DESC
LIMIT 15;
```

### Laboratorio 5.5: Mapa Real de Dependencias

```sql
-- Usando la vista service_interactions
SELECT
    caller_service,
    target_service,
    SUM(interaction_count) AS total_interacciones,
    GROUP_CONCAT(DISTINCT action ORDER BY action SEPARATOR ', ') AS acciones
FROM service_interactions
WHERE caller_service IS NOT NULL
GROUP BY caller_service, target_service
ORDER BY total_interacciones DESC
LIMIT 25;
```

**Descubrimientos tipicos:**
| caller_service | target_service | Significado |
|---|---|---|
| cloudformation.amazonaws.com | ec2.amazonaws.com | CFN provisiona EC2 |
| cloudformation.amazonaws.com | iam.amazonaws.com | CFN crea roles/policies |
| autoscaling.amazonaws.com | ec2.amazonaws.com | ASG verifica instancias |
| lambda.amazonaws.com | logs.amazonaws.com | Lambda escribe logs |
| eks.amazonaws.com | ec2.amazonaws.com | EKS gestiona nodos EC2 |

### Laboratorio 5.6: SQS vs SNS - ¿Son lo Mismo?

```sql
-- Comparar estructura de eventos de SQS vs SNS
SELECT
    s.source,
    n.name AS operacion,
    COUNT(*) AS frecuencia,
    e.request_parameters->>"$.QueueUrl" AS queue_url, -- Corregido typo 'parametrs'
    e.request_parameters->>"$.TopicArn" AS topic_arn,
    e.request_parameters->>"$.Message" AS message_sample,
    inv.invoker as invoked_by
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN invocation_sources inv ON i.invoker_id = inv.id
WHERE s.source IN ('sqs.amazonaws.com', 'sns.amazonaws.com')
GROUP BY s.source, n.name,
         e.request_parameters->>"$.QueueUrl",
         e.request_parameters->>"$.TopicArn",
         e.request_parameters->>"$.Message",
         inv.invoker
ORDER BY s.source, frecuencia DESC
LIMIT 20;```

**Hipotesis del curso:** SQS y SNS comparten infraestructura subyacente pero exponen contratos de entrega diferentes (cola vs pub/sub). CloudTrail te permite ver si las operaciones internas tienen patrones similares.

---

## Proyecto Final: Reconstruir una Arquitectura desde Cero

**Duracion:** 3 horas  
**Contexto:** Tu equipo heredo una aplicacion serverless sin documentacion. Solo tienes CloudTrail.

### Paso 1: Encontrar el Request Inicial (1 hora)

```sql
-- Encuentra requests que inicien en API Gateway
SELECT
    e.event_time,
    e.request_id,
    n.name AS operacion,
    e.request_parameters->>"$.resource" AS api_resource,
    e.request_parameters->>"$.httpMethod" AS http_method,
    e.request_parameters->>"$.stage" AS stage,
    i.arn AS caller,
    e.source_ip
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
JOIN event_sources s ON e.source_id = s.id
WHERE s.source = 'apigateway.amazonaws.com'
  AND n.name REGEXP 'Invoke|Execute'
ORDER BY e.event_time DESC
LIMIT 5;
```

```sql
-- Con un request_id especifico, traza TODA la cadena
SELECT
    e.event_time,
    TIMESTAMPDIFF(MICROSECOND, 
        FIRST_VALUE(e.event_time) OVER (ORDER BY e.event_time), 
        e.event_time
    ) / 1000.0 AS ms_desde_inicio,
    s.source AS servicio,
    n.name AS operacion,
    i.type AS tipo_auth,
    iss.user_name AS rol,
    CASE WHEN e.error_code_id IS NULL THEN 'OK' ELSE ec.code END AS estado,
    e.request_parameters->>"$.functionName" AS lambda_target,
    e.request_parameters->>"$.tableName" AS dynamo_table,
    e.request_parameters->>"$.Key" AS dynamo_key,
    e.source_ip
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
LEFT JOIN error_codes ec ON e.error_code_id = ec.id
WHERE e.request_id = 'REEMPLAZA_CON_REQUEST_ID'
   OR e.event_time BETWEEN (
       SELECT MIN(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
   ) AND (
       SELECT MAX(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
   )
ORDER BY e.event_time;
```

### Paso 2: Mapeo de Roles y Permisos (1 hora)

```sql
-- Roles involucrados en la cadena
SELECT DISTINCT
    iss.user_name AS rol,
    iss.arn AS rol_arn,
    s.source AS servicio_que_usa,
    n.name AS operacion,
    e.event_time
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
WHERE (e.request_id = 'REEMPLAZA_CON_REQUEST_ID'
    OR e.event_time BETWEEN (
        SELECT MIN(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ) AND (
        SELECT MAX(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ))
  AND iss.arn IS NOT NULL
ORDER BY e.event_time;
```

### Paso 3: Parametros que Fluyen Entre Servicios (30 min)

```sql
-- Extraer parametros clave de cada paso
SELECT
    e.event_time,
    s.source,
    n.name,
    JSON_PRETTY(e.request_parameters) AS parametros_completos,
    e.response_elements->>"$.statusCode" AS http_status,
    CASE
        WHEN s.source = 'apigateway.amazonaws.com' THEN '1. Entrada'
        WHEN s.source = 'lambda.amazonaws.com' THEN '2. Computo'
        WHEN s.source = 'dynamodb.amazonaws.com' THEN '3. Persistencia'
        ELSE '4. Otro'
    END AS capa_arquitectura
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE (e.request_id = 'REEMPLAZA_CON_REQUEST_ID'
    OR e.event_time BETWEEN (
        SELECT MIN(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ) AND (
        SELECT MAX(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ))
ORDER BY e.event_time;
```

### Paso 4: Deteccion de Errores y Bottlenecks (30 min)

```sql
-- Errores en la cadena
SELECT
    e.event_time,
    s.source,
    n.name AS operacion,
    ec.code AS error,
    e.error_message,
    e.request_parameters->>"$.functionName" AS lambda,
    e.request_parameters->>"$.tableName" AS tabla
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN error_codes ec ON e.error_code_id = ec.id
WHERE (e.request_id = 'REEMPLAZA_CON_REQUEST_ID'
    OR e.event_time BETWEEN (
        SELECT MIN(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ) AND (
        SELECT MAX(event_time) FROM events WHERE request_id = 'REEMPLAZA_CON_REQUEST_ID'
    ))
ORDER BY e.event_time;
```

```sql
-- Latencias entre pasos
WITH cadena AS (
    SELECT
        e.event_time,
        s.source,
        n.name,
        LAG(e.event_time) OVER (ORDER BY e.event_time) AS prev_time,
        TIMESTAMPDIFF(MICROSECOND, 
            LAG(e.event_time) OVER (ORDER BY e.event_time),
            e.event_time
        ) / 1000.0 AS latencia_ms
    FROM events e
    JOIN event_names n ON e.event_name_id = n.id
    JOIN event_sources s ON e.source_id = s.id
    WHERE e.request_id = 'TU_REQUEST_ID' -- Recuerda cambiar esto
)
SELECT
    source,
    name,
    latencia_ms,
    CASE
        WHEN latencia_ms < 10 THEN '⚡ Rapido (cached)'
        WHEN latencia_ms < 100 THEN '✓ Normal'
        WHEN latencia_ms < 500 THEN '⚠️ Lento' -- Corregido typo 'latenci'
        ELSE '🔴 Muy lento o timeout'
    END AS evaluacion
FROM cadena
ORDER BY event_time;
```

### Diagrama de Secuencia Esperado

```
Usuario
  | HTTP GET /api/users
  v
API Gateway  [request_id: abc-123]
  | Invoke lambda:GetUsers
  v
Lambda (rol: api-lambda-role)  [AssumeRole automatico]
  | Scan dynamodb:UsersTable
  v
DynamoDB
  | (retorna items)
  v
Lambda (procesa respuesta)
  | (retorna a API Gateway)
  v
API Gateway (formatea HTTP response)
  |
Usuario <- HTTP 200 + JSON

Cada flecha deja un evento en CloudTrail con el MISMO request_id
```

### Rubrica de Evaluacion

| Criterio | Puntaje | Logrado |
|---|---|---|
| Encontro todos los eventos de la cadena | 25 pts | ☐ |
| Identifico correctamente cada rol usado | 20 pts | ☐ |
| Mapeo los parametros que pasan entre servicios | 20 pts | ☐ |
| Detecto al menos 1 error potencial o bottleneck | 15 pts | ☐ |
| El diagrama de secuencia es preciso y completo | 20 pts | ☐ |
| **TOTAL** | **100 pts** | |

---

e A: Vistas del Instructor

Queries utiles para generar ejemplos didacticos automaticamente:

```sql
-- A.1: Un ejemplo de cada tipo de error
SELECT DISTINCT
    ec.code AS error_code,
    e.error_message,
    n.name AS operacion,
    s.source AS servicio,
    e.event_time
FROM events e
JOIN error_codes ec ON e.error_code_id = ec.id
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
WHERE ec.code IS NOT NULL
ORDER BY ec.code, e.event_time DESC;

-- A.2: Ejemplos de cada mecanismo de autenticacion
SELECT
    ca.credential_source,
    ca.identity_type,
    ca.principal_id,
    ca.event_name,
    ca.event_source,
    ca.mfa_authenticated,
    COUNT(*) AS ejemplos
FROM credential_analysis ca
GROUP BY ca.credential_source, ca.identity_type, ca.principal_id,
         ca.event_name, ca.event_source, ca.mfa_authenticated
ORDER BY ca.credential_source, ejemplos DESC;

-- A.3: Servicios que mas llaman a otros
SELECT
    invoker,
    COUNT(DISTINCT target_service) AS servicios_llamados,
    SUM(interaction_count) AS total_llamadas
FROM service_interactions
WHERE caller_service IS NOT NULL
GROUP BY invoker
ORDER BY servicios_llamados DESC;

-- A.4: Ejemplo de asuncion de rol completa (con credenciales resultantes)
SELECT
    e.event_time,
    n.name,
    i.arn AS quien_solicita,
    e.request_parameters->>"$.roleArn" AS rol_solicitado,
    e.response_elements->>"$.credentials.accessKeyId" AS ak_temporal,
    e.response_elements->>"$.credentials.sessionToken" AS session_token_truncado,
    e.response_elements->>"$.sourceIdentity" AS source_identity
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
WHERE n.name = 'AssumeRole'
ORDER BY e.event_time DESC
LIMIT 5;

-- A.5: Eventos de un solo servicio (para analisis profundo)
-- Cambia 'ec2.amazonaws.com' por cualquier servicio
SELECT
    n.name AS operation,
    COUNT(*) AS freq,
    SUM(CASE WHEN e.read_only = 1 THEN 1 ELSE 0 END) AS `reads`, -- Agregado backticks
    SUM(CASE WHEN e.read_only = 0 THEN 1 ELSE 0 END) AS `writes`, -- Agregado backticks
    COUNT(DISTINCT i.type) AS tipos_identity
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN event_sources s ON e.source_id = s.id
JOIN identities i ON e.identity_id = i.id
WHERE s.source = 'ec2.amazonaws.com'
GROUP BY n.name
ORDER BY freq DESC
LIMIT 30;
```

---

## Apendice B: Glosario de Patrones

### Patrones de Autenticacion
| Patron | Signature CloudTrail | Significado |
|---|---|---|
| **Service Auto-Auth** | `invokedBy = servicio.aws.amazon.com` + `type = AssumedRole` | El servicio se autentica solo via STS |
| **Human with MFA** | `type = IAMUser` + `mfaAuthenticated = true` | Usuario con segundo factor |
| **App via Role** | `type = AssumedRole` + `sessionIssuer` es un rol de app | Aplicacion usando rol con credenciales temporales |
| **Cross-Account** | `accountId != recipientAccountId` | Acceso entre cuentas AWS |

### Patrones de Operacion
| Patron | Signature CloudTrail | Significado |
|---|---|---|
| **Health Check Loop** | Mismo eventName cada 60 segundos, `invokedBy` presente | Servicio sondeando estado |
| **Cascade Failure** | Mismo request_id, multiples errores progresivos | Fallo en cascada entre servicios |
| **Retry Pattern** | Mismo request_id, errorCode cambia de Throttling a OK | Reintento automatico exitoso |
| **Config Drift** | `Update*` sin `Create*` previo en ventana reciente | Modificacion de recurso existente |

### Patrones de Arquitectura
| Patron | Signature CloudTrail | Significado |
|---|---|---|
| **Event-Driven** | Lambda invokedBy = `events.amazonaws.com` o `sns.amazonaws.com` | Arquitectura basada en eventos |
| **API Gateway → Lambda** | `apigateway:Invoke` seguido de `lambda:Invoke` | Serverless API |
| **Container Orchestration** | `eks:*` o `ecs:*` llamando a `ec2:*` y `iam:PassRole` | Cluster de contenedores |
| **IaC Deployment** | `cloudformation:*` con decenas de llamadas subsecuentes | Infrastructure as Code |

---

## Tabla Resumen: Cada Campo del Modelo, una Leccion

| Campo/Tabla | Leccion que Enseña |
|---|---|
| `event_names` |da servicio tiene un vocabulario propio de operaciones |
| `event_sources` | La red de servicios que componen tu cuenta |
| `identities.type` | Los 4 mecanismos de autenticacion |
| `identities.principalId` | STS sessions (AROA...) vs credenciales largas (AKIA) |
| `identities.invoker_id` | Cross-service authentication |
| `issuers` | La cadena de confianza de roles |
| `events.read_only` | 90% de la actividad es lectura (sondeo, caching) |
| `events.mfa_authenticated` | Postura de seguridad de la cuenta |
| `events.source_ip` | Geolocalizacion y control de acceso por red |
| `events.request_id` | Trazabilidad distribuida |
| `events.request_parameters` | El "contrato" de cada API: que parametros acepta |
| `events.response_elements` | El resultado y su estructura |
| `events.error_code` | El sistema de "rejection" de AWS |
| `events.session_creation_date` | TTL de credenciales temporales |
| `event_resources` | El grafo de recursos afectados |

