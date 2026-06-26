import logging
from pathlib import Path
import numpy as np

from config import CONFIG


def get_onnx_providers():
    """Get optimal ONNX providers in priority order."""
    import onnxruntime
    available_providers = onnxruntime.get_available_providers()
    preferred_providers = []

    acceleration = str(getattr(CONFIG, 'acceleration', 'cpu')).lower()
    if acceleration == 'directml' and 'DmlExecutionProvider' in available_providers:
        preferred_providers.append('DmlExecutionProvider')
    elif acceleration == 'directml':
        logging.warning(
            'DirectML was requested but DmlExecutionProvider is not available. '
            'Falling back to CPU.'
        )
    elif acceleration == 'coreml' and 'CoreMLExecutionProvider' in available_providers:
        preferred_providers.append('CoreMLExecutionProvider')
    elif acceleration == 'coreml':
        logging.warning(
            'CoreML was requested but CoreMLExecutionProvider is not available. '
            'Falling back to CPU.'
        )
    preferred_providers.append('CPUExecutionProvider')

    return preferred_providers


def create_optimized_session_options(use_directml=False):
    """Create optimized ONNX session options for maximum performance."""
    import onnxruntime

    session_options = onnxruntime.SessionOptions()

    if use_directml:
        session_options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        session_options.enable_mem_pattern = False
    else:
        session_options.execution_mode = onnxruntime.ExecutionMode.ORT_PARALLEL
        session_options.enable_mem_pattern = True
    session_options.graph_optimization_level = \
        onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL

    session_options.enable_mem_reuse = True

    session_options.add_session_config_entry('session.disable_prepacking', '0')
    session_options.add_session_config_entry('session.use_env_allocators', '1')
    session_options.add_session_config_entry('session.disable_cpu_ep_fallback', '0')
    session_options.add_session_config_entry(
        'session.enable_cpu_ep_use_ort_cpu_provider_arena', '1'
    )
    session_options.add_session_config_entry('session.force_spinning_stop', '0')

    logging.info(
        f'ONNX Session configured with '
        f'intra_op_threads={session_options.intra_op_num_threads}, '
        f'inter_op_threads={session_options.inter_op_num_threads}'
    )

    return session_options


def get_cpu_provider_options():
    """Get optimized CPU provider options for maximum performance."""
    return {
        'arena_extend_strategy': 'kSameAsRequested',
        'enable_cpu_mem_arena': '1',
        'use_arena': '1',
        'enable_op_level_parallel': '1',
        'use_gemm_conv1d_optimization': '1',
        'cpu_thread_spinning': '1',
        'allow_non_zero_dimension_args': '1',
        'use_xnnpack': '0',
        'disable_spinning': '0',
        'force_hybrid_sequential_execution': '0',
    }


def get_directml_provider_options():
    """Get DirectML provider options."""
    device_id = int(getattr(CONFIG, 'directml_device_id', 0) or 0)
    return {'device_id': str(max(0, device_id))}


def resolve_model_path(configured_path, default_paths):
    """Resolve actual model path from configured path and defaults."""
    model_path = Path(configured_path)
    if model_path.exists():
        return model_path

    for default_path in default_paths:
        if default_path.exists():
            logging.info(
                f"Configured path not found, using default: {default_path}"
            )
            return default_path

    raise FileNotFoundError(
        f"No model found. Checked {model_path} and defaults: {default_paths}"
    )


class HifiGANLoader:
    """HifiGAN loader: ONNX (default) or PyTorch ckpt (needs torch)."""

    def __init__(self, model_path, device=None):
        self.model_path = model_path
        self.device = device  # only used for PyTorch path

    def get_default_paths(self):
        return [
            Path("models/pc_nsf/model.onnx"),
            Path("pc_nsf_hifigan_44.1k_hop512_128bin_2025.02/model.ckpt"),
            Path("pc_nsf_hifigan_44.1k_hop512_128bin_2025.02/model.onnx"),
        ]

    def load_model(self):
        actual_path = resolve_model_path(self.model_path, self.get_default_paths())

        if actual_path.suffix == '.onnx':
            return self.load_onnx_model(actual_path)
        else:
            return self.load_pytorch_model(actual_path)

    def load_pytorch_model(self, actual_path):
        try:
            import torch
            from util.nsf_hifigan import NsfHifiGAN
        except ImportError:
            raise ImportError(
                "PyTorch is required to load .ckpt HifiGAN models. "
                "Install torch or convert your model to ONNX format."
            )

        vocoder = NsfHifiGAN(model_path=actual_path)
        if self.device is not None:
            vocoder.to_device(self.device)
        logging.info(f'Loaded HifiGAN (PyTorch): {actual_path} on {self.device}')
        return vocoder, 'pytorch'

    def load_onnx_model(self, actual_path):
        import onnxruntime

        preferred_providers = get_onnx_providers()
        session_options = create_optimized_session_options(
            use_directml='DmlExecutionProvider' in preferred_providers
        )

        provider_options = []
        for provider in preferred_providers:
            if provider == 'CPUExecutionProvider':
                provider_options.append(
                    ('CPUExecutionProvider', get_cpu_provider_options())
                )
            elif provider == 'DmlExecutionProvider':
                provider_options.append(
                    ('DmlExecutionProvider', get_directml_provider_options())
                )
            else:
                provider_options.append((provider, {}))

        session = onnxruntime.InferenceSession(
            str(actual_path),
            providers=provider_options,
            sess_options=session_options,
        )
        used_provider = session.get_providers()[0]

        logging.info(
            f'Loaded HifiGAN (ONNX): {actual_path} using provider {used_provider}'
        )

        if used_provider == 'DmlExecutionProvider' and CONFIG.max_workers != 1:
            logging.info(
                'DirectML detected: forcing max_workers=1 to avoid DML multi-thread bug.'
            )
            CONFIG.max_workers = 1

        return session, 'onnx'


class HNSEPLoader:
    """HN-SEP loader: ONNX (default) or PyTorch pt (needs torch)."""

    def __init__(self, model_path, device=None):
        self.model_path = model_path
        self.device = device

    def get_model_config(self, model_path):
        import yaml
        import os
        from util.audio import DotDict

        model_dir = os.path.dirname(os.path.abspath(model_path))
        config_file = os.path.join(model_dir, 'config.yaml')

        with open(config_file, "r") as config:
            args_dict = yaml.safe_load(config)
        return DotDict(args_dict), args_dict

    def load_model(self):
        actual_path = Path(self.model_path)

        if actual_path.suffix == '.onnx':
            return self.load_onnx_model(actual_path)
        else:
            return self.load_pytorch_model(actual_path)

    def load_pytorch_model(self, actual_path):
        try:
            import torch
            from hnsep.nets import CascadedNet
        except ImportError:
            raise ImportError(
                "PyTorch is required to load .pt HN-SEP models. "
                "Install torch or convert your model to ONNX format."
            )

        args, args_dict = self.get_model_config(actual_path)

        model = CascadedNet(
            args_dict['n_fft'],
            args_dict['hop_length'],
            args_dict['n_out'],
            args_dict['n_out_lstm'],
            True,
            is_mono=args_dict['is_mono'],
            fixed_length=(
                True if args_dict.get('fixed_length', None) is None
                else args_dict['fixed_length']
            ),
        )
        model.to(self.device or torch.device('cpu'))
        model.load_state_dict(torch.load(actual_path, map_location='cpu'))
        model.eval()

        logging.info(f"Loaded HN-SEP (PyTorch): {actual_path}")
        return model, 'pytorch', args

    def load_onnx_model(self, actual_path):
        import onnxruntime
        from util.hnsep import HnsepModel

        args, args_dict = self.get_model_config(actual_path)

        preferred_providers = get_onnx_providers()
        session_options = create_optimized_session_options(
            use_directml='DmlExecutionProvider' in preferred_providers
        )

        provider_options = []
        for provider in preferred_providers:
            if provider == 'CPUExecutionProvider':
                provider_options.append(
                    ('CPUExecutionProvider', get_cpu_provider_options())
                )
            elif provider == 'DmlExecutionProvider':
                provider_options.append(
                    ('DmlExecutionProvider', get_directml_provider_options())
                )
            else:
                provider_options.append((provider, {}))

        session = onnxruntime.InferenceSession(
            str(actual_path),
            providers=provider_options,
            sess_options=session_options,
        )
        used_provider = session.get_providers()[0]

        logging.info(
            f'Loaded HN-SEP (ONNX): {actual_path} using provider {used_provider}'
        )

        model = HnsepModel(session, args_dict)
        return model, 'onnx', args
