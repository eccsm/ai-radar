{{- with secret "ai-radar/nats" -}}
NATS_URL=nats://{{ .Data.data.host }}:{{ .Data.data.port }}
NATS_SUBJECT_PREFIX={{ .Data.data.subject_prefix }}
NATS_STREAM_NAME={{ .Data.data.stream_name }}
{{- end -}}
