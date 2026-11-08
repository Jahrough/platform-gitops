# platform-gitops

Declarative Kubernetes desired state for the `product-catalog` and
`product-search` services, Kafka Connect, and Kubernetes controllers/workloads
assigned to Argo CD. Terraform remains the owner of cloud infrastructure,
EKS foundations, and AWS-managed EKS add-ons; service repositories remain the
owners of application behavior and service container builds.

> **Deployment status:** This repository contains configuration, not proof of
> a deployed cluster. Argo CD Applications are intentionally manual-sync.
> Populate the documented cluster, secret-store, and immutable image inputs
> and obtain deployment approval before syncing.

Cross-repository architecture decisions are tracked in the canonical [Product Platform ADR index](https://github.com/Jahrough/ai-native-engineering/blob/main/docs/architecture/adr/README.md). Those records are proposals unless explicit approval is recorded; they do not imply implementation or deployment.

## Architecture

```mermaid
flowchart TB
  subgraph sources["Application image sources"]
    direction TB
    appRepos["Catalog + Search<br/>service repositories and CI"]
    cdcBuild["Kafka Connect image workflow<br/>platform-infrastructure"]
    registry[("GHCR<br/>digest placeholders")]
    appRepos -->|"publishes"| registry
    cdcBuild -->|"publishes"| registry
  end

  subgraph gitops["platform-gitops — versioned desired state"]
    config["Cloud root · AppProject · child Applications<br/>Spring Helm chart + cloud values<br/>CDC Kustomize resources"]
    localConfig["Local root · restricted AppProject<br/>Local service Applications + Helm values"]
  end

  subgraph infra["platform-infrastructure — Terraform + local development"]
    direction TB
    terraform["VPC / EKS foundations<br/>AWS-managed add-ons<br/>IAM / IRSA · Secrets Manager<br/>RDS · MSK · Redis · OpenSearch"]
    compose["Docker Compose<br/>local apps + dependencies"]
  end

  subgraph target["Intended Amazon EKS target — live state unverified"]
    direction TB
    eks["Amazon EKS"]
    argocd["Argo CD<br/>(installation is a prerequisite)"]
    workloads["Catalog + Search · 6 Apps<br/>dev / staging / production<br/>Kafka Connect · production<br/>External Secrets + ClusterSecretStore<br/>AWS Load Balancer Controller<br/>(ingress optional)"]
    argocd -->|"manual sync"| workloads
  end

  subgraph localTarget["Optional local cluster — not provisioned"]
    direction TB
    localArgo["Local Argo CD<br/>(installation prerequisite)"]
    localWorkloads["Catalog + Search<br/>platform-local namespace"]
    localArgo -->|"manual sync"| localWorkloads
  end

  operator["Authorized operator"]
  operator -->|"kubectl apply root manifest"| config
  config -. "Argo CD reads Git source" .-> argocd
  operator -->|"applies local bootstrap separately"| localConfig
  localConfig -. "Git source on reachable branch" .-> localArgo
  registry -->|"image pulls"| workloads
  terraform -->|"provisions"| eks
  appRepos -->|"Compose build contexts"| compose
  appRepos -. "local build + image load" .-> localWorkloads

  classDef source fill:#e8f5e9,stroke:#2e7d32,color:#102a13
  classDef gitopsNode fill:#e8eaf6,stroke:#3949ab,color:#151b45
  classDef targetNode fill:#e0f2f1,stroke:#00796b,color:#102a28
  classDef infraNode fill:#fff3e0,stroke:#ef6c00,color:#3e2410
  classDef external fill:#f5f5f5,stroke:#616161,color:#212121
  class appRepos,cdcBuild source
  class config,localConfig gitopsNode
  class eks,argocd,workloads,localArgo,localWorkloads targetNode
  class terraform,compose infraNode
  class registry external
```

Solid arrows show publishing, provisioning, bootstrap, or runtime flows;
dotted arrows show Git references, rendering, reconciliation, or external
configuration. Argo CD Applications are configured for manual sync. The EKS
target, Argo CD installation, AWS resources, and image availability have not
been verified as deployed; this diagram describes repository configuration
and intended relationships, not live status.
Runtime detail is collapsed for readability: External Secrets uses
Terraform-provisioned IRSA to read AWS Secrets Manager and materialize
referenced Kubernetes Secrets; workloads consume configured endpoints for
Terraform-managed data services. The optional local Argo CD path is configured
in Git but not installed or tested; the existing Compose dependencies are not
directly reachable from local Kubernetes pods without additional networking.

## Ownership boundaries

| Owner                                 | Responsibilities                                                                                                                                                                                             |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Terraform / `platform-infrastructure` | VPC, EKS, IAM/IRSA, AWS-managed EKS add-ons, managed PostgreSQL, Kafka, Redis and OpenSearch, Secrets Manager resources, and infrastructure outputs                                                          |
| Service repositories                  | Application source, Dockerfiles, tests, APIs, migrations, event contracts, and service-specific behavior                                                                                                     |
| `platform-gitops`                     | Argo CD projects/applications, Helm-installed Kubernetes controllers, workloads, services, probes, resource sizing, NetworkPolicies, environment configuration, and references to externally managed secrets |

Do not configure Terraform and Argo CD to manage the same Kubernetes resource.
The source manifests and Applications previously declared in
`platform-infrastructure` have been moved or consolidated into this repository.
That source change does not establish whether an older Argo CD root is active
in a cluster. Before syncing, inventory live Applications and resources from
an authorized operator context and deliberately transfer the root to this
repository; do not reconcile both roots against the same resources.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart TD
    inventory["Inventory live Argo CD Applications<br/>and resources<br/>from an authorized operator context"]
    old{"Older root from<br/>platform-infrastructure<br/>active in the cluster?"}
    switch["Deliberately switch the existing<br/>platform-root source<br/>to this repository"]
    apply["Apply this repository's<br/>root Application"]
    sync(["Manually sync platform-root"])
    both(["Never reconcile both roots<br/>against the same resources"])

    inventory --> old
    old -->|"yes"| switch
    old -->|"no"| apply
    switch --> sync
    apply --> sync
    old -.->|"avoid"| both

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef danger fill:#21262d,stroke:#f85149,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class inventory,switch,apply internal
    class old gate
    class both danger
    class sync terminal
```

## Repository layout

```text
argocd/
  bootstrap/root-app.yaml       # Manually applied root Application
  bootstrap/local-*.yaml        # Restricted local bootstrap; separately applied
  projects/platform.yaml        # Restricted source/destination/resource boundary
  apps/                         # Child Applications
  local/                        # Local-only project and service Applications
charts/spring-service/          # Reusable Helm chart for Spring Boot workloads
  templates/                    # Deployment, Service, secrets, scaling, policies, optional ingress
  values/
    product-catalog.yaml         # Service-specific settings
    product-search.yaml
    environments/                # Cloud environment values plus local defaults
    local/                       # Local service-specific values
kubernetes/platform/
  providers/aws/
    cluster-secret-store.yaml    # AWS-specific External Secrets configuration
  cdc/                           # Kafka Connect Deployment, service, policies, and secrets
scripts/                         # Production image pinning and optional ingress helper
.github/workflows/validate.yaml  # Helm lint and template validation
```

Helm is the primary service deployment format: one reusable chart renders
either service, and Argo CD combines service-specific values with environment
values. Cloud environments require image digests; the opt-in local profile
uses locally built tags and disables External Secrets and cloud-only resources.
Production values render autoscalers, disruption budgets, and service-specific
egress policies; ingress remains disabled until the domain and certificate
are configured. Kafka Connect uses a small Kustomize base because it is a
separate platform runtime, not a Spring service. Upstream components are
consumed as pinned Helm charts directly through Argo CD.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    chart["charts/spring-service<br/>Deployment, Service, secrets,<br/>scaling, policies, optional ingress"]
    svcvals["Service values<br/>product-catalog.yaml<br/>product-search.yaml"]
    envvals["Cloud environment values<br/>dev, staging, production<br/>image digest required"]
    localvals["Local profile<br/>locally built tags<br/>External Secrets and<br/>cloud-only resources disabled"]
    argocd["Argo CD<br/>combines chart and values"]
    rendered["Rendered service workload"]
    prod["Production only<br/>autoscalers, disruption budgets,<br/>service-specific egress policies"]
    ingress["Ingress<br/>disabled until domain and<br/>certificate are configured"]

    svcvals --> argocd
    envvals --> argocd
    localvals -.->|"opt-in"| argocd
    chart --> argocd
    argocd --> rendered
    envvals -.-> prod
    prod -.-> rendered
    ingress -.-> rendered

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef external fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class argocd core
    class chart,svcvals,envvals,rendered internal
    class localvals,prod,ingress external
```

The `platform` AppProject restricts repository sources and destination
namespaces. Its resource allowlists cover the External Secrets and AWS Load
Balancer controller integrations, cluster-scoped AWS ClusterSecretStore,
and the namespaced workload resources. Review rendered chart resources before
tightening or expanding those lists.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    op(["Authorized operator"])
    root["platform-root<br/>argocd/bootstrap/root-app.yaml"]
    proj["AppProject: platform<br/>restricted sources, destinations,<br/>and resource kinds"]

    subgraph children["Child Applications — all manual sync"]
        eso["External Secrets Operator<br/>pinned Helm chart"]
        cfg["platform-cluster-config<br/>AWS ClusterSecretStore"]
        alb["AWS Load Balancer Controller<br/>pinned Helm chart"]
        cdc["CDC: Kafka Connect<br/>Kustomize, production"]
        svc["Catalog + Search<br/>6 Applications<br/>dev, staging, production"]
    end

    subgraph localside["Local path — separate, restricted to platform-local"]
        lproj["Local bootstrap AppProject"]
        lroot["platform-local-root"]
        lsvc["Local Catalog + Search<br/>Applications"]
    end

    op -->|"kubectl apply"| root
    root -->|"creates and reconciles"| proj
    root -->|"creates and reconciles"| children
    op -->|"applies separately"| lproj
    op -->|"applies separately"| lroot
    lroot -->|"creates and reconciles"| lsvc

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class root,lroot core
    class proj,eso,cfg,alb,cdc,svc,lproj,lsvc internal
    class op terminal
```

Syncing the root creates only the AppProject and child Application objects; it
does not authorize service deployment.

## Cross-repository ownership and migration

The Kubernetes manifests and Argo CD Applications are now declared here.
Terraform remains the source for AWS resources, IAM roles, and non-secret
infrastructure outputs. The infrastructure configuration helper writes
reviewed role ARNs, region, and Secrets Manager identifiers into this
repository's placeholders; it does not transfer or reveal secret values.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    tf["Terraform<br/>IAM / IRSA<br/>Secrets Manager resources"]
    helper["configure-argocd-from-terraform.py<br/>platform-infrastructure helper"]
    git["Reviewed Git change<br/>role ARNs, region, secret identifiers<br/>no secret values"]
    sm[("AWS Secrets Manager<br/>per-environment values")]
    eso["External Secrets Operator<br/>assumes IRSA role"]
    css["ClusterSecretStore<br/>AWS provider"]
    secrets["Kubernetes Secrets"]
    pods["Workloads"]

    tf -->|"non-secret outputs"| helper
    helper -->|"writes placeholders"| git
    git -->|"configures"| eso
    git -->|"configures"| css
    eso -->|"reads"| sm
    css --- eso
    eso -->|"materializes referenced secrets"| secrets
    secrets --> pods

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef external fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class eso core
    class tf,helper,git,css,secrets,pods internal
    class sm external
```

The AWS Load Balancer Controller and CDC Applications are defined here.
The controller is manually synced and requires the Terraform-created IAM role.
CDC is a separate manually synced Kustomize application; wait until the
catalog migration has created `public.outbox`, RDS logical replication is
active, and the CDC database credential exists before syncing it and
registering the connector.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    p1["Catalog migration has<br/>created public.outbox"]
    p2["RDS logical replication<br/>is active"]
    p3["CDC database credential<br/>exists"]
    p4["Kafka Connect image digest<br/>published and pinned"]
    ready{"All prerequisites<br/>ready?"}
    sync["Manually sync<br/>CDC Application"]
    register(["Register connector<br/>from a trusted host<br/>interim config in platform-infrastructure"])
    wait(["Wait: do not sync CDC"])

    p1 --> ready
    p2 --> ready
    p3 --> ready
    p4 --> ready
    ready -->|"yes"| sync
    sync --> register
    ready -->|"no"| wait

    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class p1,p2,p3,p4 internal
    class sync core
    class ready gate
    class register,wait terminal
```

The source move does not prove that the old infrastructure root is inactive.
Before applying the GitOps root in an existing cluster, inspect actual
Applications and resource ownership, then switch the existing `platform-root`
source deliberately. Do not apply both roots or assume that merging these
files performs a safe live handoff.

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
- A published Kafka Connect image digest before syncing the CDC Application.

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
   and `ClusterSecretStore` region from reviewed Terraform outputs. From the
   infrastructure repository, run
   `scripts/configure-argocd-from-terraform.py --gitops-repo <path-to-this-repo>`
   after outputs and application secret values are ready. Review and commit the
   generated non-secret settings; never put secret values in Git.
4. Obtain reviewed immutable catalog, search, and (for production) Kafka
   Connect image digests. From this repository, update the environment's
   service values; production also updates the CDC Kustomize image pin:

   ```sh
   python3 scripts/set-image-digests.py \
     --environment production \
     --catalog-digest sha256:CATALOG_DIGEST \
     --search-digest sha256:SEARCH_DIGEST \
     --connect-digest sha256:KAFKA_CONNECT_DIGEST
   ```

   Use `--environment dev` or `--environment staging` to pin the two service
   images in those environments; omit `--connect-digest` there.
   The all-zero pins intentionally fail closed. Promote the same tested
   digests between environments rather than promoting `latest`.
   Before a production sync, run
   `python3 scripts/validate-production-config.py` to check that AWS
   placeholders and zero image digests have been replaced.

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
8. Sync the CDC Application only after its prerequisites are ready. Register
   the connector from a trusted host using the interim connector configuration
   and helper in `platform-infrastructure`. The product-catalog service owns
   the outbox schema and event semantics; move connector configuration to that
   service repository when it can publish and maintain the definition.

All child Applications are manual-sync. The root only creates/reconciles the
Argo CD Application and AppProject objects; syncing the root does not authorize
service deployment.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart TD
    s1["1. Review runbooks<br/>provision infrastructure separately<br/>no Terraform from this repository"]
    s2["2. Confirm cluster access<br/>inventory Applications and owners<br/>agree a migration if needed"]
    s3["3. Configure External Secrets role and<br/>ClusterSecretStore region from Terraform outputs<br/>review and commit non-secret settings"]
    s4["4. Pin reviewed image digests<br/>set-image-digests.py<br/>production: validate-production-config.py"]
    s5["5. Review and merge Git changes<br/>kubectl apply root-app.yaml only"]
    s6["6. Manually sync platform-root"]
    s6a["Sync External Secrets Operator first"]
    g6a{"Deployment and CRDs<br/>healthy?"}
    s6b["Sync platform-cluster-config"]
    g6b{"ClusterSecretStore<br/>Ready?"}
    g7{"Secret references and<br/>images ready?"}
    s7["7. Sync one environment's<br/>service Application<br/>verify health, rollout, events, logs"]
    g8{"CDC prerequisites<br/>ready?"}
    s8["8. Sync CDC Application<br/>register connector from a trusted host"]
    hold(["Stop and resolve before continuing"])

    s1 --> s2 --> s3 --> s4 --> s5 --> s6 --> s6a --> g6a
    g6a -->|"yes"| s6b
    g6a -->|"no"| hold
    s6b --> g6b
    g6b -->|"yes"| g7
    g6b -->|"no"| hold
    g7 -->|"yes"| s7
    g7 -->|"no"| hold
    s7 --> g8
    g8 -->|"yes"| s8
    g8 -->|"no"| hold

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class s1,s2,s3,s4,s5,s6a,s6b internal
    class s6,s7,s8 core
    class g6a,g6b,g7,g8 gate
    class hold terminal
```

## Image promotion

Service CI publishes images to:

- `ghcr.io/jahrough/product-catalog`
- `ghcr.io/jahrough/product-search`
- `ghcr.io/jahrough/platform-infrastructure/kafka-connect`

Use immutable registry digests from successful builds and update the
production service pins with `scripts/set-image-digests.py`; CDC's pin is in
`kubernetes/platform/cdc/kustomization.yaml`. Promote the same tested digest
between environments rather than rebuilding. This repository does not
currently have a verified published digest; all-zero fail-closed pins must be
replaced before the corresponding Application is synced.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    ci["Service CI and<br/>Kafka Connect workflow"]
    ghcr[("GHCR<br/>product-catalog<br/>product-search<br/>kafka-connect")]
    digest{"Reviewed immutable digest<br/>from a successful build?"}
    script["scripts/set-image-digests.py"]
    svcvals["Environment service values"]
    cdcpin["CDC Kustomize image pin<br/>kubernetes/platform/cdc/kustomization.yaml"]
    review["Review and merge"]
    sync["Manual sync of<br/>the Application"]
    zero(["All-zero pins stay in place<br/>image pull fails closed"])
    promote["Promote the same tested digest<br/>dev, then staging, then production<br/>never rebuild or use latest"]

    ci -->|"publishes"| ghcr
    ghcr --> digest
    digest -->|"yes"| script
    digest -->|"no"| zero
    script --> svcvals
    script -->|"production, Connect digest"| cdcpin
    svcvals --> review
    cdcpin --> review
    review --> sync
    review -.-> promote

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef danger fill:#21262d,stroke:#f85149,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class ci,ghcr,script,svcvals,cdcpin,review internal
    class sync core
    class digest gate
    class zero danger
    class promote terminal
```

## Rollback

Revert the Git commit that changed the image digest or Kubernetes settings,
merge the revert, and manually sync the affected Application. Verify the
Deployment rollout and application health. Application data migrations and
managed-service recovery belong to the service/infrastructure owners; a
manifest rollback does not reverse database changes.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    revert["Revert the Git commit<br/>that changed the digest<br/>or Kubernetes settings"]
    merge["Merge the revert"]
    sync["Manually sync the<br/>affected Application"]
    verify["Verify Deployment rollout<br/>and application health"]
    data(["Database changes are not reversed<br/>owned by service and<br/>infrastructure owners"])

    revert --> merge --> sync --> verify
    verify -.-> data

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class revert,merge,verify internal
    class sync core
    class data terminal
```

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

The GitHub Actions workflow runs `helm lint`, all six service/environment
renders, validates production policy resources, renders the CDC Kustomize
configuration, parses rendered YAML, and tests the helper scripts. This checks
chart structure and template output; it does not prove live API compatibility,
CRDs, cloud values, image availability, Argo CD sync status, or workload
health.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    trigger(["validate.yaml workflow"])

    subgraph checks["Checks"]
        lint["helm lint"]
        render["Render all six<br/>service and environment<br/>combinations"]
        policy["Validate production<br/>policy resources"]
        kustomize["Render CDC<br/>Kustomize configuration"]
        parse["Parse rendered YAML"]
        scripts["Test helper scripts"]
    end

    gaps(["Not proven by these checks<br/>live API compatibility, CRDs, cloud values,<br/>image availability, Argo CD sync status,<br/>workload health"])

    trigger --> lint
    trigger --> render
    trigger --> policy
    trigger --> kustomize
    trigger --> parse
    trigger --> scripts
    checks -.-> gaps

    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class lint,render,policy,kustomize,parse,scripts internal
    class trigger,gaps terminal
```

## Optional ingress

The ALB controller Application must be configured from Terraform outputs and
synced before enabling ingress. For a domain controlled by you and a matching
regional ACM certificate, run:

```sh
python3 scripts/enable-ingress.py \
  --domain example.com \
  --certificate-arn arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000 \
  --region us-east-1 \
  --scheme internal
```

This enables ingress in production values only. `internet-facing` exposes
services publicly; the product APIs' authentication requirements must be
reviewed before choosing it. Review and commit the GitOps change, sync the
Applications only after approval, then create DNS records after the load
balancer is provisioned.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart LR
    alb["ALB controller Application<br/>configured from Terraform outputs<br/>and synced"]
    run["scripts/enable-ingress.py<br/>domain, ACM certificate,<br/>region, scheme"]
    prod["Production values only<br/>ingress enabled"]
    scheme{"Scheme"}
    internal["internal"]
    public["internet-facing<br/>exposes services publicly<br/>review API authentication first"]
    commit["Review and commit<br/>GitOps change"]
    approve{"Approved?"}
    sync["Sync Applications"]
    dns(["Create DNS records after the<br/>load balancer is provisioned"])
    hold(["Do not sync"])

    alb --> run --> prod --> scheme
    scheme --> internal
    scheme --> public
    internal --> commit
    public --> commit
    commit --> approve
    approve -->|"yes"| sync
    approve -->|"no"| hold
    sync --> dns

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef danger fill:#21262d,stroke:#f85149,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class alb,run,prod,commit,internal internal
    class sync core
    class scheme,approve gate
    class public danger
    class dns,hold terminal
```

## Local development, monitoring, and exposure

Run local application development from the service repositories or the
infrastructure repository's Compose setup. From the infrastructure repository
root, with the three repositories checked out as siblings:

```sh
export POSTGRES_PASSWORD='use-a-local-development-password'
docker compose -f compose/compose.yml -f compose/compose.apps.yaml up --build
```

Compose starts both applications and local PostgreSQL, Redis, Kafka,
OpenSearch, and Kafka Connect. The app endpoints are `http://localhost:8080`
and `http://localhost:8081`. The local OpenSearch security plugin is disabled;
keep this stack on a trusted development machine. Stop it with the matching
`docker compose ... down` command; named volumes preserve local data.

### Optional local Kubernetes and Argo CD

The local Argo CD configuration is separate from the cloud root and restricted
to the `platform-local` namespace. It deploys only the two service charts,
uses locally built images, and does not install External Secrets, the AWS Load
Balancer Controller, CDC, ingress, or cluster-scoped resources. All local
Applications use manual sync. A local Argo CD installation and cluster are
prerequisites and are **not** created by this repository workflow.

The local service values expect reachable dependency services named
`postgres`, `redis`, `kafka`, and `elasticsearch` in `platform-local`. The
Compose stack's service DNS names and loopback-bound host ports are not
reachable from cluster pods as-is. Do not sync the local service Applications
until those endpoints and the local database Secret are available. This
repository does not yet provide a Kubernetes dependency stack or a Compose to
cluster network bridge; Compose remains the supported full-stack local runtime.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'lineColor': '#8b949e', 'edgeLabelBackground': '#21262d', 'primaryTextColor': '#e6edf3', 'tertiaryTextColor': '#e6edf3', 'clusterBkg': '#161b22', 'clusterBorder': '#30363d', 'titleColor': '#e6edf3'}}}%%
flowchart TD
    prereq(["Separately approved local cluster<br/>and Argo CD installation<br/>not created by this repository"])
    l1["1. Verify kubectl context is the local cluster<br/>not EKS<br/>create platform-local namespace"]
    l2["2. Build and load local images<br/>from sibling service checkouts"]
    l3["3. Create product-catalog-db and<br/>product-search-db Secrets<br/>local-only password, never committed"]
    l4["4. Apply local bootstrap project<br/>and local root Application"]
    l5["5. Manually sync platform-local-root"]
    ready{"Dependency endpoints<br/>postgres, redis, kafka, elasticsearch<br/>and Secrets ready?"}
    svc["Sync an individual service Application<br/>verify sync, health, rollout, events, logs"]
    hold(["Do not sync service Applications yet"])

    prereq --> l1 --> l2 --> l3 --> l4 --> l5 --> ready
    ready -->|"yes"| svc
    ready -->|"no"| hold

    classDef core fill:#1f6feb,stroke:#79c0ff,stroke-width:2px,color:#ffffff
    classDef internal fill:#21262d,stroke:#58a6ff,stroke-width:2px,color:#e6edf3
    classDef gate fill:#21262d,stroke:#d29922,stroke-width:2px,color:#e6edf3
    classDef terminal fill:#21262d,stroke:#8b949e,stroke-width:2px,stroke-dasharray:5 5,color:#e6edf3
    class l1,l2,l3,l4,l5 internal
    class svc core
    class ready gate
    class prereq,hold terminal
```

When a local cluster and Argo CD have been separately approved and prepared:

1. Verify `kubectl config current-context` identifies the intended local
   cluster, not an EKS context. Create the target namespace if needed:

   ```sh
   kubectl create namespace platform-local
   ```

2. Build and load local images from sibling service checkouts:

   ```sh
   docker build -t ghcr.io/jahrough/product-catalog:local ../product-catalog
   docker build -t ghcr.io/jahrough/product-search:local ../product-search
   kind load docker-image --name <local-cluster> \
     ghcr.io/jahrough/product-catalog:local \
     ghcr.io/jahrough/product-search:local
   ```

3. Create `product-catalog-db` and `product-search-db` Secrets in
   `platform-local` with a local-only `password` key. For example, set
   `LOCAL_POSTGRES_PASSWORD` in the shell without echoing it:

   ```sh
   kubectl create secret generic product-catalog-db \
     --namespace platform-local \
     --from-literal=password="${LOCAL_POSTGRES_PASSWORD:?Set LOCAL_POSTGRES_PASSWORD}"
   kubectl create secret generic product-search-db \
     --namespace platform-local \
     --from-literal=password="${LOCAL_POSTGRES_PASSWORD:?Set LOCAL_POSTGRES_PASSWORD}"
   ```

   Do not commit the value or reuse a cloud credential.

4. Apply the restricted bootstrap project and local root only after Argo CD is
   installed:

   ```sh
   kubectl apply -f argocd/bootstrap/local-bootstrap-project.yaml
   kubectl apply -f argocd/bootstrap/local-root-app.yaml
   ```

5. Manually sync `platform-local-root`, then sync an individual service
   Application only after its dependency endpoints and Secret are ready.
   Verify Argo CD sync/health, rollout status, pod events, and logs.

Argo CD reads Git, not a developer's uncommitted working tree. These local
Applications default to `main`; for a feature-branch test, make the
`targetRevision` in the local root and both local service Applications match
the same pushed, reviewed branch. Do not change or apply the cloud root for
local testing. Local cluster creation, Argo CD installation, and sync are
separate operator actions requiring explicit approval.

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

- The source move does not establish the live Argo CD root or workload
  ownership; inspect the cluster before changing the root source.
- The adjacent service build workflows publish tags, but no current image
  digest has been verified here. The configured all-zero image digests
  intentionally prevent a successful pull until reviewed.
- AWS role ARN, Secrets Manager region/keys, actual service endpoints, and
  cluster readiness have not been verified.
- The service repository metadata disagrees on Java versions for catalog and
  search; resolving that is out of this repository's ownership and approved
  scope.
