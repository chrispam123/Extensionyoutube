The Nocturne es una proyecto profesional diseñada para la migración y respaldo de "reliquias" de YouTube (Suscripciones y Playlists). A diferencia de herramientas convencionales, Nocturne utiliza una arquitectura distribuida en AWS para garantizar la resiliencia, la gobernanza de cuotas y la escalabilidad infinita.
🏗️ Arquitectura del Sistema
El proyecto está construido bajo el principio de Desacoplamiento Total, utilizando un Monorepo gestionado por pnpm.

      [ FRONTEND: CHROME EXTENSION ]
             (React + Vite)
                   |
      (HTTPS)      v      (OIDC Auth)
+---------------------------------------+
|        AWS API GATEWAY (v2)           |
+---------------------------------------+
      |                |                |
      v                v                v
[Dispatcher] ---> [ SQS QUEUE ] ---> [ Worker ]
  (Ingesta)        (Resiliencia)      (Ejecución)
      |                |                |
      +------> [ DynamoDB ] <-----------+
               (State & Logs)           |
                                        v
      [ YouTube API ] <---------- [ S3 Búnker ]
Componentes Clave:
Dispatcher (Lambda): Punto de entrada que realiza el intercambio de tokens OAuth2 y valida el "Semáforo" de concurrencia.
Worker (Lambda): El motor de ejecución. Implementa Conciencia Temporal (Auto-relevo antes del timeout) e Idempotencia (Checkpoints en DynamoDB).
QuotaLedger (DynamoDB): Gobernanza en tiempo real que protege el presupuesto de la API de Google mediante contadores atómicos.
Resumer (Lambda): Sistema de Autocuración que reanima rituales pausados por falta de cuota mediante EventBridge.
🌑 Filosofía de Diseño: "The Modern Nocturne"
La interfaz rechaza la suavidad moderna en favor de una estética gótica-editorial:

Tipografía: MedievalSharp (Títulos) y Newsreader (Cuerpo).
Visual: Tenebrismo de alto contraste, bordes de 0px y acentos en Rojo Sangre.
UX: Flujo de "Identidad Silenciosa" que reconoce al usuario sin fricciones tras el primer ritual.
🛠️ Stack Tecnológico
Frontend: React 19, Vite, Tailwind CSS v4 (CSS-First).
Backend: Node.js 20 (ESM), AWS SDK v3.
Infraestructura: Terraform 1.10+ (S3 Native Locking).
Laboratorio Local: Docker Compose + LocalStack 3.0.
CI/CD: GitHub Actions + OpenID Connect (OIDC) para despliegues sin llaves secretas.
🚀 Guía de Inicio Rápido
1. Laboratorio Local (Simulación AWS)
El entorno es 100% reproducible. No necesitas instalar bases de datos en tu host.

# Clonar y preparar
git clone
pnpm install

# Levantar infraestructura local (DynamoDB, SQS, KMS, SSM)
docker compose up -d
2. Compilación y Empaquetado
# Validar tipos y generar bundles
pnpm build

# El robot de CI/CD generará los artefactos .zip automáticamente
🛡️ Seguridad y Gobernanza
Zero-Trust: Las Lambdas operan bajo el Principio de Mínimo Privilegio, con acceso restringido a ARNs específicos de tablas e índices.
Secret Management: Las credenciales de Google nunca tocan el código; residen cifradas en AWS SSM Parameter Store mediante llaves KMS.
Circuit Breaker: El sistema bloquea nuevas peticiones si detecta que la cuota diaria de YouTube está próxima a agotarse (Buffer de seguridad de 100 unidades).
📈 Roadmap de Ingeniería
 v1.0.0: Identidad persistente y Exportación Jerárquica.
 v1.1.0: Importación con Idempotencia y Escalabilidad (Auto-relevo).
 v1.2.0: Observabilidad avanzada con AWS X-Ray.
 v1.3.0: Soporte para migración de comentarios y metadatos extendidos.
Desarrollado con rigor por uopechris@gmail.com
Ingeniería de Sistemas arquietctura EDA+serverless asincrono.
