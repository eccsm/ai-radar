# AI RADAR SYSTEM

A distributed, microservice-based system for monitoring AI developments across the web.

## System Architecture

The AI Radar system consists of several components:

- **Core Infrastructure**: PostgreSQL database with pgvector, NATS message queue, and MinIO object storage
- **Tool Hub**: Central API service that provides endpoints for fetching and processing content
- **Agent Services**: Specialized microservices for specific tasks
  - **Fetcher Agent**: Retrieves content from various sources
  - **Summariser Agent**: Generates summaries and embeddings for content
  - **Ranker Agent**: Ranks and prioritizes content based on importance
  - **Scheduler Agent**: Manages scheduled tasks and periodic updates
- **Dashboard**: Streamlit app for visualizing system data
- **Monitoring Stack**: Comprehensive monitoring tools for system health

## Getting Started

### Prerequisites

- Docker and Docker Compose
- OpenAI API key for summarization and ranking
- (Optional) NewsAPI key for additional content sources
- (Optional) Slack webhook URL for notifications

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/eccsm/ai-radar.git
   cd ai-radar
   ```

2. Create directory structure:
   ```
   chmod +x create_example_files.sh
   ./create_example_files.sh
   ```

3. Configure environment variables in `.env`:
   ```
   POSTGRES_DB=ai_radar
   POSTGRES_USER=ai
   POSTGRES_PASSWORD=ai_pwd
   MINIO_ROOT_USER=minio
   MINIO_ROOT_PASSWORD=minio_pwd
   OPENAI_API_KEY=your_openai_api_key
   NEWSAPI_KEY=your_newsapi_key
   SLACK_WEBHOOK_URL=your_slack_webhook_url
   PGADMIN_DEFAULT_EMAIL=admin@example.com
   PGADMIN_DEFAULT_PASSWORD=admin
   ```

4. Start the system:
   ```
   docker-compose up -d
   ```

### Accessing Tools

- **Dashboard**: http://localhost:8501
- **pgAdmin**: http://localhost:5050
- **MinIO Console**: http://localhost:9001
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
- **Portainer**: http://localhost:9000
- **cAdvisor**: http://localhost:8080
- **NATS Monitoring**: http://localhost:8222

## Usage

### Adding RSS Sources

You can add new RSS sources using the Tool Hub API:

```bash
curl -X POST http://localhost:8000/sources/rss \
  -H "Content-Type: application/json" \
  -d '{"url": "https://blog.example.com/feed", "name": "Example Blog"}'
```

### Fetching Articles

Fetch articles from a specific URL:

```bash
curl -X POST http://localhost:8000/article/fetch \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'
```

### Viewing Content

Access the dashboard at http://localhost:8501 to view:
- System overview
- Trending articles
- Source analytics
- Article explorer
- Search functionality

## Extending the System

### Adding New Agents

1. Create a new directory in `agents/`:
   ```
   mkdir -p agents/new-agent/new_agent
   touch agents/new-agent/new_agent/__init__.py
   ```

2. Create Dockerfile and requirements.txt

3. Add your agent to docker-compose.yaml:
   ```yaml
   new-agent:
     build:
       context: ./agents/new-agent
       dockerfile: Dockerfile
     <<: *service-base
     environment:
       <<: *base-env
     depends_on:
       nats:
         condition: service_healthy
   ```

4. Implement the agent code to subscribe to relevant NATS subjects

### Using NATS for Communication

Subscribe to subjects:
```python
sub = await js.subscribe(
    "ai-radar.tasks.your_task",
    cb=your_callback_function,
    durable="your-consumer-name",
    manual_ack=True,
)
```

Publish messages:
```python
await js.publish(
    "ai-radar.tasks.your_task",
    json.dumps(payload).encode()
)
```

## Monitoring

The system includes a comprehensive monitoring stack:

- **Prometheus**: Metrics collection and storage
- **Grafana**: Visualization dashboards
- **cAdvisor**: Container metrics
- **Postgres Exporter**: Database metrics
- **Portainer**: Container management

## Maintenance

### Backing Up Data

Backup PostgreSQL:
```bash
docker exec -t ai-radar-db-1 pg_dump -U ai ai_radar > backup.sql
```

Backup volumes:
```bash
docker run --rm -v ai-radar_pg_data:/source -v $(pwd):/backup alpine tar -czf /backup/pg_backup.tar.gz -C /source .
```

### Updating Components

```bash
docker-compose pull
docker-compose up -d --build
```

## Secrets Management

This project uses HashiCorp Vault for secrets management in production. For development:

1. Copy `.env.example` to `.env` and fill in your credentials
2. Use the included scripts to initialize Vault:
   ```powershell
   # On Windows
   .\vault-init.ps1
   
   # On Linux/macOS
   ./vault-init.sh
   ```

### GitHub Setup

When pushing to GitHub:

1. The `.gitignore` file is configured to exclude sensitive files including:
   - `.env` files and secret files
   - Vault data and tokens
   - Database files and MinIO data
   - Docker override files that might contain secrets

2. For contributors:
   - Clone the repository
   - Copy `.env.example` to `.env` and fill with your own credentials
   - Never commit actual secrets or credentials to the repository
   - Use Vault for production secrets management

3. CI/CD considerations:
   - Use GitHub Secrets or similar for CI/CD pipelines
   - Consider using Vault integration in your CI/CD workflow
   - Never print secrets in logs or expose them in build artifacts

## Architecture Diagram

```
┌────────────────┐     ┌────────────┐     ┌─────────┐
│                │     │            │     │         │
│  Tool Hub API  │◄───►│  Database  │◄───►│  MinIO  │
│                │     │            │     │         │
└───────┬────────┘     └────────────┘     └─────────┘
        │                     ▲                ▲
        ▼                     │                │
┌────────────────┐            │                │
│                │            │                │
│      NATS      │            │                │
│                │            │                │
└───┬─────┬──────┘            │                │
    │     │                   │                │
    ▼     ▼                   │                │
┌────┐ ┌────┐                 │                │
│    │ │    │                 │                │
│ F  │ │ S  │─────────────────┘                │
│    │ │    │                                  │
└────┘ └────┘                                  │
                                               │
┌────┐ ┌────┐                                  │
│    │ │    │                                  │
│ R  │ │ Sc │                                  │
│    │ │    │                                  │
└────┘ └────┘                                  │
                                               │
┌────────────────┐                             │
│                │                             │
│   Dashboard    │─────────────────────────────┘
│                │
└────────────────┘
```

F = Fetcher, S = Summariser, R = Ranker, Sc = Scheduler

## License

This project is licensed under the MIT License.