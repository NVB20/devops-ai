{{/* Names: with the release called "devops-ai" every resource is devops-ai, devops-ai-db, ... */}}
{{- define "devops-ai.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/* Common labels. app.kubernetes.io/name and /instance come from selectorLabels, on the resources that have one */}}
{{- define "devops-ai.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/part-of: devops-ai
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/* Selector labels never change after install (Kubernetes refuses a changed Deployment selector) */}}
{{- define "devops-ai.selectorLabels" -}}
app.kubernetes.io/name: {{ .component }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end -}}

{{- define "devops-ai.image" -}}
{{- printf "%s:%s" .Values.image.repository (default .Chart.AppVersion .Values.image.tag) -}}
{{- end -}}

{{/* The Secret holding DATABASE_URL, and the URL itself when the chart creates that Secret */}}
{{- define "devops-ai.databaseSecret" -}}
{{- default (printf "%s-database" (include "devops-ai.fullname" .)) .Values.database.existingSecret -}}
{{- end -}}

{{- define "devops-ai.databaseUrl" -}}
{{- if .Values.postgres.enabled -}}
{{- with .Values.postgres -}}
{{- printf "postgresql://%s:%s@%s-db:5432/%s" .user .password (include "devops-ai.fullname" $) .database -}}
{{- end -}}
{{- else -}}
{{- .Values.database.url -}}
{{- end -}}
{{- end -}}

{{- define "devops-ai.openrouterSecret" -}}
{{- default (printf "%s-openrouter" (include "devops-ai.fullname" .)) .Values.llm.existingSecret -}}
{{- end -}}

{{/* Stop at render time on settings that can't work, instead of pods that crash later */}}
{{- define "devops-ai.validate" -}}
{{- $sources := 0 -}}
{{- if .Values.postgres.enabled }}{{ $sources = add1 $sources }}{{ end -}}
{{- if .Values.database.url }}{{ $sources = add1 $sources }}{{ end -}}
{{- if .Values.database.existingSecret }}{{ $sources = add1 $sources }}{{ end -}}
{{- if ne $sources 1 -}}
{{- fail "Set exactly one of postgres.enabled, database.url or database.existingSecret" -}}
{{- end -}}
{{- if not (has .Values.llm.provider (list "openrouter" "ollama")) -}}
{{- fail (printf "llm.provider must be openrouter or ollama, not %q" .Values.llm.provider) -}}
{{- end -}}
{{- if and .Values.llm.openrouterApiKey .Values.llm.existingSecret -}}
{{- fail "Set llm.openrouterApiKey or llm.existingSecret, not both" -}}
{{- end -}}
{{- end -}}

{{/* The DATABASE_URL env entry, shared by the app and the ingest Job */}}
{{- define "devops-ai.databaseEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "devops-ai.databaseSecret" . }}
      key: DATABASE_URL
{{- end -}}
