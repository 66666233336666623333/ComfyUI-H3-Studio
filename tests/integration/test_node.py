"""Boundary, timing and encoder-gate tests; no model weights are loaded."""

import importlib.util
import json
from pathlib import Path
import sys
from fractions import Fraction
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from bootstrap import package
import torch
node_module = sys.modules["h3_studio_test.reference.conditioning"]
validation = sys.modules["h3_studio_test.reference.validation"]
Node = node_module.H3StudioReferenceConditioning


def audio(seconds, rate=32000):
    return {"waveform": torch.zeros(1, 1, round(seconds * rate)), "sample_rate": rate}


class Video:
    def __init__(self, seconds=2, fps=24, soundtrack=None, corrupt=False):
        self.seconds, self.fps = seconds, Fraction(fps)
        self.frames = (torch.arange(round(seconds * fps), dtype=torch.float32)
                       / max(round(seconds * fps), 1)).view(-1, 1, 1, 1)
        self.frames = self.frames.expand(-1, 32, 32, 3)
        self.soundtrack, self.corrupt = soundtrack, corrupt
        self.decode_calls = 0

    def get_duration(self):
        return self.seconds

    def get_frame_rate(self):
        return self.fps

    def get_components(self):
        self.decode_calls += 1
        frames = self.frames[:0] if self.corrupt else self.frames
        return SimpleNamespace(images=frames, audio=self.soundtrack, frame_rate=self.fps)


class VAE:
    audio_sample_rate = 32000

    def __init__(self):
        self.calls = []

    def encode(self, data):
        self.calls.append(data)
        if data.ndim == 3:
            return torch.zeros(1, 32, 2, round(data.shape[1] / 32000 * 40))
        t = 1 if data.shape[0] == 1 else node_module.h3.video_latent_t(data.shape[0])
        return torch.zeros(1, 24, t, data.shape[1] // 16, data.shape[2] // 16)


class Clip:
    def __init__(self):
        self.calls = []

    def tokenize(self, prompt, minimax_ref_items):
        self.calls.append(minimax_ref_items)
        return "tokens"

    def encode_from_tokens_scheduled(self, tokens):
        return [[torch.zeros(1, 1, 1), {}]]


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.image = torch.zeros(1, 32, 32, 3)

    def run_node(self, **refs):
        clip, vae, audio_vae = Clip(), VAE(), VAE()
        result = Node.execute(clip=clip, vae=vae, audio_vae=audio_vae,
                              prompt="test", width=32, height=32, length=5, **refs)
        return result, clip, vae, audio_vae

    def test_schema_fixed_sockets_and_lazy_models(self):
        schema = Node.define_schema()
        inputs = {item.id: item for item in schema.inputs}
        for kind, maximum in validation.PORTS.items():
            self.assertEqual(sum(key.startswith(kind + "_") for key in inputs
                                 if key != "audio_vae"), maximum)
        for key in ("clip", "vae", "audio_vae"):
            self.assertTrue(inputs[key].lazy)

    def test_nine_images_are_encoded(self):
        result, clip, vae, _ = self.run_node(**{f"image_{i}": self.image for i in range(1, 10)})
        refs = result[0][0][1]["minimax_refs"]
        self.assertEqual(len(refs), 9)
        self.assertEqual(len(vae.calls), 9)
        self.assertEqual(len(clip.calls[0]), 9)
        self.assertEqual(json.loads(result[2])["labels"]["image_9"], "<Picture 9>")

    def test_all_three_video_and_audio_ports_work(self):
        refs = {f"video_{i}": Video(2) for i in range(1, 4)}
        refs.update({f"audio_{i}": audio(2) for i in range(1, 4)})
        result, _, vae, avae = self.run_node(**refs)
        self.assertEqual(len(vae.calls), 3)
        self.assertEqual(len(avae.calls), 3)
        self.assertEqual(len(result[0][0][1]["minimax_refs"]), 6)

    def test_twelve_mixed_files_pass(self):
        refs = {f"image_{i}": self.image for i in range(1, 10)}
        refs.update(video_1=Video(2), audio_1=audio(2), audio_2=audio(2))
        self.assertEqual(validation.validate_references(refs)[2]["files"], 12)

    def test_thirteen_files_fail_before_video_decode_or_encoder(self):
        refs = {f"image_{i}": self.image for i in range(1, 10)}
        video = Video(2)
        refs.update(video_1=video, audio_1=audio(2), audio_2=audio(2), audio_3=audio(2))
        clip, vae = Mock(), Mock()
        with self.assertRaisesRegex(ValueError, "13.*12"):
            Node.execute(clip=clip, vae=vae, prompt="", width=32, height=32, length=5, **refs)
        self.assertEqual(video.decode_calls, 0)
        clip.tokenize.assert_not_called()
        vae.encode.assert_not_called()

    def test_duration_boundaries(self):
        for kind, factory in (("audio", audio), ("video", Video)):
            for seconds in (2, 15):
                validation.validate_references({kind + "_1": factory(seconds)})
            for seconds in (1.999, 15.001):
                with self.subTest(kind=kind, seconds=seconds):
                    with self.assertRaisesRegex(ValueError, "2–15"):
                        validation.validate_references({kind + "_1": factory(seconds)})

    def test_single_audio_sample_over_limit_fails(self):
        value = {"waveform": torch.zeros(1, 1, 480001), "sample_rate": 32000}
        with self.assertRaisesRegex(ValueError, "2–15"):
            validation.validate_references({"audio_1": value})

    def test_each_modality_total_is_independent(self):
        refs = {"video_1": Video(5), "video_2": Video(5), "video_3": Video(5),
                "audio_1": audio(5), "audio_2": audio(5), "audio_3": audio(5)}
        report = validation.validate_references(refs)[2]
        self.assertEqual((report["video_seconds"], report["audio_seconds"]), (15, 15))
        for key, value in (("video_3", Video(5.01)), ("audio_3", audio(5.01))):
            with self.assertRaisesRegex(ValueError, "总时长"):
                validation.validate_references(refs | {key: value})

    def test_image_batches_and_extra_sockets_fail(self):
        for refs in ({"image_1": self.image.expand(2, -1, -1, -1)}, {"image_10": self.image}):
            with self.assertRaises(ValueError):
                validation.validate_references(refs)

    def test_invalid_reference_blocks_lazy_model_loading(self):
        with self.assertRaisesRegex(ValueError, "2–15"):
            Node.check_lazy_status(clip=None, vae=None, audio_vae=None, video_1=Video(1))
        required = Node.check_lazy_status(clip=None, vae=None, audio_vae=None,
                                         image_1=self.image, audio_1=audio(2))
        self.assertEqual(set(required), {"clip", "vae", "audio_vae"})

    def test_corrupt_video_blocks_every_encoder(self):
        clip, vae, avae = Mock(), Mock(), Mock()
        with self.assertRaisesRegex(ValueError, "无法解码"):
            Node.execute(clip=clip, vae=vae, audio_vae=avae, prompt="", width=32, height=32,
                         length=5, image_1=self.image, video_1=Video(2, corrupt=True))
        clip.tokenize.assert_not_called()
        vae.encode.assert_not_called()
        avae.encode.assert_not_called()

    def test_downsample_and_repeat_keep_timing(self):
        for fps in (12, 24, 30, 60):
            video = Video(2, fps)
            frames, content, padding = node_module.resample_reference_frames(video.frames, video.fps, Fraction(2))
            expected = torch.tensor([min((i * fps) // 24, round(2 * fps) - 1) / round(2 * fps)
                                     for i in range(48)])
            self.assertTrue(torch.equal(frames[:48, 0, 0, 0], expected))
            self.assertEqual((content, padding, len(frames)), (48, 8, 56))
            self.assertTrue(torch.all(frames[48:] == frames[47]))

    def test_long_reference_is_not_cropped_to_output(self):
        result, _, vae, _ = self.run_node(video_1=Video(10, 30))
        self.assertEqual(len(vae.calls[0]), 243)
        # Native Lanczos resizing quantizes through an 8-bit image.
        self.assertAlmostEqual(vae.calls[0][239, 0, 0, 0].item(), 298 / 300, delta=1 / 255)
        self.assertEqual(result[1]["samples"].tensors[0].shape[2], node_module.h3.video_latent_t(5))
        detail = json.loads(result[2])["videos_detail"][0]
        self.assertEqual((detail["content_frames_24fps"], detail["tail_padding_frames"]), (240, 3))

    def test_video_soundtrack_is_one_file_and_labels_are_explicit(self):
        result, _, _, avae = self.run_node(video_2=Video(2, soundtrack=audio(2)), audio_3=audio(2))
        report = json.loads(result[2])
        self.assertEqual(report["files"], 2)
        self.assertEqual((report["audios"], report["audio_seconds"]), (2, 4))
        self.assertEqual(report["labels"], {"video_2.audio": "<Audio 1>",
                                           "video_2": "<Video 1>", "audio_3": "<Audio 2>"})
        self.assertEqual(len(avae.calls), 2)

    def test_combined_audio_count_blocks_lazy_models(self):
        refs = {"video_1": Video(2, soundtrack=audio(2)),
                "audio_1": audio(2), "audio_2": audio(2), "audio_3": audio(2)}
        with self.assertRaisesRegex(ValueError, "合并音频超限：共 4 段、8 秒") as error:
            Node.check_lazy_status(clip=None, vae=None, audio_vae=None, **refs)
        self.assertIn("video_1.audio=2秒", str(error.exception))
        self.assertIn("audio_3=2秒", str(error.exception))

    def test_combined_audio_duration_blocks_lazy_models(self):
        with self.assertRaisesRegex(ValueError, "共 2 段、16 秒"):
            Node.check_lazy_status(clip=None, vae=None, audio_vae=None,
                                   video_1=Video(8, soundtrack=audio(8)), audio_1=audio(8))

    def test_combined_audio_rechecked_before_any_encoder(self):
        for refs in (
            {"video_1": Video(2, soundtrack=audio(2)),
             "audio_1": audio(2), "audio_2": audio(2), "audio_3": audio(2)},
            {"video_1": Video(8, soundtrack=audio(8)), "audio_1": audio(8)},
        ):
            clip, vae, avae = Mock(), Mock(), Mock()
            with self.assertRaisesRegex(ValueError, "合并音频超限"):
                Node.execute(clip=clip, vae=vae, audio_vae=avae, prompt="", width=32,
                             height=32, length=5, image_1=self.image, **refs)
            clip.tokenize.assert_not_called()
            vae.encode.assert_not_called()
            avae.encode.assert_not_called()

    def test_three_combined_tracks_at_fifteen_seconds_pass(self):
        result, clip, _, avae = self.run_node(
            video_1=Video(5, soundtrack=audio(5)), video_2=Video(5, soundtrack=audio(5)),
            audio_3=audio(5))
        report = json.loads(result[2])
        self.assertEqual((report["audios"], report["audio_seconds"]), (3, 15))
        self.assertEqual((report["standalone_audios"], report["video_audio_tracks"]), (1, 2))
        self.assertEqual(report["files"], 3)
        self.assertEqual(len(avae.calls), 3)
        self.assertEqual(sum(item["type"] == "audio" for item in clip.calls[0]), 3)

    def test_disabled_video_audio_does_not_consume_audio_budget(self):
        refs = {f"video_{i}": Video(5, soundtrack=audio(5)) for i in range(1, 4)}
        refs.update({f"audio_{i}": audio(5) for i in range(1, 4)})
        result, _, _, avae = self.run_node(use_video_audio=False, **refs)
        report = json.loads(result[2])
        self.assertEqual((report["audios"], report["audio_seconds"]), (3, 15))
        self.assertEqual(report["video_audio_tracks"], 0)
        self.assertEqual(len(avae.calls), 3)
        self.assertFalse(any(key.endswith(".audio") for key in report["labels"]))

    def test_embedded_audio_must_meet_clip_duration_limits(self):
        for seconds in (1.999, 15.001):
            with self.assertRaises(ValueError):
                self.run_node(video_1=Video(2, soundtrack=audio(seconds)))

    def test_one_audio_sample_over_combined_limit_fails(self):
        extra_sample = {"waveform": torch.zeros(1, 1, 160001), "sample_rate": 32000}
        with self.assertRaisesRegex(ValueError, "合并音频超限"):
            self.run_node(video_1=Video(5, soundtrack=audio(5)),
                          video_2=Video(5, soundtrack=audio(5)), audio_1=extra_sample)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
