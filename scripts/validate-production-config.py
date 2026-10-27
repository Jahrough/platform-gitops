#!/usr/bin/env python3
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILES = (
    ROOT / "argocd/apps/external-secrets.yaml",
    ROOT / "argocd/apps/aws-load-balancer-controller.yaml",
    ROOT / "kubernetes/platform/providers/aws/cluster-secret-store.yaml",
    ROOT / "charts/spring-service/values/environments/production.yaml",
    ROOT / "kubernetes/platform/cdc/platform-cdc-db.external-secret.yaml",
    ROOT / "kubernetes/platform/cdc/platform-runtime-config.external-secret.yaml",
)


def main():
    failures = []
    for path in CONFIG_FILES:
        content = path.read_text()
        if re.search(r"__[A-Z][A-Z0-9_]+__", content):
            failures.append(f"Unresolved Terraform configuration token in {path.relative_to(ROOT)}")
        if "REPLACE_ME" in content:
            failures.append(f"Unresolved deployment placeholder in {path.relative_to(ROOT)}")

    image_files = (
        ROOT / "charts/spring-service/values/environments/production.yaml",
        ROOT / "kubernetes/platform/cdc/kustomization.yaml",
    )
    for path in image_files:
        if re.search(
            r"(?m)^\s+[\w.-]+:\s*(?:sha256:0{64}|>-\n\s+sha256:0{64})\s*$",
            path.read_text(),
        ):
            failures.append(f"Replace the fail-closed image digest in {path.relative_to(ROOT)}")
        if re.search(
            r"(?m)^\s+digest:\s*(?:sha256:0{64}|>-\n\s+sha256:0{64})\s*$",
            path.read_text(),
        ):
            failures.append(f"Replace the fail-closed image digest in {path.relative_to(ROOT)}")

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Production GitOps configuration has no unresolved tokens or placeholder image digests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
