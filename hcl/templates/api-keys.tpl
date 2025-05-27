{{- with secret "ai-radar/api-keys" -}}
NEWSAPI_KEY={{ .Data.data.newsapi }}
OPENAI_API_KEY={{ .Data.data.openai }}
SLACK_WEBHOOK={{ .Data.data.slack }}
{{- end -}}
