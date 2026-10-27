#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_VALUES = ROOT / "charts/spring-service/values/environments/production.yaml"


def update_field(block, field, value):
    pattern = re.compile(rf"(?m)^  {re.escape(field)}:.*$")
    replacement, count = pattern.subn(f"  {field}: {value}", block)
    if count != 1:
        raise ValueError(f"Expected exactly one ingress.{field} setting.")
    return replacement


def main():
    parser = argparse.ArgumentParser(
        description="Enable production ALB ingress in GitOps values."
    )
    parser.add_argument("--domain", required=True, help="DNS zone, e.g. example.com")
    parser.add_argument("--certificate-arn", required=True, help="Regional ACM certificate ARN")
    parser.add_argument(
        "--scheme",
        choices=("internet-facing", "internal"),
        default="internet-facing",
        help="ALB exposure scheme (default: internet-facing)",
    )
    parser.add_argument("--region", required=True, help="AWS region containing the certificate")
    args = parser.parse_args()

    if not re.fullmatch(
        r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}",
        args.domain,
    ):
        parser.error("--domain must be a valid DNS zone name without a hostname prefix.")
    arn_pattern = (
        rf"^arn:aws(?:-[a-z0-9]+)*:acm:{re.escape(args.region)}:"
        r"\d{12}:certificate/[0-9a-fA-F-]{36}$"
    )
    if not re.fullmatch(arn_pattern, args.certificate_arn):
        parser.error("--certificate-arn must identify a certificate in --region.")

    content = PRODUCTION_VALUES.read_text()
    match = re.search(r"(?ms)^ingress:\n((?:^  .*\n|^\n)*)", content)
    if match is None:
        parser.error("Could not locate ingress settings in production values.")
    block = "ingress:\n" + match.group(1)
    try:
        block = update_field(block, "enabled", "true")
        block = update_field(block, "scheme", args.scheme)
        block = update_field(block, "domain", json.dumps(args.domain))
        block = update_field(block, "certificateArn", json.dumps(args.certificate_arn))
    except ValueError as error:
        parser.error(str(error))

    PRODUCTION_VALUES.write_text(content[: match.start()] + block + content[match.end() :])
    print(f"Enabled production ingress for {args.domain} ({args.scheme}).")
    print("Review and commit the GitOps values change; create DNS records after provisioning.")


if __name__ == "__main__":
    main()
