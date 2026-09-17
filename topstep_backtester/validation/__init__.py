"""Checks that this pipeline is still the thing it claims to be.

Three questions, each answered by reading the tree rather than by trusting a comment:

    layering.py    does anything but the seam touch the upstream package, and is there any
                   order-transmission or credential code anywhere in here?
    integrity.py   does the same input still give the same number, and does every reported
                   figure still correspond to the spec and data that produced it?

These are run by the test suite on every commit. A rule nobody checks is a rule that has
already been broken somewhere you have not looked yet.
"""
from __future__ import annotations

__all__: list[str] = []
