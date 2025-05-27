#!/usr/bin/env pwsh
# Fix Vault Script - Creates all required secrets in Vault

Write-Host "Fixing Vault configuration for AI Radar..." -ForegroundColor Green

# Enable KV secrets engine if not already enabled
Write-Host "Enabling KV secrets engine at path 'ai-radar'..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault secrets enable -path=ai-radar kv-v2 || true"

# Create database secrets
Write-Host "Creating database secrets..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/database host=db port=5432 username=ai password=ai_pwd database=ai_radar"

# Create NATS secrets
Write-Host "Creating NATS secrets..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/nats host=nats port=4222 subject_prefix=ai-radar stream_name=ai-radar"

# Create MinIO secrets
Write-Host "Creating MinIO secrets..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/minio endpoint=minio:9000 access_key=minio secret_key=minio_pwd bucket=ai-radar-content"

# Create API Keys secrets
Write-Host "Creating API Keys secrets..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/api-keys newsapi=your_newsapi_key_here openai=your_openai_key_here slack=your_slack_webhook_here"

# Create JWT secret
Write-Host "Creating JWT secret key..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv put ai-radar/JWT_SECRET_KEY value=ai_radar_jwt_secret"

# Verify secrets are created
Write-Host "Verifying secrets are created..." -ForegroundColor Cyan
docker-compose exec vault sh -c "VAULT_ADDR=http://vault:8200 VAULT_TOKEN=root vault kv list ai-radar/"

Write-Host "Vault setup complete!" -ForegroundColor Green
Write-Host "You can access the Vault UI at http://localhost:8200 with token: root" -ForegroundColor Green
Write-Host "After checking the Vault UI, restart your services with: .\ai-radar.ps1 dev" -ForegroundColor Green
