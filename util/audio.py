import logging
from pathlib import Path
import numpy as np
import resampy
from config import CONFIG
import soundfile as sf

if CONFIG.wave_norm:
    try:
        import pyloudnorm as pyln
        logging.info("pyloudnorm imported for wave normalization.")
    except ImportError:
        logging.warning(
            "pyloudnorm not found, wave normalization disabled.")
        CONFIG.wave_norm = False


class DotDict(dict):
    def __getattr__(*args):
        val = dict.get(*args)
        return DotDict(val) if type(val) is dict else val

    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def dynamic_range_compression_torch(x, C=1, clip_val=1e-9):
    return np.log(np.maximum(x, clip_val) * C)


def loudness_norm(
    audio: np.ndarray, rate: int, peak=-1.0, loudness=-23.0, block_size=0.400, strength=100
) -> np.ndarray:
    """
    Perform loudness normalization (ITU-R BS.1770-4) on audio files.

    Args:
        audio: audio data
        rate: sample rate
        peak: peak normalize audio to N dB. Defaults to -1.0.
        loudness: loudness normalize audio to N dB LUFS. Defaults to -23.0.
        block_size: block size for loudness measurement. Defaults to 0.400. (400 ms)
        strength: strength of the normalization. Defaults to 100.

    Returns:
        loudness normalized audio
    """

    original_length = len(audio)
    original_audio = audio.copy()

    if CONFIG.trim_silence:
        def get_rms_db(audio_segment):
            if len(audio_segment) == 0:
                return -np.inf
            rms = np.sqrt(np.mean(np.square(audio_segment)))
            if rms < 1e-10:
                return -np.inf
            return 20 * np.log10(rms)

        frame_length = int(rate * 0.02)
        hop_length = int(rate * 0.01)

        rms_values = []
        for i in range(0, len(audio) - frame_length, hop_length):
            frame = audio[i:i+frame_length]
            rms_db = get_rms_db(frame)
            rms_values.append(rms_db)

        voiced_frames = [i for i, rms in enumerate(
            rms_values) if rms > CONFIG.silence_threshold]

        if voiced_frames:
            first_voiced = voiced_frames[0]
            last_voiced = voiced_frames[-1]

            padding_frames = int(rate * 0.1) // hop_length

            start_sample = max(0, first_voiced * hop_length)
            end_sample = min(len(audio), (last_voiced + 1 +
                             padding_frames) * hop_length + frame_length)

            trimmed_audio = audio[start_sample:end_sample]
            logging.info(
                f'Trimmed silence: {len(audio)} -> {len(trimmed_audio)} samples')

            audio = trimmed_audio

    if len(audio) < int(rate * block_size):
        padding_length = int(rate * block_size) - len(audio)
        audio = np.pad(audio, (0, padding_length), mode='reflect')

    meter = pyln.Meter(rate, block_size=block_size)
    _loudness = meter.integrated_loudness(audio)

    final_loudness = _loudness + (loudness - _loudness) * strength / 100

    audio = pyln.normalize.loudness(audio, _loudness, final_loudness)

    if CONFIG.trim_silence:
        output = np.zeros(original_length)

        if voiced_frames:
            start_sample = max(0, first_voiced * int(hop_length))

            available_length = min(len(audio), original_length - start_sample)

            fade_length = min(int(rate * 0.2), available_length // 4)
            fade_out = np.ones(available_length)

            if fade_length > 0:
                fade_out[-fade_length:] = np.linspace(1.0, 0.0, fade_length)

            output[start_sample:start_sample +
                   available_length] = audio[:available_length] * fade_out
            if start_sample + available_length < original_length:
                remain_length = original_length - \
                    (start_sample + available_length)
                crossfade_length = min(fade_length, remain_length)

                if crossfade_length > 0:
                    crossfade_start = start_sample + available_length
                    remain_audio = original_audio[crossfade_start:original_length]

                    fade_in = np.ones(remain_length)
                    fade_in[:crossfade_length] = np.linspace(
                        0.0, 1.0, crossfade_length)

                    output[crossfade_start:original_length] = remain_audio * fade_in
        else:
            output = audio[:original_length]

        audio = output

    if original_length < int(rate * block_size):
        audio = audio[:original_length]

    return audio


def pre_emphasis_base_tension(wave, b):
    """
    Apply pre-emphasis with base tension using numpy STFT/iSTFT.

    Args:
        wave: ndarray [1, 1, t] or [1, t]
        b: float, tension coefficient
    """
    from util.stft_numpy import stft_numpy, istft_numpy, _periodic_hann

    wave = np.asarray(wave, dtype=np.float32)

    original_length = wave.shape[-1]
    pad_length = (CONFIG.hop_size - (original_length %
                  CONFIG.hop_size)) % CONFIG.hop_size
    wave = np.pad(wave, ((0, 0), (0, pad_length)), mode='constant')

    if wave.ndim == 3:
        wave = wave.reshape(wave.shape[1], wave.shape[2])  # [1, t]
    elif wave.ndim == 2 and wave.shape[0] == 1:
        wave = wave[0]

    hann_win = _periodic_hann(CONFIG.win_size)

    spec = stft_numpy(
        wave,
        n_fft=CONFIG.n_fft,
        hop_length=CONFIG.hop_size,
        win_length=CONFIG.win_size,
        window=hann_win,
        center=True,
    )
    spec_amp = np.abs(spec)
    spec_phase = np.arctan2(spec.imag, spec.real)

    spec_amp_db = np.log(np.maximum(spec_amp, 1e-9))

    fft_bin = CONFIG.n_fft // 2 + 1
    x0 = fft_bin / ((CONFIG.sample_rate / 2) / 1500)
    freq_filter = (-b / x0) * np.arange(fft_bin, dtype=np.float32) + b
    freq_filter = np.clip(freq_filter, -2, 2)
    spec_amp_db = spec_amp_db + freq_filter[:, np.newaxis]

    spec_amp = np.exp(spec_amp_db)

    # Reconstruct complex spec
    spec_filtered = spec_amp * (np.cos(spec_phase) + 1j * np.sin(spec_phase))

    filtered_wave = istft_numpy(
        spec_filtered,
        n_fft=CONFIG.n_fft,
        hop_length=CONFIG.hop_size,
        win_length=CONFIG.win_size,
        window=hann_win,
        center=True,
    )

    original_max = np.max(np.abs(wave))
    filtered_max = np.max(np.abs(filtered_wave))
    if filtered_max > 1e-10:
        filtered_wave = filtered_wave * \
            (original_max / filtered_max) * (np.clip(b/(-15), 0, 0.33) + 1)

    filtered_wave = filtered_wave[:original_length]

    return filtered_wave.reshape(1, 1, -1)


def read_wav(loc):
    """Read audio files supported by soundfile and resample to 44.1kHz if needed.
    Mixes down to mono if needed.

    Parameters
    ----------
    loc : str or file
        Input audio file.

    Returns
    -------
    ndarray
        Data read from WAV file remapped to [-1, 1] and in 44.1kHz
    """
    if type(loc) is str:
        loc = Path(loc)

    exists = loc.exists()
    if not exists:
        for ext in sf.available_formats().keys():
            loc = loc.with_suffix('.' + ext.lower())
            exists = loc.exists()
            if exists:
                break

    if not exists:
        raise FileNotFoundError("No supported audio file was found.")

    x, fs = sf.read(str(loc))
    if len(x.shape) == 2:
        x = np.mean(x, axis=1)

    if fs != CONFIG.sample_rate:
        x = resampy.resample(x, fs, CONFIG.sample_rate)

    return x


def save_wav(loc, x):
    """Save data into a WAV file.

    Parameters
    ----------
    loc : str or file
        Output WAV file.

    x : ndarray
        Audio data in 44.1kHz within [-1, 1].

    Returns
    -------
    None
    """
    try:
        sf.write(str(loc), x, CONFIG.sample_rate, 'PCM_16')
    except Exception as e:
        logging.error(f"Error saving WAV file: {e}")
