from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from suno_mastering import cli
from suno_mastering.config import StemConfig
from suno_mastering.io.stem_separation import clear_model_cache, split_stems


SOURCES = ("drums", "bass", "other", "vocals")


class FakeTensor:
    def __init__(self, value: np.ndarray) -> None:
        self.value = value

    def float(self) -> FakeTensor:
        return self

    def unsqueeze(self, _axis: int) -> FakeTensor:
        return self


class FakeTorch:
    __version__ = "fake-torch-1"
    cuda = SimpleNamespace(is_available=lambda: False)
    backends = SimpleNamespace(
        mps=SimpleNamespace(is_available=lambda: False),
        cudnn=SimpleNamespace(deterministic=True, benchmark=False),
    )

    @staticmethod
    def from_numpy(value: np.ndarray) -> FakeTensor:
        return FakeTensor(value)

    @staticmethod
    def no_grad():
        return nullcontext()

    @staticmethod
    def initial_seed() -> int:
        return 1234

    @staticmethod
    def are_deterministic_algorithms_enabled() -> bool:
        return True


class FakeModel:
    sources = SOURCES
    segment = 7.5

    def to(self, _device: str) -> FakeModel:
        return self


@pytest.fixture(autouse=True)
def isolated_model_cache():
    clear_model_cache()
    yield
    clear_model_cache()


def _valid_output(samples: int) -> np.ndarray:
    output = np.zeros((1, len(SOURCES), 2, samples), dtype=np.float32)
    for index in range(len(SOURCES)):
        output[0, index] = (index + 1) * 0.01
    return output


def test_tc020_05_active_profile_pass_through() -> None:
    audio = np.full((32, 2), 0.2, dtype=np.float64)
    config = StemConfig(
        enabled=True,
        # Explicit four-stem model: this test is scoped to profile pass-through
        # (the product default is now htdemucs_6s, which the 4-source FakeModel
        # does not satisfy).
        model_name="htdemucs",
        shifts=3,
        overlap=0.4,
        segment_seconds=9.25,
        profile_version="qa-profile-v3",
    )
    calls: list[dict] = []

    def apply_model(model, tensor, **kwargs):
        calls.append({"model": model, "tensor": tensor, **kwargs})
        return _valid_output(audio.shape[0])

    bundle = split_stems(
        audio,
        48_000,
        stem_config=config,
        torch_module=FakeTorch(),
        model_loader=lambda _name: FakeModel(),
        apply_model_fn=apply_model,
    )

    assert len(calls) == 1
    assert {key: value for key, value in calls[0].items() if key not in {"model", "tensor"}} == {
        "device": "cpu",
        "shifts": 3,
        "overlap": 0.4,
        "segment": 9.25,
        "split": True,
        "progress": False,
    }
    assert bundle.runtime_metadata["profile"] == {
        "version": "qa-profile-v3",
        "shifts": 3,
        "overlap": 0.4,
        "segment_seconds": 9.25,
    }
    assert bundle.runtime_metadata["effective_model_segment"] == 7.5


@pytest.mark.parametrize(
    "overrides",
    [
        {"shifts": True},
        {"shifts": 0},
        {"overlap": float("nan")},
        {"overlap": 1.0},
        {"segment_seconds": 0.0},
        {"segment_seconds": float("inf")},
        {"profile_version": "  "},
    ],
)
def test_tc020_06_invalid_profile_fails_before_loading(overrides: dict) -> None:
    loader_calls = 0

    def loader(_name: str):
        nonlocal loader_calls
        loader_calls += 1
        raise AssertionError("model loader must not run")

    with pytest.raises(ValueError):
        config = StemConfig(**overrides)
        split_stems(
            np.zeros((8, 2), dtype=np.float64),
            44_100,
            stem_config=config,
            torch_module=FakeTorch(),
            model_loader=loader,
            apply_model_fn=lambda *_args, **_kwargs: None,
        )

    assert loader_calls == 0


def test_tc020_07_nested_json_cli_precedence_and_version_requirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "input.wav"
    original_bytes = b"read-only-input-sentinel"
    input_path.write_bytes(original_bytes)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "stem_config": {
                    "enabled": True,
                    "model_name": "htdemucs_6s",
                    "shifts": 2,
                    "overlap": 0.3,
                    "segment_seconds": 8.0,
                    "profile_version": "json-profile-v2",
                    "allow_device_fallback": False,
                    "bass_mono_cutoff_hz": 75.0,
                    "vocal_lpf_hz": 14_250.0,
                    "vocal_hpf_hz": 95.0,
                }
            }
        ),
        encoding="utf-8",
    )
    captured = {}

    def fake_master(input_file, output_dir=None, config=None, reporter=None):
        captured["input_file"] = input_file
        captured["output_dir"] = output_dir
        captured["config"] = config
        return SimpleNamespace(
            output_path=str(tmp_path / "mastered.wav"),
            integrity_verified=True,
            quality_review=None,
            report=SimpleNamespace(
                solver={
                    "achieved_lufs": -12.0,
                    "achieved_true_peak_dbtp": -1.0,
                    "achieved_dr": 9.0,
                }
            ),
        )

    monkeypatch.setattr(cli, "master", fake_master)
    result = cli.main(
        [
            str(input_path),
            "--config",
            str(config_path),
            "--stem-overlap",
            "0.45",
            "--stem-profile-version",
            "cli-profile-v3",
            "--no-progress",
            "--no-report",
        ]
    )

    assert result == 0
    effective = captured["config"].stem_config
    assert effective.model_name == "htdemucs_6s"
    assert effective.shifts == 2
    assert effective.overlap == 0.45
    assert effective.segment_seconds == 8.0
    assert effective.profile_version == "cli-profile-v3"
    assert effective.allow_device_fallback is False
    assert effective.bass_mono_cutoff_hz == 75.0
    assert effective.vocal_lpf_hz == 14_250.0
    assert effective.vocal_hpf_hz == 95.0
    assert input_path.read_bytes() == original_bytes

    with pytest.raises(SystemExit):
        cli.main(
            [
                str(input_path),
                "--config",
                str(config_path),
                "--stem-shifts",
                "4",
                "--no-progress",
                "--dry-run",
            ]
        )

    missing_version_path = tmp_path / "missing-version.json"
    missing_version_path.write_text(
        json.dumps({"stem_config": {"overlap": 0.2}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="profile_version"):
        cli._load_config(str(missing_version_path))