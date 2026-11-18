"""Offline release-control checks for Docker and GHCR deployment."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ContainerDeploymentTests(unittest.TestCase):
    def test_sensitive_files_excluded(self):
        ignored = (ROOT / ".dockerignore").read_text()
        for word in (".env", "cases", "data", "private_patent_workspace", "external"):
            self.assertIn(word, ignored)
        dockerfile = (ROOT / "Dockerfile").read_text()
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("pandoc", dockerfile)
        self.assertIn("COPY src/ ./src/", dockerfile)
        self.assertNotIn("COPY . ", dockerfile)

    def test_loopback_and_bind_mount(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("network_mode: host", compose)
        self.assertIn("127.0.0.1", compose)
        self.assertIn("create_host_path: false", compose)
        self.assertIn("read_only: true", compose)
        self.assertIn("target: /data", compose)
        self.assertNotIn("ports:", compose)

    def test_release_gate(self):
        workflow = (ROOT / ".github/workflows/container.yml").read_text()
        for text in ("packages: write", "needs: verify", "pull_request:", "linux/amd64,linux/arm64", "type=sha,prefix=sha-"):
            self.assertIn(text, workflow)


if __name__ == "__main__":
    unittest.main()
