#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IntroAct-TS ICLR 2027 论文图源生成器.

单一几何定义 -> 同时输出:
  *.eps   可编辑矢量图源 (Illustrator / Inkscape / Word 可打开)
  *.pptx  可编辑 PowerPoint 图源
  *.pdf    由 eps 经 ghostscript 转出, 供 pdflatex 直接 \\includegraphics

画布尺寸 = 论文中的最终显示尺寸 (pt), 因此 LaTeX 里用 width=\\textwidth 即可,
字号即为真实字号 (6-8pt).

用法:
  python build_figures.py            # 生成 eps + pptx
  bash build_pdf.sh                  # eps -> pdf (需要 ghostscript)
"""

from __future__ import annotations

import os
import sys

# --------------------------------------------------------------------------
# 调色板 (浅色主题, 黑白打印亦可区分)
# --------------------------------------------------------------------------
INK = (0.11, 0.12, 0.14)
MUTED = (0.42, 0.45, 0.49)
FAINT = (0.62, 0.65, 0.68)
BLUE = (0.13, 0.33, 0.60)
BLUE_L = (0.90, 0.94, 0.99)
AMBER = (0.68, 0.42, 0.04)
AMBER_L = (0.995, 0.95, 0.86)
GREEN = (0.10, 0.44, 0.31)
GREEN_L = (0.90, 0.96, 0.93)
RED = (0.68, 0.17, 0.17)
RED_L = (0.99, 0.92, 0.92)
GREY_L = (0.945, 0.945, 0.955)
GREY_M = (0.80, 0.81, 0.83)
WHITE = (1.0, 1.0, 1.0)

FONT = "Helvetica"
FONT_B = "Helvetica-Bold"
FONT_I = "Helvetica-Oblique"


_ASCII_FOLD = {
    "\u2014": "-",   # em dash
    "\u2013": "-",   # en dash
    "\u2212": "-",   # minus sign
    "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"',
    "\u2026": "...",
    "\u2192": "->",
    "\u00d7": "x",
    "\u2265": ">=", "\u2264": "<=", "\u2260": "!=",
    "\u03bb": "lambda", "\u03c4": "tau", "\u03b8": "theta",
    "\u0394": "Delta", "\u03b1": "alpha", "\u03b2": "beta",
    "\u2208": "in", "\u227b": ">", "\u2261": "=",
    "\u2a2f": "@",
}


def esc(s: str) -> str:
    """转义 PostScript 字符串字面量。

    EPS 输出固定使用 latin-1 编码，任何超出 latin-1 的字符（破折号、箭头、
    希腊字母等）都会让 write() 抛 UnicodeEncodeError，所以这里先做一次
    ASCII 折叠。PPTX 路径不经过本函数，仍保留原始 Unicode 字符。
    """
    for u, a in _ASCII_FOLD.items():
        s = s.replace(u, a)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


class Fig:
    """极简绘图 DSL, 坐标为左上原点 (x 向右, y 向下)."""

    def __init__(self, w: float, h: float, name: str):
        self.w, self.h, self.name = w, h, name
        self.ops: list[tuple] = []

    # ---------------- primitives ----------------
    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.7, r=0, dash=None):
        self.ops.append(("rect", x, y, w, h, fill, stroke, lw, r, dash))

    def line(self, x1, y1, x2, y2, color=INK, lw=0.7, dash=None):
        self.ops.append(("line", x1, y1, x2, y2, color, lw, dash))

    def arrow(self, x1, y1, x2, y2, color=INK, lw=0.9, head=4.0, dash=None):
        self.ops.append(("arrow", x1, y1, x2, y2, color, lw, head, dash))

    def poly(self, pts, color=BLUE, lw=1.0, dash=None):
        self.ops.append(("poly", list(pts), color, lw, dash))

    def text(self, x, y, s, size=6.5, color=INK, align="l", bold=False, italic=False):
        self.ops.append(("text", x, y, s, size, color, align, bold, italic))

    def diamond(self, cx, cy, w, h, fill=AMBER_L, stroke=AMBER, lw=0.8):
        pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
        self.ops.append(("diamond", pts, fill, stroke, lw))

    def circle(self, cx, cy, rad, fill=None, stroke=INK, lw=0.7):
        self.ops.append(("circle", cx, cy, rad, fill, stroke, lw))

    # ---------------- helpers ----------------
    def chip(self, x, y, w, h, label, fill=BLUE_L, stroke=BLUE, size=6.0, color=INK):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, lw=0.6, r=2.0)
        self.text(x + w / 2, y + h / 2 + size * 0.34, label, size=size, color=color, align="c")

    def box(self, x, y, w, h, lines, fill=GREY_L, stroke=GREY_M, size=6.5, lh=None,
            color=INK, bold_first=False):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, lw=0.7, r=2.5)
        if isinstance(lines, str):
            lines = [lines]
        lh = lh or size + 1.9
        total = len(lines) * lh
        y0 = y + h / 2 - total / 2 + lh * 0.72
        for i, ln in enumerate(lines):
            self.text(x + w / 2, y0 + i * lh, ln, size=size, color=color, align="c",
                      bold=(bold_first and i == 0))

    def caption(self, x, y, w, s, size=6.0, color=MUTED):
        self.text(x + w / 2, y, s, size=size, color=color, align="c")

    def axes(self, x, y, w, h, xlabel="", ylabel="", ticks_x=(), ticks_y=()):
        """结果图骨架: 带刻度的空坐标系."""
        self.line(x, y + h, x + w, y + h, INK, 0.7)
        self.line(x, y, x, y + h, INK, 0.7)
        for tx, lab in ticks_x:
            px = x + tx * w
            self.line(px, y + h, px, y + h + 2.5, INK, 0.6)
            self.text(px, y + h + 9.0, lab, size=5.4, color=MUTED, align="c")
        for ty, lab in ticks_y:
            py = y + h - ty * h
            self.line(x - 2.5, py, x, py, INK, 0.6)
            self.text(x - 3.6, py + 1.9, lab, size=5.4, color=MUTED, align="r")
        if xlabel:
            self.text(x + w / 2, y + h + 17.5, xlabel, size=6.0, color=INK, align="c")
        if ylabel:
            # EPS 发射器不支持文字旋转, 因此 y 轴标题放在坐标区左上角水平排布,
            # 避免横排文字压在轴线上。
            self.text(x - 3.0, y - 5.0, ylabel, size=5.4, color=INK, align="l")

    # ---------------- EPS ----------------
    def _eps_color(self, c):
        return "%.4f %.4f %.4f setrgbcolor" % c

    def _eps_path_lines(self, kind, o):
        """只构造路径本身（不含 fill / stroke）。"""
        out = []
        if kind == "rect":
            _, x, y, w, h, fill, stroke, lw, r, dash = o
            if r:
                k = r * 0.5523
                x2, y2 = x + w, y + h
                out.append("%.3f %.3f moveto" % (x + r, y))
                out.append("%.3f %.3f %.3f %.3f %.3f %.3f curveto" % (x2 - r, y, x2, y + r, x2, y + r))
                out.append("%.3f %.3f lineto" % (x2, y2 - r))
                out.append("%.3f %.3f %.3f %.3f %.3f %.3f curveto" % (x2, y2 - r, x2 - r, y2, x2 - r, y2))
                out.append("%.3f %.3f lineto" % (x + r, y2))
                out.append("%.3f %.3f %.3f %.3f %.3f %.3f curveto" % (x + r, y2, x, y2 - r, x, y2 - r))
                out.append("%.3f %.3f lineto" % (x, y + r))
                out.append("%.3f %.3f %.3f %.3f %.3f %.3f curveto" % (x, y + r, x + r, y, x + r, y))
            else:
                # 不用 Level-2 的 `rect` 算子: 部分 ghostscript 构建未定义它。
                x2, y2 = x + w, y + h
                out.append("%.3f %.3f moveto" % (x, y))
                out.append("%.3f %.3f lineto" % (x2, y))
                out.append("%.3f %.3f lineto" % (x2, y2))
                out.append("%.3f %.3f lineto" % (x, y2))
            out.append("closepath")
        return out

    def _eps_draw(self, kind, o):
        """按 `newpath -> 路径 -> fill -> newpath -> 路径 -> stroke` 输出。

        必须重建两次路径: PostScript 的 fill/stroke 都会清空当前路径, 且不同
        ghostscript 构建对"是否清空"的行为并不一致。若不显式 newpath, 路径会
        跨图形累积, 后续 fill 会把前面所有图形一起重填 —— 表现为颜色错位。
        """
        L = []
        if kind == "rect":
            _, x, y, w, h, fill, stroke, lw, r, dash = o
            pl = self._eps_path_lines("rect", o)
            if fill is not None:
                if dash:
                    L.append("[%s] 0 setdash" % " ".join("%.2f" % d for d in dash))
                L.append("newpath")
                L.extend(pl)
                L.append("gsave %s fill grestore" % self._eps_color(fill))
            if stroke is not None:
                if dash:
                    L.append("[%s] 0 setdash" % " ".join("%.2f" % d for d in dash))
                L.append("newpath")
                L.extend(pl)
                L.append("gsave %s %.2f setlinewidth stroke grestore" % (self._eps_color(stroke), lw))
            if dash:
                L.append("[] 0 setdash")
            L.append("newpath")
        elif kind == "line":
            _, x1, y1, x2, y2, c, lw, dash = o
            if dash:
                L.append("[%s] 0 setdash" % " ".join("%.2f" % d for d in dash))
            L.append("newpath %.3f %.3f moveto %.3f %.3f lineto gsave %s %.2f setlinewidth stroke grestore newpath"
                     % (x1, y1, x2, y2, self._eps_color(c), lw))
            if dash:
                L.append("[] 0 setdash")
        elif kind == "arrow":
            _, x1, y1, x2, y2, c, lw, head, dash = o
            if dash:
                L.append("[%s] 0 setdash" % " ".join("%.2f" % d for d in dash))
            dx, dy = x2 - x1, y2 - y1
            n = (dx * dx + dy * dy) ** 0.5 or 1.0
            ux, uy = dx / n, dy / n
            bx, by = x2 - ux * head, y2 - uy * head
            px, py = -uy, ux
            L.append("newpath %.3f %.3f moveto %.3f %.3f lineto gsave %s %.2f setlinewidth stroke grestore newpath"
                     % (x1, y1, bx, by, self._eps_color(c), lw))
            L.append("newpath %.3f %.3f moveto %.3f %.3f lineto %.3f %.3f lineto closepath "
                     "gsave %s fill grestore newpath"
                     % (x2, y2, bx + px * head * 0.42, by + py * head * 0.42,
                        bx - px * head * 0.42, by - py * head * 0.42, self._eps_color(c)))
            if dash:
                L.append("[] 0 setdash")
        elif kind == "poly":
            _, pts, c, lw, dash = o
            if dash:
                L.append("[%s] 0 setdash" % " ".join("%.2f" % d for d in dash))
            L.append("newpath %.3f %.3f moveto" % pts[0])
            for p in pts[1:]:
                L.append("%.3f %.3f lineto" % p)
            L.append("gsave %s %.2f setlinewidth stroke grestore newpath" % (self._eps_color(c), lw))
            if dash:
                L.append("[] 0 setdash")
        elif kind == "diamond":
            _, pts, fill, stroke, lw = o
            L.append("newpath %.3f %.3f moveto" % pts[0])
            for p in pts[1:]:
                L.append("%.3f %.3f lineto" % p)
            L.append("closepath")
            L.append("gsave %s fill grestore" % self._eps_color(fill))
            L.append("gsave %s %.2f setlinewidth stroke grestore newpath" % (self._eps_color(stroke), lw))
        elif kind == "circle":
            _, cx, cy, rad, fill, stroke, lw = o
            L.append("newpath %.3f %.3f %.3f 0 360 arc closepath" % (cx, cy, rad))
            if fill is not None:
                L.append("gsave %s fill grestore" % self._eps_color(fill))
            if stroke is not None:
                L.append("gsave %s %.2f setlinewidth stroke grestore" % (self._eps_color(stroke), lw))
            L.append("newpath")
        return L

    def _eps_emit(self):
        L = []
        L.append("%!PS-Adobe-3.0 EPSF-3.0")
        L.append("%%%%BoundingBox: 0 0 %d %d" % (round(self.w), round(self.h)))
        L.append("%%Creator: IntroAct-TS figure generator")
        L.append("%%Title: %s" % self.name)
        L.append("%%EndComments")
        L.append("1 setlinejoin 1 setlinecap")
        L.append("%d %d translate 1 -1 scale" % (0, round(self.h)))
        L.append("/Lft { gsave translate 1 -1 scale 0 0 moveto show grestore } bind def")
        L.append("/Ctr { gsave translate 1 -1 scale 0 0 moveto dup stringwidth pop -0.5 mul 0 rmoveto show grestore } bind def")
        L.append("/Rgt { gsave translate 1 -1 scale 0 0 moveto dup stringwidth pop -1 mul 0 rmoveto show grestore } bind def")
        for o in self.ops:
            k = o[0]
            if k == "text":
                _, x, y, s, size, c, align, bold, italic = o
                f = FONT_B if bold else (FONT_I if italic else FONT)
                proc = {"l": "Lft", "c": "Ctr", "r": "Rgt"}[align]
                # 栈序为 "(string) x y PROC": translate 需要先弹出 y 再弹出 x,
                # 因此字符串必须最先压栈。文字之前先 newpath, 否则 moveto 会把
                # 游离子路径留在当前路径里污染下一个图形。
                L.append("newpath gsave /%s findfont %.2f scalefont setfont %s (%s) %.3f %.3f %s grestore newpath"
                         % (f, size, self._eps_color(c), esc(s), x, y, proc))
            else:
                L.extend(self._eps_draw(k, o))
        L.append("showpage")
        L.append("%%EOF")
        return "\n".join(L) + "\n"

    # ---------------- PPTX ----------------
    def _pptx(self, path):
        from pptx import Presentation
        from pptx.util import Emu, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.enum.shapes import MSO_SHAPE

        PT = 12700  # EMU per point

        def rgb(c):
            return RGBColor(int(c[0] * 255), int(c[1] * 255), int(c[2] * 255))

        prs = Presentation()
        prs.slide_width = Emu(int(self.w * PT))
        prs.slide_height = Emu(int(self.h * PT))
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        shapes = slide.shapes

        for o in self.ops:
            k = o[0]
            if k == "rect":
                _, x, y, w, h, fill, stroke, lw, r, dash = o
                shp = shapes.add_shape(
                    MSO_SHAPE.ROUNDED_RECTANGLE if r else MSO_SHAPE.RECTANGLE,
                    Emu(int(x * PT)), Emu(int(y * PT)), Emu(int(w * PT)), Emu(int(h * PT)))
                if r:
                    shp.adjustments[0] = min(0.5, r / max(w, h) / 2.0)
                if fill is None:
                    shp.fill.background()
                else:
                    shp.fill.solid()
                    shp.fill.fore_color.rgb = rgb(fill)
                if stroke is None:
                    shp.line.fill.background()
                else:
                    shp.line.color.rgb = rgb(stroke)
                    shp.line.width = Pt(max(lw, 0.5))
                shp.shadow.inherit = False
            elif k == "line":
                _, x1, y1, x2, y2, c, lw, dash = o
                cn = shapes.add_connector(1, Emu(int(x1 * PT)), Emu(int(y1 * PT)),
                                          Emu(int(x2 * PT)), Emu(int(y2 * PT)))
                cn.line.color.rgb = rgb(c)
                cn.line.width = Pt(max(lw, 0.5))
                if dash:
                    from pptx.enum.dml import MSO_LINE_DASH_STYLE
                    cn.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            elif k == "arrow":
                _, x1, y1, x2, y2, c, lw, head, dash = o
                cn = shapes.add_connector(2, Emu(int(x1 * PT)), Emu(int(y1 * PT)),
                                          Emu(int(x2 * PT)), Emu(int(y2 * PT)))
                cn.line.color.rgb = rgb(c)
                cn.line.width = Pt(max(lw, 0.5))
                if dash:
                    from pptx.enum.dml import MSO_LINE_DASH_STYLE
                    cn.line.dash_style = MSO_LINE_DASH_STYLE.DASH
            elif k == "poly":
                _, pts, c, lw, dash = o
                fb = shapes.build_freeform(Emu(int(pts[0][0] * PT)), Emu(int(pts[0][1] * PT)), scale=1.0)
                fb.add_line_segments([(Emu(int(px * PT)), Emu(int(py * PT))) for px, py in pts[1:]],
                                     close=False)
                shp = fb.convert_to_shape()
                shp.fill.background()
                shp.line.color.rgb = rgb(c)
                shp.line.width = Pt(max(lw, 0.5))
                shp.shadow.inherit = False
            elif k == "diamond":
                _, pts, fill, stroke, lw = o
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                shp = shapes.add_shape(MSO_SHAPE.DIAMOND, Emu(int(min(xs) * PT)), Emu(int(min(ys) * PT)),
                                       Emu(int((max(xs) - min(xs)) * PT)), Emu(int((max(ys) - min(ys)) * PT)))
                shp.fill.solid()
                shp.fill.fore_color.rgb = rgb(fill)
                shp.line.color.rgb = rgb(stroke)
                shp.line.width = Pt(max(lw, 0.5))
                shp.shadow.inherit = False
            elif k == "circle":
                _, cx, cy, rad, fill, stroke, lw = o
                shp = shapes.add_shape(MSO_SHAPE.OVAL, Emu(int((cx - rad) * PT)), Emu(int((cy - rad) * PT)),
                                       Emu(int(2 * rad * PT)), Emu(int(2 * rad * PT)))
                if fill is None:
                    shp.fill.background()
                else:
                    shp.fill.solid()
                    shp.fill.fore_color.rgb = rgb(fill)
                if stroke is None:
                    shp.line.fill.background()
                else:
                    shp.line.color.rgb = rgb(stroke)
                    shp.line.width = Pt(max(lw, 0.5))
                shp.shadow.inherit = False
            elif k == "text":
                _, x, y, s, size, c, align, bold, italic = o
                pad = 120
                tb = shapes.add_textbox(Emu(int((x - pad) * PT)), Emu(int((y - size * 1.35) * PT)),
                                        Emu(int((pad * 2) * PT)), Emu(int(size * 2.4 * PT)))
                tf = tb.text_frame
                tf.word_wrap = False
                tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
                tf.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = tf.paragraphs[0]
                p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
                r = p.add_run()
                r.text = s
                r.font.size = Pt(size)
                r.font.bold = bold
                r.font.italic = italic
                r.font.color.rgb = rgb(c)
                r.font.name = "Helvetica"
        prs.save(path)

    # ---------------- public ----------------
    def save(self, outdir: str):
        base = os.path.join(outdir, self.name)
        with open(base + ".eps", "w", encoding="latin-1", newline="\n") as f:
            f.write(self._eps_emit())
        try:
            self._pptx(base + ".pptx")
        except Exception as e:  # pptx 可选
            print("  [warn] pptx failed for %s: %s" % (self.name, e), file=sys.stderr)
        print("  wrote %s.eps / .pptx" % base)


# ==========================================================================
# Figure 1 -- Repair is a selective forecasting decision
# ==========================================================================
def fig1():
    W, H = 396.0, 198.0
    f = Fig(W, H, "fig1_selective_governance")

    colx = [4.0, 138.0, 272.0]
    colw = [128.0, 128.0, 120.0]

    # ---- panel A ----
    f.text(colx[0] + colw[0] / 2, 9.0, "(a) Same incomplete context,", size=6.4, bold=True, align="c")
    f.text(colx[0] + colw[0] / 2, 17.5, "different best action", size=6.4, bold=True, align="c")

    eps = [("Episode A", "KEEP is best", GREEN, GREEN_L),
           ("Episode B", "Single TS-ICL is best", BLUE, BLUE_L),
           ("Episode C", "Multi TS-ICL is best", AMBER, AMBER_L)]
    for i, (name, best, col, coll) in enumerate(eps):
        y = 26.0 + i * 47.0
        f.rect(colx[0], y, colw[0], 30.0, fill=WHITE, stroke=GREY_M, lw=0.6, r=2.0)
        # 迷你序列: 观测段 + 缺口 + 观测段
        gx0, gx1 = colx[0] + 40.0, colx[0] + 66.0
        base = y + 18.0
        pts = []
        import math
        for k in range(0, 101):
            px = colx[0] + 5.0 + k / 100.0 * (colw[0] - 10.0)
            if gx0 <= px <= gx1:
                continue
            py = base - 7.0 * math.sin(k / 7.0) - 2.0 * math.sin(k / 2.3)
            pts.append((px, py))
        f.poly(pts, color=INK, lw=0.9)
        f.rect(gx0, y + 5.0, gx1 - gx0, 20.0, fill=RED_L, stroke=RED, lw=0.5)
        f.text((gx0 + gx1) / 2, y + 16.5, "gap", size=5.0, color=RED, align="c")
        f.text(colx[0] + colw[0] / 2, y + 38.0, "%s: %s" % (name, best), size=5.8, color=col, align="c")
        f.text(colx[0] + colw[0] / 2, y + 45.5, "same repair, different utility", size=5.2,
               color=MUTED, align="c")

    # ---- panel B ----
    f.text(colx[1] + colw[1] / 2, 9.0, "(b) Counterfactual replay", size=6.4, bold=True, align="c")
    f.text(colx[1] + colw[1] / 2, 17.5, "on historical TRAIN windows", size=6.4, bold=True, align="c")
    bx, bw = colx[1], colw[1]
    f.box(bx, 26.0, bw, 20.0, ["Fully observed TRAIN window", "(its future is legal history)"],
          fill=GREY_L, size=5.6)
    f.arrow(bx + bw / 2, 47.0, bx + bw / 2, 55.0, INK, 0.9, 3.4)
    f.box(bx, 56.0, bw, 20.0, ["Inject the deployment", "missingness mechanism"],
          fill=RED_L, stroke=RED, size=5.6)
    f.arrow(bx + bw / 2, 77.0, bx + bw / 2, 85.0, INK, 0.9, 3.4)
    f.box(bx, 86.0, bw, 24.0, ["Execute every legal action", "with the frozen forecaster F",
                               "and observe the true future"],
          fill=BLUE_L, stroke=BLUE, size=5.6)
    f.arrow(bx + bw / 2, 111.0, bx + bw / 2, 119.0, INK, 0.9, 3.4)
    f.box(bx, 120.0, bw, 24.0, ["Record the realised task loss",
                                "L[i,a] and regret r[i,a] = L[i,a] - L*[i]"],
          fill=GREEN_L, stroke=GREEN, size=5.2)
    f.text(bx + bw / 2, 152.0, "replay bank  B = {(z[i], a, L[i,a])}", size=5.6, color=GREEN, align="c")
    f.text(bx + bw / 2, 161.0, "the bank stores a task consequence,", size=5.2, color=MUTED, align="c")
    f.text(bx + bw / 2, 169.0, "not a reconstruction score", size=5.2, color=MUTED, align="c")

    # ---- panel C ----
    f.text(colx[2] + colw[2] / 2, 9.0, "(c) Score -> rank -> select / KEEP", size=6.2,
           bold=True, align="c")
    cx, cw = colx[2], colw[2]
    f.box(cx, 26.0, cw, 18.0, ["New request: X, M"], fill=GREY_L, size=5.8)
    f.arrow(cx + cw / 2, 45.0, cx + cw / 2, 52.0, INK, 0.9, 3.4)
    f.box(cx, 53.0, cw, 20.0, ["Observable state z", "(no forecast is read)"],
          fill=BLUE_L, stroke=BLUE, size=5.6)
    f.arrow(cx + cw / 2, 74.0, cx + cw / 2, 81.0, INK, 0.9, 3.4)
    f.box(cx, 82.0, cw, 22.0, ["Regret-aware scoring",
                               "S[a] over the replay bank B"],
          fill=AMBER_L, stroke=AMBER, size=5.2)
    f.arrow(cx + cw / 2, 105.0, cx + cw / 2, 112.0, INK, 0.9, 3.4)
    f.diamond(cx + cw / 2, 126.0, 88.0, 26.0)
    f.text(cx + cw / 2, 127.8, "argmax S[a] = KEEP ?", size=5.4, align="c")
    f.arrow(cx + 18.0, 139.0, cx + 18.0, 150.0, GREEN, 1.0, 3.4)
    f.text(cx + 14.0, 147.0, "yes", size=5.2, color=GREEN, align="r")
    f.arrow(cx + cw - 18.0, 139.0, cx + cw - 18.0, 150.0, RED, 1.0, 3.4)
    f.text(cx + cw - 14.0, 147.0, "no", size=5.2, color=RED, align="l")
    f.box(cx - 2.0, 151.0, cw / 2 - 4.0, 26.0, ["KEEP", "input untouched"],
          fill=RED_L, stroke=RED, size=5.6, bold_first=True)
    f.box(cx + cw / 2 + 4.0, 151.0, cw / 2 - 2.0, 26.0, ["SELECT", "execute F(X[a*])"],
          fill=GREEN_L, stroke=GREEN, size=5.6, bold_first=True)
    f.text(198.0, 189.0, "KEEP is one of the arms, so abstention is a decision outcome",
           size=5.2, color=MUTED, align="c")

    # 面板分隔
    f.line(colx[1] - 5.0, 24.0, colx[1] - 5.0, 182.0, GREY_M, 0.5, dash=(1.5, 2.0))
    f.line(colx[2] - 5.0, 24.0, colx[2] - 5.0, 182.0, GREY_M, 0.5, dash=(1.5, 2.0))
    return f


# ==========================================================================
# Figure 2 -- IntroAct-TS architecture
# ==========================================================================
def fig2():
    W, H = 396.0, 206.0
    f = Fig(W, H, "fig2_introact_architecture")
    BW, GAP = 91.0, 8.0

    # ---------------- offline band ----------------
    f.text(4.0, 9.0, "Offline  (TRAIN only \u2014 the only place a future is read)",
           size=6.0, bold=True, color=GREEN)
    off = [
        ["Complete historical window", "(X_i, y_i); its future", "is already legal history"],
        ["Inject the deployment", "missingness mechanism", "-> controlled incomplete context"],
        ["Execute every legal action", "with the frozen forecaster F;", "record L[i,a] and r[i,a]"],
        ["Counterfactual replay bank", "B = {(z[i], a, L[i,a])}", "frozen once, read-only"],
    ]
    for i, lines in enumerate(off):
        x = 4.0 + i * (BW + GAP)
        last = (i == len(off) - 1)
        f.box(x, 15.0, BW, 34.0, lines,
              fill=(GREEN_L if last else WHITE), stroke=(GREEN if last else GREY_M), size=5.0)
        if not last:
            f.arrow(x + BW + 0.5, 32.0, x + BW + GAP - 0.5, 32.0, INK, 0.9, 3.2)

    f.line(4.0, 56.0, 392.0, 56.0, GREY_M, 0.7, dash=(2.0, 2.0))
    f.text(198.0, 61.0, "no future target crosses this line", size=5.2, color=RED, align="c")

    # ---------------- online band ----------------
    f.text(4.0, 72.0, "Online  (deployment \u2014 no future is available)",
           size=6.0, bold=True, color=BLUE)
    onl = [
        ["Incomplete context", "(X, M) at the", "forecast origin"],
        ["Observable state z", "episode + intervention", "state; no forecast read"],
        ["Regret-aware scoring", "S[a] over the frozen bank;", "a* = argmax S[a]"],
        ["Frozen TSFM, one call", "F(X[a*]) is returned;", "KEEP is one of the arms"],
    ]
    for i, lines in enumerate(onl):
        x = 4.0 + i * (BW + GAP)
        hi = (i == 2)
        f.box(x, 78.0, BW, 34.0, lines,
              fill=(BLUE_L if hi else WHITE), stroke=(BLUE if hi else GREY_M), size=5.0)
        if i < len(onl) - 1:
            f.arrow(x + BW + 0.5, 95.0, x + BW + GAP - 0.5, 95.0, INK, 0.9, 3.2)

    # ---------------- action catalog ----------------
    chips = ["KEEP a0", "FFILL", "Single TS-ICL", "Multi TS-ICL", "Context Ridge"]
    cw, gap = 74.0, 4.0
    for i, c in enumerate(chips):
        f.chip(4.0 + i * (cw + gap), 120.0, cw, 14.0, c, size=5.4)
    f.text(4.0, 142.0,
           "action catalog A: fixed and closed; KEEP is a normal arm, not an exception path",
           size=5.0, color=MUTED)

    # ---------------- state groups ----------------
    f.rect(4.0, 150.0, 388.0, 34.0, fill=GREY_L, stroke=GREY_M, lw=0.6, r=2.5)
    f.text(10.0, 159.0, "Episode state", size=5.4, bold=True, color=BLUE)
    f.text(68.0, 159.0,
           "missing ratio, run structure, distance to origin, pattern, visible-context summary",
           size=5.0, color=MUTED)
    f.text(10.0, 172.0, "Intervention state", size=5.4, bold=True, color=BLUE)
    f.text(68.0, 172.0,
           "action identity, fraction of entries changed, change near the forecast origin",
           size=5.0, color=MUTED)

    f.text(198.0, 194.0,
           "the returned forecast always comes from exactly one executed input version",
           size=5.2, color=GREEN, align="c")
    return f


# ==========================================================================
# Figure 3 -- reconstruction vs forecast utility (骨架)
# ==========================================================================
def fig3():
    W, H = 396.0, 190.0
    f = Fig(W, H, "fig3_action_opportunity")

    # ---- (a) 机会分层 ----
    f.text(4.0, 9.0, "(a) Opportunity strata", size=6.2, bold=True)
    ax, ay, aw, ah = 42.0, 30.0, 130.0, 92.0
    base = ay + ah                      # 基线在坐标区底部
    f.axes(ax, ay, aw, ah, xlabel="oracle opportunity  Delta_i",
           ylabel="share of episodes",
           ticks_x=[(0.0, "0"), (0.5, ""), (1.0, "max")],
           ticks_y=[(0.0, "0"), (0.5, ""), (1.0, "")])
    # 柱体自底向上生长: rect 的 y 是顶边, 所以顶边 = 基线 - 高度
    bars = [(0.05, 0.66, "no-op"), (0.38, 0.42, "low"), (0.71, 0.24, "high")]
    for fx, fh, lab in bars:
        h = ah * fh
        f.rect(ax + aw * fx, base - h, aw * 0.24, h, fill=GREY_L, stroke=GREY_M, lw=0.6)
        f.text(ax + aw * (fx + 0.12), base - h - 4.0, lab, size=5.0, align="c")

    # ---- (b) 各层相对 KEEP 的改善 ----
    f.text(190.0, 9.0, "(b) Improvement over KEEP by stratum", size=6.2, bold=True)
    bx, by, bw, bh = 232.0, 30.0, 156.0, 92.0
    bbase = by + bh
    zy = by + bh * 0.5                  # 零线居中, 曲线可正可负
    f.axes(bx, by, bw, bh, xlabel="oracle opportunity stratum",
           ylabel="MASE improvement vs KEEP",
           ticks_x=[(0.17, "no-op"), (0.50, "low"), (0.83, "high")],
           ticks_y=[(0.0, "-"), (0.5, "0"), (1.0, "+")])
    f.line(bx, zy, bx + bw, zy, GREY_M, 0.6, dash=(2.0, 2.0))

    def px(fr):
        return bx + bw * fr

    def py(ty):
        # ty 为轴分数 (0=底, 1=顶); 零线在 0.5
        return bbase - bh * ty

    # 固定修复策略: 在 no-op 层为负收益, 全程贴地
    f.poly([(px(0.17), py(0.34)), (px(0.50), py(0.40)), (px(0.83), py(0.47))],
           color=GREY_M, lw=1.0, dash=(2.5, 2.0))
    # IntroAct: no-op 层基本不动, 机会越高改善越大
    f.poly([(px(0.17), py(0.50)), (px(0.50), py(0.62)), (px(0.83), py(0.85))],
           color=BLUE, lw=1.2)

    # 独立图例, 避免压在曲线上
    f.line(bx + 5.0, by + 7.0, bx + 19.0, by + 7.0, BLUE, 1.2)
    f.text(bx + 22.0, by + 8.8, "IntroAct", size=5.0, color=BLUE)
    f.line(bx + 5.0, by + 16.0, bx + 19.0, by + 16.0, GREY_M, 1.0, dash=(2.5, 2.0))
    f.text(bx + 22.0, by + 17.8, "fixed repair", size=5.0, color=MUTED)

    f.text(bx + 5.0, bbase - 5.0, "below zero: worse than doing nothing",
           size=4.8, color=MUTED)

    # ---- 占位与说明 ----
    f.text(ax + aw / 2, 152.0, "[FIG-STRATUM-SHARES]", size=5.2, color=RED, align="c")
    f.text(bx + bw / 2, 152.0, "[FIG-OPPORTUNITY-CURVES]", size=5.2, color=RED, align="c")
    f.text(198.0, 172.0,
           "A fixed repair policy must act where nothing can be gained; the decision problem "
           "is to act only where it pays.", size=5.2, color=MUTED, align="c")
    return f


# ==========================================================================
# Figure 4 -- governance diagnostics (骨架)
# ==========================================================================
def fig4():
    W, H = 396.0, 156.0
    f = Fig(W, H, "fig4_governance_diagnostics")

    f.text(4.0, 9.0, "(a) Harmful loss by method", size=6.0, bold=True)
    ax, ay, aw, ah = 46.0, 30.0, 132.0, 92.0
    f.axes(ax, ay, aw, ah, xlabel="method",
           ylabel="Harmful loss  HL  (lower is better)",
           ticks_x=[(0.08, "TOI"), (0.29, "TOIVSF"), (0.50, "GIMCC"),
                    (0.71, "SRDI"), (0.92, "CTF")],
           ticks_y=[(0.0, "0"), (0.5, ""), (1.0, "")])
    f.text(ax + aw / 2, ay + ah / 2, "[FIG-HARMFUL-LOSS-BARS]", size=5.8, color=RED, align="c")

    f.text(206.0, 9.0, "(b) Predicted vs realised ranking utility", size=6.0, bold=True)
    bx, by, bw, bh = 252.0, 30.0, 132.0, 92.0
    f.axes(bx, by, bw, bh, xlabel="Predicted S[a] (binned)",
           ylabel="Realised utility  g",
           ticks_x=[(0.0, "neg"), (0.5, "0"), (1.0, "pos")],
           ticks_y=[(0.0, "neg"), (0.5, "0"), (1.0, "pos")])
    f.line(bx, by + bh * 0.5, bx + bw, by + bh * 0.5, GREY_M, 0.6, dash=(2.0, 2.0))
    f.text(bx + bw / 2, by + bh / 2 - 6.0, "[FIG-UTILITY-CALIBRATION]", size=5.8, color=RED, align="c")
    f.text(bx + bw / 2, by + bh / 2 + 6.0, "bins + 95% CI", size=5.2, color=MUTED, align="c")

    f.text(198.0, 146.0, "Sign agreement only; no calibration guarantee is claimed.",
           size=5.2, color=MUTED, align="c")
    return f


# ==========================================================================
# Figure 5 -- robustness to missingness (骨架)
# ==========================================================================
def fig5():
    W, H = 396.0, 154.0
    f = Fig(W, H, "fig5_robustness_missingness")
    panels = ["Bolt", "TimesFM", "Chronos-2"]
    pw = 118.0
    for i, p in enumerate(panels):
        px = 8.0 + i * 128.0
        f.text(px + pw / 2, 9.0, p, size=6.0, bold=True, align="c")
        ax, ay, aw, ah = px + 22.0, 30.0, pw - 22.0, 86.0
        f.axes(ax, ay, aw, ah,
               xlabel="missing severity",
               ylabel=("relative MASE improvement vs KEEP" if i == 0 else ""),
               ticks_x=[(0.0, "10%"), (0.5, "30%"), (1.0, "50%")],
               ticks_y=[(0.0, "0"), (0.5, ""), (1.0, "+")])
        f.line(ax, ay + ah * 0.42, ax + aw, ay + ah * 0.42, GREY_M, 0.6, dash=(2.0, 2.0))
        f.text(ax + aw / 2, ay + ah / 2 + 18.0, "[FIG-ROBUST-%s]" % p.upper().replace("-", ""),
               size=5.6, color=RED, align="c")
    f.text(198.0, 148.0, "Each line is one method; all methods reuse the models and rules frozen on "
           "TRAIN, with no per-severity retuning.", size=5.2, color=MUTED, align="c")
    return f


def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    print("generating figure sources into %s" % outdir)
    for fn in (fig1, fig2, fig3, fig4, fig5):
        fn().save(outdir)


if __name__ == "__main__":
    main()
