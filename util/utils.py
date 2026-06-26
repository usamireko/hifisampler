import numpy as np
from scipy.interpolate import CubicSpline


def get_mel_fn(
        sr: float,
        n_fft: int,
        n_mels: int,
        fmin: float,
        fmax: float,
        htk: bool,
        device: str = 'cpu'
) -> np.ndarray:
    '''
    Compute mel filterbank weights, pure numpy, no torch needed.

    Args:
        sr: sample rate
        n_fft: FFT size
        n_mels: number of mel bands
        fmin: minimum frequency
        fmax: maximum frequency
        htk: Whether to use HTK formula or Slaney formula
        device: ignored, kept for API compatibility

    Returns:
        weights: ndarray [shape = (n_mels, n_fft // 2 + 1)]
    '''
    fmin = float(fmin)
    fmax = float(fmax)

    if htk:
        min_mel = 2595.0 * np.log10(1.0 + fmin / 700.0)
        max_mel = 2595.0 * np.log10(1.0 + fmax / 700.0)
        mels = np.linspace(min_mel, max_mel, n_mels + 2)
        mel_f = 700.0 * (10.0 ** (mels / 2595.0) - 1.0)
    else:
        f_sp = 200.0 / 3
        min_log_hz = 1000.0
        min_log_mel = min_log_hz / f_sp
        logstep = np.log(6.4) / 27.0

        if fmin >= min_log_hz:
            min_mel = min_log_mel + np.log(fmin / min_log_hz) / logstep
        else:
            min_mel = fmin / f_sp

        if fmax >= min_log_hz:
            max_mel = min_log_mel + np.log(fmax / min_log_hz) / logstep
        else:
            max_mel = fmax / f_sp

        mels = np.linspace(min_mel, max_mel, n_mels + 2)
        mel_f = np.zeros_like(mels)

        log_t = mels >= min_log_mel
        mel_f[~log_t] = f_sp * mels[~log_t]
        mel_f[log_t] = min_log_hz * np.exp(logstep * (mels[log_t] - min_log_mel))

    n_mels = int(n_mels)
    N = 1 + n_fft // 2
    weights = np.zeros((n_mels, N), dtype=np.float32)

    fftfreqs = (sr / n_fft) * np.arange(0, N, dtype=np.float32)

    fdiff = np.diff(mel_f)
    ramps = mel_f[:, np.newaxis] - fftfreqs[np.newaxis, :]

    lower = -ramps[:-2] / fdiff[:-1, np.newaxis]
    upper = ramps[2:] / fdiff[1:, np.newaxis]
    weights = np.maximum(0.0, np.minimum(lower, upper))

    enorm = 2.0 / (mel_f[2: n_mels + 2] - mel_f[:n_mels])
    weights *= enorm[:, np.newaxis]

    return weights.astype(np.float32)


def expand_uv(uv):
    uv = uv.astype('float')
    uv = np.min(np.array([uv[:-2], uv[1:-1], uv[2:]]), axis=0)
    uv = np.pad(uv, (1, 1), constant_values=(uv[0], uv[-1]))

    return uv


def norm_f0(f0: np.ndarray, uv=None):
    if uv is None:
        uv = f0 == 0

    f0 = np.log2(f0 + uv)
    f0[uv] = -np.inf

    return f0


def denorm_f0(f0: np.ndarray, uv, pitch_padding=None):
    f0 = 2 ** f0

    if uv is not None:
        f0[uv > 0] = 0

    if pitch_padding is not None:
        f0[pitch_padding] = 0

    return f0


def interp_f0_spline(f0: np.ndarray, uv=None):
    if uv is None:
        uv = f0 == 0
    f0max = np.max(f0)
    f0 = norm_f0(f0, uv)

    if uv.any() and not uv.all():
        spline = CubicSpline(np.where(~uv)[0], f0[~uv])
        f0[uv] = spline(np.where(uv)[0])

    return np.clip(denorm_f0(f0, uv=None), 0, f0max), uv


def interp_f0(f0: np.ndarray, uv=None):
    if uv is None:
        uv = f0 == 0
    f0 = norm_f0(f0, uv)

    if uv.any() and not uv.all():
        f0[uv] = np.interp(np.where(uv)[0], np.where(~uv)[0], f0[~uv])

    return denorm_f0(f0, uv=None), uv


class AttrDict(dict):
    """A dictionary with attribute-style access."""
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)

    def __getstate__(self):
        return self.__dict__.items()

    def __setstate__(self, items):
        for key, val in items:
            self.__dict__[key] = val

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, dict.__repr__(self))

    def __setitem__(self, key, value):
        return super(AttrDict, self).__setitem__(key, value)

    def __getitem__(self, name):
        return super(AttrDict, self).__getitem__(name)

    def __delitem__(self, name):
        return super(AttrDict, self).__delitem__(name)

    __getattr__ = __getitem__
    __setattr__ = __setitem__

    def copy(self):
        return AttrDict(self)


def init_weights(m, mean=0.0, std=0.01):
    classname = m.__class__.__name__
    if classname.find("Conv") != -1:
        m.weight.data.normal_(mean, std)


def get_padding(kernel_size, dilation=1):
    return int((kernel_size*dilation - dilation)/2)


if __name__ == '__main__':
    pass
