{{- define "inventory-service.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "inventory-service.fullname" -}}
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

{{- define "inventory-service.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "inventory-service.labels" -}}
helm.sh/chart: {{ include "inventory-service.chart" . }}
{{ include "inventory-service.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: {{ .Values.partOf | default (include "inventory-service.name" .) }}
{{- end }}

{{- define "inventory-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "inventory-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Call as: (dict "root" . "component" "server") */}}
{{- define "inventory-service.componentLabels" -}}
{{ include "inventory-service.labels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "inventory-service.componentSelectorLabels" -}}
{{ include "inventory-service.selectorLabels" .root }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "inventory-service.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "inventory-service.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "inventory-service.image" -}}
{{- $repo := required "image.repository is required" .Values.image.repository -}}
{{- if and .Values.image.requireDigest (not .Values.image.digest) -}}
{{- fail "image.digest is required when image.requireDigest is true (prod pins images by digest)" -}}
{{- end -}}
{{- $tag := .Values.image.tag | default .Chart.AppVersion -}}
{{- if .Values.image.digest -}}
{{- printf "%s:%s@%s" $repo $tag .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end -}}
{{- end -}}

{{/*
Secret holding DB credentials. Chart-internal and Vault modes both produce <fullname>-db;
externalSecret mode points at a pre-existing Secret, so the mount and env refs must follow it.
*/}}
{{- define "inventory-service.dbSecretName" -}}
{{- if and .Values.database.externalSecret.enable (not .Values.database.vault.enable) -}}
{{- required "database.externalSecret.name is required" .Values.database.externalSecret.name -}}
{{- else -}}
{{- printf "%s-db" (include "inventory-service.fullname" .) -}}
{{- end -}}
{{- end -}}

{{- define "inventory-service.dbUsernameKey" -}}
{{- if .Values.database.vault.enable -}}
{{- .Values.database.vault.usernameKey -}}
{{- else if .Values.database.externalSecret.enable -}}
{{- .Values.database.externalSecret.usernameKey -}}
{{- else -}}
username
{{- end -}}
{{- end -}}

{{- define "inventory-service.dbPasswordKey" -}}
{{- if .Values.database.vault.enable -}}
{{- .Values.database.vault.passwordKey -}}
{{- else if .Values.database.externalSecret.enable -}}
{{- .Values.database.externalSecret.passwordKey -}}
{{- else -}}
password
{{- end -}}
{{- end -}}

{{- define "inventory-service.render" -}}
{{- if typeIs "string" .value -}}
{{- tpl .value .context }}
{{- else -}}
{{- tpl (.value | toYaml) .context }}
{{- end -}}
{{- end -}}
