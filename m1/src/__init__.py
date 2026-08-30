"""M1 Document Processing Pipeline.

Shared document-processing infrastructure for the Legal Intelligence Assistant.
Turns raw legal documents (PDF / DOCX / TXT / image) into standardized
``DocumentChunk`` objects consumed by M2/M3 (retrieval + QA) and M5 (contract
intelligence).

Everything runs locally. No cloud APIs, no LangChain.
"""

import os

# Docling's layout model (RT-DETR via transformers) is wrapped in torch.compile.
# On Windows without MSVC on PATH, TorchDynamo tries to invoke `cl` and dies
# with InvalidCxxCompiler, taking the whole Docling stage down. Eager mode is a
# little slower per page but has no toolchain dependency, so we disable Dynamo
# before torch is imported anywhere. Remove this if the firm's servers are Linux
# with a working toolchain and the compile speedup is wanted.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def quiet_third_party_logs(level: int | None = None) -> None:
    """Turn down the ML stack's INFO chatter.

    Docling, RapidOCR, PaddleOCR and transformers all log verbosely at import
    and per page, which buries our own engine-log output. Not applied
    automatically -- call it from an entry point (scripts and the API do) so
    library consumers keep control of their own logging.
    """
    import logging

    level = logging.WARNING if level is None else level
    for name in (
        "docling", "docling_core", "docling_ibm_models", "rapidocr", "RapidOCR",
        "transformers", "torch", "PIL", "matplotlib", "urllib3", "filelock",
        "huggingface_hub", "ppocr", "paddle",
    ):
        logging.getLogger(name).setLevel(level)


__version__ = "0.1.0"
