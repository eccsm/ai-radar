# Vault Agent configuration for fetcher agent
# This file configures Vault Agent to authenticate with Vault and retrieve secrets

# Auto-auth configuration
auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path = "/vault/role-id"
      secret_id_file_path = "/vault/secret-id"
    }
  }

  sink "file" {
    config = {
      path = "/vault/token"
    }
  }
}

# Template configuration for fetching secrets
template {
  source = "/vault/templates/minio.tpl"
  destination = "/vault/secrets/minio.env"
}

template {
  source = "/vault/templates/postgres.tpl"
  destination = "/vault/secrets/postgres.env"
}

template {
  source = "/vault/templates/nats.tpl"
  destination = "/vault/secrets/nats.env"
}

template {
  source = "/vault/templates/newsapi.tpl"
  destination = "/vault/secrets/newsapi.env"
}

# Vault API proxy settings
vault {
  address = "http://vault:8200"
}

# Enable Prometheus metrics
telemetry {
  prometheus_retention_time = "24h"
  disable_hostname = true
}
