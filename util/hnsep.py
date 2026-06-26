"""
HN-SEP ONNX inference wrapper. Numpy STFT/iSTFT, no torch needed for ONNX path.
"""

import logging
import os
from pathlib import Path
import yaml
import numpy as np
from util.audio import DotDict
from util.stft_numpy import stft_numpy, istft_numpy, _periodic_hann


class HnsepModel:
    """HN-SEP ONNX inference wrapper."""

    def __init__(self, onnx_session, config_args):
        self.session = onnx_session
        self.config = config_args
        self.n_fft = config_args['n_fft']
        self.hop_length = config_args['hop_length']
        self.max_bin = self.n_fft // 2
        self.output_bin = self.n_fft // 2 + 1
        self.offset = 64

    def forward(self, x):
        """x: complex ndarray [..., channels, freq, time]."""
        was_3d = x.ndim == 3
        if was_3d:
            x = x[np.newaxis, ...]

        B, C, F, T = x.shape
        x_input = np.zeros((B, 2 * C, F, T), dtype=np.float32)
        for c in range(C):
            x_input[:, 2 * c] = x[:, c].real
            x_input[:, 2 * c + 1] = x[:, c].imag

        output = self.session.run(['output'], {'input': x_input})[0]

        C_out = output.shape[1] // 2
        out_complex = np.zeros((B, C_out, output.shape[2], output.shape[3]), dtype=np.complex64)
        for c in range(C_out):
            out_complex[:, c] = output[:, 2 * c] + 1j * output[:, 2 * c + 1]

        return out_complex[0] if was_3d else out_complex

    def predict_fromaudio(self, x):
        B, C, T = x.shape
        x = x.reshape(B * C, T)
        T1 = T + self.hop_length
        seg_length = 32 * self.hop_length
        T_pad = seg_length * ((T1 - 1) // seg_length + 1) - T1
        nl_pad = T_pad // 2 // self.hop_length
        Tl_pad = nl_pad * self.hop_length
        x = np.pad(x, ((0, 0), (Tl_pad, T_pad - Tl_pad)))

        # Create Hann window
        window = _periodic_hann(self.n_fft)

        spec = stft_numpy(
            x,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.n_fft,
            window=window,
            center=True,
        )
        spec = spec.reshape(B, C, spec.shape[-2], spec.shape[-1])

        mask = self.forward(spec)
        spec_pred = spec * mask
        spec_pred = spec_pred.reshape(B * C, spec.shape[-2], spec.shape[-1])

        x_pred = istft_numpy(
            spec_pred,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            win_length=self.n_fft,
            window=window,
            center=True,
        )
        x_pred = x_pred[:, Tl_pad: Tl_pad + T]
        x_pred = x_pred.reshape(B, C, T)
        return x_pred


def load_sep_model_pt(model_path, device=None):
    """Load HN-SEP model from PyTorch checkpoint. Requires torch.

    Use HNSEPLoader for unified loading instead.
    """
    try:
        import torch
    except ImportError:
        raise ImportError(
            "PyTorch is required to load .pt HN-SEP models. "
            "Convert the model to ONNX first or install torch."
        )

    from hnsep.nets import CascadedNet

    model_dir = os.path.dirname(os.path.abspath(model_path))
    config_file = os.path.join(model_dir, 'config.yaml')

    with open(config_file, "r") as config:
        args_dict = yaml.safe_load(config)
    args = DotDict(args_dict)

    model_path_obj = Path(model_path)

    if model_path_obj.suffix == '.onnx':
        raise ValueError(
            "ONNX models should be loaded through HNSEPLoader "
            "for unified session management"
        )

    model = CascadedNet(
        args_dict['n_fft'],
        args_dict['hop_length'],
        args_dict['n_out'],
        args_dict['n_out_lstm'],
        True,
        is_mono=args_dict['is_mono'],
        fixed_length=True if args_dict.get('fixed_length', None) is None
        else args_dict['fixed_length']
    )
    model.to(torch.device('cpu'))
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    logging.info(f"Loaded HN-SEP model (PyTorch): {model_path}")
    return model, args
