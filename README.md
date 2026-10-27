# platform-gitops

Declarative Kubernetes desired state for the `product-catalog` and
`product-search` services and the small set of cluster add-ons assigned to
Argo CD. Terraform remains the owner of cloud infrastructure and EKS
foundations; service repositories remain the owners of application behavior
and container builds.

> **Deployment status:** This repository contains configuration, not proof of
> a deployed cluster. Argo CD Applications are intentionally manual-sync.
> Populate the documented cluster, secret-store, and immutable image inputs
> and obtain deployment approval before syncing.

## Ownership boundaries

| Owner | Responsibilities |
| --- | --- |
| Terraform / `platform-infrastructure` | VPC, EKS, IAM/IRSA, managed PostgreSQL, Kafka, Redis and OpenSearch, EKS add-ons, and infrastructure outputs |
| Service repositories | Application source, Dockerfiles, tests, APIs, migrations, event contracts, and service-specific behavior |
| `platform-gitops` | Argo CD projects/applications, Kubernetes workloads, services, probes, resource sizing, environment overlays, and references to externally managed secrets |

Do not configure Terraform and Argo CD to manage the same Kubernetes resource.
Before adopting this repository in a cluster that already uses the
`platform-infrastructure` Argo CD root, migrate or disable that root and review
resource ownership. Do not run both roots against the same workloads.

## Repository layout

```text
argocd/
  bootstrap/root-app.yaml       # Manually applied root Application
  projects/platform.yaml        # Restricted source/destination/resource boundary
  apps/                         # Child Applications
charts/spring-service/          # Reusable Helm chart for Spring Boot workloads
  templates/                    # Deployment, Service, and ExternalSecrets
  values/
    product-catalog.yaml         # Service-specific settings
    product-search.yaml
    environments/                # Per-environment replicas, digests, secret IDs
kubernetes/platform/
  providers/aws/
    cluster-secret-store.yaml    # AWS-specific External Secrets configuration
.github/workflows/validate.yaml  # Helm lint and template validation
```

Helm is the primary service deployment format: one reusable chart renders
either service, and Argo CD combines the service values file with one
environment values file. This avoids duplicated workload templates while
keeping environment promotion explicit. Upstream components are consumed as
pinned Helm charts directly through Argo CD. Kustomize is not used because the
current requirements do not need a separate patch/overlay composition layer.

The `platform` AppProject restricts repository sources and destination
namespaces. Its cluster-scoped allowlist permits only the kinds needed by the
External Secrets chart and AWS ClusterSecretStore. Review rendered chart
resources before tightening or expanding that list.

## Cross-repository ownership and migration

The local `platform-infrastructure` repository also declares Argo CD and
workload resources. In particular:

| Resource | Current declarations | Intended GitOps owner |
| --- | --- | --- |
| Root Application | `platform-infrastructure/argocd/root-app.yaml` and `platform-gitops/argocd/bootstrap/root-app.yaml` both use `platform-root` | `platform-gitops`; the infrastructure root must be retired as part of an approved handoff |
| External Secrets Application | `platform-infrastructure/argocd/apps/external-secrets-app.yaml` and `platform-gitops/argocd/apps/external-secrets.yaml` | `platform-gitops` after an approved handoff |
| Metrics Server Application | `platform-infrastructure/argocd/apps/metrics-server-app.yaml` | Defer; add only if a GitOps-owned workload requires HPA and the cluster does not already provide metrics |
| Catalog/search workloads | `platform-infrastructure/kubernetes/base/` plus production overlay and `platform-gitops/charts/spring-service/` | `platform-gitops` |
| ClusterSecretStore | `platform-infrastructure/kubernetes/cluster-config/cluster-secret-store.yaml` and `platform-gitops/kubernetes/platform/providers/aws/cluster-secret-store.yaml` | `platform-gitops` for the Kubernetes object; Terraform for IAM |
| AWS Load Balancer Controller and CDC | `platform-infrastructure/argocd/apps/aws-load-balancer-controller-app.yaml`, `product-cdc-app.yaml`, and `kubernetes/overlays/prod/cdc/` | Defer; migrate only when ingress or CDC is explicitly in scope |

These are source declarations, not evidence that resources are deployed. Do
not reconcile both roots against a cluster. Before adoption, inventory the
actual Argo CD Applications and resource owners from an authorized operator
context; then hand off each resource deliberately. The existing External
Secrets targets and remote-key layout differ from this chart's
service-specific target names and placeholder remote keys, so agree on a
single contract before changing either repository. The catalog Service name
also differs: infrastructure uses `product-catalog-service`, and the Helm
chart preserves that name; search uses `product-search` in both sources.
Infrastructure's production Application also configures Image Updater
Kustomize writeback; this repository uses reviewed Helm values promotion.
Retire the competing updater behavior during the handoff rather than run both.

## Prerequisites

- An EKS cluster and foundational cloud resources provisioned by Terraform.
- A reachable Kubernetes API for the operator performing bootstrap and sync.
- Argo CD installed in `argocd`, configured to read this repository.
- A reviewed change to `argocd/bootstrap/root-app.yaml` if the repository URL
  or target branch differs from the defaults.
- Terraform-provided AWS identity/IRSA for External Secrets Operator and a
  provisioned Secrets Manager store with the expected per-environment values.
  The AWS-specific store definition is isolated under
  `kubernetes/platform/providers/aws/`.
- A GitHub Container Registry pull path available to cluster nodes.
- Published service image digests, recorded in the corresponding environment
  values file before syncing any service Application.

No cluster, AWS account, endpoint, CRD, secret, domain, or image digest is
assumed to exist. The checked-in `REPLACE_ME` values are intentionally
non-operational placeholders, not deployable defaults. Never replace secret
references with secret values.

## Bootstrap and deployment

1. Review the Terraform and infrastructure deployment runbooks. Provision
   infrastructure separately; do not apply Terraform from this repository.
2. Confirm cluster access and identify existing Argo CD Applications and
   resource owners. If `platform-infrastructure` already manages these
   workloads, agree on a migration before proceeding.
3. Configure the External Secrets chart's AWS service-account role annotation
   and `ClusterSecretStore` region from reviewed Terraform outputs. Provision
   environment-specific Secrets Manager entries through the owning
   infrastructure/operations process.
4. Obtain the published catalog and search image digests from their CI
   workflows. Replace the all-zero `sha256:` placeholders in the intended
   environment values file with the matching published digests; do not
   promote `latest`.
5. Review and merge those Git changes. Apply only the root Application:

   ```sh
   kubectl apply -f argocd/bootstrap/root-app.yaml
   ```

6. Manually sync `platform-root` in Argo CD to create the AppProject and child
   Applications. Sync the External Secrets Operator Application first. Verify
   its deployment and CRDs are healthy; then sync `platform-cluster-config`
   and confirm the ClusterSecretStore reports `Ready`.
7. Sync one environment's service Application only after its secret
   references and images are ready. Verify Argo CD health, rollout status,
   pod events, application readiness, and logs without printing secret data.

All child Applications are manual-sync. The root only creates/reconciles the
Argo CD Application and AppProject objects; syncing the root does not authorize
service deployment.

## Image promotion

Service CI publishes images to:

- `ghcr.io/jahrough/product-catalog`
- `ghcr.io/jahrough/product-search`

Use an immutable registry digest from the successful service build and update
only that service's digest in
`charts/spring-service/values/environments/<env>.yaml` by reviewed pull
request. Promote the same tested digest between environments rather than
rebuilding. This repository does not currently have a verified published
digest; the all-zero fail-closed digest values must be replaced before service
sync.

## Rollback

Revert the Git commit that changed the image digest or Kubernetes settings,
merge the revert, and manually sync the affected Application. Verify the
Deployment rollout and application health. Application data migrations and
managed-service recovery belong to the service/infrastructure owners; a
manifest rollback does not reverse database changes.

## Validation

Install the Helm CLI and render each service with its environment values:

```sh
for environment in dev staging production; do
  for service in product-catalog product-search; do
    helm template "$service" charts/spring-service \
      --namespace "platform-${environment}" \
      --values "charts/spring-service/values/${service}.yaml" \
      --values "charts/spring-service/values/environments/${environment}.yaml" \
      >/dev/null
  done
done
```

The GitHub Actions workflow runs `helm lint` and all six renders. This checks
chart structure and template output; it does not prove live API compatibility,
CRDs, cloud values, image availability, Argo CD sync status, or workload
health.

## Local development, monitoring, and exposure

Run local application development from the service repositories or the
infrastructure repository's Compose setup. No Kubernetes cluster or paid
cloud resources are required for that workflow.

The applications expose Spring Actuator health endpoints used for probes.
Prometheus/Grafana and an OpenTelemetry Collector/backend are not deployed by
this repository because no scrape/retention backend or tracing destination has
been verified. Do not enable external ingress until a controller, DNS/TLS
ownership, and application authentication requirements have been addressed.
In particular, the product-search API is currently documented as
unauthenticated.

## Teardown boundaries

Deleting an Argo CD Application with resource pruning can delete the
Kubernetes objects it manages. Review the Application's resources and
ownership before deleting or disabling it. Do not delete Terraform-owned
cloud infrastructure, managed data, Secrets Manager entries, or EKS resources
as part of a GitOps teardown. Preserve production data and recovery controls.

## Known blockers and assumptions

- The adjacent `platform-infrastructure` repository already contains an
  independent Argo CD root, Kubernetes workloads, and External Secrets
  configuration. Its ownership must be reconciled before adopting this repo.
- The adjacent service build workflows publish tags, but no current image
  digest has been verified here. The configured all-zero image digests
  intentionally prevent a successful pull until reviewed.
- AWS role ARN, Secrets Manager region/keys, actual service endpoints, and
  cluster readiness have not been verified.
- The service repository metadata disagrees on Java versions for catalog and
  search; resolving that is out of this repository's ownership and approved
  scope.
