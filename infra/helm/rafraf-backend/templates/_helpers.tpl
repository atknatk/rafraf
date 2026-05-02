{{/*
Expand the name of the chart.
*/}}
{{- define "rafraf-backend.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully qualified app name. Truncated to 63 chars (DNS label limit)
and the trailing "-" is removed if present.
*/}}
{{- define "rafraf-backend.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart name + version, used as the chart label.
*/}}
{{- define "rafraf-backend.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels (recommended K8s labels).
*/}}
{{- define "rafraf-backend.labels" -}}
helm.sh/chart: {{ include "rafraf-backend.chart" . }}
{{ include "rafraf-backend.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: rafraf
{{- end }}

{{/*
Selector labels (must remain stable across releases — used by Service/HPA/PDB).
*/}}
{{- define "rafraf-backend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "rafraf-backend.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name.
*/}}
{{- define "rafraf-backend.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "rafraf-backend.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Fully-qualified container image reference.
- If image.tag is set, use it.
- Otherwise fall back to .Chart.AppVersion (logged as a WARNING via NOTES.txt).
*/}}
{{- define "rafraf-backend.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end }}

{{/*
Name of the k8s Secret created by ESO (or referenced manually).
*/}}
{{- define "rafraf-backend.secretName" -}}
{{- default (printf "%s-secrets" (include "rafraf-backend.fullname" .)) .Values.externalSecrets.targetSecretName -}}
{{- end }}
