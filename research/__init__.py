"""Lissara Research: Conceptual research case study and technical proposal.

Version 0.1, October 2026. No experimental results claimed.

This module contains the research proposal content previously in MAIN.PY
and index.html, converted to structured Python modules for further development.

Key components documented:
- Proposed system architecture (Core/CLI/Studio)
- Mathematical scene representation (MathScene format)
- Pipeline stages (preprocessing through validation/export)
- Training data strategy (synthetic + licensed anime data)
- Evaluation metrics and research questions
- Risks, limitations, and ethical considerations
"""
from core.lissara_core.scene import MathScene, PathRecord

__all__ = ["MathScene", "PathRecord"]