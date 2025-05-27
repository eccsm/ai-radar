{{- with secret "ai-radar/database" -}}
DB_HOST={{ .Data.data.host }}
DB_PORT={{ .Data.data.port }}
DB_USER={{ .Data.data.username }}
DB_PASSWORD={{ .Data.data.password }}
DB_NAME={{ .Data.data.database }}
{{- end -}}
