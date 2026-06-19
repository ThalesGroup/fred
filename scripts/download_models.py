#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from docling.models.utils.hf_model_download import download_hf_model
from docling.utils.model_downloader import download_models


_parser = argparse.ArgumentParser()
_parser.add_argument("--models-dir", default="./models",
                     help="Target directory for model files (default: ./models, matching path_base_model='.' in config)")
_args, _ = _parser.parse_known_args()
os.environ["PADDLE_PDX_CACHE_HOME"] = os.path.abspath(_args.models_dir)

from paddlex import create_model

MODELS_PP_OCR = [
    "latin_PP-OCRv5_mobile_rec",
    "PP-OCRv6_tiny_det",
]

LAYOUT_HERON_ONNX_REPO = "docling-project/docling-layout-heron-onnx"
FIGURE_CLASSIFIER_REPO = "docling-project/DocumentFigureClassifier-v2.5"


def is_model_present(name: str, target_dir: Path) -> bool:
    """Return True and print a skip message if the model directory already exists and is non-empty."""
    if target_dir.exists() and any(target_dir.iterdir()):
        print(f"  -> {name}: already present at {target_dir}, skipping")
        return True
    return False


def write_rec_dict(model) -> None:
    character_dict = model.config["PostProcess"]["character_dict"]
    dict_path = os.path.join(model.model_dir, "dict.txt")
    with open(dict_path, "w", encoding="utf-8") as f:
        for char in character_dict:
            f.write((char if char is not None else "") + "\n")
    print(f"  -> dictionnaire ({len(character_dict)} caractères) écrit dans {dict_path}")


def paddle_ocr_model(models_dir: Path) -> None:
    for name in MODELS_PP_OCR:
        # PaddleX stores models under {PADDLE_PDX_CACHE_HOME}/official_models/{name}_onnx
        target_dir = models_dir / "official_models" / (name + "_onnx")
        if is_model_present(name, target_dir):
            continue
        print(f"\nDownloading: {name}")
        model = create_model(name, engine="onnxruntime")
        if name.endswith("_rec"):
            write_rec_dict(model)


def docling_model(models_dir: Path) -> None:
    tableformer_dir = models_dir / "docling-project--docling-models" / "model_artifacts" / "tableformer"
    classifier_dir = models_dir / FIGURE_CLASSIFIER_REPO.replace("/", "--")
    if not is_model_present("TableFormer", tableformer_dir) or not is_model_present("DocumentFigureClassifier", classifier_dir):
        print("\nDownloading docling models (TableFormer + DocumentFigureClassifier)")
        download_models(
            output_dir=models_dir,
            with_layout=False,
            with_tableformer=True,
            with_tableformer_v2=False,
            with_picture_classifier=True,
            with_code_formula=False,
            with_rapidocr=False,
            with_easyocr=False,
            progress=True,
        )

    heron_dir = models_dir / LAYOUT_HERON_ONNX_REPO.replace("/", "--")
    if not is_model_present("layout-heron-onnx", heron_dir):
        print("\nDownloading layout model (ONNX variant used in pipeline)")
        download_hf_model(
            repo_id=LAYOUT_HERON_ONNX_REPO,
            local_dir=heron_dir,
            progress=True,
        )


def main(models_dir: str) -> None:
    models_dir = Path(models_dir)
    print(f"Target directory : {models_dir}")
    paddle_ocr_model(models_dir)
    docling_model(models_dir)
    print("\nDone, the models have been downloaded!")


if __name__ == "__main__":
    main(_args.models_dir)
