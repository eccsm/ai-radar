#!/usr/bin/env pwsh
# AI Radar Management Script for Windows
# Provides convenient commands for managing the Docker Compose environment

param (
    [Parameter(Position=0)]
    [string]$Command = "help",
    
    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments
)

function Show-Help {
    Write-Host "AI Radar Management Commands:"
    Write-Host "  .\ai-radar.ps1 up              - Start all services in development mode"
    Write-Host "  .\ai-radar.ps1 down            - Stop all services"
    Write-Host "  .\ai-radar.ps1 prod            - Start all services in production mode"
    Write-Host "  .\ai-radar.ps1 dev             - Start all services in development mode with code mounting"
    Write-Host "  .\ai-radar.ps1 reset-db        - Reset the database (delete all articles)"
    Write-Host "  .\ai-radar.ps1 logs <service>  - View logs for a specific service"
    Write-Host "  .\ai-radar.ps1 build <service> - Rebuild a specific service (or all if none specified)"
    Write-Host "  .\ai-radar.ps1 vault           - Set up Vault for secrets management (includes running vault-setup.ps1)"
    Write-Host "  .\ai-radar.ps1 vault-ui        - Open Vault UI in browser"
    Write-Host "  .\ai-radar.ps1 ui              - Open React UI in browser"
    Write-Host "  .\ai-radar.ps1 api             - Open API Swagger UI in browser"
    Write-Host "  .\ai-radar.ps1 backup          - Run a manual database backup"
    Write-Host "  .\ai-radar.ps1 clean           - Remove all containers and volumes"
    Write-Host "  .\ai-radar.ps1 prune           - Remove unused Docker resources"
    Write-Host "  .\ai-radar.ps1 status          - Show status of all services"
    Write-Host "  .\ai-radar.ps1 setup           - Create required secret files"
}

function New-DirectoryIfNotExists {
    param (
        [string]$Path
    )
    
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
        Write-Host "Created directory: $Path"
    }
}

function Initialize-VaultConfiguration {
    # Check if port 8200 is already in use
    $portInUse = Get-NetTCPConnection -LocalPort 8200 -ErrorAction SilentlyContinue
    if ($portInUse) {
        Write-Host "Port 8200 is already in use. Using port 8201 instead."
        $vaultPort = 8201
    } else {
        $vaultPort = 8200
    }

    # Check if Vault container already exists
    $vaultExists = docker ps -a | Select-String -Pattern "vault"
    if ($vaultExists) {
        Write-Host "Removing existing Vault container..."
        docker rm -f vault
    }

    # Start Vault in dev mode
    Write-Host "Starting Vault container on port $vaultPort..."
    docker run -d --name vault -p ${vaultPort}:8200 `
        -e "VAULT_DEV_ROOT_TOKEN_ID=root" `
        -e "VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200" `
        hashicorp/vault:1.15 server -dev

    Write-Host "Waiting for Vault to become responsive..."
    $vaultReady = $false
    $maxAttempts = 6 # Try for up to 30 seconds (6 attempts * 5 seconds interval)
    $currentAttempt = 0
    while (-not $vaultReady -and $currentAttempt -lt $maxAttempts) {
        $currentAttempt++
        Write-Host "Checking Vault status (attempt $currentAttempt of $maxAttempts)..."
        docker exec vault vault status 2>$null # Suppress stderr for the check command itself
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Vault container is responsive."
            $vaultReady = $true
        } else {
            if ($currentAttempt -lt $maxAttempts) {
                Write-Host "Vault not ready yet, waiting 5 seconds..."
                Start-Sleep -Seconds 5
            }
        }
    }

    if (-not $vaultReady) {
        Write-Error "Vault container 'vault' did not become responsive after $maxAttempts attempts. Please check 'docker logs vault' for errors."
        # Consider whether to halt script execution here if Vault is critical
        # For example: exit 1
        # Or return from function if appropriate
    }

    # Write the Vault token to secrets directory
    "root" | Out-File -FilePath "./secrets/vault_token.txt" -NoNewline -Encoding utf8
    Write-Host "Saved Vault token to secrets/vault_token.txt"

    # Create vault-auth directory for role IDs and secret IDs
    New-DirectoryIfNotExists -Path "./vault-auth"

    # Create placeholder role IDs and secret IDs for services
    $services = @("fetcher", "summariser", "ranker", "scheduler", "api", "ui")
    foreach ($service in $services) {
        "placeholder-role-id" | Out-File -FilePath "./vault-auth/$service-role-id.txt" -NoNewline -Encoding utf8
        "placeholder-secret-id" | Out-File -FilePath "./vault-auth/$service-secret-id.txt" -NoNewline -Encoding utf8
        Write-Host "Created placeholder auth files for $service"
    }

    Write-Host "Vault setup complete!"
    Write-Host "You can access the Vault UI at http://localhost:$vaultPort with token: root"
}

function Initialize-VaultTemplates {
    # Create Vault template files
    New-DirectoryIfNotExists -Path "./hcl/templates"

    # Database template
    $databaseTemplate = @"
{{- with secret "ai-radar/database" -}}
DB_HOST={{ .Data.data.host }}
DB_PORT={{ .Data.data.port }}
DB_USER={{ .Data.data.username }}
DB_PASSWORD={{ .Data.data.password }}
DB_NAME={{ .Data.data.database }}
{{- end -}}
"@

    # NATS template
    $natsTemplate = @"
{{- with secret "ai-radar/nats" -}}
NATS_URL=nats://{{ .Data.data.host }}:{{ .Data.data.port }}
NATS_SUBJECT_PREFIX={{ .Data.data.subject_prefix }}
NATS_STREAM_NAME={{ .Data.data.stream_name }}
{{- end -}}
"@

    # MinIO template
    $minioTemplate = @"
{{- with secret "ai-radar/minio" -}}
MINIO_ENDPOINT={{ .Data.data.endpoint }}
MINIO_ACCESS_KEY={{ .Data.data.access_key }}
MINIO_SECRET_KEY={{ .Data.data.secret_key }}
MINIO_BUCKET={{ .Data.data.bucket }}
{{- end -}}
"@

    # API Keys template
    $apiKeysTemplate = @"
{{- with secret "ai-radar/api-keys" -}}
NEWSAPI_KEY={{ .Data.data.newsapi }}
OPENAI_API_KEY={{ .Data.data.openai }}
SLACK_WEBHOOK={{ .Data.data.slack }}
{{- end -}}
"@

    # Write template files
    $databaseTemplate | Out-File -FilePath "./hcl/templates/database.tpl" -Encoding utf8
    $natsTemplate | Out-File -FilePath "./hcl/templates/nats.tpl" -Encoding utf8
    $minioTemplate | Out-File -FilePath "./hcl/templates/minio.tpl" -Encoding utf8
    $apiKeysTemplate | Out-File -FilePath "./hcl/templates/api-keys.tpl" -Encoding utf8

    Write-Host "Created Vault template files in hcl/templates directory"
}

function Initialize-SecretFiles {
    # Create secrets directory
    New-DirectoryIfNotExists -Path "./secrets"
    New-DirectoryIfNotExists -Path "./monitoring/loki"
    New-DirectoryIfNotExists -Path "./monitoring/promtail"
    New-DirectoryIfNotExists -Path "./backups"
    New-DirectoryIfNotExists -Path "./hcl/templates"
    
    # Create secret files if they don't exist
    $secretFiles = @{
        "pg_pass.txt" = "ai_pwd";
        "minio_user.txt" = "minio";
        "minio_pass.txt" = "minio_pwd";
        "postgres_url.txt" = "postgresql://ai:ai_pwd@db:5432/ai_radar";
        "nats_url.txt" = "nats://nats:4222";
        "minio_endpoint.txt" = "minio:9000";
        "newsapi_key.txt" = "your_newsapi_key_here";
        "openai_key.txt" = "your_openai_key_here";
        "grafana_user.txt" = "admin";
        "grafana_pass.txt" = "admin";
        "pgadmin_email.txt" = "admin@example.com";
        "pgadmin_pass.txt" = "admin";
        "postgres_exporter_dsn.txt" = "postgresql://ai:ai_pwd@db:5432/ai_radar?sslmode=disable";
        "vault_token.txt" = "root";
    }
    
    foreach ($file in $secretFiles.Keys) {
        $path = "./secrets/$file"
        if (-not (Test-Path $path)) {
            $secretFiles[$file] | Out-File -FilePath $path -NoNewline -Encoding utf8
            Write-Host "Created secret file: $path"
        }
    }
    
    # Create Loki config
    $lokiConfig = @"
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    address: 127.0.0.1
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
    final_sleep: 0s
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2020-05-15
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb:
    directory: /loki/index

  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h

chunk_store_config:
  max_look_back_period: 0s

table_manager:
  retention_deletes_enabled: false
  retention_period: 0s
"@
    
    if (-not (Test-Path "./monitoring/loki/local-config.yaml")) {
        $lokiConfig | Out-File -FilePath "./monitoring/loki/local-config.yaml" -Encoding utf8
        Write-Host "Created Loki config file"
    }
    
    # Create Promtail config
    $promtailConfig = @"
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: system
    static_configs:
      - targets:
          - localhost
        labels:
          job: varlogs
          __path__: /var/log/*log
"@
    
    if (-not (Test-Path "./monitoring/promtail/config.yaml")) {
        $promtailConfig | Out-File -FilePath "./monitoring/promtail/config.yaml" -Encoding utf8
        Write-Host "Created Promtail config file"
    }
    
    Write-Host "Secrets setup complete! You can now run '.\ai-radar.ps1 vault' to set up Vault."
}

function Start-VaultIfNotRunning {
    Write-Host "Checking Vault status..."
    $RunningVaultID = docker ps -q -f "name=^vault$" # Check for RUNNING container

    if ($RunningVaultID) {
        Write-Host "Vault container 'vault' (ID: $RunningVaultID) is already running."
        return
    }

    Write-Host "Vault container 'vault' is not running."
    # Check for ANY container (running or stopped) with the name 'vault'.
    # We use -a for all containers, -q for quiet (ID only).
    $ExistingVaultID = docker ps -aq -f "name=^vault$"

    if ($ExistingVaultID) {
        # Container exists but is not running (checked by $RunningVaultID), so it must be stopped.
        Write-Host "Found stopped Vault container 'vault' (ID: $ExistingVaultID). Starting it..."
        docker start vault | Out-Null # 'vault' is the container name
        Write-Host "Waiting for Vault to initialize (5 seconds)..."
        Start-Sleep -Seconds 5
        
        $VaultNowRunningID = docker ps -q -f "name=^vault$"
        if ($VaultNowRunningID) {
            Write-Host "Vault container 'vault' (ID: $VaultNowRunningID) started successfully from stopped state."
        } else {
            Write-Warning "Failed to start stopped Vault container 'vault'. Please check Docker logs for 'vault'."
        }
        return # Attempted to start the stopped container, so we are done with this function.
    }
    
    # If we reach here, Vault container does not exist at all (neither running nor stopped).
    # Perform full fresh initialization.
    Write-Host "Vault container 'vault' does not exist. Performing full fresh initialization sequence..."
    
    Initialize-VaultConfiguration # This function creates and starts the Vault container, token, auth files.
    Initialize-VaultTemplates     # This function creates HCL templates.
    
    Write-Host "Running external Vault setup script (vault-setup.ps1)..."
    ./vault-setup.ps1             # Run user's custom setup.
    
    Write-Host "Vault fully initialized as part of startup process."
    # Note: Initialize-VaultConfiguration also prints its own completion messages and checks for start success.
}

# Execute the appropriate command
switch ($Command) {
    "vault" {
        Initialize-VaultConfiguration
        Initialize-VaultTemplates
        Write-Host "Running external Vault setup script (vault-setup.ps1)..."
        ./vault-setup.ps1
        Write-Host "Vault setup complete! You can now run '.\ai-radar.ps1 dev' to start the services."
    }
    "help" {
        Show-Help
    }
    "build" {
        $service = $Arguments[0]
        
        if ($service) {
            Write-Host "Rebuilding service: $service"
            docker compose build --no-cache $service
            
            # Restart the service after rebuilding
            Write-Host "Restarting service: $service"
            docker compose stop $service
            docker compose rm -f $service
            docker compose up -d $service
        } else {
            Write-Host "Rebuilding all services..."
            docker compose build --no-cache
            
            # Restart all services
            Write-Host "Restarting all services..."
            docker compose down
            docker compose up -d
        }
    }
    "up" {
        Start-VaultIfNotRunning
        docker compose up -d
    }
    "down" {
        docker compose down
    }
    "prod" {
        Start-VaultIfNotRunning
        Write-Host "Starting services in production mode..."
        docker compose --profile prod up -d
    }
    "dev" {
        Start-VaultIfNotRunning
        # In dev mode, we use ui-dev service instead of ui
        Write-Host "Starting services in development mode..."
        docker compose --profile dev up -d
    }
    "reset-db" {
        docker compose exec db psql -U ${env:POSTGRES_USER:-ai} -d ${env:POSTGRES_DB:-ai_radar} -c "DELETE FROM articles"
    }
    "logs" {
        $service = $Arguments[0]
        if ($service) {
            docker compose logs -f $service
        } else {
            Write-Host "Please specify a service name: .\ai-radar.ps1 logs <service-name>"
        }
    }
    "vault-ui" {
        Start-Process "http://localhost:8200"
    }
    "ui" {
        # Check if ui-dev is running
        $uiDev = docker ps -q -f "name=^ai-radar-ui-dev$"
        if ($uiDev) {
            Write-Host "Opening development UI at http://localhost:3000"
            Start-Process "http://localhost:3000"
        } else {
            Write-Host "Opening production UI at http://localhost:3000"
            Start-Process "http://localhost:3000"
        }
    }
    "api" {
        Start-Process "http://localhost:8001/docs"
    }
    "backup" {
        docker compose exec backup /bin/bash -c "pg_dump -h db -U ${env:POSTGRES_USER:-ai} ${env:POSTGRES_DB:-ai_radar} > /backups/$(Get-Date -Format 'yyyy-MM-dd').sql"
        docker compose exec backup /bin/bash -c "mc config host add minio http://minio:9000 ${env:MINIO_ROOT_USER:-minio} ${env:MINIO_ROOT_PASSWORD:-minio_pwd}"
        docker compose exec backup /bin/bash -c "mc cp /backups/$(Get-Date -Format 'yyyy-MM-dd').sql minio/ai-radar-backups/"
    }
    "clean" {
        docker compose down -v
    }
    "prune" {
        docker system prune -f
    }
    "status" {
        docker compose ps
    }
    "setup" {
        Initialize-SecretFiles
    }
    default {
        Write-Host "Unknown command: $Command"
        Show-Help
    }
}
