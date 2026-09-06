#!/usr/bin/env python3
"""
Generate a printable ChArUco calibration board.

    python src/make_board.py                      # sensible default, A3-ish
    python src/make_board.py --square-size-mm 30 --squares 8x6

Two files are written:

  board.svg   Print THIS. SVG carries real physical dimensions, so it
              prints at true scale from any browser or Inkscape without
              depending on DPI guesswork.
  board.png   The same board as a raster, if you prefer to place it in
              another document.

The SVG includes a 100 mm verification ruler. After printing, measure
it. If it is not 100 mm your printer rescaled the page ("fit to page"
is the usual culprit) and EVERY distance ORB-SLAM3 later reports will
be wrong by that same factor.

Then measure one actual square and pass that to calibrate_stereo.py.
Trust the ruler, not the number you asked for.
"""

import argparse
import base64
import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from charuco import CharucoBoardSpec, DICTIONARIES  # noqa: E402


SVG_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
     width="{page_w}mm" height="{page_h}mm"
     viewBox="0 0 {page_w} {page_h}">

  <rect x="0" y="0" width="{page_w}" height="{page_h}" fill="white"/>

  <!-- The board, at exact physical size -->
  <image x="{bx}" y="{by}" width="{bw}" height="{bh}"
         xlink:href="data:image/png;base64,{data}"
         image-rendering="pixelated"/>

  <!-- Verification ruler: this line is exactly 100 mm -->
  <g stroke="black" stroke-width="0.3" fill="black">
    <line x1="{rx}" y1="{ry}" x2="{rx2}" y2="{ry}"/>
    <line x1="{rx}" y1="{ry_a}" x2="{rx}" y2="{ry_b}"/>
    <line x1="{rx2}" y1="{ry_a}" x2="{rx2}" y2="{ry_b}"/>
  </g>
  <text x="{rx}" y="{ry_t}" font-family="sans-serif" font-size="4" fill="black">
    Measure this line: it must be exactly 100 mm. If not, your printer rescaled the page.
  </text>
  <text x="{rx}" y="{ry_t2}" font-family="sans-serif" font-size="4" fill="black">
    {label}
  </text>
</svg>
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    ap = argparse.ArgumentParser(
        description="Generate a printable ChArUco board",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--squares",
        default="8x6",
        help="board size in SQUARES (not inner corners), e.g. 8x6",
    )
    ap.add_argument(
        "--square-size-mm",
        type=float,
        default=40.0,
        help="physical square edge length in mm. Bigger is better for a "
             "fisheye: aim for at least 25 px per square in the image",
    )
    ap.add_argument(
        "--marker-ratio",
        type=float,
        default=0.75,
        help="marker edge as a fraction of the square (0.7-0.8 works well)",
    )
    ap.add_argument("--dictionary", default="DICT_5X5_1000", choices=sorted(DICTIONARIES))
    ap.add_argument("--dpi", type=int, default=300,
                    help="raster resolution. 300 dpi is ~470 px per 40 mm square, "
                         "far more than any printer resolves")
    ap.add_argument("--margin-mm", type=float, default=8.0)
    ap.add_argument("--out", default=os.path.join(root, "calibration"))
    args = ap.parse_args()

    sx, sy = (int(v) for v in args.squares.lower().split("x"))
    square = args.square_size_mm / 1000.0
    marker = square * args.marker_ratio

    spec = CharucoBoardSpec(
        squares_x=sx,
        squares_y=sy,
        square_length=square,
        marker_length=marker,
        dictionary=args.dictionary,
    )

    print()
    print("=" * 62)
    print(" NOVEX CHARUCO BOARD")
    print("=" * 62)
    print(spec.describe())

    board_w_mm = spec.width_m * 1000.0
    board_h_mm = spec.height_m * 1000.0

    for name, w, h in (("A4", 210, 297), ("A4 landscape", 297, 210),
                       ("A3", 297, 420), ("A3 landscape", 420, 297)):
        fits = (board_w_mm + 2 * args.margin_mm <= w and
                board_h_mm + 2 * args.margin_mm <= h)
        print(f"  fits {name:13}: {'yes' if fits else 'NO'}")

    os.makedirs(args.out, exist_ok=True)

    png_path = os.path.join(args.out, "board.png")
    svg_path = os.path.join(args.out, "board.svg")

    img = spec.generate_image(dpi=args.dpi, margin_mm=0)
    cv2.imwrite(png_path, img)

    with open(png_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")

    margin = args.margin_mm
    ruler_block = 22.0

    page_w = board_w_mm + 2 * margin
    page_h = board_h_mm + 2 * margin + ruler_block

    ry = board_h_mm + 2 * margin + 6

    svg = SVG_TEMPLATE.format(
        page_w=f"{page_w:.3f}",
        page_h=f"{page_h:.3f}",
        bx=f"{margin:.3f}", by=f"{margin:.3f}",
        bw=f"{board_w_mm:.3f}", bh=f"{board_h_mm:.3f}",
        data=data,
        rx=f"{margin:.3f}", rx2=f"{margin + 100.0:.3f}",
        ry=f"{ry:.3f}",
        ry_a=f"{ry - 2:.3f}", ry_b=f"{ry + 2:.3f}",
        ry_t=f"{ry + 7:.3f}", ry_t2=f"{ry + 12:.3f}",
        label=(
            f"ChArUco {sx}x{sy}, square {args.square_size_mm:.1f} mm, "
            f"marker {marker * 1000:.1f} mm, {args.dictionary}"
        ),
    )

    with open(svg_path, "w") as f:
        f.write(svg)

    print()
    print(f"  PNG : {png_path}  ({img.shape[1]}x{img.shape[0]} px at {args.dpi} dpi)")
    print(f"  SVG : {svg_path}  <-- print this one")
    print()
    print("PRINTING")
    print("  1. Open board.svg in a browser or Inkscape and print at 100% /")
    print("     'Actual size'. Turn OFF 'fit to page' and 'shrink to fit'.")
    print("  2. Measure the 100 mm ruler line on the print. If it is wrong,")
    print("     the scale is wrong - reprint before going any further.")
    print("  3. Glue the sheet to something rigid and FLAT. A board that")
    print("     curves even slightly will quietly corrupt the calibration.")
    print("  4. Measure one square edge with a ruler and use that value:")
    print()
    print(f"     python src/calibrate_stereo.py --board charuco \\")
    print(f"         --squares {sx}x{sy} --square-size <measured_metres> \\")
    print(f"         --marker-size <measured_metres>")
    print()


if __name__ == "__main__":
    main()
