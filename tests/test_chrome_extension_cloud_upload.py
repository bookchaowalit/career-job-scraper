import hashlib
import base64
import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
EXTENSION = ROOT / "chrome-extension"
# Derived from manifest "key"; OAuth redirect URIs registered with each
# provider are https://<this id>.chromiumapp.org/, so it must not drift.
EXPECTED_EXTENSION_ID = "gbipaflofmmmglinopjefeffngikmggb"


class ChromeExtensionCloudUploadTests(unittest.TestCase):
    def test_manifest_key_pins_the_extension_id(self):
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(base64.b64decode(manifest["key"])).hexdigest()[:32]
        extension_id = digest.translate(
            str.maketrans("0123456789abcdef", "abcdefghijklmnop")
        )
        self.assertEqual(extension_id, EXPECTED_EXTENSION_ID)

    def test_manifest_declares_only_the_cloud_hosts_it_uses(self):
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("identity", manifest["permissions"])
        self.assertEqual(manifest["options_ui"]["page"], "options.html")
        for host in (
            "https://www.googleapis.com/*",
            "https://api.dropboxapi.com/*",
            "https://content.dropboxapi.com/*",
            "https://graph.microsoft.com/*",
        ):
            self.assertIn(host, manifest["host_permissions"])

    def test_cloud_upload_is_off_unless_enabled(self):
        cloud_js = (EXTENSION / "cloud.js").read_text(encoding="utf-8")
        self.assertIn("autoUpload: false", cloud_js)
        self.assertIn("settings.autoUpload = input.autoUpload === true", cloud_js)
        # Tokens stay in memory-only session storage.
        self.assertIn("chromeApi.storage.session", cloud_js)

    def test_background_uploads_every_csv_export(self):
        background = (EXTENSION / "background.js").read_text(encoding="utf-8")
        self.assertIn("importScripts('cloud.js')", background)
        self.assertEqual(background.count("cloud.uploadExport("), 2)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_cloud_js_offline_suite(self):
        tests = sorted(str(path) for path in (ROOT / "tests" / "js").glob("*.test.js"))
        result = subprocess.run(
            ["node", "--test", *tests],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:]
        )
