{{- define "shopflow-infra.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Call as: (dict "root" . "name" "postgres" "component" "database") */}}
{{- define "shopflow-infra.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{- define "shopflow-infra.labels" -}}
helm.sh/chart: {{ include "shopflow-infra.chart" .root }}
{{ include "shopflow-infra.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
app.kubernetes.io/part-of: {{ .root.Values.partOf | default .root.Chart.Name }}
{{- end }}

{{- define "shopflow-infra.postgres.image" -}}
{{- with .Values.postgres.image -}}
{{- if .digest -}}
{{- printf "%s:%s@%s" .repository .tag .digest -}}
{{- else -}}
{{- printf "%s:%s" .repository .tag -}}
{{- end -}}
{{- end -}}
{{- end -}}
