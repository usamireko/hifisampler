import dataclasses
from pathlib import Path
import torch
from util.load_config_from_yaml import load_config_from_yaml
from typing import Any

@dataclasses.dataclass
@load_config_from_yaml(script_path=Path(__file__))
class Config:
    sample_rate: int = 44100  # UTAU only really likes 44.1khz
    win_size: int = 2048     # 必须和vocoder训练时一致
    hop_size: int = 512      # 必须和vocoder训练时一致
    origin_hop_size: int = 128  # 插值前的hopsize,可以适当调小改善长音的电音
    n_mels: int = 128        # 必须和vocoder训练时一致
    n_fft: int = 2048        # 必须和vocoder训练时一致
    mel_fmin: float = 40     # 必须和vocoder训练时一致
    mel_fmax: float = 16000  # 必须和vocoder训练时一致
    fill: int = 6
    vocoder_path: str = r"\path\to\your\vocoder\pc_nsf_hifigan\model.ckpt"
    model_type: str = 'ckpt'  # or 'onnx'
    hnsep_model_path: str = r"\path\to\your\hnsep\model.onnx"
    wave_norm: bool = False
    trim_silence: bool = True  # 是否在响度标准化前截取无声部分
    silence_threshold: float = -52.0
    loop_mode: bool = False
    peak_limit: float = 1.0
    # max_workers can be an int or 'auto' (resolved to physical cores at runtime)
    max_workers: Any = 2
    acceleration: str = "cpu"  # cpu or directml
    directml_device_id: int = 0
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

CONFIG = Config()
