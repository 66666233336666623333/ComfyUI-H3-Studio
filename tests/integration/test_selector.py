"""Selection boundaries, native file loading and downstream empty-slot behavior."""

import json
import os
from pathlib import Path
import tempfile
import unittest
import wave

from PIL import Image

from test_node import Clip, Node as Guard, VAE
import sys

selector = sys.modules["h3_studio_test.reference.selector"]
Node = selector.H3StudioReferenceLoader


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(selector.folder_paths.get_input_directory()).resolve()
        cls.temporary = tempfile.TemporaryDirectory(prefix="h3_selector_test_", dir=cls.root)
        cls.folder = Path(cls.temporary.name).resolve()
        assert cls.folder.is_relative_to(cls.root)
        Image.new("RGB", (32, 32), (20, 100, 150)).save(cls.folder / "still.png")
        with wave.open(str(cls.folder / "tone.wav"), "wb") as stream:
            stream.setparams((1, 2, 32000, 0, "NONE", "not compressed"))
            stream.writeframes(bytes(2 * 32000 * 2))
        import av
        import numpy as np
        with av.open(str(cls.folder / "clip.mkv"), "w") as container:
            stream = container.add_stream("ffv1", rate=24)
            stream.width = stream.height = 32
            stream.pix_fmt = "yuv420p"
            for _ in range(48):
                frame = av.VideoFrame.from_ndarray(np.full((32, 32, 3), 70, dtype=np.uint8), format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
            for packet in stream.encode():
                container.mux(packet)

    @classmethod
    def tearDownClass(cls):
        # The test created this exact folder inside ComfyUI input.
        assert cls.folder.is_relative_to(cls.root)
        cls.temporary.cleanup()

    def entry(self, name, enabled=True):
        return {"path": (self.folder / name).relative_to(self.root).as_posix(), "enabled": enabled}

    def test_schema_order_has_fifteen_references_boolean_and_report(self):
        schema = Node.define_schema()
        names = [value.display_name for value in schema.outputs]
        self.assertEqual(names, [f"{kind}_{i}" for kind, count in selector.PORTS.items()
                                 for i in range(1, count + 1)] + ["use_video_audio", "selection_report"])

    def test_native_loaders_and_sparse_slots_feed_guard(self):
        state = {"image": [None] * 8 + [self.entry("still.png")],
                 "audio": [None, None, self.entry("tone.wav")],
                 "video": [None, self.entry("clip.mkv"), self.entry("missing.mkv", False)]}
        manifest = json.dumps(state)
        self.assertIs(Node.validate_inputs(manifest), True)
        result = Node.execute(manifest, False)
        self.assertEqual(result[8].shape, (1, 32, 32, 3))
        self.assertEqual(result[11]["waveform"].shape[-1], 64000)
        self.assertAlmostEqual(float(result[13].get_duration()), 2)
        self.assertIsNone(result[14])
        self.assertIs(result[15], False)
        self.assertEqual(json.loads(result[16])["enabled_files"], 3)
        refs = {f"{kind}_{i + 1}": result[offset + i]
                for kind, count, offset in (("image", 9, 0), ("audio", 3, 9), ("video", 3, 12))
                for i in range(count)}
        guarded = Guard.execute(clip=Clip(), vae=VAE(), audio_vae=VAE(), prompt="test",
                                width=32, height=32, length=5, use_video_audio=result[15], **refs)
        self.assertEqual(json.loads(guarded[2])["files"], 3)

    def test_disabled_missing_files_are_not_read(self):
        manifest = json.dumps({"image": [self.entry("missing.png", False)]})
        self.assertIs(Node.validate_inputs(manifest), True)
        self.assertEqual(Node.fingerprint_inputs(manifest, True)[2], [])
        result = Node.execute(manifest, True)
        self.assertTrue(all(result[i] is None for i in range(15)))
        self.assertIs(result[15], True)

    def test_total_limit_counts_only_enabled_and_keeps_slots(self):
        state = {kind: [self.entry({"image": "still.png", "audio": "tone.wav", "video": "clip.mkv"}[kind])
                        for _ in range(count)] for kind, count in selector.PORTS.items()}
        self.assertIn("15", Node.validate_inputs(json.dumps(state)))
        for entry in state["video"]:
            entry["enabled"] = False
        self.assertIs(Node.validate_inputs(json.dumps(state)), True)
        self.assertEqual(len(selector.parse_selection(json.dumps(state))["video"]), 3)

    def test_invalid_manifest_and_capacity_fail(self):
        for value in ("no json", "[]", '{"other":[]}', '{"image":[{}]}',
                      '{"image":[{"path":"x","enabled":1}]}',
                      json.dumps({"image": [None] * 10})):
            with self.subTest(value=value):
                self.assertIsInstance(Node.validate_inputs(value), str)

    def test_paths_cannot_escape_input_or_override_type(self):
        for path in ("../outside.png", "C:/outside.png", "/outside.png", "still.png [output]",
                     self.entry("tone.wav")["path"], "missing.png"):
            with self.subTest(path=path):
                self.assertIsInstance(Node.validate_inputs(json.dumps({"image": [{"path": path}]})), str)

    def test_fingerprint_tracks_file_changes_and_boolean(self):
        manifest = json.dumps({"image": [self.entry("still.png")]})
        first = Node.fingerprint_inputs(manifest, False)
        self.assertNotEqual(first, Node.fingerprint_inputs(manifest, True))
        path = self.folder / "still.png"
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
        self.assertNotEqual(first, Node.fingerprint_inputs(manifest, False))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
