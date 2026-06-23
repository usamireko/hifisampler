#!/usr/bin/env python3
"""
Convert HN-SEP PyTorch model to ONNX format for inference optimization.
"""

import os
import argparse
import torch
import torch.nn as nn
import yaml
from pathlib import Path
import logging
from hnsep.nets import CascadedNet
from util.audio import DotDict
import onnx
import onnxslim

logging.basicConfig(format='%(message)s', level=logging.INFO)

class OnnxCompatibleCascadedNet(nn.Module):
    """ONNX-compatible version of CascadedNet that handles complex numbers as separate real/imag channels"""
    
    def __init__(self, original_model):
        super(OnnxCompatibleCascadedNet, self).__init__()
        self.n_fft = original_model.n_fft
        self.hop_length = original_model.hop_length
        self.max_bin = original_model.max_bin
        self.output_bin = original_model.output_bin
        self.offset = original_model.offset
        
        # Copy all model components properly
        self.stg1_low_band_net = original_model.stg1_low_band_net
        self.stg1_high_band_net = original_model.stg1_high_band_net
        self.stg2_low_band_net = original_model.stg2_low_band_net
        self.stg2_high_band_net = original_model.stg2_high_band_net
        self.stg3_full_band_net = original_model.stg3_full_band_net
        self.out = original_model.out
    
    def forward(self, x):
        """
        Forward pass with real/imaginary parts as separate channels
        x: [batch, 2, freq, time] where channel 0=real, channel 1=imag
        """
        # x already comes in as [batch, 2, freq, time]
        x = x[:, :, :self.max_bin]
        
        bandw = x.size()[2] // 2
        l1_in = x[:, :, :bandw]
        h1_in = x[:, :, bandw:]
        l1 = self.stg1_low_band_net(l1_in)
        h1 = self.stg1_high_band_net(h1_in)
        aux1 = torch.cat([l1, h1], dim=2)

        l2_in = torch.cat([l1_in, l1], dim=1)
        h2_in = torch.cat([h1_in, h1], dim=1)
        l2 = self.stg2_low_band_net(l2_in)
        h2 = self.stg2_high_band_net(h2_in)
        aux2 = torch.cat([l2, h2], dim=2)

        f3_in = torch.cat([x, aux1, aux2], dim=1)
        f3 = self.stg3_full_band_net(f3_in)

        # Output processing - convert back to complex-like format
        mask = self.out(f3)
        
        # Split into real and imaginary parts for bounded_mask operation
        real_part = mask[:, :1]  # First channel as real
        imag_part = mask[:, 1:]  # Second channel as imaginary
        
        # Apply bounded mask operation manually
        mask_mag = torch.sqrt(real_part**2 + imag_part**2 + 1e-8)
        tanh_mag = torch.tanh(mask_mag)
        
        # Normalize by magnitude
        real_normalized = tanh_mag * real_part / (mask_mag + 1e-8)
        imag_normalized = tanh_mag * imag_part / (mask_mag + 1e-8)
        
        # Combine back to [batch, 2, freq, time]
        mask = torch.cat([real_normalized, imag_normalized], dim=1)
        
        # Pad to output_bin
        mask = torch.nn.functional.pad(
            input=mask,
            pad=(0, 0, 0, self.output_bin - mask.size()[2]),
            mode='replicate'
        )

        return mask

def load_sep_model(model_path, device=torch.device('cpu')):
    """Load HN-SEP model from checkpoint."""
    model_dir = os.path.dirname(os.path.abspath(model_path))
    config_file = os.path.join(model_dir, 'config.yaml')
    
    with open(config_file, "r") as config:
        args_dict = yaml.safe_load(config)
    args = DotDict(args_dict)
    
    model = CascadedNet(
        args_dict['n_fft'],
        args_dict['hop_length'],
        args_dict['n_out'],
        args_dict['n_out_lstm'],
        is_complex=True,  # 复数输入
        is_mono=args_dict['is_mono'],
        fixed_length=True if args_dict.get('fixed_length', None) is None else args_dict['fixed_length']
    )
    
    model.to(device)
    model.load_state_dict(torch.load(model_path, map_location='cpu'))
    model.eval()
    
    return model, args

def convert_to_onnx(model_path, output_path=None, device=torch.device('cpu')):
    """Convert HN-SEP model to ONNX format."""
    
    # Load the model
    logging.info(f"Loading model from: {model_path}")
    model, args = load_sep_model(model_path, device)
    
    # Create ONNX-compatible wrapper
    onnx_model = OnnxCompatibleCascadedNet(model)
    onnx_model.eval()
    
    # Set output path
    if output_path is None:
        model_dir = os.path.dirname(model_path)
        output_path = os.path.join(model_dir, 'model.onnx')
    
    # Create dummy input for ONNX export
    # According to the requirement: 单声道复数输入 [1, 1, 1024, 256]
    # For ONNX, we use real/imaginary parts as separate channels: [1, 2, 1024, 256]
    batch_size = 1
    channels = 2  # Real and imaginary parts as separate channels
    freq_bins = args['n_fft'] // 2 + 1  # 1025 for n_fft=2048, but we use 1024 in practice
    time_frames = 256
    
    dummy_input = torch.randn(batch_size, channels, freq_bins, time_frames, device=device)
    
    logging.info("Converting model to ONNX...")
    logging.info(f"Input shape: {dummy_input.shape}")
    logging.info(f"Model config: n_fft={args['n_fft']}, hop_length={args['hop_length']}")
    logging.info(f"              n_out={args['n_out']}, n_out_lstm={args['n_out_lstm']}")
    logging.info(f"              is_mono={args['is_mono']}")
    
    try:
        # Export to ONNX
        torch.onnx.export(
            onnx_model,
            (dummy_input,),
            output_path,
            export_params=True,
            opset_version=11,
            do_constant_folding=True,
            input_names=['input'],
            output_names=['output'],
            dynamic_axes={
                'input': {3: 'time_frames'},
                'output': {3: 'time_frames'}
            },
            verbose=False
        )
        
        logging.info(f"Successfully converted to ONNX: {output_path}")
        
        # simplify ONNX model by onnxslim
        try:
            logging.info(f"Running OnnxSlim on: {output_path}")
            model_onnx = onnxslim.slim(output_path)
            onnx.save(model_onnx, output_path)
        
        except Exception as e:
            logging.warning(f"Running OnnxSlim failed: {e}")
        
        # Verify the ONNX model
        try:
            import onnxruntime as ort
            ort_session = ort.InferenceSession(output_path, providers=['CPUExecutionProvider'])
            
            # Test inference
            dummy_input_np = dummy_input.detach().cpu().numpy()
            ort_outputs = ort_session.run(['output'], {'input': dummy_input_np})
            
            logging.info("ONNX model verification successful!")
            logging.info(f"Output shape: {ort_outputs[0].shape}")
            
        except Exception as e:
            logging.warning(f"ONNX model verification failed: {e}")
            
    except Exception as e:
        logging.error(f"Failed to convert to ONNX: {e}")
        raise

def main():
    """Main conversion function."""
    parser = argparse.ArgumentParser(description="Convert HN-SEP PyTorch model to ONNX.")
    parser.add_argument("--model-dir", default="vr", help="Directory containing model_fp16.pt or model.pt and config.yaml.")
    parser.add_argument("--output", default=None, help="Output ONNX path. Defaults to model-dir/model_fp16.onnx.")
    args_cli = parser.parse_args()
    
    # Default paths
    model_dir = Path(args_cli.model_dir)
    pt_model_path = model_dir / "model_fp16.pt"
    fallback_model_path = model_dir / "model.pt"
    onnx_output_path = Path(args_cli.output) if args_cli.output else model_dir / "model_fp16.onnx"
    
    # Check which model exists
    if pt_model_path.exists():
        input_model = pt_model_path
    elif fallback_model_path.exists():
        input_model = fallback_model_path
    else:
        raise FileNotFoundError(f"No HN-SEP model found in {model_dir}. Expected model_fp16.pt or model.pt.")
    
    logging.info(f"Found model: {input_model}")
    
    # Use CPU for conversion to avoid device compatibility issues
    device = torch.device('cpu')
    
    # Convert to ONNX
    convert_to_onnx(str(input_model), str(onnx_output_path), device)
    
    logging.info("Conversion completed successfully!")

if __name__ == "__main__":
    main()
