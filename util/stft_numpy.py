"""Numpy STFT/iSTFT matching torch conventions."""

import numpy as np


def _periodic_hann(window_length: int, dtype=np.float32) -> np.ndarray:
    """Periodic Hann: w[n] = 0.5*(1 - cos(2πn/N)). Sum = N/2. Matches torch.hann_window."""
    n = np.arange(window_length, dtype=np.float64)
    return (0.5 - 0.5 * np.cos(2.0 * np.pi * n / window_length)).astype(dtype)


def stft_numpy(
    y: np.ndarray,
    n_fft: int,
    hop_length: int,
    win_length: int,
    window: np.ndarray | None = None,
    center: bool = True,
    pad_mode: str = "reflect",
    normalized: bool = False,
    onesided: bool = True,
    return_complex: bool = True,
) -> np.ndarray:
    """Numpy STFT matching torch.stft. Supports 1D or batched (batch, samples) input."""
    if window is None:
        window = _periodic_hann(win_length, dtype=y.dtype)

    # Handle batching: if 2D, treat first dim as batch
    was_1d = y.ndim == 1
    if was_1d:
        y = y.reshape(1, -1)

    batch_size = y.shape[0]
    results = []

    for b in range(batch_size):
        x = y[b]

        if center:
            pad = n_fft // 2
            x = np.pad(x, (pad, pad), mode=pad_mode)

        n_frames = max(0, 1 + (len(x) - win_length) // hop_length)
        if n_frames == 0:
            spec = np.zeros((n_fft // 2 + 1 if onesided else n_fft, 0), dtype=np.complex64)
        else:
            # Frame using sliding window view (no copy)
            frames = np.lib.stride_tricks.sliding_window_view(x, win_length)[: n_frames * hop_length : hop_length]
            frames = frames.astype(np.float64) * window.astype(np.float64)

            if onesided:
                spec = np.fft.rfft(frames, n=n_fft, axis=1)
            else:
                spec = np.fft.fft(frames, n=n_fft, axis=1)

            if normalized:
                scale = np.sqrt((window**2).sum())
                spec = spec / scale

            spec = spec.T  # (n_freq, n_frames)

        results.append(spec)

    if was_1d:
        return results[0]
    return np.stack(results, axis=0)


def istft_numpy(
    spec: np.ndarray,
    n_fft: int,
    hop_length: int,
    win_length: int,
    window: np.ndarray | None = None,
    center: bool = True,
    length: int | None = None,
) -> np.ndarray:
    """Numpy iSTFT matching torch.istft. Overlap-add reconstruction."""
    if window is None:
        window = _periodic_hann(win_length)

    window = window.astype(np.float64)

    # Handle batching
    was_no_batch = spec.ndim == 2
    if was_no_batch:
        spec = spec[np.newaxis, ...]

    batch_size = spec.shape[0]
    results = []

    for b in range(batch_size):
        sp = spec[b]  # (n_freq, n_frames)

        # iFFT
        frames = np.fft.irfft(sp, n=n_fft, axis=0).T  # (n_frames, win_length)
        frames = frames[:, :win_length]

        # Apply synthesis window
        frames = frames * window

        # Overlap-add
        n_frames = frames.shape[0]
        expected_len = (n_frames - 1) * hop_length + win_length
        y = np.zeros(expected_len, dtype=np.float64)
        norm = np.zeros(expected_len, dtype=np.float64)
        win_sq = window**2

        for i in range(n_frames):
            start = i * hop_length
            y[start : start + win_length] += frames[i]
            norm[start : start + win_length] += win_sq

        # Normalize by window overlap
        mask = norm > 1e-10
        y[mask] /= norm[mask]

        # Remove center padding
        if center:
            pad = n_fft // 2
            y = y[pad:-pad] if pad > 0 and len(y) > 2 * pad else y

        # Trim to requested length
        if length is not None:
            y = y[:length]

        results.append(y.astype(np.float32))

    if was_no_batch:
        return results[0]
    return np.stack(results, axis=0)
