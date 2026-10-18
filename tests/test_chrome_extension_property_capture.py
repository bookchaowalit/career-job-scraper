import json
import unittest
from pathlib import Path


EXTENSION = Path(__file__).parents[1] / "chrome-extension"


class ChromeExtensionPropertyCaptureTests(unittest.TestCase):
    def test_manifest_declares_local_property_export_capability(self):
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "1.3.0")
        self.assertIn("downloads", manifest["permissions"])
        self.assertIn("property", manifest["description"].lower())

    def test_manifest_icons_exist(self):
        # Chrome refuses to load an unpacked extension whose icons are missing.
        manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
        icon_paths = set(manifest["icons"].values()) | set(manifest["action"]["default_icon"].values())
        for icon in icon_paths:
            self.assertTrue((EXTENSION / icon).is_file(), icon)

    def test_popup_and_scripts_wire_property_capture_actions(self):
        popup = (EXTENSION / "popup.html").read_text(encoding="utf-8")
        popup_js = (EXTENSION / "popup.js").read_text(encoding="utf-8")
        content_js = (EXTENSION / "content.js").read_text(encoding="utf-8")
        background_js = (EXTENSION / "background.js").read_text(encoding="utf-8")
        for marker in (
            "propertyModeBtn",
            "savePropertyBtn",
            "exportPropertiesBtn",
            "propertyBedrooms",
            "propertyBathrooms",
            "propertyAreaSqm",
            "Capture public property lead",
        ):
            self.assertIn(marker, popup)
        for marker in ("extractProperty", "saveProperty", "exportProperties"):
            self.assertIn(marker, popup_js)
            self.assertIn(marker, content_js if marker == "extractProperty" else background_js)

    def test_extension_does_not_add_an_outbound_url_fetch_for_property_capture(self):
        content_js = (EXTENSION / "content.js").read_text(encoding="utf-8")
        property_start = content_js.index("function extractPropertyFromPage")
        property_code = content_js[property_start : content_js.index("// Add floating save button", property_start)]
        self.assertNotIn("fetch(", property_code)
        self.assertNotIn("XMLHttpRequest", property_code)

    def test_group_capture_wires_post_selection_and_visibility(self):
        popup = (EXTENSION / "popup.html").read_text(encoding="utf-8")
        popup_js = (EXTENSION / "popup.js").read_text(encoding="utf-8")
        content_js = (EXTENSION / "content.js").read_text(encoding="utf-8")
        background_js = (EXTENSION / "background.js").read_text(encoding="utf-8")
        for marker in (
            "facebookGroupModeBtn",
            "facebookGroupPosts",
            "facebookGroupVisibility",
            "captureNextFacebookGroupPageBtn",
            "clearFacebookGroupCaptureBtn",
            "exportFacebookGroupCaptureBtn",
            "saveFacebookGroupPostsBtn",
            "exportFacebookGroupPostsBtn",
            "Capture Facebook Group posts",
        ):
            self.assertIn(marker, popup)
        for marker in (
            "extractFacebookGroupPosts",
            "saveFacebookGroupPosts",
            "exportFacebookGroupPosts",
            "mergeFacebookGroupPosts",
            "canonicalFacebookGroupPostUrl",
            "persistFacebookGroupCaptureDraft",
            "exportFacebookGroupCapture",
            "facebookGroupCaptureDraft",
            "FACEBOOK_GROUP_DRAFT_TTL_MS",
            "visibility",
            "post_url",
        ):
            self.assertIn(marker, popup_js)
            self.assertIn(marker, content_js if marker == "extractFacebookGroupPosts" else background_js if marker.startswith("save") or marker.startswith("export") else popup_js)
        self.assertIn("isBetterFacebookGroupPost", background_js)
        self.assertIn("exportFacebookGroupCapture", background_js)
        self.assertIn("facebook_group_current_capture.csv", background_js)
        self.assertIn("parsed.username", background_js)

    def test_group_extraction_reads_articles_without_network(self):
        content_js = (EXTENSION / "content.js").read_text(encoding="utf-8")
        group_start = content_js.index("function extractFacebookGroupPosts")
        group_code = content_js[group_start : content_js.index("// Add floating save button", group_start)]
        self.assertIn("[role=\"article\"]", group_code)
        self.assertIn("text_complete", group_code)
        self.assertIn("capture_method", group_code)
        self.assertIn("parsed.username", group_code)
        self.assertNotIn("fetch(", group_code)
        self.assertNotIn("XMLHttpRequest", group_code)


if __name__ == "__main__":
    unittest.main()
