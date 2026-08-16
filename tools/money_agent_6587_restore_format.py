#!/usr/bin/env python3
"""Restore original BOM/newline format after deterministic text transforms."""

from pathlib import Path
import codecs
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "src/Mod/TechDraw/App/DrawViewDimension.h",
    "src/Mod/TechDraw/App/DrawViewDimension.cpp",
    "src/Mod/TechDraw/Gui/QGIViewDimension.cpp",
    "src/Mod/TechDraw/Gui/CommandExtensionDims.cpp",
    "src/Mod/TechDraw/Gui/Workbench.cpp",
    "src/Mod/TechDraw/Gui/Resources/TechDraw.qrc",
)

for rel in FILES:
    original = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
    current = (ROOT / rel).read_bytes()

    had_bom = original.startswith(codecs.BOM_UTF8)
    original_body = original[len(codecs.BOM_UTF8):] if had_bom else original
    newline = b"\r\n" if b"\r\n" in original_body else b"\n"

    current_body = current[len(codecs.BOM_UTF8):] if current.startswith(codecs.BOM_UTF8) else current
    text = current_body.decode("utf-8").replace("\r\n", "\n")
    encoded = text.replace("\n", newline.decode("ascii")).encode("utf-8")
    if had_bom:
        encoded = codecs.BOM_UTF8 + encoded

    (ROOT / rel).write_bytes(encoded)

print("Original newline/BOM formats restored")
