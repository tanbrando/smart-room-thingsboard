"""Unit tests for configuration loading and validation."""
from __future__ import annotations

import unittest
from pathlib import Path

from config import ConfigError, ROOT, load_config


class TestConfig(unittest.TestCase):
    def test_load_example_config(self):
        example_path = ROOT.parent / ".env.example" if ROOT.name == "tests" else ROOT / ".env.example"
        self.assertTrue(example_path.is_file(), ".env.example must exist in the root folder")

        cfg = load_config(example_path)
        self.assertEqual(cfg.tb_host, "eu.thingsboard.cloud")
        self.assertEqual(cfg.tb_port, 1883)
        self.assertEqual(cfg.dht_pin, 4)
        self.assertEqual(cfg.led_pin, 17)
        self.assertEqual(cfg.fan_in1, 27)
        self.assertEqual(cfg.fan_hysteresis, 1.0)
        self.assertEqual(cfg.default_threshold, 30.0)

    def test_validation_fails_when_tokens_missing(self):
        example_path = ROOT.parent / ".env.example" if ROOT.name == "tests" else ROOT / ".env.example"
        cfg = load_config(example_path)
        with self.assertRaises(ConfigError) as ctx:
            cfg.validate()
        self.assertIn("Missing required access token", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

