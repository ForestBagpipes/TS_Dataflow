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

import json
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
COLOUR45 = {"bolt": BLUE, "timesfm": AMBER, "chronos2": GREEN}
NAME45 = {"bolt": "Bolt", "timesfm": "TimesFM", "chronos2": "Chronos-2"}
COLOUR45M = {"FULL_INTROACT": BLUE, "BEST_FIXED": AMBER, "R2_CART": GREEN,
             "SAITS": RED, "TATO": FAINT}
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
    """Figure 1: motivation (measured) + replay construction + online decision.

    面板 (a) 必须由真实评测统计驱动。统计从 figure/fig1_stats.json 读取，schema:
        {"best_action_share": {"KEEP": float, "FFILL": float,
                               "SINGLE_TSICL": float, "MULTI_TSICL": float,
                               "CONTEXT_RIDGE": float},
         "best_fixed_gap": float}
    文件不存在时画空坐标系并标注来源，绝不填造数字。
    """
    import json

    W, H = 396.0, 198.0
    f = Fig(W, H, "fig1_selective_governance")

    colx = [4.0, 138.0, 272.0]
    colw = [128.0, 128.0, 120.0]

    stats_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig1_stats.json")
    stats = None
    if os.path.exists(stats_path):
        with open(stats_path, "r", encoding="utf-8") as fh:
            stats = json.load(fh)

    # ---- panel A: measured action heterogeneity ----
    f.text(colx[0] + colw[0] / 2, 9.0, "(a) Oracle-best action", size=6.4, bold=True, align="c")
    f.text(colx[0] + colw[0] / 2, 17.5, "share on the evaluation episodes", size=6.4,
           bold=True, align="c")

    ax0 = colx[0] + 14.0
    ay0 = 30.0
    aw, ah = colw[0] - 22.0, 90.0
    f.axes(ax0, ay0, aw, ah, ylabel="",
           ticks_y=[(0.0, "0"), (0.5, "0.25"), (1.0, "0.50")])
    labels = ["KEEP", "FFILL", "S-ICL", "M-ICL", "RIDGE"]
    keys = ["KEEP", "FFILL", "SINGLE_TSICL", "MULTI_TSICL", "CONTEXT_RIDGE"]
    colors = [RED, BLUE, BLUE, BLUE, AMBER]
    slot = aw / len(labels)
    for i, lab in enumerate(labels):
        cx = ax0 + slot * (i + 0.5)
        f.line(cx, ay0 + ah, cx, ay0 + ah + 2.5, INK, 0.6)
        f.text(cx, ay0 + ah + 9.0, lab, size=4.8, color=MUTED, align="c")
        if stats is not None:
            # The axis tops out at 0.50, so a share maps to twice its value in
            # axis units.  Drawing the share directly would halve every bar.
            v = float(stats["best_action_share"].get(keys[i], 0.0)) / 0.5
            v = max(0.0, min(1.0, v))
            if v > 0.0:
                f.rect(cx - slot * 0.26, ay0 + ah - v * ah, slot * 0.52, v * ah,
                       fill=colors[i], stroke=colors[i], lw=0.5)
    if stats is None:
        f.rect(ax0 + 6.0, ay0 + 22.0, aw - 12.0, 40.0, fill=None, stroke=FAINT,
               lw=0.6, dash=(2.0, 2.0))
        f.text(ax0 + aw / 2, ay0 + 38.0, "measured from the", size=5.0, color=MUTED, align="c")
        f.text(ax0 + aw / 2, ay0 + 45.0, "evaluation episodes", size=5.0, color=MUTED, align="c")
        f.text(ax0 + aw / 2, ay0 + 52.0, "(Section 4.2)", size=5.0, color=MUTED, align="c")

    gap_txt = "BEST FIXED gap = [MAIN_HET_GAP]"
    if stats is not None and "best_fixed_gap" in stats:
        gap_txt = "BEST FIXED gap = %.3f" % float(stats["best_fixed_gap"])
    f.text(colx[0] + colw[0] / 2, ay0 + ah + 20.0, "share of episodes on which each action",
           size=4.9, color=MUTED, align="c")
    f.text(colx[0] + colw[0] / 2, ay0 + ah + 27.0, "is oracle-best", size=4.9,
           color=MUTED, align="c")
    f.text(colx[0] + colw[0] / 2, ay0 + ah + 37.0, gap_txt, size=5.2, color=INK, align="c")
    f.text(colx[0] + colw[0] / 2, ay0 + ah + 45.0, "one fixed policy leaves improvement unused",
           size=4.9, color=MUTED, align="c")

    # ---- panel B: historical full-action replay ----
    f.text(colx[1] + colw[1] / 2, 9.0, "(b) Historical full-action replay", size=6.4,
           bold=True, align="c")
    f.text(colx[1] + colw[1] / 2, 17.5, "on TRAIN windows", size=6.4, bold=True, align="c")
    bx, bw = colx[1], colw[1]
    f.box(bx, 26.0, bw, 20.0, ["Complete TRAIN window", "(its future is available history)"],
          fill=GREY_L, size=5.6)
    f.arrow(bx + bw / 2, 47.0, bx + bw / 2, 55.0, INK, 0.9, 3.4)
    f.box(bx, 56.0, bw, 20.0, ["Inject the registered", "missingness protocol"],
          fill=RED_L, stroke=RED, size=5.6)
    f.arrow(bx + bw / 2, 77.0, bx + bw / 2, 85.0, INK, 0.9, 3.4)
    f.box(bx, 86.0, bw, 24.0, ["Execute every catalog action", "with the frozen forecaster F",
                               "and observe the realised future"],
          fill=BLUE_L, stroke=BLUE, size=5.6)
    f.arrow(bx + bw / 2, 111.0, bx + bw / 2, 119.0, INK, 0.9, 3.4)
    f.box(bx, 120.0, bw, 24.0, ["Record realised utility",
                                "g[i,a] = loss(KEEP) - loss(a)"],
          fill=GREEN_L, stroke=GREEN, size=5.2)
    f.text(bx + bw / 2, 152.0, "replay bank  B = {(z[i,a], a, g[i,a])}", size=5.4,
           color=GREEN, align="c")
    f.text(bx + bw / 2, 161.0, "the bank holds realised forecasting utility", size=5.2,
           color=MUTED, align="c")
    f.text(bx + bw / 2, 169.0, "and not a reconstruction score", size=5.2, color=MUTED, align="c")

    # ---- panel C: online act-or-keep ----
    f.text(colx[2] + colw[2] / 2, 9.0, "(c) Online act-or-keep", size=6.4, bold=True, align="c")
    f.text(colx[2] + colw[2] / 2, 17.5, "one request at a time", size=6.4, bold=True, align="c")
    cx, cw = colx[2], colw[2]
    f.box(cx, 26.0, cw, 18.0, ["New request: X, M"], fill=GREY_L, size=5.8)
    f.arrow(cx + cw / 2, 45.0, cx + cw / 2, 52.0, INK, 0.9, 3.4)
    f.box(cx, 53.0, cw, 22.0, ["Reference call p0 = F(X[a0])", "state z_a per action"],
          fill=BLUE_L, stroke=BLUE, size=5.6)
    f.arrow(cx + cw / 2, 76.0, cx + cw / 2, 83.0, INK, 0.9, 3.4)
    f.box(cx, 84.0, cw, 22.0, ["Score S[a] from the", "same-action neighbourhood"],
          fill=AMBER_L, stroke=AMBER, size=5.2)
    f.arrow(cx + cw / 2, 107.0, cx + cw / 2, 114.0, INK, 0.9, 3.4)
    f.diamond(cx + cw / 2, 128.0, 88.0, 26.0)
    f.text(cx + cw / 2, 129.8, "max S[a] > 0 ?", size=5.4, align="c")
    f.arrow(cx + 18.0, 141.0, cx + 18.0, 152.0, RED, 1.0, 3.4)
    f.text(cx + 14.0, 149.0, "no", size=5.2, color=RED, align="r")
    f.arrow(cx + cw - 18.0, 141.0, cx + cw - 18.0, 152.0, GREEN, 1.0, 3.4)
    f.text(cx + cw - 14.0, 149.0, "yes", size=5.2, color=GREEN, align="l")
    f.box(cx - 2.0, 153.0, cw / 2 - 4.0, 26.0, ["KEEP", "input untouched"],
          fill=RED_L, stroke=RED, size=5.6, bold_first=True)
    f.box(cx + cw / 2 + 4.0, 153.0, cw / 2 - 2.0, 26.0, ["ACT", "execute F(X[a*])"],
          fill=GREEN_L, stroke=GREEN, size=5.6, bold_first=True)
    f.text(198.0, 189.0,
           "the reference action is always available, so the decision rule always returns a forecast",
           size=5.2, color=MUTED, align="c")

    # 面板分隔
    f.line(colx[1] - 5.0, 24.0, colx[1] - 5.0, 182.0, GREY_M, 0.5, dash=(1.5, 2.0))
    f.line(colx[2] - 5.0, 24.0, colx[2] - 5.0, 182.0, GREY_M, 0.5, dash=(1.5, 2.0))
    return f


# ==========================================================================
# Figure 2 -- IntroAct-TS architecture
# ==========================================================================
def fig2():
    W, H = 396.0, 214.0
    f = Fig(W, H, "fig2_introact_architecture")
    BW, GAP = 91.0, 8.0

    # ---------------- offline band ----------------
    f.text(4.0, 9.0, "Offline  (TRAIN only, the only place a future is read)",
           size=6.0, bold=True, color=GREEN)
    off = [
        ["Complete historical window", "(X_i, y_i); its future", "is available TRAIN history"],
        ["Inject the registered", "missingness protocol", "-> incomplete context (X_i, M_i)"],
        ["Execute every catalog action", "with the frozen pipeline F;", "record realised utility g[i,a]"],
        ["Historical replay bank", "B = {(z[i,a], a, g[i,a])}", "frozen once, read-only"],
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
    f.text(4.0, 72.0, "Online  (deployment, no future is available)",
           size=6.0, bold=True, color=BLUE)
    onl = [
        ["Incomplete context", "(X, M) at the", "forecast origin"],
        ["Reference call", "p0 = F(X[a0]);", "action-conditioned state z_a"],
        ["Local utility scoring", "same-action neighbourhoods", "of the frozen bank B"],
        ["Frozen TSFM, one call", "F(X[a*]) is returned;", "KEEP means input untouched"],
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
           "catalog A: fixed and closed; the reference action a0 is an ordinary arm",
           size=5.0, color=MUTED)
    f.text(4.0, 151.0,
           "online cost: 1-2 forecasting-backbone calls (reference, plus the selected action);",
           size=5.0, color=MUTED)
    f.text(4.0, 160.0,
           "candidate materialisation is paid before the decision and is counted separately",
           size=5.0, color=MUTED)

    # ---------------- state groups ----------------
    f.rect(4.0, 168.0, 388.0, 40.0, fill=GREY_L, stroke=GREY_M, lw=0.6, r=2.5)
    f.text(10.0, 177.0, "Mask state", size=5.2, bold=True, color=BLUE)
    f.text(68.0, 177.0, "missing ratio, run structure, distance to origin, pattern",
           size=4.9, color=MUTED)
    f.text(10.0, 186.0, "Visible-context state", size=5.2, bold=True, color=BLUE)
    f.text(68.0, 186.0, "level, local trend, autocorrelation, seasonality, volatility",
           size=4.9, color=MUTED)
    f.text(10.0, 195.0, "Intervention state", size=5.2, bold=True, color=BLUE)
    f.text(68.0, 195.0, "per action a: action identity, changed fraction, change near origin",
           size=4.9, color=MUTED)
    f.text(10.0, 204.0, "Reference-forecast state", size=5.0, bold=True, color=BLUE)
    f.text(88.0, 204.0, "computed from p0 = F(X[a0]) only, never from a non-selected candidate",
           size=4.9, color=MUTED)

    return f


# ==========================================================================
# ==========================================================================
# Figure 3 -- why forecasting utility and why selectivity (骨架)
# ==========================================================================
def fig3():
    """Figure 3: why the criterion has to be forecasting utility, and why selective.

    Both panels read ``figure/fig3_stats.json``.  Panel (a) is the joint
    distribution of the within-episode reconstruction rank and realised-utility
    rank over the four catalog interventions, row-normalised.  Panel (b) is the
    cross-validated harm against intervention rate over the penalty grid.  With
    no stats file the panels are drawn empty and labelled, never filled in.
    """
    import json
    import os

    W, H = 396.0, 190.0
    f = Fig(W, H, "fig3_why_selective")
    stats_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig3_stats.json")
    stats = None
    if os.path.exists(stats_path):
        with open(stats_path, "r", encoding="utf-8") as fh:
            stats = json.load(fh)

    # ---- (a) rank agreement between the two criteria ----
    f.text(4.0, 9.0, "(a) Reconstruction rank vs realised-utility rank", size=6.0, bold=True)
    ax, ay, aw, ah = 42.0, 30.0, 120.0, 92.0
    n_rank = len(stats["rank_grid"]) if stats and stats.get("rank_grid") else 4
    step = 1.0 / n_rank
    ticks_x = [((i + 0.5) * step, str(i + 1)) for i in range(n_rank)]
    # Row j of the grid is utility rank j+1 and is drawn from the top, while the
    # axis fraction runs upward, so the y labels count down.
    ticks_y = [((i + 0.5) * step, str(n_rank - i)) for i in range(n_rank)]
    f.axes(ax, ay, aw, ah, ylabel="realised utility rank",
           ticks_x=ticks_x, ticks_y=ticks_y)
    if stats is not None and stats.get("rank_grid"):
        grid = stats["rank_grid"]
        cw, ch = aw / n_rank, ah / n_rank
        labels = []
        for i, row in enumerate(grid):
            total = float(sum(row)) or 1.0
            for j, count in enumerate(row):
                share = count / total
                # Blue saturates towards the row maximum; 0.25 is chance.
                t = max(0.0, min(1.0, share / 0.45))
                fill = (BLUE_L[0] + (BLUE[0] - BLUE_L[0]) * t,
                        BLUE_L[1] + (BLUE[1] - BLUE_L[1]) * t,
                        BLUE_L[2] + (BLUE[2] - BLUE_L[2]) * t)
                # Cell (i, j) sits at column i and row j from the top, so the
                # two criteria agree exactly on the diagonal.  Those cells are
                # outlined rather than crossed by a line, which would run
                # through the numbers printed inside them.
                f.rect(ax + i * cw, ay + j * ch, cw, ch, fill=fill,
                       stroke=(INK if i == j else WHITE), lw=(0.9 if i == j else 0.5))
                labels.append((ax + (i + 0.5) * cw, ay + (j + 0.5) * ch + 1.4,
                               "%.2f" % share, WHITE if t > 0.62 else INK))
        for tx, ty, label, colour in labels:
            f.text(tx, ty, label, size=4.2, color=colour, align="c")
        f.text(ax + aw / 2, ay + ah + 20.0, "reconstruction rank within episode",
               size=4.9, color=MUTED, align="c")
        f.text(ax + aw / 2, ay + ah + 29.0,
               "outlined cells = the two criteria agree; agreement %.0f%%"
               % (100.0 * stats["winner_agreement"]), size=4.9, color=INK, align="c")
        f.text(ax + aw / 2, ay + ah + 37.0,
               "discordant pairs %.0f%%, within-episode rho %.2f"
               % (100.0 * stats["discordant_rate"], stats["spearman"]),
               size=4.9, color=MUTED, align="c")
    else:
        f.rect(ax + 6.0, ay + 24.0, aw - 12.0, 42.0, fill=None, stroke=FAINT, lw=0.6,
               dash=(2.0, 2.0))
        f.text(ax + aw / 2, ay + 44.0, "from the recorded diagnostics", size=5.0,
               color=MUTED, align="c")

    # ---- (b) harm against intervention rate over the penalty grid ----
    f.text(200.0, 9.0, "(b) Harm against intervention rate", size=6.0, bold=True)
    bx, by, bw, bh = 236.0, 30.0, 150.0, 92.0
    f.axes(bx, by, bw, bh, ylabel="conditional harmful rate",
           ticks_x=[(0.0, "0"), (0.5, "0.5"), (1.0, "1")],
           ticks_y=[(0.0, "0.25"), (0.5, "0.38"), (1.0, "0.50")])
    if stats is not None and stats.get("curve"):
        style = {"bolt": (BLUE, "Bolt"), "timesfm": (AMBER, "TimesFM"),
                 "chronos2": (GREEN, "Chronos-2")}
        lo, hi = 0.25, 0.50
        for backbone, (colour, label) in style.items():
            points = [p for p in stats["curve"] if p["backbone"] == backbone]
            points.sort(key=lambda p: p["intervention_rate"])
            for p in points:
                px = bx + bw * max(0.0, min(1.0, p["intervention_rate"]))
                py = by + bh - bh * max(0.0, min(1.0, (p["conditional_hir"] - lo) / (hi - lo)))
                if p.get("selected"):
                    f.rect(px - 2.4, py - 2.4, 4.8, 4.8, fill=colour, stroke=INK, lw=0.7)
                else:
                    f.rect(px - 1.1, py - 1.1, 2.2, 2.2, fill=colour, stroke=None, lw=0.0)
        y_cap = by + bh - bh * max(0.0, min(1.0, (stats["cap"] - lo) / (hi - lo)))
        f.line(bx, y_cap, bx + bw, y_cap, RED, 0.7, dash=(2.5, 2.0))
        f.text(bx + bw - 2.0, y_cap - 3.0, "harm cap", size=4.6, color=RED, align="r")
        for i, (backbone, (colour, label)) in enumerate(style.items()):
            lx = bx + 4.0 + i * 46.0
            f.rect(lx, by + 4.0, 4.0, 4.0, fill=colour, stroke=None, lw=0.0)
            f.text(lx + 6.0, by + 8.0, label, size=4.8, color=MUTED)
        f.text(bx + bw / 2, by + bh + 20.0, "intervention rate", size=4.9,
               color=MUTED, align="c")
        f.text(bx + bw / 2, by + bh + 29.0,
               "one point per neighbourhood size and penalty strength", size=4.9,
               color=MUTED, align="c")
        f.text(bx + bw / 2, by + bh + 37.0,
               "large marker = the point the cross-validation selected", size=4.9,
               color=MUTED, align="c")
    else:
        f.rect(bx + 8.0, by + 24.0, bw - 16.0, 42.0, fill=None, stroke=FAINT, lw=0.6,
               dash=(2.0, 2.0))
        f.text(bx + bw / 2, by + 44.0, "from the recorded grid", size=5.0,
               color=MUTED, align="c")

    f.text(198.0, 176.0,
           "The two criteria agree barely more often than chance, and moving along the penalty "
           "grid trades intervention rate against accuracy at a nearly fixed harmful rate.",
           size=5.0, color=MUTED, align="c")
    return f


# ==========================================================================
# Figure 4 -- governance diagnostics (骨架)
# ==========================================================================
def _load45():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fig45_stats.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fig4():
    W, H = 396.0, 162.0
    f = Fig(W, H, "fig4_governance_diagnostics")
    stats = _load45()

    # ---- (a) harmful loss per method ----
    # The bars run horizontally so that the method names sit on the axis with
    # room to be read, which they do not have across six upright bars.
    f.text(4.0, 9.0, "(a) Harmful loss by method", size=6.0, bold=True)
    rows = (stats or {}).get("harmful_loss") or []
    ax, ay, aw, ah = 62.0, 30.0, 112.0, 88.0
    top = max([r["harmful_loss"] for r in rows] + [0.05]) * 1.16
    n = max(len(rows), 1)
    ticks_y = [(1.0 - (i + 0.5) / n, r["label"]) for i, r in enumerate(rows)]
    f.axes(ax, ay, aw, ah, xlabel="harmful loss (lower is better)", ylabel="",
           ticks_x=[(v / top, "%.2f" % v) for v in (0.0, 0.10, 0.20, 0.30) if v <= top],
           ticks_y=ticks_y)
    slot = ah / n
    for i, row in enumerate(rows):
        width = aw * (row["harmful_loss"] / top)
        ours = row["key"] == "FULL_INTROACT"
        f.rect(ax, ay + i * slot + slot * 0.24, max(width, 0.4), slot * 0.52,
               fill=(BLUE if ours else GREY_M), stroke=(INK if ours else FAINT), lw=0.6)
        f.text(ax + width + 2.6, ay + i * slot + slot * 0.5 + 1.6,
               "%.3f" % row["harmful_loss"], size=4.6,
               color=(INK if ours else MUTED), align="l")
    f.text(ax + aw / 2, ay + ah + 27.0,
           "mean over the three backbones, and the reference action adds none",
           size=4.6, color=MUTED, align="c")

    # ---- (b) realised utility against the score bin ----
    f.text(206.0, 9.0, "(b) Realised utility against the score bin", size=6.0, bold=True)
    bx, by, bw, bh = 250.0, 32.0, 132.0, 86.0
    calib = (stats or {}).get("calibration") or {}
    series = [(b, COLOUR45.get(b, INK)) for b in ("bolt", "timesfm", "chronos2") if b in calib]
    values = [v for b, _ in series for row in calib[b]["bins"] for v in (row["lo"], row["hi"])]
    lo_v = min(values + [-0.05])
    hi_v = max(values + [0.05])
    span = hi_v - lo_v
    lo_v, hi_v = lo_v - span * 0.08, hi_v + span * 0.08
    bins = max((len(calib[b]["bins"]) for b, _ in series), default=8)

    def why(value):
        return by + bh - bh * (value - lo_v) / (hi_v - lo_v)

    f.axes(bx, by, bw, bh, xlabel="conservative score, quantile bin",
           ylabel="realised utility",
           ticks_x=[(((i + 0.5) / bins), str(i + 1)) for i in range(bins)],
           ticks_y=[((v - lo_v) / (hi_v - lo_v), "%.2f" % v)
                    for v in (-0.3, -0.15, 0.0, 0.15) if lo_v <= v <= hi_v])
    f.line(bx, why(0.0), bx + bw, why(0.0), GREY_M, 0.6, dash=(2.0, 2.0))
    for index, (backbone, colour) in enumerate(series):
        offset = (index - (len(series) - 1) / 2.0) * (bw / bins) * 0.22
        points = []
        for row in calib[backbone]["bins"]:
            px = bx + ((row["bin"] - 0.5) / bins) * bw + offset
            points.append((px, why(row["utility"])))
            f.line(px, why(row["lo"]), px, why(row["hi"]), colour, 0.5)
        f.poly(points, colour, 0.9)
        for px, py in points:
            f.rect(px - 1.1, py - 1.1, 2.2, 2.2, fill=colour, stroke=WHITE, lw=0.3)
    for index, (backbone, colour) in enumerate(series):
        lx = bx + 6.0 + index * 44.0
        f.rect(lx, 14.0, 4.0, 4.0, fill=colour, stroke=None)
        f.text(lx + 6.0, 18.0, NAME45.get(backbone, backbone), size=5.0, color=INK)
    f.text(bx + bw / 2, by + bh + 26.0,
           "whiskers are 95% intervals that resample parents", size=4.6,
           color=MUTED, align="c")
    f.text(198.0, 156.0,
           "The score orders actions and the order agrees in sign with what the actions did. "
           "No claim is made that the score is on the scale of the utility.",
           size=5.0, color=MUTED, align="c")
    return f


def fig5():
    W, H = 396.0, 174.0
    f = Fig(W, H, "fig5_robustness_missingness")
    stats = _load45()
    severity = (stats or {}).get("severity") or {}
    panels = [("bolt", "Bolt"), ("timesfm", "TimesFM"), ("chronos2", "Chronos-2")]
    everything = [p["improvement"] for b, _ in panels if b in severity
                  for s in severity[b].values() for p in s["points"]]
    lo_v = min(everything + [0.0]) - 0.03
    hi_v = max(everything + [0.05]) + 0.03
    pw = 118.0
    order = ("FULL_INTROACT", "BEST_FIXED", "R2_CART", "SAITS", "TATO")
    for i, (key, title) in enumerate(panels):
        px = 8.0 + i * 128.0
        f.text(px + pw / 2, 9.0, title, size=6.0, bold=True, align="c")
        ax, ay, aw, ah = px + 26.0, 36.0, pw - 26.0, 84.0

        def why(value, ay=ay, ah=ah):
            return ay + ah - ah * (value - lo_v) / (hi_v - lo_v)

        f.axes(ax, ay, aw, ah, xlabel="missing severity",
               ylabel=("MASE improvement over the untouched input" if i == 0 else ""),
               ticks_x=[(0.0, "10%"), (0.5, "30%"), (1.0, "50%")],
               ticks_y=[((v - lo_v) / (hi_v - lo_v), "%+.0f%%" % (v * 100))
                        for v in (-0.2, -0.1, 0.0, 0.1, 0.2) if lo_v <= v <= hi_v])
        f.line(ax, why(0.0), ax + aw, why(0.0), GREY_M, 0.6, dash=(2.0, 2.0))
        series = severity.get(key, {})
        for name in order:
            entry = series.get(name)
            if not entry:
                continue
            colour = COLOUR45M.get(name, MUTED)
            ours = name == "FULL_INTROACT"
            points = [(ax + aw * j / 2.0, why(p["improvement"]))
                      for j, p in enumerate(entry["points"])]
            f.poly(points, colour, 1.4 if ours else 0.8)
            for cx, cy in points:
                f.rect(cx - 1.3, cy - 1.3, 2.6, 2.6, fill=colour, stroke=WHITE, lw=0.3)
    legend = [(name, COLOUR45M.get(name, MUTED),
               (severity.get("bolt", {}).get(name) or {}).get("label", name))
              for name in order]
    lx = 30.0
    for name, colour, label in legend:
        f.rect(lx, 148.0, 4.0, 4.0, fill=colour, stroke=None)
        f.text(lx + 6.0, 152.0, label, size=5.0, color=INK)
        lx += 20.0 + 3.2 * len(label)
    f.text(198.0, 167.0,
           "Every method reuses the rule frozen on TRAIN, with no retuning between levels.",
           size=5.0, color=MUTED, align="c")
    return f


def main():
    outdir = os.path.dirname(os.path.abspath(__file__))
    print("generating figure sources into %s" % outdir)
    for fn in (fig1, fig2, fig3, fig4, fig5):
        fn().save(outdir)


if __name__ == "__main__":
    main()
