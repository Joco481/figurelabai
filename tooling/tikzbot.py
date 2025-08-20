#!/usr/bin/env python3
import subprocess, json, re, shutil
from pathlib import Path
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

ROOT = Path(__file__).resolve().parents[1]
PNG_DIR = ROOT / "png"
CH_DIR = ROOT / "figures" / "chapters"
GEN_DIR = CH_DIR / "_generated"
OUT_DIR = ROOT / "figures" / "out"
TIKZ_DIR = ROOT / "figures" / "tikz"

SSIM_OK = 0.985

def run(cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True)

def compile_driver(driver_tex):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    run(["latexmk", "-pdf", str(driver_tex)], cwd=ROOT)

def pdf_to_png(pdf_path, out_prefix):
    if shutil.which("gs"):
        run([
            "gs","-dSAFER","-dBATCH","-dNOPAUSE","-sDEVICE=pngalpha","-r300",
            f"-sOutputFile={str(out_prefix)}_%03d.png", str(pdf_path)
        ])
    elif shutil.which("magick"):
        run(["magick","-density","300",str(pdf_path),str(out_prefix)+"_%03d.png"])
    else:
        raise RuntimeError("Need Ghostscript or ImageMagick")

def to_gray(imgpath):
    img = cv2.imread(str(imgpath), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError(f"Cannot read {imgpath}")
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img

def ssim_score(a, b):
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    score, _ = ssim(a, b, full=True)
    return score

def tweak_knobs(snippet_path, adjust):
    txt = snippet_path.read_text(encoding="utf-8")
    for knob, val in adjust.items():
        # replace \def\knob{...}
        txt = re.sub(rf"(\\def\\{knob}\{{)[^}}]+(\}})", rf"\g<1>{val}\2", txt)
    snippet_path.write_text(txt, encoding="utf-8")

def build_manifest_for_driver(ch_slug):
    """Map page -> (target_png, snippet_path)"""
    # Recreate list of snippets in the same order as _generated list
    list_tex = GEN_DIR / f"{ch_slug}_list.tex"
    items = []
    for line in list_tex.read_text(encoding="utf-8").splitlines():
        m = re.search(r"\\input\{([^\}]+)\}", line)
        if m:
            rel = m.group(1)
            snip = (CH_DIR / rel).resolve()  # via chapters dir
            # deduce target png by snippet filename
            stem = Path(rel).name.replace(".tikz.tex","")
            # If it looks like NN_M_xxx, use that png name; else misc name
            target = PNG_DIR / f"{stem}.png"
            if not target.exists():
                # fall back: misc arbitrary names
                target = PNG_DIR / f"{stem}.png"
            items.append({"stem": stem, "snippet": snip, "target": target})
    return items

def refine_page_once(item, gen_png):
    # Compare and optionally tweak knobs
    a = to_gray(item["target"])
    b = to_gray(gen_png)
    score = ssim_score(a, b)
    print(f"  - {item['stem']}: SSIM={score:.5f}")
    if score >= SSIM_OK:
        return True, score
    # simple heuristic knobs – extend with your own rules
    adjust = {}
    if score < 0.96:
        adjust.update({"springAmp":"0.8","springTurns":"12"})
    else:
        adjust.update({"lineThick":"1.6pt","axisLift":"0.12"})
    tweak_knobs(Path(item["snippet"]), adjust)
    return False, score

def main():
    # 1) Generate/update chapter lists and drivers
    run(["python", "tooling/gen_chapter_list.py"], cwd=ROOT)

    # 2) Find drivers to process (chapters + misc)
    drivers = sorted(CH_DIR.glob("*_figs.tex"))

    for drv in drivers:
        ch_slug = drv.stem.replace("_figs","")  # ch11, misc, ...
        print(f"[{ch_slug}] compiling...")
        compile_driver(drv)

        pdf = drv.with_suffix(".pdf")
        out_prefix = OUT_DIR / ch_slug
        pdf_to_png(pdf, out_prefix)

        items = build_manifest_for_driver(ch_slug)
        # Iterate pages in order
        for i, item in enumerate(items, start=1):
            gen_png = Path(f"{out_prefix}_{i:03d}.png")
            # Try up to N refinement rounds for this single figure
            for attempt in range(6):
                ok, score = refine_page_once(item, gen_png)
                if ok:
                    break
                # Recompile only this one snippet quickly via a temporary 1-figure driver
                tmp = OUT_DIR / f"tmp_single_{ch_slug}.tex"
                tmp.write_text(
                    "\\documentclass{ximera}\n"
                    "\\input{../../preamble/preamble}\n"
                    "\\PassOptionsToPackage{active,tightpage}{preview}\n"
                    "\\usepackage{preview}\n\\PreviewEnvironment{figurlab}\n"
                    "\\begin{document}\n\\begin{figurlab}\n"
                    f"\\input{{{item['snippet'].relative_to(CH_DIR).as_posix()}}}\n"
                    "\\end{figurlab}\n\\end{document}\n",
                    encoding="utf-8"
                )
                compile_driver(tmp)
                pdf_to_png(tmp.with_suffix(".pdf"), out_prefix)  # overwrites _001.png
                gen_png = Path(f"{out_prefix}_001.png")          # tmp has single page

            # Commit snippet + last output
            subprocess.run(["git","add",str(item["snippet"]), str(gen_png)], cwd=ROOT)
        subprocess.run(["git","commit","-m",f"{ch_slug}: auto-fig updates"], cwd=ROOT)

if __name__ == "__main__":
    main()
