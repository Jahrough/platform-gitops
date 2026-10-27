#!/usr/bin/env python3
import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = ("dev", "staging", "production")
CONNECT_IMAGE = "ghcr.io/jahrough/platform-infrastructure/kafka-connect"


def valid_digest(value):
    return re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def pins_for(environment):
    values = ROOT / f"charts/spring-service/values/environments/{environment}.yaml"
    pins = {
        "catalog": (
            values,
            "product-catalog",
            re.compile(
                r"(?m)^(\s+product-catalog:)\s*(?:sha256:[0-9a-f]{64}|>-\n\s+sha256:[0-9a-f]{64})$"
            ),
        ),
        "search": (
            values,
            "product-search",
            re.compile(
                r"(?m)^(\s+product-search:)\s*(?:sha256:[0-9a-f]{64}|>-\n\s+sha256:[0-9a-f]{64})$"
            ),
        ),
    }
    if environment == "production":
        pins["connect"] = (
            ROOT / "kubernetes/platform/cdc/kustomization.yaml",
            CONNECT_IMAGE,
            re.compile(
                r"(?m)^(\s+digest:)\s*(?:sha256:[0-9a-f]{64}|>-\n\s+sha256:[0-9a-f]{64})$"
            ),
        )
    return pins


def main():
    parser = argparse.ArgumentParser(
        description="Set immutable image digests in GitOps environment configuration."
    )
    parser.add_argument(
        "--environment",
        choices=ENVIRONMENTS,
        default="production",
        help="Target environment (default: production).",
    )
    for name in ("catalog", "search", "connect"):
        parser.add_argument(
            f"--{name}-digest",
            help="sha256:<64 lowercase hex chars>",
        )
    args = parser.parse_args()
    pins = pins_for(args.environment)

    updates = {}
    for name, (path, image, pattern) in pins.items():
        digest = getattr(args, f"{name}_digest")
        if digest is None:
            parser.error(f"--{name}-digest is required for {args.environment}.")
        if not valid_digest(digest) or digest == "sha256:" + "0" * 64:
            parser.error(f"--{name}-digest must be a real sha256 digest.")
        content = updates.get(path, path.read_text())
        matches = list(pattern.finditer(content))
        if len(matches) != 1:
            parser.error(f"Expected exactly one digest pin for {image} in {path}.")
        match = matches[0]
        indent = len(match.group(1)) - len(match.group(1).lstrip())
        replacement = f"{match.group(1)} >-\n{' ' * (indent + 2)}{digest}"
        updates[path] = pattern.sub(lambda _: replacement, content)

    if args.environment != "production" and args.connect_digest:
        parser.error("--connect-digest is only supported for production.")

    for path, content in updates.items():
        path.write_text(content)
    for name, (_, image, _) in pins.items():
        print(f"Pinned {image} to {getattr(args, f'{name}_digest')}")
    print(f"Review and commit the immutable {args.environment} image pins.")


if __name__ == "__main__":
    main()
