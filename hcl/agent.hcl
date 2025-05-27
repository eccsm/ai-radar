exit_after_auth = false
pid_file = "/tmp/agent.pid"

auto_auth {
  method "token" {
    config {
      token = "root"
    }
  }
}

template {
  source      = "/vault/templates/database.tpl"
  destination = "/vault/secrets/database.env"
}

template {
  source      = "/vault/templates/nats.tpl"
  destination = "/vault/secrets/nats.env"
}

template {
  source      = "/vault/templates/minio.tpl"
  destination = "/vault/secrets/minio.env"
}

template {
  source      = "/vault/templates/api-keys.tpl"
  destination = "/vault/secrets/api-keys.env"
}

vault {
  address = "http://vault:8200"
}
