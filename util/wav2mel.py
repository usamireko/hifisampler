# Forked from SingingVocoders, numpy backend (no torch).

import numpy as np
from librosa.filters import mel as librosa_mel_fn
from util.stft_numpy import stft_numpy, _periodic_hann


class PitchAdjustableMelSpectrogram:
    def __init__(
        self,
        sample_rate=44100,
        n_fft=2048,
        win_length=2048,
        hop_length=512,
        f_min=40.0,
        f_max=16000.0,
        n_mels=128,
        center=False,
    ):
        self.sample_rate = sample_rate
        self.n_fft = n_fft
        self.win_size = win_length
        self.hop_length = hop_length
        self.f_min = f_min
        self.f_max = f_max
        self.n_mels = n_mels
        self.center = center

        self.mel_basis = {}
        self.hann_window = {}

    def __call__(self, y, key_shift=0, speed=1.0):
        """Compute mel spectrogram from audio.

        Parameters
        ----------
        y : ndarray, shape (batch, samples) or (samples,)
            Audio waveform.
        key_shift : float
            Pitch shift in semitones.
        speed : float
            Speed factor.
        """
        y = np.asarray(y, dtype=np.float32)
        was_1d = y.ndim == 1
        if was_1d:
            y = y.reshape(1, -1)

        factor = 2 ** (key_shift / 12)
        n_fft_new = int(np.round(self.n_fft * factor))
        win_size_new = int(np.round(self.win_size * factor))
        hop_length = int(np.round(self.hop_length * speed))

        # Cache mel basis (keyed by f_max only, no device tracking needed)
        mel_basis_key = str(self.f_max)
        if mel_basis_key not in self.mel_basis:
            mel = librosa_mel_fn(
                sr=self.sample_rate,
                n_fft=self.n_fft,
                n_mels=self.n_mels,
                fmin=self.f_min,
                fmax=self.f_max,
            )
            self.mel_basis[mel_basis_key] = mel.astype(np.float32)

        # Cache hann window (keyed by key_shift / resulting win_size)
        hann_window_key = str(key_shift)
        if hann_window_key not in self.hann_window:
            self.hann_window[hann_window_key] = _periodic_hann(win_size_new)

        # Pad with reflect mode (matching torch)
        pad_left = int((win_size_new - hop_length) // 2)
        pad_right = int((win_size_new - hop_length + 1) // 2)
        y_padded = np.pad(y, ((0, 0), (pad_left, pad_right)), mode='reflect')

        # STFT
        spec = stft_numpy(
            y_padded if was_1d else y_padded,
            n_fft=n_fft_new,
            hop_length=hop_length,
            win_length=win_size_new,
            window=self.hann_window[hann_window_key],
            center=False,  # we padded manually
            pad_mode='reflect',
            normalized=False,
            onesided=True,
            return_complex=True,
        )
        if was_1d:
            spec = spec[np.newaxis, ...]

        spec = np.abs(spec)

        if key_shift != 0:
            size = self.n_fft // 2 + 1
            resize = spec.shape[1]
            if resize < size:
                spec = np.pad(spec, ((0, 0), (0, size - resize), (0, 0)))
            spec = spec[:, :size, :] * (self.win_size / win_size_new)

        # Mel projection: (n_mels, n_freq) @ (batch, n_freq, n_frames) → (batch, n_mels, n_frames)
        mel = self.mel_basis[mel_basis_key]
        spec = mel @ spec

        return spec.squeeze(0) if was_1d else spec

    def dynamic_range_compression_torch(self, x, C=1, clip_val=1e-5):
        return np.log(np.maximum(x, clip_val) * C)


if __name__ == '__main__':
    import glob
    from tqdm import tqdm

    # Legacy test runner, kept for reference. torch removed.
    print("wav2mel module loaded (numpy backend). Use PitchAdjustableMelSpectrogram class.")
