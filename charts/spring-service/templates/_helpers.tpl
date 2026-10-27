{{- define "spring-service.name" -}}
{{- required "service.name is required" .Values.service.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "spring-service.labels" -}}
app.kubernetes.io/name: {{ include "spring-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: {{ .Values.service.partOf }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "spring-service.databaseRemoteKey" -}}
{{- $key := index .Values.externalSecrets.database.remoteKeys .Values.service.name -}}
{{- required (printf "externalSecrets.database.remoteKeys.%s is required" .Values.service.name) $key -}}
{{- end -}}

{{- define "spring-service.imageDigest" -}}
{{- $digest := index .Values.images .Values.service.name -}}
{{- required (printf "images.%s digest is required" .Values.service.name) $digest -}}
{{- end -}}

{{- define "spring-service.envSecretName" -}}
{{- if eq .secret "database" -}}
{{- printf "%s-db" $.Values.service.name -}}
{{- else -}}
{{- printf "%s-%s" $.Values.service.name .secret -}}
{{- end -}}
{{- end -}}
