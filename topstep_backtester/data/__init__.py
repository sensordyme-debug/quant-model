"""Data preparation: reach the canonical layer, do not become a second one.

``quant_brain.data`` already owns adapters, the schema contract, the quality gate and
dataset manifests, and all of it is certified. This directory adds the two things that layer
does not know about - the extra conditions the ENGINE imposes, and the record of what was
loaded for a particular run - and nothing else.
"""
from __future__ import annotations

__all__: list[str] = []
