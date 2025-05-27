{{- with secret "ai-radar/minio" -}}
MINIO_ENDPOINT={{ .Data.data.endpoint }}
MINIO_ACCESS_KEY={{ .Data.data.access_key }}
MINIO_SECRET_KEY={{ .Data.data.secret_key }}
MINIO_BUCKET={{ .Data.data.bucket }}
{{- end -}}
