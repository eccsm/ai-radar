{{ with secret "ai-radar/database" }}
POSTGRES_HOST={{ .Data.host }}
POSTGRES_PORT={{ .Data.port }}
POSTGRES_USER={{ .Data.username }}
POSTGRES_PASSWORD={{ .Data.password }}
POSTGRES_DB={{ .Data.database }}
{{ end }}
