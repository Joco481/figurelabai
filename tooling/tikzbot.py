#!/usr/bin/env python3
import subprocess, sys, json, yaml, re, shutil
from pathlib import Path
import numpy as np
from skimage.metrics import structural_similarity as ssim
import cv2

ROOT = Path(__file__).resolve().parents[1]
PNG_DIR = ROOT / "png"
TIKZ_DIR = ROOT / "figures" / "tikz"
OUT_DIR = ROOT / "figures" / "out"
MAP_YAML = ROOT / "figures" / "map.yaml"

# Tunable thresholds
SSIM_OK = 0.985

TEMPLATE = r"""
\documentclass[tikz,border=2pt]{standalone}
\input{../preamble/preamble}
\begin{document}
\begin{figurlab}
% --AUTO-START--
% knobs:
% \def\springAmp{0.5}
% \def\springTurns{8}
% \def\axisShift{0.0} % move axis up/down
% \def\lineThick{1.2pt}
% YOUR TIKZ HERE; use the knobs above where possible.
% --AUTO-END--
\end{figurlab}
\end{document}
"""

def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)

def ensure_tex(name):
    tex = TIKZ_DIR / f"{name}.tex"
    if not tex.exists():
        tex.parent.mkdir(parents=True, exist_ok=True)
        tex.write_text(TEMPLATE)
    return tex

def compile_tex(tex):
    run(["latexmk", "-pdf", str(tex)], cwd=ROOT)

def pdf_to_png(pdf_path, png_out):
    # Use Ghostscript or ImageMagick; try gs first
    if shutil.which("gs"):
        run([
            "gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pngalpha",
            "-r300", f"-sOutputFile={png_out}", str(pdf_path)
        ])
    else:
        run(["magick", "-density", "300", str(pdf_path), "-quality", "100", str(png_out)])

def compare(a_path, b_path):
    a = cv2.imread(str(a_path), cv2.IMREAD_UNCHANGED)
    b = cv2.imread(str(b_path), cv2.IMREAD_UNCHANGED)
    # Convert to grayscale for SSIM
    a_gray = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    b_gray = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    # Resize to match if needed
    if a_gray.shape != b_gray.shape:
        b_gray = cv2.resize(b_gray, (a_gray.shape[1], a_gray.shape[0]))
    score, _ = ssim(a_gray, b_gray, full=True)
    return score

def tweak_knobs(tex_path, adjust):
    text = tex_path.read_text()
    # Simple knob edits by regex replacing values in defs
    for knob, newval in adjust.items():
        text = re.sub(rf"(\\def\\{knob}\{{)([^}}]+)(\}})", rf"\g<1>{newval}\g<3>", text)
    tex_path.write_text(text)

def main():
    mapping = {}
    if MAP_YAML.exists():
        mapping = yaml.safe_load(MAP_YAML.read_text()) or {}

    for png in sorted(PNG_DIR.glob("*.png")):
        name = png.stem
        tex = ensure_tex(name)
        pdf = OUT_DIR / f"{name}.pdf"
        genpng = OUT_DIR / f"{name}.png"

        # Try a few refinement rounds
        for attempt in range(6):
            compile_tex(tex)
            pdf_to_png(pdf, genpng)
            score = compare(png, genpng)
            print(f"[{name}] attempt {attempt} SSIM={score:.5f}")

            if score >= SSIM_OK:
                # commit and move on
                run(["git", "add", str(tex), str(pdf), str(genpng)], cwd=ROOT)
                run(["git", "commit", "-m", f"fig({name}): auto-match SSIM {score:.4f}"], cwd=ROOT)
                break
            else:
                # naive heuristic tweaks (example)
                # You can extend with per-figure rules in map.yaml
                adjust = {}
                if score < 0.96:
                    adjust["springAmp"] = "0.7"
                    adjust["springTurns"] = "10"
                else:
                    adjust["lineThick"] = "1.6pt"
                    adjust["axisShift"] = "0.15"

                # Merge with map.yaml hints if present
                if name in mapping.get("hints", {}):
                    adjust.update(mapping["hints"][name])

                tweak_knobs(tex, adjust)
        else:
            print(f"[{name}] did not reach target SSIM; leaving for manual review.")

if __name__ == "__main__":
    main()
