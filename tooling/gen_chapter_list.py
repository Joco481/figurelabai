#!/usr/bin/env python3
import re, shutil
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
PNG_DIR = ROOT / "png"
TIKZ_DIR = ROOT / "figures" / "tikz"
CH_DIR = ROOT / "figures" / "chapters"
GEN_DIR = CH_DIR / "_generated"
DRIVER_TPL = CH_DIR / "chapter_driver_template.tex"
SNIPPET_TPL = TIKZ_DIR / "_snippet_template.tikz.tex"

CH_RE = re.compile(r"^(?P<ch>\d{1,2})_(?P<idx>\d+)_")

def main():
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    TIKZ_DIR.mkdir(parents=True, exist_ok=True)

    buckets = defaultdict(list)  # ch -> [(idx, name, png)]
    misc = []

    for png in sorted(PNG_DIR.glob("*.png")):
        m = CH_RE.match(png.name)
        if m:
            ch = int(m.group("ch"))
            idx = int(m.group("idx"))
            buckets[ch].append((idx, png.stem, png))
        else:
            misc.append(png)

    # per chapter
    for ch, items in sorted(buckets.items()):
        items.sort(key=lambda x: (x[0], x[1]))  # by idx then name
        ch_slug = f"ch{ch:02d}"
        ch_snip_dir = TIKZ_DIR / ch_slug
        ch_snip_dir.mkdir(parents=True, exist_ok=True)

        # ensure snippets exist
        snippet_rel_paths = []
        for _, stem, _ in items:
            snip = ch_snip_dir / f"{stem}.tikz.tex"
            if not snip.exists():
                shutil.copyfile(SNIPPET_TPL, snip)
            snippet_rel_paths.append(Path("..")/ "tikz" / ch_slug / f"{stem}.tikz.tex")

        # write generated list
        lst = GEN_DIR / f"{ch_slug}_list.tex"
        with lst.open("w", encoding="utf-8") as f:
            for rel in snippet_rel_paths:
                f.write("\\begin{figurlab}\n  \\input{" + str(rel).replace('\\','/') + "}\n\\end{figurlab}\n\n")

        # ensure driver
        drv = CH_DIR / f"{ch_slug}_figs.tex"
        if not drv.exists():
            text = DRIVER_TPL.read_text(encoding="utf-8")
            text = text.replace("__CHAPTER__", ch_slug)
            drv.write_text(text, encoding="utf-8")

    # misc
    if misc:
        misc_snip_dir = TIKZ_DIR / "misc"
        misc_snip_dir.mkdir(parents=True, exist_ok=True)
        snippet_rel_paths = []
        for png in sorted(misc):
            stem = png.stem
            snip = misc_snip_dir / f"{stem}.tikz.tex"
            if not snip.exists():
                shutil.copyfile(SNIPPET_TPL, snip)
            snippet_rel_paths.append(Path("..")/ "tikz" / "misc" / f"{stem}.tikz.tex")

        lst = GEN_DIR / "misc_list.tex"
        with lst.open("w", encoding="utf-8") as f:
            for rel in snippet_rel_paths:
                f.write("\\begin{figurlab}\n  \\input{" + str(rel).replace('\\','/') + "}\n\\end{figurlab}\n\n")

        drv = CH_DIR / "misc_figs.tex"
        if not drv.exists():
            text = DRIVER_TPL.read_text(encoding="utf-8")
            text = text.replace("__CHAPTER__", "misc")
            drv.write_text(text, encoding="utf-8")

if __name__ == "__main__":
    main()
