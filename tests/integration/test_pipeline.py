"""Registration and expanded graph checks. No model loading or sampling."""
import asyncio
import itertools
import json
import unittest
from pathlib import Path

from bootstrap import PACKAGE, package
from h3_studio_test.pipeline import build_pipeline
from h3_studio_test.nodes import H3StudioEngine, H3StudioReferences

class PipelineTests(unittest.TestCase):
    def options(self):
        graph = json.loads((PACKAGE / "examples/H3_Studio.api.json").read_text(encoding="utf-8"))
        return {k: v for k, v in graph["4"]["inputs"].items() if k not in ("prompt", "references", "control")}

    def test_registration_is_self_contained(self):
        extension = asyncio.run(package.comfy_entrypoint())
        classes = asyncio.run(extension.get_node_list())
        ids = [node.define_schema().node_id for node in classes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 7)
        self.assertIn("H3StudioReferenceLoader", ids)
        self.assertIn("H3StudioReferenceConditioning", ids)
        self.assertIs(H3StudioReferences.validate_inputs('{}'), True)
        for cls in classes: self.assertTrue(cls.GET_NODE_INFO_V1())

    def test_eight_feature_combinations(self):
        for fast, fun, lora in itertools.product((False, True), repeat=3):
            options = self.options()
            options.update(enable_fasth3=fast, enable_funcontrol=fun, enable_lora=lora)
            graph, outputs = build_pipeline(options, "A calm lake.", {"manifest": "{}", "use_video_audio": False},
                {"file": "control.mp4", "start_time": 0, "duration": 0}, prefix="test.")
            kinds = [node["class_type"] for node in graph.values()]
            with self.subTest(fast=fast, fun=fun, lora=lora):
                for kind in ("ModelPatchLoader", "RTDETR_detect", "SDPoseKeypointExtractor", "LoadVideo"):
                    self.assertEqual(kind in kinds, fun and not fast)
                self.assertEqual("LoraLoaderModelOnly" in kinds, lora and not fast)
                self.assertEqual("BlockSparseAttention" in kinds, fast)
                self.assertEqual(graph["test.258"]["inputs"]["steps"], 8 if fast or lora else 20)
                self.assertEqual(graph["test.conditioning"]["inputs"]["length"], 124)
                self.assertIn("H3StudioReferenceLoader", kinds)
                self.assertNotIn("MiniMaxH3ReferenceSelector", kinds)
                for node in graph.values():
                    for value in node["inputs"].values():
                        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                            self.assertIn(value[0], graph)
                for output in outputs: self.assertIn(output[0], graph)

    def test_missing_control_fails_before_expansion(self):
        options = self.options()
        options.update(enable_fasth3=False, enable_funcontrol=True)
        with self.assertRaisesRegex(ValueError, "控制视频"):
            build_pipeline(options, "", {"manifest": "{}", "use_video_audio": False}, None)

    def test_builtin_node_ids_are_available(self):
        import nodes
        asyncio.run(nodes.init_builtin_extra_nodes())
        extension = asyncio.run(package.comfy_entrypoint())
        registered = set(nodes.NODE_CLASS_MAPPINGS)
        registered.update(c.define_schema().node_id for c in asyncio.run(extension.get_node_list()))
        for fast in (False, True):
            options = self.options()
            options.update(enable_fasth3=fast, enable_funcontrol=True, enable_lora=True)
            graph, _ = build_pipeline(options, "test", {"manifest": "{}", "use_video_audio": False},
                {"file": "control.mp4", "start_time": 0, "duration": 0}, prefix="builtin.")
            self.assertEqual({n["class_type"] for n in graph.values()} - registered, set())

if __name__ == "__main__": unittest.main()
