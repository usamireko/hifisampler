import logging

from config import CONFIG
from util.wav2mel import PitchAdjustableMelSpectrogram
from util.model_loader import HifiGANLoader, HNSEPLoader

vocoder = None
ort_session = None
hnsep_model = None
mel_analyzer = None
vocoder_type = None
hnsep_type = None

logging.basicConfig(format='%(message)s', level=logging.INFO)

def initialize_models():
    global vocoder, ort_session, hnsep_model, mel_analyzer, vocoder_type, hnsep_type
    
    logging.info("Initializing models...")

    hifigan_loader = HifiGANLoader(CONFIG.vocoder_path)
    hnsep_loader = HNSEPLoader(CONFIG.hnsep_model_path)
    
    vocoder_result = hifigan_loader.load_model()
    model_or_session, vocoder_type = vocoder_result
    if vocoder_type == 'onnx':
        ort_session = model_or_session
        CONFIG.model_type = 'onnx'
    else:
        vocoder = model_or_session
    
    hnsep_result = hnsep_loader.load_model()
    hnsep_model, hnsep_type, _ = hnsep_result

    # 3. 初始化 Mel Spectrogram 工具
    mel_analyzer = PitchAdjustableMelSpectrogram(
        sample_rate=CONFIG.sample_rate,
        n_fft=CONFIG.n_fft,
        win_length=CONFIG.win_size,
        hop_length=CONFIG.origin_hop_size,
        f_min=CONFIG.mel_fmin,
        f_max=CONFIG.mel_fmax,
        n_mels=CONFIG.n_mels
    )
    logging.info(f'Initialized Mel Analysis with hop_size={CONFIG.origin_hop_size}.')

    logging.info("Models initialized successfully.")