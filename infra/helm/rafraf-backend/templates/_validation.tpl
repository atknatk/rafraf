{{- /*
T3.5-polish-fix (HIGH #2): fail-fast guard against placeholder NetworkPolicy
CIDRs slipping into a production deploy.

values-prod.yaml ships with illustrative subnet CIDRs (10.10.1-3.0/24 for RDS,
10.10.11-13.0/24 for Redis) that MUST be replaced with the real prod VPC
subnet CIDRs before first deploy. Without this guard the chart would render
silently with placeholder values and the live backend would fail to reach
RDS/Redis (egress blocked → /ready returns 503 → ALB health checks fail →
traffic never lands → silent prod-down).

The guard fires only when:
  * prodGuard.enabled is true (set in values-prod.yaml only), AND
  * any rdsCIDR or redisCIDR matches a known placeholder string.

Operator workaround for emergency edge cases: --set prodGuard.enabled=false
(but the LOG WILL ECHO the bypass — see NOTES.txt rendering).
*/ -}}

{{- define "rafraf-backend.validatePlaceholderCIDRs" -}}
{{- $placeholders := list "10.10.1.0/24" "10.10.2.0/24" "10.10.3.0/24" "10.10.11.0/24" "10.10.12.0/24" "10.10.13.0/24" -}}
{{- range .Values.networkPolicy.rdsCIDRs -}}
{{- if has . $placeholders -}}
{{- fail (printf "DEPLOY BLOCKED: networkPolicy.rdsCIDRs still contains placeholder %q from values-prod.yaml. Replace with the actual prod RDS subnet CIDRs (aws ec2 describe-subnets --filters Name=tag:Tier,Values=database) before deploying. To bypass for non-prod testing, set prodGuard.enabled=false." .) -}}
{{- end -}}
{{- end -}}
{{- range .Values.networkPolicy.redisCIDRs -}}
{{- if has . $placeholders -}}
{{- fail (printf "DEPLOY BLOCKED: networkPolicy.redisCIDRs still contains placeholder %q from values-prod.yaml. Replace with the actual prod ElastiCache subnet CIDRs (aws elasticache describe-cache-subnet-groups) before deploying. To bypass for non-prod testing, set prodGuard.enabled=false." .) -}}
{{- end -}}
{{- end -}}
{{- end -}}

