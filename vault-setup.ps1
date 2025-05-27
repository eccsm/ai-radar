#!/usr/bin/env pwsh
# Vault Setup Script for AI Radar
# This script initializes Vault and configures it with the necessary secrets

# Check if port 8200 is already in use
$portInUse = Get-NetTCPConnection -LocalPort 8200 -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "Port 8200 is already in use. This could be your standalone Vault server or Docker Vault container."
    $vaultPort = 8200
} else {
    $vaultPort = 8200
}

# Determine if we should use Docker or standalone mode
$useDocker = $false
try {
    # Try to check Docker status
    docker ps 2>&1 | Out-Null # We only care about the exit code
    if ($LASTEXITCODE -eq 0) {
        $useDocker = $true
        Write-Host "Docker is running, will use Docker mode."
    } else {
        Write-Host "Docker not available, will use standalone mode."
    }
} catch {
    Write-Host "Docker not available, will use standalone mode."
}

# Check if we're in standalone mode and a Vault server is running
$standaloneVaultRunning = $false # This variable acts as a status flag, useful for readability, though not explicitly checked later.
if (-not $useDocker) {
    try {
        # Try a simple Vault status command to see if there's a responsive Vault server
        $env:VAULT_ADDR = "http://127.0.0.1:$vaultPort"
        vault status 2>&1 | Out-Null # We only care about the exit code
        if ($LASTEXITCODE -eq 0) {
            $standaloneVaultRunning = $true
            Write-Host "Found standalone Vault server running at $env:VAULT_ADDR"
            Write-Host "Please enter the root token for your Vault server:"
            $rootToken = Read-Host
            $env:VAULT_TOKEN = $rootToken
        } else {
            Write-Host "No standalone Vault server detected."
            Write-Host "Please start a Vault server in another terminal using:"
            Write-Host "vault server -dev"
            Write-Host "Then note the Root Token and run this script again."
            exit 1
        }
    } catch {
        Write-Host "Error connecting to Vault: $_"
        Write-Host "Please start a Vault server in another terminal using:"
        Write-Host "vault server -dev"
        Write-Host "Then note the Root Token and run this script again."
        exit 1
    }
}

if ($useDocker) {
    Write-Host "Using Docker Vault service. Targeting 'vault' service."

    # Set Vault address and token for CLI
    $env:VAULT_ADDR = "http://localhost:$vaultPort"
    $env:VAULT_TOKEN = "root"

    # Configure Docker exec command to use HTTP and set token (This might not be needed if exec commands set it directly)
    # docker exec vault sh -c "export VAULT_ADDR=http://127.0.0.1:8200 && export VAULT_TOKEN=root"

    # Wait a moment to ensure Vault is ready
    Start-Sleep -Seconds 2

    # Check if Vault is accessible
    try {
        $status = docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault status"
        Write-Host "Vault is running and accessible."
        Write-Host "Vault Status: $status"
    } catch {
        Write-Host "Error connecting to Vault: $_"
        exit 1
    }

    # Enable the KV secrets engine version 2
    Write-Host "Enabling KV secrets engine..."
    try {
        $result = docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault secrets enable -path=ai-radar kv-v2"
        Write-Host "KV secrets engine enabled: $result"
    } catch {
        Write-Host "Error enabling KV secrets engine: $_"
        # Continue even if there's an error, it might already be enabled
    }

    # Create secrets for database
    Write-Host "Creating database secrets..."
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/database host=db port=5432 username=ai password=ai_pwd database=ai_radar"

    # Create secrets for NATS
    Write-Host "Creating NATS secrets..."
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/nats host=nats port=4222 subject_prefix=ai-radar stream_name=ai-radar"

    # Create secrets for MinIO
    Write-Host "Creating MinIO secrets..."
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/minio endpoint=minio:9000 access_key=minio secret_key=minio_pwd bucket=ai-radar-content"

    # Create secrets for API keys
    Write-Host "Creating API keys secrets..."
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/api-keys newsapi=your_newsapi_key_here openai=your_openai_api_key_here slack=your_slack_webhook_url_here"

    # Create an AppRole for authentication
    Write-Host "Creating AppRole authentication..."
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault auth enable approle"
} else {
    # Standalone mode
    # Enable the KV secrets engine version 2
    Write-Host "Enabling KV secrets engine in standalone mode..."
    try {
        vault secrets enable -path=ai-radar kv-v2 2>&1
        Write-Host "KV secrets engine enabled."
    } catch {
        Write-Host "Error enabling KV secrets engine: $_"
        # Continue even if there's an error, it might already be enabled
    }

    # Create secrets for database
    Write-Host "Creating database secrets..."
    vault kv put ai-radar/database host="db" port="5432" username="ai" password="ai_pwd" database="ai_radar"

    # Create secrets for NATS
    Write-Host "Creating NATS secrets..."
    vault kv put ai-radar/nats host="nats" port="4222" subject_prefix="ai-radar" stream_name="ai-radar"

    # Create secrets for MinIO
    Write-Host "Creating MinIO secrets..."
    vault kv put ai-radar/minio endpoint="http://minio:9000" access_key="minio" secret_key="minio_pwd" bucket="ai-radar-content"

    # Create secrets for API keys
    Write-Host "Creating API keys secrets..."
    vault kv put ai-radar/api-keys newsapi="your_newsapi_key_here" openai="your_openai_api_key_here" slack="your_slack_webhook_url_here"
    
    # Add JWT secret key for authentication
    Write-Host "Creating JWT secret key..."
    vault kv put ai-radar/JWT_SECRET_KEY value="your_jwt_secret_key_here"

    # Create an AppRole for authentication if needed
    Write-Host "Creating AppRole authentication..."
    try {
        vault auth enable approle
    } catch {
        Write-Host "Error enabling AppRole authentication: $_"
        # Continue even if there's an error, it might already be enabled
    }
}

# Create a policy for AI Radar services
$policyHCL = @"
# AI Radar Policy
path "ai-radar/*" {
  capabilities = ["read"]
}
"@

[System.IO.File]::WriteAllText("./ai-radar-policy.hcl", $policyHCL, (New-Object System.Text.UTF8Encoding($false)))

if ($useDocker) {
    docker-compose cp ai-radar-policy.hcl vault:/tmp/ai-radar-policy.hcl
    docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault policy write ai-radar-policy /tmp/ai-radar-policy.hcl"

    # Create roles for each service
    $services = @("fetcher", "summariser", "ranker", "scheduler", "dashboard")
    foreach ($service in $services) {
        Write-Host "Creating role for $service..."
        docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault write auth/approle/role/$service policies=ai-radar-policy token_ttl=1h token_max_ttl=24h"
        
        # Get role ID and secret ID
        $roleId = docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault read -format=json auth/approle/role/$service/role-id" | ConvertFrom-Json
        $secretId = docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault write -format=json -f auth/approle/role/$service/secret-id" | ConvertFrom-Json
        
        # Create directory for role IDs and secret IDs if it doesn't exist
        if (-not (Test-Path "./vault-auth")) {
            New-Item -ItemType Directory -Path "./vault-auth" -Force | Out-Null
            Write-Host "Created vault-auth directory"
        }
        
        # Save role ID and secret ID to files
        if ($roleId -and $roleId.data -and $roleId.data.role_id) {
            [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", $roleId.data.role_id, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "Saved role ID for $service"
        } else {
            Write-Host "Warning: Could not get role ID for $service"
            [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", "placeholder-role-id", (New-Object System.Text.UTF8Encoding($false)))
        }

        if ($secretId -and $secretId.data -and $secretId.data.secret_id) {
            [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", $secretId.data.secret_id, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "Saved secret ID for $service"
        } else {
            Write-Host "Warning: Could not get secret ID for $service"
            [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", "placeholder-secret-id", (New-Object System.Text.UTF8Encoding($false)))
        }
        
        Write-Host "Role ID and Secret ID for $service saved to vault-auth directory"
    }
} else {
    # Standalone mode
    Write-Host "Creating policy in standalone mode..."
    vault policy write ai-radar-policy ai-radar-policy.hcl

    # Create roles for each service in standalone mode
    $services = @("fetcher", "summariser", "ranker", "scheduler", "dashboard")
    foreach ($service in $services) {
        Write-Host "Creating role for $service in standalone mode..."
        vault write auth/approle/role/$service policies=ai-radar-policy token_ttl=1h token_max_ttl=24h
        
        # Get role ID and secret ID
        try {
            $roleIdOutput = vault read -format=json auth/approle/role/$service/role-id
            $roleId = $roleIdOutput | ConvertFrom-Json
            $secretIdOutput = vault write -format=json -f auth/approle/role/$service/secret-id
            $secretId = $secretIdOutput | ConvertFrom-Json
        } catch {
            Write-Host "Error getting role/secret IDs: $_"
        }
        
        # Create directory for role IDs and secret IDs if it doesn't exist
        if (-not (Test-Path "./vault-auth")) {
            New-Item -ItemType Directory -Path "./vault-auth" -Force | Out-Null
            Write-Host "Created vault-auth directory"
        }
        
        # Save role ID and secret ID to files
        if ($roleId -and $roleId.data -and $roleId.data.role_id) {
            [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", $roleId.data.role_id, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "Saved role ID for $service"
        } else {
            Write-Host "Warning: Could not get role ID for $service"
            [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", "placeholder-role-id", (New-Object System.Text.UTF8Encoding($false)))
        }

        if ($secretId -and $secretId.data -and $secretId.data.secret_id) {
            [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", $secretId.data.secret_id, (New-Object System.Text.UTF8Encoding($false)))
            Write-Host "Saved secret ID for $service"
        } else {
            Write-Host "Warning: Could not get secret ID for $service"
            [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", "placeholder-secret-id", (New-Object System.Text.UTF8Encoding($false)))
        }
        
        Write-Host "Role ID and Secret ID for $service saved to vault-auth directory"
    }
}

Write-Host "Vault setup complete!"
if ($useDocker) {
    Write-Host "You can access the Vault UI at http://localhost:$vaultPort with token: root"
} else {
    Write-Host "You can access the Vault UI at http://localhost:$vaultPort with your provided token"
}
Write-Host "Role IDs and Secret IDs for services are saved in the vault-auth directory"
Write-Host "To start the services with Vault integration, run: .\ai-radar.ps1 dev"

# Clean up
Remove-Item -Path "./ai-radar-policy.hcl" -Force
