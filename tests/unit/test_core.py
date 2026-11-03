import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("h3_core", ROOT / "core.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class CoreTests(unittest.TestCase):
    def test_text_encodings(self):
        text = "中文镜头与光线。\n# Prompt"
        for encoding in core.ENCODINGS[1:]:
            source = "A calm lake." if encoding == "ascii" else text
            with self.subTest(encoding=encoding):
                self.assertEqual(core.decode_text(source.encode(encoding), encoding)[0], source)

    def test_auto_detection(self):
        text = "中文镜头与光线"
        for encoding in ("utf-8", "utf-8-sig", "utf-16", "utf-32", "gb2312", "gbk", "gb18030"):
            self.assertEqual(core.decode_text(text.encode(encoding))[0], text)
        for data, encoding in ((b"\xff", "utf-8"), (b"a\0b\0", "自动")):
            with self.assertRaises(ValueError): core.decode_text(data, encoding)

    def test_file_size_boundary(self):
        self.assertEqual(len(core.decode_text(b"a" * core.MAX_TEXT_BYTES)[0]), core.MAX_TEXT_BYTES)
        with self.assertRaises(ValueError): core.decode_text(b"a" * (core.MAX_TEXT_BYTES + 1))

    def test_input_and_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "prompt.md").write_text("A calm lake.", encoding="utf-8")
            self.assertEqual(core.input_text_path(root, "prompt.md"), root / "prompt.md")
            for bad in ("../prompt.md", "missing.txt", "prompt.py"):
                with self.assertRaises(ValueError): core.input_text_path(root, bad)
            self.assertEqual(core.resolve_output_dir(root, ""), root)
            self.assertEqual(core.resolve_output_dir(root, "videos"), root / "videos")
            with self.assertRaises(ValueError): core.resolve_output_dir(root, "../outside")

    def test_filename_prefix(self):
        for bad in ("", "../x", "a/b", "CON", "x:bad"):
            with self.assertRaises(ValueError): core.safe_prefix(bad)
        self.assertEqual(core.safe_prefix("H3_Studio"), "H3_Studio")

    def test_native_frame_bins(self):
        self.assertEqual(core.duration_frames(3), (72, 73))
        self.assertEqual(core.duration_frames(12), (288, 294))
        self.assertEqual(core.duration_frames(15), (360, 362))
        for seconds in range(3, 16):
            target, frames = core.duration_frames(seconds)
            self.assertEqual(frames % 17, 5)
            self.assertTrue(target <= frames < target + 17)

    def test_example_has_portable_defaults(self):
        workflow = json.loads((ROOT / "examples/H3_Studio.json").read_text(encoding="utf-8"))
        api = json.loads((ROOT / "examples/H3_Studio.api.json").read_text(encoding="utf-8"))
        by_type = {node["type"]: node for node in workflow["nodes"]}
        refs = by_type["H3StudioReferences"]["widgets_values_named"]
        self.assertEqual(json.loads(refs["manifest"]), {"image": [], "audio": [], "video": []})
        self.assertEqual(by_type["H3StudioSaveVideo"]["widgets_values_named"]["output_directory"], "")
        self.assertEqual(by_type["H3StudioPrompt"]["widgets_values_named"]["text_file"], "")
        engine = by_type["H3StudioEngine"]["widgets_values_named"]
        self.assertEqual(engine["seed"], 0)
        self.assertIn("fasth3", engine["fasth3_model"].lower())
        self.assertNotIn("fasth3", engine["minimax_model"].lower())
        self.assertIn(engine["resolution"], core.PRESETS)
        for node in workflow["nodes"]:
            values = node.get("widgets_values_named", {})
            if values:
                self.assertEqual(node["widgets_values"], list(values.values()))
                for key, value in values.items():
                    if key != "control_after_generate":
                        self.assertEqual(api[str(node["id"])]["inputs"][key], value)

if __name__ == "__main__": unittest.main()
