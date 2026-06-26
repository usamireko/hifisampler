import dataclasses
from pathlib import Path
from util.load_config_from_yaml import load_config_from_yaml
from typing import Any


@dataclasses.dataclass
@load_config_from_yaml(script_path=Path(__file__))
class Config:
    sample_rate: int = 44100
    win_size: int = 2048
    hop_size: int = 512
    origin_hop_size: int = 128
    n_mels: int = 128
    n_fft: int = 2048
    mel_fmin: float = 40
    mel_fmax: float = 16000
    fill: int = 6
    vocoder_path: str = r"\path\to\your\vocoder\pc_nsf_hifigan\model.ckpt"
    model_type: str = 'ckpt'
    hnsep_model_path: str = r"\path\to\your\hnsep\model.onnx"
    wave_norm: bool = False
    trim_silence: bool = True
    silence_threshold: float = -52.0
    loop_mode: bool = False
    peak_limit: float = 1.0
    max_workers: Any = 2
    acceleration: str = "cpu"
    directml_device_id: int = 0


CONFIG = Config()
