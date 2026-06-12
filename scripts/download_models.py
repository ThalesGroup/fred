#!/usr/bin/env python3
import argparse
import os


_parser = argparse.ArgumentParser()
_parser.add_argument("--models-dir", required=True)
_args, _ = _parser.parse_known_args()
os.environ["PADDLE_PDX_CACHE_HOME"] = os.path.abspath(_args.models_dir)

from paddlex import create_model

MODELS = [
    "PP-OCRv5_mobile_det",
    "latin_PP-OCRv5_mobile_rec",
]


def main(models_dir):
    print(f"Target directory : {models_dir}")
    for name in MODELS:
        print(f"\nDownloading {name}...")
        create_model(name)
    print("\nDone")


if __name__ == "__main__":
    main(_args.models_dir)
