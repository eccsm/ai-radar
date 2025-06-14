# vault-setup.ps1 - Updated with dynamic port detection

# Detect vault port automatically
$vaultPort = 8200
$vaultContainer = docker ps --format "{{.Names}} {{.Ports}}" | Select-String "vault"
if ($vaultContainer) {
    $portsLine = $vaultContainer.ToString()
    if ($portsLine -match "0\.0\.0\.0:(\d+)->8200") {
        $vaultPort = [int]$matches[1]
        Write-Host "Detected Vault running on port $vaultPort"
    }
} else {
    Write-Host "No Vault container detected. Please run .\ai-radar.ps1 vault first."
    exit 1
}

# Rest of your existing vault-setup.ps1 logic...
# But update the port references to use $vaultPort

# Set Vault address and token for CLI
$env:VAULT_ADDR = "http://localhost:$vaultPort"
$env:VAULT_TOKEN = "root"

Write-Host "Using Vault at $env:VAULT_ADDR"

# Function to execute Vault commands
function Invoke-VaultCommand {
    param([string]$Command)
    
    # Always use standalone docker since ai-radar.ps1 creates standalone container
    $fullCmd = "docker exec vault sh -c `"VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=root $Command`""
    return Invoke-Expression $fullCmd
}

# Check if Vault is accessible
try {
    $status = Invoke-VaultCommand "vault status"
    Write-Host "[OK] Vault is running and accessible. Status: $($status | Out-String)" 
} catch {
    Write-Host "[ERROR] Error connecting to Vault: $_"
    Write-Host "Checking container logs..."
    docker logs vault --tail 10
    exit 1
}

# Enable the KV secrets engine version 2
Write-Host "Enabling KV secrets engine..."
try {
    $result = Invoke-VaultCommand "vault secrets enable -path=ai-radar kv-v2"
    Write-Host "[OK] KV secrets engine enabled. Result: $($result | Out-String)" 
} catch {
    Write-Host "[WARNING] KV secrets engine might already be enabled (this is OK)"
}

# Create secrets for database
Write-Host "Creating database secrets..."
Invoke-VaultCommand "vault kv put ai-radar/database host=db port=5432 username=ai password=ai_pwd database=ai_radar"

# Create secrets for NATS
Write-Host "Creating NATS secrets..."
Invoke-VaultCommand "vault kv put ai-radar/nats host=nats port=4222 subject_prefix=ai-radar stream_name=ai-radar"

# Create secrets for MinIO
Write-Host "Creating MinIO secrets..."
Invoke-VaultCommand "vault kv put ai-radar/minio endpoint=minio:9000 access_key=minio secret_key=minio_pwd bucket=ai-radar-content"

# Create secrets for API keys (Replace with your actual keys)
Write-Host "Creating API keys secrets..."
Write-Warning "[SECURITY] Replace these placeholder API keys with your actual keys!"
Invoke-VaultCommand "vault kv put ai-radar/api-keys newsapi=YOUR_NEWSAPI_KEY_HERE openai=YOUR_OPENAI_API_KEY_HERE slack=YOUR_SLACK_WEBHOOK_URL_HERE linkedin_access_token=YOUR_LINKEDIN_ACCESS_TOKEN_HERE linkedin_author_urn=urn:li:organization:YOUR_COMPANY_PAGE_ID_HERE"

# Create an AppRole for authentication
Write-Host "Creating AppRole authentication..."
try {
    Invoke-VaultCommand "vault auth enable approle"
} catch {
    Write-Host "[WARNING] AppRole might already be enabled (this is OK)"
}

# Create a policy for AI Radar services
$policyHCL = @"
# AI Radar Policy
path "ai-radar/*" {
  capabilities = ["read"]
}
"@

[System.IO.File]::WriteAllText("./ai-radar-policy.hcl", $policyHCL, (New-Object System.Text.UTF8Encoding($false)))

# Copy policy file to container and create policy
docker cp ai-radar-policy.hcl vault:/tmp/ai-radar-policy.hcl
Invoke-VaultCommand "vault policy write ai-radar-policy /tmp/ai-radar-policy.hcl"

# Create roles for each service
$services = @("fetcher", "summariser", "ranker", "scheduler", "api", "ui")
foreach ($service in $services) {
    Write-Host "Creating role for $service..."
    Invoke-VaultCommand "vault write auth/approle/role/$service policies=ai-radar-policy token_ttl=1h token_max_ttl=24h"
    
    # Get role ID and secret ID
    try {
        $roleIdOutput = Invoke-VaultCommand "vault read -format=json auth/approle/role/$service/role-id"
        $roleId = $roleIdOutput | ConvertFrom-Json

        $secretIdOutput = Invoke-VaultCommand "vault write -format=json -f auth/approle/role/$service/secret-id"
        $secretId = $secretIdOutput | ConvertFrom-Json
    } catch {
        Write-Host "[WARNING] Error getting role/secret IDs for $service - $_"
    }
    
    # Create directory for role IDs and secret IDs if it doesn't exist
    if (-not (Test-Path "./vault-auth")) {
        New-Item -ItemType Directory -Path "./vault-auth" -Force | Out-Null
        Write-Host "Created vault-auth directory"
    }
    
    # Save role ID and secret ID to files
    if ($roleId -and $roleId.data -and $roleId.data.role_id) {
        [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", $roleId.data.role_id, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "[OK] Saved role ID for $service"
    } else {
        Write-Host "[WARNING] Could not get role ID for $service, using placeholder"
        [System.IO.File]::WriteAllText("./vault-auth/$service-role-id.txt", "placeholder-role-id", (New-Object System.Text.UTF8Encoding($false)))
    }

    if ($secretId -and $secretId.data -and $secretId.data.secret_id) {
        [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", $secretId.data.secret_id, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "[OK] Saved secret ID for $service"
    } else {
        Write-Host "[WARNING] Could not get secret ID for $service, using placeholder"
        [System.IO.File]::WriteAllText("./vault-auth/$service-secret-id.txt", "placeholder-secret-id", (New-Object System.Text.UTF8Encoding($false)))
    }
}

Write-Host "`n[SUCCESS] Vault setup complete!"
Write-Host "[OK] You can access the Vault UI at http://localhost:$vaultPort with token: root"
Write-Host "[OK] Role IDs and Secret IDs for services are saved in the vault-auth directory"
Write-Host "[OK] To start the services with Vault integration, run: .\ai-radar.ps1 dev"

# Clean up
Remove-Item -Path "./ai-radar-policy.hcl" -Force