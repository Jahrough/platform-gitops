import contextlib
import importlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
pin_images = importlib.import_module("set-image-digests")
enable_ingress = importlib.import_module("enable-ingress")


class ImagePinTests(unittest.TestCase):
    def test_replaces_production_and_cdc_pins(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            environments = root / "charts/spring-service/values/environments"
            environments.mkdir(parents=True)
            production = environments / "production.yaml"
            production.write_text(
                "images:\n"
                "  product-catalog: sha256:" + "0" * 64 + "\n"
                "  product-search: sha256:" + "0" * 64 + "\n"
            )
            cdc = root / "kubernetes/platform/cdc/kustomization.yaml"
            cdc.parent.mkdir(parents=True)
            cdc.write_text(
                "images:\n"
                "  - name: ghcr.io/jahrough/platform-infrastructure/kafka-connect\n"
                "    digest: sha256:" + "0" * 64 + "\n"
            )
            pin_images.ROOT = root
            digests = {"catalog": "1" * 64, "search": "2" * 64, "connect": "3" * 64}
            argv = ["set-image-digests.py", "--environment", "production"]
            for name, digest in digests.items():
                argv.extend((f"--{name}-digest", f"sha256:{digest}"))
            with patch.object(sys, "argv", argv):
                pin_images.main()
            self.assertIn("sha256:" + digests["catalog"], production.read_text())
            self.assertIn("sha256:" + digests["search"], production.read_text())
            self.assertIn("sha256:" + digests["connect"], cdc.read_text())

    def test_updates_dev_and_staging_without_requiring_cdc_digest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            environments = root / "charts/spring-service/values/environments"
            environments.mkdir(parents=True)
            pin_images.ROOT = root

            for environment in ("dev", "staging"):
                values = environments / f"{environment}.yaml"
                values.write_text(
                    "images:\n"
                    "  product-catalog: sha256:" + "0" * 64 + "\n"
                    "  product-search: sha256:" + "0" * 64 + "\n"
                )
                with patch.object(
                    sys,
                    "argv",
                    [
                        "set-image-digests.py",
                        "--environment",
                        environment,
                        "--catalog-digest",
                        "sha256:" + "1" * 64,
                        "--search-digest",
                        "sha256:" + "2" * 64,
                    ],
                ):
                    pin_images.main()
                rendered = values.read_text()
                self.assertIn("sha256:" + "1" * 64, rendered)
                self.assertIn("sha256:" + "2" * 64, rendered)

    def test_rejects_connect_digest_for_nonproduction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            values = root / "charts/spring-service/values/environments/staging.yaml"
            values.parent.mkdir(parents=True)
            values.write_text(
                "images:\n"
                "  product-catalog: sha256:" + "0" * 64 + "\n"
                "  product-search: sha256:" + "0" * 64 + "\n"
            )
            pin_images.ROOT = root
            original = values.read_text()
            with patch.object(
                sys,
                "argv",
                [
                    "set-image-digests.py",
                    "--environment",
                    "staging",
                    "--catalog-digest",
                    "sha256:" + "1" * 64,
                    "--search-digest",
                    "sha256:" + "2" * 64,
                    "--connect-digest",
                    "sha256:" + "3" * 64,
                ],
            ), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                pin_images.main()
            self.assertEqual(original, values.read_text())

    def test_requires_connect_digest_for_production(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            values = root / "charts/spring-service/values/environments/production.yaml"
            values.parent.mkdir(parents=True)
            values.write_text(
                "images:\n"
                "  product-catalog: sha256:" + "0" * 64 + "\n"
                "  product-search: sha256:" + "0" * 64 + "\n"
            )
            pin_images.ROOT = root
            with patch.object(
                sys,
                "argv",
                [
                    "set-image-digests.py",
                    "--catalog-digest",
                    "sha256:" + "1" * 64,
                    "--search-digest",
                    "sha256:" + "2" * 64,
                ],
            ), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                pin_images.main()

    def test_rejects_malformed_digest(self):
        with patch.object(
            sys,
            "argv",
            [
                "set-image-digests.py",
                "--catalog-digest",
                "latest",
                "--search-digest",
                "sha256:" + "2" * 64,
            ],
        ), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            pin_images.main()


class EnableIngressTests(unittest.TestCase):
    def test_configures_disabled_ingress_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            values = Path(temp_dir) / "production.yaml"
            values.write_text(
                'ingress:\n'
                '  enabled: false\n'
                '  scheme: internet-facing\n'
                '  domain: ""\n'
                '  certificateArn: ""\n'
            )
            enable_ingress.PRODUCTION_VALUES = values
            with patch.object(
                sys,
                "argv",
                [
                    "enable-ingress.py",
                    "--domain",
                    "example.com",
                    "--certificate-arn",
                    "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000",
                    "--region",
                    "us-east-1",
                    "--scheme",
                    "internal",
                ],
            ):
                enable_ingress.main()
            rendered = values.read_text()
            self.assertIn("  enabled: true", rendered)
            self.assertIn("  scheme: internal", rendered)
            self.assertIn('"example.com"', rendered)
            self.assertIn(
                '"arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000"',
                rendered,
            )

    def test_rejects_certificate_from_another_region_without_editing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            values = Path(temp_dir) / "production.yaml"
            original = (
                'ingress:\n'
                '  enabled: false\n'
                '  scheme: internet-facing\n'
                '  domain: ""\n'
                '  certificateArn: ""\n'
            )
            values.write_text(original)
            enable_ingress.PRODUCTION_VALUES = values
            with patch.object(
                sys,
                "argv",
                [
                    "enable-ingress.py",
                    "--domain",
                    "example.com",
                    "--certificate-arn",
                    "arn:aws:acm:us-east-1:123456789012:certificate/00000000-0000-0000-0000-000000000000",
                    "--region",
                    "us-west-2",
                ],
            ), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                enable_ingress.main()
            self.assertEqual(original, values.read_text())


if __name__ == "__main__":
    unittest.main()
