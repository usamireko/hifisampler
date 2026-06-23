from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort


def make_session_options(provider: str) -> ort.SessionOptions:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if provider == "DmlExecutionProvider":
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.enable_mem_pattern = False
    else:
        options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
        options.enable_mem_pattern = True
    return options


def select_provider(requested: str) -> str:
    available = ort.get_available_providers()
    if requested == "auto":
        if "DmlExecutionProvider" in available:
            return "DmlExecutionProvider"
        return "CPUExecutionProvider"

    provider = {
        "directml": "DmlExecutionProvider",
        "cpu": "CPUExecutionProvider",
    }[requested]
    if provider not in available:
        raise RuntimeError(f"{provider} is not available. Available providers: {', '.join(available)}")
    return provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test HNSEP ONNX with ONNX Runtime.")
    parser.add_argument("--model", default="hnsep/model.onnx", help="Path to HNSEP ONNX model.")
    parser.add_argument("--provider", choices=("auto", "directml", "cpu"), default="auto")
    parser.add_argument("--directml-device-id", type=int, default=0, help="DirectML adapter index.")
    parser.add_argument("--frames", type=int, default=256, help="Dummy spectrogram frame count.")
    args = parser.parse_args()

    model_path = Path(args.model).resolve()
    if not model_path.exists():
        print(f"ERROR: model not found: {model_path}")
        return 1

    print(f"ONNX Runtime: {ort.__version__}")
    print(f"Available providers: {', '.join(ort.get_available_providers())}")

    try:
        provider = select_provider(args.provider)
        provider_options: list[tuple[str, dict[str, str]] | str]
        if provider == "DmlExecutionProvider":
            provider_options = [
                ("DmlExecutionProvider", {"device_id": str(max(0, args.directml_device_id))}),
                "CPUExecutionProvider",
            ]
        else:
            provider_options = ["CPUExecutionProvider"]

        session = ort.InferenceSession(
            str(model_path),
            providers=provider_options,
            sess_options=make_session_options(provider),
        )
    except Exception as exc:
        print(f"ERROR: failed to create ONNX session: {exc}")
        return 1

    print(f"Requested provider: {provider}")
    print(f"Session providers: {', '.join(session.get_providers())}")

    input_meta = session.get_inputs()[0]
    output_meta = session.get_outputs()[0]
    print(f"Input: {input_meta.name} {input_meta.shape} {input_meta.type}")
    print(f"Output: {output_meta.name} {output_meta.shape} {output_meta.type}")

    dummy = np.random.randn(1, 2, 1025, args.frames).astype(np.float32)
    try:
        output = session.run([output_meta.name], {input_meta.name: dummy})[0]
    except Exception as exc:
        print(f"ERROR: inference failed: {exc}")
        return 1

    print(f"OK: inference completed")
    print(f"Output shape: {output.shape}")
    print(f"Output dtype: {output.dtype}")
    print(f"Output finite: {bool(np.isfinite(output).all())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
