#!/usr/bin/env pwsh
# Enhanced AI Radar Management Script

param (
    [Parameter(Position=0)]
    [string]$Command = "help",

    [Parameter(Position=1, ValueFromRemainingArguments=$true)]
    [string[]]$Arguments = @()
)

# Configuration constants
$script:VAULT_PORT               = 8200
$script:VAULT_TOKEN              = "root"
$script:VAULT_ADDR               = "http://localhost:$($script:VAULT_PORT)"
$script:REQUIRED_SERVICES        = @("db", "nats", "minio", "toolhub", "api", "ui-dev", "fetcher", "scheduler", "summariser", "ranker", "sharer")
$script:INFRASTRUCTURE_SERVICES  = @("db", "nats", "minio")
$script:SETUP_SERVICES           = @("toolhub")
$script:APPLICATION_SERVICES     = @("api")
$script:AGENT_SERVICES           = @("fetcher", "scheduler", "summariser", "ranker", "sharer")
$script:UI_SERVICES              = @("ui-dev")

# Helper: Write-Status
function Write-Status {
    param (
        [string]$Message,
        [string]$Type = "Info"
    )
    $prefix = switch ($Type) {
        "Success" { "[SUCCESS]" }
        "Warning" { "[WARNING]" }
        "Error"   { "[ERROR]" }
        "Debug"   { "[DEBUG]" }
        default   { "[INFO]" }
    }
    $color = switch ($Type) {
        "Info"    { "White" }
        "Success" { "Green" }
        "Warning" { "Yellow" }
        "Error"   { "Red" }
        "Debug"   { "Gray" }
        default   { "White" }
    }
    Write-Host "$prefix $Message" -ForegroundColor $color
} # End Write-Status

# Show Help Text
function Show-Help {
    Write-Host "Enhanced AI Radar Management Commands:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Service Management:" -ForegroundColor Yellow
    Write-Host "  .\ai-radar.ps1 up              - Start complete AI Radar system"
    Write-Host "  .\ai-radar.ps1 down            - Stop all services"
    Write-Host "  .\ai-radar.ps1 dev             - Start development environment"
    Write-Host "  .\ai-radar.ps1 prod            - Start production environment"
    Write-Host "  .\ai-radar.ps1 restart         - Restart all services"
    Write-Host "  .\ai-radar.ps1 status          - Show detailed service status"
    Write-Host "  .\ai-radar.ps1 agents          - Start only the AI agents (fetcher, scheduler, summariser)"
    Write-Host "  .\ai-radar.ps1 infra           - Start only infrastructure (db, nats, minio)"
    Write-Host ""
    Write-Host "Vault Management:" -ForegroundColor Yellow
    Write-Host "  .\ai-radar.ps1 vault-init      - Initialize Vault with secrets"
    Write-Host "  .\ai-radar.ps1 vault-status    - Check Vault status"
    Write-Host "  .\ai-radar.ps1 vault-ui        - Open Vault UI"
    Write-Host ""
    Write-Host "Database Management:" -ForegroundColor Yellow
    Write-Host "  .\ai-radar.ps1 validate-sql    - Validate your existing SQL files"
    Write-Host "  .\ai-radar.ps1 fix-sql         - Fix SQL file encoding/permissions"
    Write-Host "  .\ai-radar.ps1 fix-db          - Fix database mounting/initialization"
    Write-Host "  .\ai-radar.ps1 init-db         - Initialize database schema and add sample sources"
    Write-Host "  .\ai-radar.ps1 check-db        - Check database contents and article count"
    Write-Host "  .\ai-radar.ps1 trigger-feeds   - Manually trigger RSS feed fetching via NATS"
    Write-Host "  .\ai-radar.ps1 fetch-simple    - Run simple RSS fetcher directly (recommended)"
    Write-Host ""
    Write-Host "Troubleshooting:" -ForegroundColor Yellow
    Write-Host "  .\ai-radar.ps1 logs `<service>`  - View service logs"
    Write-Host "  .\ai-radar.ps1 diagnose        - Run comprehensive diagnostics"
    Write-Host "  .\ai-radar.ps1 test-api        - Test API endpoints"
    Write-Host ""
    Write-Host "Development:" -ForegroundColor Yellow
    Write-Host "  .\ai-radar.ps1 build `<service>` - Rebuild specific service"
    Write-Host "  .\ai-radar.ps1 clean           - Clean up containers and volumes"
    Write-Host "  .\ai-radar.ps1 reset           - Complete system reset"
    Write-Host "  .\ai-radar.ps1 setup           - Validate setup and initialize Vault"
    Write-Host ""
    Write-Host "Your existing SQL files will be used:" -ForegroundColor Green
    Write-Host "  • init-db.sql" -ForegroundColor Gray
    Write-Host "  • init-pgvector.sql" -ForegroundColor Gray
    Write-Host "  • 05-add-api-tables.sql" -ForegroundColor Gray
    Write-Host "  • init_tables.sql (optional)" -ForegroundColor Gray
} # End Show-Help

# Create directory if it does not exist
function New-DirectoryIfNotExists {
    param([string]$Path)
    if (-not (Test-Path $Path -PathType Container)) {
        try {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
            Write-Status "Created directory: $Path" "Success"
        }
        catch {
            Write-Status "Failed to create directory: $Path. Error: $($_.Exception.Message)" "Error"
            return $false
        }
    }
    return $true
} # End New-DirectoryIfNotExists

# Validate SQL files: check existence and basic structure
function Validate-DatabaseFiles {
    Write-Status "Validating database files..." "Info"
    # Assuming SQL files are in a 'sql' subdirectory relative to the script
    $sqlDir = Join-Path $PSScriptRoot "sql"
    $requiredFiles = @("init-db.sql", "init-pgvector.sql", "05-add-api-tables.sql")
    $allFilesExist = $true

    foreach ($file in $requiredFiles) {
        $filePath = Join-Path $sqlDir $file
        if (-not (Test-Path $filePath)) {
            Write-Status "Required SQL file not found: $filePath" "Error"
            $allFilesExist = $false
        }
        else {
            Write-Status "Found SQL file: $filePath" "Debug"
        }
    }
    # Optional files check can be added here if needed
    if ($allFilesExist) {
        Write-Status "All required SQL files found in $sqlDir" "Success"
    }
    return $allFilesExist
} # End Validate-DatabaseFiles

# Fix SQL file permissions and encoding (if possible)
function Fix-SqlFilePermissions {
    Write-Status "Checking/fixing SQL file permissions and encoding..." "Info"
    $sqlDir = Join-Path $PSScriptRoot "sql"
    Get-ChildItem -Path $sqlDir -Filter "*.sql" | ForEach-Object {
        try {
            $content = Get-Content $_.FullName -Raw
            # Ensure UTF-8 encoding without BOM, and LF line endings
            $content = $content -replace "`r`n", "`n" # CRLF to LF
            $content = $content -replace "`r", "`n"   # CR to LF (for Mac classic)
            # PowerShell Core (pwsh) defaults to UTF8NoBOM for Set-Content
            Set-Content -Path $_.FullName -Value $content -Encoding UTF8 -NoNewline
            Write-Status "Processed $($_.Name)" "Debug"
        }
        catch {
            Write-Status "Could not process file $($_.Name): $($_.Exception.Message)" "Warning"
        }
    }
} # End Fix-SqlFilePermissions

# Test connection to Vault
function Test-VaultConnection {
    try {
        $response = Invoke-WebRequest -Uri "$($script:VAULT_ADDR)/v1/sys/health" -TimeoutSec 2 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            return $true
        }
    }
    catch {
        # Expected to fail if Vault is not ready
    }
    return $false
} # End Test-VaultConnection

# Initialize Vault container if not running
function Initialize-VaultContainer {
    try {
        # Check if Docker is running
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Docker daemon is not running. Please start Docker Desktop first." "Error"
            return $false
        }
        
        Write-Status "Checking Vault container..." "Info"

        $existingVault = docker ps --filter name=vault --format "{{.Names}}" 2>&1
        if ($existingVault) {
            Write-Status "Vault container already running." "Success"
            return $true
        }

        $stoppedVault = docker ps -aq -f "name=^vault$" # Check for stopped container
        if ($stoppedVault) {
            Write-Status "Starting existing stopped Vault container..." "Info"
            docker start vault | Out-Null
        }
        else {
            Write-Status "Creating new Vault container..." "Info"
            # Ensure VAULT_ADDR for the container itself is 0.0.0.0 to listen on all interfaces within the container
            docker run -d --name vault -p "$($script:VAULT_PORT):8200" `
                -e "VAULT_DEV_ROOT_TOKEN_ID=$($script:VAULT_TOKEN)" `
                -e "VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200" `
                hashicorp/vault:latest | Out-Null # Using official image name
        }

        Write-Status "Waiting for Vault to become ready (up to 10s)..." "Info"
        for ($i = 1; $i -le 10; $i++) {
            if (Test-VaultConnection) {
                Write-Status "Vault is ready." "Success"
                return $true
            }
            Start-Sleep -Seconds 1
        }

        Write-Status "Vault failed to start or become ready in time." "Error"
        return $false
    }
    catch {
        Write-Status "Error initializing Vault container: $($_.Exception.Message)" "Error"
        return $false
    }
} # End Initialize-VaultContainer

# Validate Docker Compose + required services
function Test-ServiceConfiguration {
    [CmdletBinding()]
    param(
        [string]$ServiceProfile = "dev" # Default to dev profile
    )
    try {
        # Check Docker and Docker Compose
        $dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
        if (-not $dockerCmd) {
            Write-Status "Docker not available. Please ensure Docker Desktop is installed and in your PATH." "Error"
            return $false
        }
        
        # Check if Docker is actually running
        $dockerInfo = docker info 2>&1
        if ($LASTEXITCODE -ne 0 -or $dockerInfo -match "Cannot connect to the Docker daemon") {
            Write-Status "Docker daemon is not running. Please start Docker Desktop first." "Error"
            Write-Status "Docker info error: $dockerInfo" "Debug" 
            return $false
        }

        $composeVersion = docker compose version 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Docker Compose not available. Please ensure Docker Desktop is running and 'docker compose' (v2) is in your PATH." "Error"
            return $false
        }

        $composeFile = Join-Path $PSScriptRoot "docker-compose.yaml"
        if (-not (Test-Path $composeFile)) {
            Write-Status "docker-compose.yaml not found at $composeFile" "Error"
            return $false
        }

        # Use the profile when checking available services
        $configOutput = docker compose -f $composeFile --profile $ServiceProfile config --services 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Status "'docker compose config' failed. Check your docker-compose.yaml for syntax errors." "Error"
            Write-Host $configOutput # Show error output from docker compose
            return $false
        }
        
        # Convert the output to a proper array of services
        $services = $configOutput -split '\s+' | Where-Object { $_ -ne '' }
        Write-Status "Found services in docker-compose.yaml: $($services -join ', ')" "Debug"

        foreach ($service in $script:REQUIRED_SERVICES) {
            if ($services -notcontains $service) {
                Write-Status "Required service '$service' not defined in docker-compose.yaml (Available services: $($services -join ', '))" "Error"
                return $false
            }
        }
    }
    catch {
        Write-Status "Error validating service configuration: $($_.Exception.Message)" "Error"
        return $false
    }

    Write-Status "Service configuration validated." "Success"
    return $true
} # End Test-ServiceConfiguration

# Start a group of services by name
function Start-ServiceGroup {
    [CmdletBinding()]
    param (
        [Parameter(Mandatory = $true)]
        [string[]]$Services,
        
        [Parameter(Mandatory = $true)]
        [string]$GroupName,
        
        [Parameter(Mandatory = $false)]
        [int]$HealthCheckTimeout = 60
    )
    
    try {
        Write-Status "Starting $GroupName services: $($Services -join ', ')" "Info"

        # Start the services
        docker compose --profile dev up -d $Services
        
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Failed to start $GroupName services with docker compose" "Error"
            return $false
        }

        # Check if all services started successfully
        $allSucceeded = $true
        foreach ($service in $Services) {
            Write-Status "Checking $service status..." "Info"
            $maxAttempts = [Math]::Max(1, $HealthCheckTimeout / 5)
            $isRunning = $false

            for ($i = 1; $i -le $maxAttempts; $i++) {
                $containerStatus = docker compose --profile dev ps --status running $service -q
                if ($containerStatus) {
                    $isRunning = $true
                    Write-Status "$service is running" "Success"
                    break
                }
                
                Write-Status "Waiting for $service to start (attempt $i/$maxAttempts)..." "Info"
                Start-Sleep -Seconds 5
            }

            if (-not $isRunning) {
                Write-Status "$service failed to start within timeout" "Error"
                $allSucceeded = $false
            }
        }

        if ($allSucceeded) {
            Write-Status "All $GroupName services started successfully" "Success"
        }
        else {
            Write-Status "$GroupName services partially failed" "Warning"
        }

        return $allSucceeded
    }
    catch {
        Write-Status "Error starting $GroupName services: $($_.Exception.Message)" "Error"
        return $false
    }
}

# --------------------------
# Show health/status of all
# running containers + Vault
# --------------------------
function Get-ServiceHealth {
    Write-Host "`nService Health Status:" -ForegroundColor Cyan
    Write-Host "=====================" -ForegroundColor Cyan

    # Get all running containers
    $containers = docker compose --profile dev ps --format "{{.Service}}\t{{.Status}}" 2>&1

    # Display status for each required service
    foreach ($service in $script:REQUIRED_SERVICES) {
        $serviceStatus = $containers | Where-Object { $_ -match "^$service\s" }
        
        if ($serviceStatus) {
            $status = if ($serviceStatus -match "running|healthy") { "Running" } else { "Unhealthy" }
            $color = if ($status -eq "Running") { "Green" } else { "Red" }
            Write-Host "$service`t`t$status`t`t" -ForegroundColor $color
        }
        else {
            Write-Host "$service`t`tDown`t`t" -ForegroundColor Red
        }
    }

    # Check Vault status separately
    if (Test-VaultConnection) {
        Write-Host "vault`t`tRunning`t`t" -ForegroundColor Green
    }
    else {
        Write-Host "vault`t`tDown`t`t" -ForegroundColor Red
    }
}

# Test API endpoints
function Test-APIEndpoints {
    [CmdletBinding()]
    param()
    
    try {
        Write-Status "Testing API endpoints..." "Info"
        
        $endpoints = @(
            @{ description = "API Health Check"; url = "http://localhost:5000/api/health" }
        )
        
        $allSuccess = $true
        foreach ($endpoint in $endpoints) {
            try {
                $resp = Invoke-WebRequest -Uri $endpoint.url -TimeoutSec 5 -UseBasicParsing
                Write-Status "[OK] $($endpoint.description): HTTP $($resp.StatusCode)" "Success"
            }
            catch {
                $allSuccess = $false
                Write-Status "[FAILED] $($endpoint.description): $($_.Exception.Message)" "Error"
            }
        }
        
        if ($allSuccess) {
            Write-Status "All API endpoints are accessible." "Success"
        } else {
            Write-Status "Some API endpoints could not be reached." "Warning"
        }
        
        return $allSuccess
    }
    catch {
        Write-Status "Error testing API endpoints: $($_.Exception.Message)" "Error"
        return $false
    }
} # End Test-APIEndpoints

# Start all services
function Start-AllServices {
    param(
        [string]$ServiceProfile = "dev"
    )
    try {
        Write-Status "Starting Infrastructure Services..." "Info"
        docker compose --profile $ServiceProfile up -d $script:INFRASTRUCTURE_SERVICES

        Write-Status "Starting Setup Services..." "Info"
        docker compose --profile $ServiceProfile up -d $script:SETUP_SERVICES

        Write-Status "Starting Application Services..." "Info"
        docker compose --profile $ServiceProfile up -d $script:APPLICATION_SERVICES

        Write-Status "Starting UI Services..." "Info"
        docker compose --profile $ServiceProfile up -d $script:UI_SERVICES

        Write-Status "All services started." "Success"
    }
    catch {
        Write-Status "Error starting services: $($_.Exception.Message)" "Error"
    }
} # End Start-AllServices

# Initialize database schema and data
function Initialize-Database {
    try {
        Write-Status "Initializing database schema..." "Info"
        
        # Wait for database to be ready
        $maxAttempts = 30
        for ($i = 1; $i -le $maxAttempts; $i++) {
            try {
                $result = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT 1;" 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Write-Status "Database is ready" "Success"
                    break
                }
            }
            catch { }
            
            if ($i -eq $maxAttempts) {
                Write-Status "Database failed to become ready" "Error"
                return $false
            }
            
            Write-Status "Waiting for database... ($i/$maxAttempts)" "Info"
            Start-Sleep -Seconds 2
        }
        
        # Enable vector extension for embeddings
        Write-Status "Enabling vector extension..." "Info"
        docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "CREATE EXTENSION IF NOT EXISTS vector;" | Out-Null
        
        # Create ai_radar schema
        Write-Status "Creating ai_radar schema..." "Info"
        docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "CREATE SCHEMA IF NOT EXISTS ai_radar;" | Out-Null
        
        # Create sources table
        Write-Status "Creating sources table..." "Info"
        $sourcesSQL = @"
CREATE TABLE IF NOT EXISTS ai_radar.sources (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL DEFAULT 'rss',
    active BOOLEAN NOT NULL DEFAULT true,
    last_fetched_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"@
        echo $sourcesSQL | docker compose --profile dev exec -T db psql -U ai -d ai_radar
        
        # Create articles table
        Write-Status "Creating articles table..." "Info"
        $articlesSQL = @"
CREATE TABLE IF NOT EXISTS ai_radar.articles (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES ai_radar.sources(id),
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    author TEXT,
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    content TEXT,
    summary TEXT,
    embedding vector(1536),
    importance_score FLOAT DEFAULT 0.5,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"@
        echo $articlesSQL | docker compose --profile dev exec -T db psql -U ai -d ai_radar
        
        # Insert sample RSS sources
        Write-Status "Adding sample RSS sources..." "Info"
        $sourcesData = @"
INSERT INTO ai_radar.sources (name, url, source_type, active) 
VALUES 
    ('TechCrunch AI', 'https://techcrunch.com/category/artificial-intelligence/feed/', 'rss', true),
    ('Wired AI', 'https://www.wired.com/feed/tag/artificial-intelligence/latest/rss', 'rss', true),
    ('MIT Technology Review', 'https://www.technologyreview.com/feed/', 'rss', true),
    ('VentureBeat AI', 'https://venturebeat.com/ai/feed/', 'rss', true),
    ('The Verge AI', 'https://www.theverge.com/ai-artificial-intelligence/rss/index.xml', 'rss', true)
ON CONFLICT (url) DO NOTHING;
"@
        echo $sourcesData | docker compose --profile dev exec -T db psql -U ai -d ai_radar
        
        # Verify database schema
        Write-Status "Verifying database schema..." "Info"
        $embeddingCheck = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT column_name FROM information_schema.columns WHERE table_schema = 'ai_radar' AND table_name = 'articles' AND column_name = 'embedding';" 2>&1
        if ($embeddingCheck -match "embedding") {
            Write-Status "✅ Database schema verified (embedding column exists)" "Success"
        }
        else {
            Write-Status "⚠️  Warning: embedding column not found, may cause summariser issues" "Warning"
        }
        
        Write-Status "Database initialization completed successfully!" "Success"
        return $true
    }
    catch {
        Write-Status "Error initializing database: $($_.Exception.Message)" "Error"
        return $false
    }
} # End Initialize-Database

# Trigger initial RSS feeds using multiple methods
function Start-InitialFeedFetch {
    try {
        Write-Status "Triggering initial RSS feed fetch..." "Info"
        
        # Wait for services to be fully ready
        Write-Status "Waiting for services to initialize..." "Info"
        Start-Sleep -Seconds 15
        
        # Method 1: Try the Python trigger script
        if (Test-Path "./trigger_feed.py") {
            try {
                Write-Status "Running trigger_feed.py..." "Info"
                python ./trigger_feed.py
                Write-Status "Python trigger script completed!" "Success"
            }
            catch {
                Write-Status "Python trigger script failed: $($_.Exception.Message)" "Warning"
            }
        }
        
        # Method 2: Restart scheduler to trigger immediate fetch
        try {
            Write-Status "Restarting scheduler to trigger immediate RSS fetch..." "Info"
            docker compose --profile dev restart scheduler
            Start-Sleep -Seconds 5
            Write-Status "Scheduler restarted - RSS feeds should start fetching automatically!" "Success"
        }
        catch {
            Write-Status "Could not restart scheduler: $($_.Exception.Message)" "Warning"
        }
        
        # Method 3: Check if simple fetcher exists and run it as backup
        if (Test-Path "./simple_fetcher.py") {
            try {
                Write-Status "Running simple RSS fetcher as backup..." "Info"
                python ./simple_fetcher.py
                Write-Status "Simple fetcher completed!" "Success"
            }
            catch {
                Write-Status "Simple fetcher failed: $($_.Exception.Message)" "Warning"
            }
        }
        
        # Give the system time to process feeds
        Write-Status "Giving system time to process feeds..." "Info"
        Start-Sleep -Seconds 10
        
        # Check if articles are being created
        try {
            $articlesCount = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT COUNT(*) FROM ai_radar.articles;" 2>&1
            if ($articlesCount -match '\d+' -and [int]($articlesCount -replace '\D','') -gt 0) {
                Write-Status "✅ Articles found in database! ($articlesCount articles)" "Success"
            }
            else {
                Write-Status "⚠️  No articles found yet - feeds may still be processing" "Warning"
                Write-Status "Check status with: .\ai-radar.ps1 check-db" "Info"
            }
        }
        catch {
            Write-Status "Could not check article count: $($_.Exception.Message)" "Warning"
        }
        
    }
    catch {
        Write-Status "Error triggering initial feeds: $($_.Exception.Message)" "Warning"
    }
} # End Start-InitialFeedFetch

# Check database contents
function Check-DatabaseContents {
    try {
        Write-Status "Checking database contents..." "Info"
        
        # Check if database is accessible
        $dbCheck = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT 1;" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Status "Database is not accessible" "Error"
            return $false
        }
        
        # Check schemas
        Write-Status "Checking schemas..." "Info"
        $schemas = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "\dn" 2>&1
        Write-Host $schemas
        
        # Check sources count
        Write-Status "Checking RSS sources..." "Info"
        $sourcesCount = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT COUNT(*) FROM ai_radar.sources WHERE active = true;" 2>&1
        Write-Host "Active RSS sources: $sourcesCount"
        
        # Check articles count
        Write-Status "Checking articles..." "Info"
        $articlesCount = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT COUNT(*) FROM ai_radar.articles;" 2>&1
        Write-Host "Total articles: $articlesCount"
        
        # Show recent articles if any exist
        $recentArticles = docker compose --profile dev exec -T db psql -U ai -d ai_radar -c "SELECT title, created_at FROM ai_radar.articles ORDER BY created_at DESC LIMIT 5;" 2>&1
        if ($recentArticles -and $recentArticles -notmatch "0 rows") {
            Write-Status "Recent articles:" "Info"
            Write-Host $recentArticles
        }
        else {
            Write-Status "No articles found in database yet" "Warning"
        }
        
        return $true
    }
    catch {
        Write-Status "Error checking database: $($_.Exception.Message)" "Error"
        return $false
    }
} # End Check-DatabaseContents

# Fix database issues
function Fix-DatabaseIssues {
    try {
        Write-Status "Fixing Database Issues..." "Info"
        Initialize-Database
        Write-Status "Database issues fixed." "Success"
    }
    catch {
        Write-Status "Error fixing Database issues: $($_.Exception.Message)" "Error"
    }
} # End Fix-DatabaseIssues

# ------------------------------------------
# Run a full diagnostic: system info + health
# ------------------------------------------
function Invoke-Diagnostics {
    Write-Status "Running comprehensive diagnostics..." "Info"

    Write-Host "`n=== System Info ===" -ForegroundColor Cyan
    Write-Host "Docker: $(docker --version)"
    Write-Host "Compose: $(docker compose version)"

    Write-Host "`n=== Service Health ===" -ForegroundColor Cyan
    Get-ServiceHealth

    Write-Host "`n=== Configuration ===" -ForegroundColor Cyan
    Test-ServiceConfiguration | Out-Null

    Write-Host "`n=== Vault Status ===" -ForegroundColor Cyan
    if (Test-VaultConnection) {
        Write-Status "Vault accessible" "Success"
    }
    else {
        Write-Status "Vault not accessible" "Error"
    }

    Write-Host "`n=== API Tests ===" -ForegroundColor Cyan
    Test-APIEndpoints
}

# -----------------------------------------------------
# Start all services in dependency order: infra → setup → app → UI
# -----------------------------------------------------
function Start-AllServices {
    [CmdletBinding()]
    param(
        [string]$ServiceProfile = "dev"  # Renamed from Profile to avoid conflict with built-in variable
    )

    try {
        Write-Status "Starting AI Radar with profile: $ServiceProfile" "Info"

        # 1) Ensure SQL files exist
        if (-not (Validate-DatabaseFiles)) {
            Write-Status "Please ensure all required SQL files are present" "Error"
            return $false
        }

        # 2) Fix encoding/permissions on .sql
        Fix-SqlFilePermissions

        # 3) Initialize or start Vault
        $vaultResult = Initialize-VaultContainer 
        if (-not $vaultResult) {
            Write-Status "Vault initialization failed, but continuing" "Warning"
        }

        # 4) If vault-setup.ps1 is present, run it
        if (Test-Path "./vault-setup.ps1") {
            Write-Status "Running vault-setup.ps1..." "Info"
            try {
                & "./vault-setup.ps1"
            }
            catch {
                Write-Status "Vault setup had issues: $($_.Exception.Message)" "Warning"
                # Continue anyway
            }
        }

        # 5) Validate Docker Compose + required services
        Write-Status "Validating service configuration..." "Info"
        if (-not (Test-ServiceConfiguration -ServiceProfile $ServiceProfile)) {
            Write-Status "Configuration validation failed" "Error"
            return $false
        }

        $overallSuccess = $true

        # 6) Start infrastructure services
        if (-not (Start-ServiceGroup -Services $script:INFRASTRUCTURE_SERVICES -GroupName "Infrastructure")) {
            $overallSuccess = $false
            Write-Status "Failed to start infrastructure services" "Error"
        }

        # 7) Start setup services (toolhub)
        if ($overallSuccess) {
            $setupResult = Start-ServiceGroup -Services $script:SETUP_SERVICES -GroupName "Setup"
            if (-not $setupResult) {
                Write-Status "Setup services startup had issues, but continuing" "Warning"
            }
            Start-Sleep -Seconds 5
        }

        # 8) Initialize database schema and data
        if ($overallSuccess) {
            Write-Status "Initializing database..." "Info"
            if (-not (Initialize-Database)) {
                Write-Status "Database initialization failed, but continuing" "Warning"
            }
        }

        # 9) Start application services (api) - skip if unhealthy, don't block agents
        if ($overallSuccess) {
            Write-Status "Starting application services..." "Info"
            $apiResult = Start-ServiceGroup -Services $script:APPLICATION_SERVICES -GroupName "Application"
            if (-not $apiResult) {
                Write-Status "API services had issues, but continuing with agents" "Warning"
            }
        }

        # 10) Start AI agent services (fetcher, scheduler, summariser, ranker)
        if ($overallSuccess) {
            Write-Status "Starting AI agent services..." "Info"
            $agentResult = Start-ServiceGroup -Services $script:AGENT_SERVICES -GroupName "AI Agents"
            if (-not $agentResult) {
                Write-Status "Some agent services had issues, but continuing" "Warning"
            }
        }

        # 11) Start UI services (ui-dev)
        if ($overallSuccess) {
            Write-Status "Starting UI services..." "Info"
            $uiResult = Start-ServiceGroup -Services $script:UI_SERVICES -GroupName "UI"
            if (-not $uiResult) {
                Write-Status "UI services had issues" "Warning"
            }
        }

        # 12) Trigger initial RSS feeds
        if ($overallSuccess) {
            Start-Sleep -Seconds 10  # Give agents time to fully start
            Start-InitialFeedFetch
        }

        if ($overallSuccess) {
            Write-Status "All services started successfully!" "Success"
            Write-Status "UI is available at:   http://localhost:3000" "Info"
            Write-Status "API is available at:  http://localhost:8001" "Info"
            Write-Status "Vault is available at http://localhost:$($script:VAULT_PORT)" "Info"

            # Quick post-start database verification
            Write-Status "Verifying your database setup..." "Info"
            Start-Sleep -Seconds 5
            try {
                $schemaCheck   = docker compose --profile $ServiceProfile exec -T db psql -U ai -d ai_radar -c "\dn" 2>&1
                $publicTables  = docker compose --profile $ServiceProfile exec -T db psql -U ai -d ai_radar -c "\dt public.*" 2>&1
                $aiRadarTables = docker compose --profile $ServiceProfile exec -T db psql -U ai -d ai_radar -c "\dt ai_radar.*" 2>&1

                if ($schemaCheck -match "ai_radar") {
                    Write-Status "[OK] ai_radar schema found" "Success"
                }
                if ($publicTables -match "sources|articles|users") {
                    Write-Status "[OK] API tables found in public schema" "Success"
                }
                if ($aiRadarTables -match "sources|articles") {
                    Write-Status "[OK] ai_radar tables found in ai_radar schema" "Success"
                }
            }
            catch {
                Write-Status "Could not verify database schema: $($_.Exception.Message)" "Warning"
            }
        }
        else {
            Write-Status "Some services failed. Run 'diagnose' for more details." "Error"
        }

        return $overallSuccess
    }
    catch {
        Write-Status "Error in Start-AllServices: $($_.Exception.Message)" "Error"
        return $false
    }
} # End of Start-AllServices

# -----------------------------------
#  Command dispatch (main entry point)
# -----------------------------------
switch ($Command.ToLower()) {
    "help" {
        Show-Help
    }

    "validate-sql" {
        Validate-DatabaseFiles
    }

    "fix-sql" {
        Fix-SqlFilePermissions
    }

    "fix-db" {
        Fix-DatabaseIssues
    }

    "vault-init" {
        Initialize-VaultContainer | Out-Null
    }

    "vault-status" {
        if (Test-VaultConnection) {
            Write-Status "Vault accessible at http://localhost:$($script:VAULT_PORT)" "Success"
        }
        else {
            Write-Status "Vault not accessible" "Error"
        }
    }

    "vault-ui" {
        if (Test-VaultConnection) {
            Start-Process "http://localhost:$($script:VAULT_PORT)"
        }
        else {
            Write-Status "Vault not running" "Error"
        }
    }

    "up" {
        Start-AllServices
    }

    "dev" {
        Start-AllServices -ServiceProfile "dev"
    }

    "down" {
        docker compose --profile dev down
        Write-Status "All services stopped" "Success"
    }

    "restart" {
        docker compose --profile dev down
        Start-Sleep -Seconds 5
        Start-AllServices
    }

    "status" {
        Get-ServiceHealth
    }

    "diagnose" {
        Invoke-Diagnostics
    }

    "test-api" {
        Test-APIEndpoints
    }

    "logs" {
        if ($Arguments.Count -gt 0) {
            $service = $Arguments[0]
            docker compose --profile dev logs -f $service
        }
        else {
            Write-Status 'Please specify service: .\ai-radar.ps1 logs <service>' "Error"
            Write-Status ('Available services: {0}' -f ($script:REQUIRED_SERVICES -join ', ')) "Info"
        }
    }

    "build" {
        if ($Arguments.Count -gt 0) {
            $service = $Arguments[0]
            Write-Status "Rebuilding $service..." "Info"
            docker compose --profile dev build --no-cache $service
            docker compose --profile dev up -d $service
        }
        else {
            Write-Status "Rebuilding all services..." "Info"
            docker compose --profile dev build --no-cache
        }
    }

    "clean" {
        Write-Status "Cleaning up..." "Warning"
        docker compose --profile dev down -v
        docker system prune -f
    }

    "reset" {
        Write-Status "Resetting system..." "Warning"
        docker compose --profile dev down -v
        docker volume prune -f
        docker network prune -f
        Write-Status "System reset complete" "Success"
    }

    "setup" {
        Validate-DatabaseFiles | Out-Null
        Fix-SqlFilePermissions
        Initialize-VaultContainer | Out-Null
    }

    "agents" {
        Write-Status "Starting AI agent services only..." "Info"
        Start-ServiceGroup -Services $script:AGENT_SERVICES -GroupName "AI Agents"
    }

    "infra" {
        Write-Status "Starting infrastructure services only..." "Info"
        Start-ServiceGroup -Services $script:INFRASTRUCTURE_SERVICES -GroupName "Infrastructure"
    }

    "init-db" {
        Initialize-Database
    }

    "trigger-feeds" {
        Start-InitialFeedFetch
    }

    "fetch-simple" {
        Write-Status "Running simple RSS fetcher..." "Info"
        if (Test-Path "./simple_fetcher.py") {
            try {
                python ./simple_fetcher.py
                Write-Status "RSS feeds fetched successfully!" "Success"
            }
            catch {
                Write-Status "Error running simple fetcher: $($_.Exception.Message)" "Error"
            }
        }
        else {
            Write-Status "simple_fetcher.py not found" "Error"
        }
    }

    "check-db" {
        Check-DatabaseContents
    }

    default {
        Write-Status ("Unknown command: {0}" -f $Command) "Error" # Fixed string literal
        Show-Help
    }
} # End main switch statement
