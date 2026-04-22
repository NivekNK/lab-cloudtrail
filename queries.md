### 1. Detección de Actividad Humana
[cite_start]Esta consulta identifica acciones realizadas por usuarios reales (IAM Users o vía SSO) en lugar de procesos automáticos, basándose en el tipo de identidad y los navegadores utilizados[cite: 107, 110, 173].

```sql
SELECT 
    e.event_time, 
    n.name AS action, 
    i.user_name, 
    i.type AS identity_type,
    e.source_ip, 
    ua.agent
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
JOIN user_agents ua ON e.user_agent_id = ua.id
WHERE i.type IN ('IAMUser', 'AssumedRole') 
  [cite_start]AND (ua.agent LIKE '%Mozilla%' OR ua.agent LIKE '%Safari%' OR ua.agent LIKE '%Chrome%') -- Detecta navegadores [cite: 173]
  AND i.user_name NOT LIKE '%role%' -- Filtra servicios comunes
ORDER BY e.event_time DESC;
```

### 2. Monitoreo de Agentes de CloudWatch y Métricas
[cite_start]Identifica qué entidades están recopilando métricas activamente, filtrando específicamente por el binario del agente de CloudWatch detectado en los logs[cite: 93].

```sql
SELECT 
    i.principal_id, 
    n.name AS api_call, 
    COUNT(*) as frequency,
    ua.agent
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
JOIN user_agents ua ON e.user_agent_id = ua.id
[cite_start]WHERE ua.agent LIKE '%CWAgent%' -- Identificado específicamente en los logs [cite: 93]
GROUP BY i.principal_id, n.name, ua.agent;
```

### 3. Actividad de Nodos de Cluster EKS
[cite_start]Esta consulta rastrea las interacciones de los nodos físicos de tu cluster (NodeGroups) con otros servicios de AWS como EC2 o EFS[cite: 92, 121].

```sql
SELECT 
    e.event_time, 
    s.source AS aws_service, 
    n.name AS action, 
    i.principal_id AS node_role,
    r.resource_name AS target_resource
FROM events e
JOIN event_sources s ON e.source_id = s.id
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
LEFT JOIN event_resources r ON e.event_id = r.event_id
[cite_start]WHERE i.arn LIKE '%assumed-role/wyc-eks-ng-role%' -- Rol de nodo detectado [cite: 92]
ORDER BY e.event_time DESC;
```

### 4. Auditoría de Seguridad: Acciones sin MFA
[cite_start]Es vital saber qué identidades con privilegios están realizando acciones sin haber pasado por una autenticación multifactor[cite: 2, 110].

```sql
SELECT 
    e.event_time, 
    i.user_name, 
    n.name AS action, 
    e.source_ip,
    iss.user_name AS role_issuer
FROM events e
JOIN identities i ON e.identity_id = i.id
JOIN event_names n ON e.event_name_id = n.id
LEFT JOIN issuers iss ON e.issuer_id = iss.id
[cite_start]WHERE e.mfa_authenticated = 0 -- Flag normalizado en el modelo [cite: 2]
  AND i.type != 'AWSService' -- Ignora servicios internos de AWS
ORDER BY e.event_time DESC;
```

---

### Propuetas para aprender las interacciones del Ecosistema AWS

Analizar estos datos te permite entender la "coreografía" invisible que ocurre en la nube. Aquí hay tres interacciones interesantes para investigar:

* [cite_start]**Cadena de Asunción de Roles:** Utiliza la tabla `issuers` para ver cómo un servicio (ej. EKS) asume un rol para obtener permisos temporales[cite: 13, 14]. [cite_start]Si buscas `AssumeRole` en `event_names`, verás la transición de permisos[cite: 9, 41].
* [cite_start]**Patrones de "Latido" (SSM):** Observa la frecuencia de `UpdateInstanceInformation`[cite: 4, 136]. [cite_start]Esto te enseñará cómo los agentes locales se comunican con el plano de control de AWS para confirmar que una máquina sigue "viva" y gestionada[cite: 5, 106].
* [cite_start]**Propagación de Errores de Permisos:** Al consultar la tabla `error_codes`, puedes aprender exactamente qué permisos (`iam:PassRole`, `s3:GetObject`, etc.) le faltan a una aplicación antes de que falle en producción[cite: 107, 124, 182].



### Consulta para ver Errores Críticos:
```sql
SELECT 
    ec.code AS error_type, 
    e.error_message, 
    n.name AS attempted_action, 
    i.arn AS identity
FROM events e
JOIN error_codes ec ON e.error_code_id = ec.id
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
WHERE e.error_code_id IS NOT NULL; [cite_start]-- Captura fallos como AccessDenied [cite: 107, 124]
```
Para visualizar los cambios realizados por humanos con un formato legible y estructurado, utilizaremos funciones de **MySQL 8.0+** como `JSON_PRETTY` para la visualización y el operador `->>` para la extracción de campos específicos.

[cite_start]Esta consulta te permite ver el "quién", "qué" y "cómo" de cada modificación de infraestructura, presentando los cuerpos de la petición y la respuesta de forma indentada[cite: 1, 3, 5].

### Consulta de Auditoría con Formateo JSON

```sql
SELECT 
    e.event_time, 
    n.name AS action_name, 
    i.user_name, 
    e.source_ip,
    -- Extraemos un resumen rápido del recurso directamente desde el JSON
    e.request_parameters->>"$.repositoryName" AS target_repo,
    e.request_parameters->>"$.instanceId" AS target_instance,
    -- Formateamos el bloque completo de la petición para lectura humana
    JSON_PRETTY(e.request_parameters) AS detailed_request,
    -- Formateamos la respuesta de AWS
    JSON_PRETTY(e.response_elements) AS detailed_response,
    -- Detalle de recursos desde la tabla normalizada
    GROUP_CONCAT(DISTINCT r.resource_name) AS affected_resources
FROM events e
JOIN event_names n ON e.event_name_id = n.id
JOIN identities i ON e.identity_id = i.id
JOIN user_agents ua ON e.user_agent_id = ua.id
LEFT JOIN event_resources r ON e.event_id = r.event_id AND e.event_time = r.event_time
WHERE 
    [cite_start]-- Filtrar solo eventos de escritura/modificación [cite: 1, 3]
    e.read_only = 0 
    [cite_start]-- Identificación de intervención humana por tipo y firma de navegador [cite: 2, 3]
    AND i.type IN ('IAMUser', 'AssumedRole')
    AND (ua.agent LIKE '%Mozilla%' OR ua.agent LIKE '%Chrome%' OR ua.agent LIKE '%Safari%')
    -- Excluir ruidos de sistema o logins
    AND n.name NOT IN ('ConsoleLogin', 'AssumeRole')
GROUP BY e.event_id, e.event_time
ORDER BY e.event_time DESC;
```

---

### Análisis de las funciones JSON utilizadas:

* [cite_start]**`JSON_PRETTY()`**: Transforma el string JSON plano almacenado en la base de datos en un bloque de texto con saltos de línea e indentación[cite: 3, 5]. [cite_start]Es ideal si estás ejecutando la consulta desde una terminal o un cliente como MySQL Workbench para revisar manualmente qué valores se cambiaron[cite: 144, 146].
* **Operador `->>`**: Es un atajo para `JSON_UNQUOTE(JSON_EXTRACT(...))`. [cite_start]Se utiliza para extraer un valor específico del JSON y presentarlo como una columna de texto normal[cite: 72, 93]. [cite_start]En la query, lo usamos para sacar el `repositoryName` (útil en eventos de ECR) o el `instanceId` (útil en EC2/SSM) sin tener que leer todo el objeto[cite: 145, 168].
* [cite_start]**Filtrado Predictivo**: Al unir con `user_agents`, descartamos automáticamente el tráfico de bots o servicios como el **Cluster Autoscaler** o **SSM Agent**, que utilizan firmas de software específicas en lugar de navegadores[cite: 3, 5, 59].

### ¿Por qué es útil para aprender AWS?
[cite_start]Al observar el `detailed_request` de un evento humano, podrás notar cómo la consola de AWS a menudo realiza múltiples llamadas "bajo el capó" o envía parámetros por defecto que no ves en la interfaz gráfica[cite: 72, 142]. [cite_start]Por ejemplo, en las subidas de imágenes a **ECR**, podrás ver el desglose de cada capa (`layerDigest`) y cómo AWS valida la disponibilidad antes de confirmar la carga[cite: 153, 155].



