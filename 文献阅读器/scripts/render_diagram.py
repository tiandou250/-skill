#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文献阅读器 · 图表渲染器

把 JSON 规格渲染成高质量 PNG 图表，供 Word 总结报告嵌入。

支持三种图：
  tree     文献结构导图（层级树，自上而下）
  flow     研究流程图（步骤链，可纵向/横向）
  concept  概念关系图（中心辐射 + 可选交叉连线）

用法：
  <python> render_diagram.py <spec.json> --outdir <输出目录>

spec.json 可以是单个图对象，也可以是 {"diagrams": [ ... ]}。
成功时 stdout 输出 JSON：
  {"ok": true, "images": [{"id": "...", "type": "tree", "path": "...", "width": 1400, "height": 900}]}

只依赖 Pillow。中文字体自动探测（Windows / macOS / Linux）。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------------
# 全局：超采样倍率。所有布局常量都以「缩放后像素」为单位，最后统一缩小回去。
# ----------------------------------------------------------------------------
S = 2

WARNINGS: list[str] = []


def warn(msg: str) -> None:
    if msg not in WARNINGS:
        WARNINGS.append(msg)


# ----------------------------------------------------------------------------
# 主题色（浅色主题：白底、深色文字、低饱和强调色）
# ----------------------------------------------------------------------------
BG = (255, 255, 255)
TITLE_C = (17, 24, 39)
TEXT_C = (31, 41, 55)
SUB_C = (107, 114, 128)
LINE_C = (148, 163, 184)
BORDER_C = (203, 213, 225)
BOX_FILL = (248, 250, 252)

ACCENTS = [
    (79, 70, 229),    # indigo
    (2, 132, 199),    # sky
    (13, 148, 136),   # teal
    (217, 119, 6),    # amber
    (190, 24, 93),    # pink
    (124, 58, 237),   # violet
    (22, 101, 52),    # green
    (185, 28, 28),    # red
]


def blend(c, f: float):
    """把颜色朝白色混合，f=0 原色，f=1 纯白。"""
    return tuple(int(round(v + (255 - v) * f)) for v in c)


def accent(i: int):
    return ACCENTS[i % len(ACCENTS)]


# ----------------------------------------------------------------------------
# 字体
# ----------------------------------------------------------------------------
def _candidates(bold: bool):
    win = os.environ.get("WINDIR") or r"C:\Windows"
    f = os.path.join(win, "Fonts")
    if bold:
        return [
            os.path.join(f, "msyhbd.ttc"),
            os.path.join(f, "simhei.ttf"),
            os.path.join(f, "msyh.ttc"),
            os.path.join(f, "simsun.ttc"),
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    return [
        os.path.join(f, "msyh.ttc"),
        os.path.join(f, "msyhl.ttc"),
        os.path.join(f, "simhei.ttf"),
        os.path.join(f, "simsun.ttc"),
        os.path.join(f, "Deng.ttf"),
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    ]


_FONT_CACHE: dict = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    for p in _candidates(bold):
        if os.path.exists(p):
            try:
                f = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = f
                return f
            except Exception:
                continue
    warn("未找到中文字体，已回退到 Pillow 默认字体，中文可能显示为方块。")
    f = ImageFont.load_default(size=size)
    _FONT_CACHE[key] = f
    return f


LINE_FACTOR = 1.45


def lh(size: int) -> float:
    """字号对应的行高（中文排版 1.45em，稳定且不受字体 metrics 影响）。"""
    return size * LINE_FACTOR


# ----------------------------------------------------------------------------
# 文本换行（中英混排：ASCII 单词整体不拆，CJK 逐字断行）
# ----------------------------------------------------------------------------
_KEEP = set("-_/.'%()+&:,")


def _tokens(text: str):
    out, buf = [], ""
    for ch in text:
        if ord(ch) < 128 and (ch.isalnum() or ch in _KEEP):
            buf += ch
        else:
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
    if buf:
        out.append(buf)
    return out


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: float):
    lines = []
    for para in str(text).split("\n"):
        if not para.strip():
            lines.append("")
            continue
        cur = ""
        for tk in _tokens(para):
            trial = cur + tk
            if cur and f.getlength(trial) > max_w:
                lines.append(cur)
                cur = tk.lstrip() if tk.strip() else ""
            else:
                cur = trial
        lines.append(cur)
    return lines or [""]


# ----------------------------------------------------------------------------
# 基础绘制
# ----------------------------------------------------------------------------
def rrect(dr: ImageDraw.ImageDraw, box, r, fill=None, outline=None, width=1):
    dr.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def arrow(dr: ImageDraw.ImageDraw, p1, p2, color, width=2, head=9):
    dr.line([p1, p2], fill=color, width=width)
    ang = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
    for da in (2.6, -2.6):
        dr.line(
            [p2, (p2[0] + head * math.cos(ang + da), p2[1] + head * math.sin(ang + da))],
            fill=color,
            width=width,
        )


def draw_lines(dr, lines, x, y_top, size, color, width_limit=None):
    """在 (x, y_top) 起逐行绘制，每行在 y_top + i*level_h 的垂直中点对齐。"""
    step = lh(size)
    for i, ln in enumerate(lines):
        dr.text(
            (x, y_top + i * step + step / 2),
            ln,
            font=font(size),
            fill=color,
            anchor="lm",
        )
    return len(lines) * step


# ----------------------------------------------------------------------------
# 通用盒子度量
# ----------------------------------------------------------------------------
class BoxText:
    """把一段文字排成一个带内边距的盒子，记录尺寸与行信息。"""

    def __init__(self, text, size, max_w, pad_x, pad_y, bold=False, sub=None, sub_size=None):
        self.size = size
        self.pad_x = pad_x
        self.pad_y = pad_y
        self.f = font(size, bold)
        inner = max(40, max_w - 2 * pad_x)
        self.lines = wrap(text, self.f, inner)
        step = lh(size)
        self.lines_h = len(self.lines) * step
        w = max(self.f.getlength(l) for l in self.lines)
        self.sub_lines = []
        self.sub_h = 0.0
        self.sub_size = sub_size or int(size * 0.82)
        if sub:
            sf = font(self.sub_size)
            self.sub_lines = wrap(sub, sf, inner)
            sstep = lh(self.sub_size)
            self.sub_h = len(self.sub_lines) * sstep
            w = max(w, max(sf.getlength(l) for l in self.sub_lines))
        self.w = min(max_w, w + 2 * pad_x)
        self.h = self.lines_h + self.sub_h + 2 * pad_y + (6 * S if self.sub_lines else 0)
        self.step = step

    def draw(self, dr, x, y, fill, outline, accent_c, radius=12 * S, bold=False, text_c=TEXT_C):
        rrect(dr, (x, y, x + self.w, y + self.h), radius, fill=fill, outline=outline, width=2 * S)
        ty = y + self.pad_y
        draw_lines(dr, self.lines, x + self.pad_x, ty, self.size, text_c)
        if self.sub_lines:
            sy = y + self.pad_y + self.lines_h + 6 * S
            draw_lines(dr, self.sub_lines, x + self.pad_x, sy, self.sub_size, SUB_C)


# ----------------------------------------------------------------------------
# 图 1：文献结构导图（层级树）
#   direction: horizontal（默认，左→右，适合文献大纲）
#              vertical  （上→下）
# ----------------------------------------------------------------------------
NODE_SIZE = 17 * S
NODE_MAXW = 240 * S
NODE_PAD_X = 13 * S
NODE_PAD_Y = 10 * S
TREE_SPAN_GAP = 18 * S    # 兄弟节点间距
TREE_DEPTH_GAP = 50 * S   # 层级间距


def render_tree(d: dict):
    root_raw = d.get("root")
    if not root_raw:
        raise ValueError("tree 图缺少 root 字段")

    vertical = (d.get("direction") or "horizontal").lower() in ("v", "vertical", "column")

    nodes = []

    def build(raw, depth, parent):
        bt = BoxText(raw.get("text", ""), NODE_SIZE, NODE_MAXW, NODE_PAD_X, NODE_PAD_Y)
        n = {"bt": bt, "depth": depth, "children": [], "parent": parent, "x": 0.0, "y": 0.0}
        nodes.append(n)
        for c in raw.get("children") or []:
            n["children"].append(build(c, depth + 1, n))
        return n

    root = build(root_raw, 0, None)

    # 「span」= 兄弟节点并排的方向；「depth」= 层级推进的方向
    # 横向（左→右）：层级沿 x 推进，兄弟沿 y 排开
    # 纵向（上→下）：层级沿 y 推进，兄弟沿 x 排开
    def span_size(n):
        return n["bt"].w if vertical else n["bt"].h

    def depth_size(n):
        return n["bt"].h if vertical else n["bt"].w

    def swidth(n):
        own = span_size(n)
        if not n["children"]:
            n["sw"] = own
            return own
        total = sum(swidth(c) for c in n["children"]) + TREE_SPAN_GAP * (len(n["children"]) - 1)
        n["sw"] = max(own, total)
        return n["sw"]

    swidth(root)

    def place(n, left):
        n["s"] = left + (n["sw"] - span_size(n)) / 2
        if not n["children"]:
            return
        total = sum(c["sw"] for c in n["children"]) + TREE_SPAN_GAP * (len(n["children"]) - 1)
        start = left + (n["sw"] - total) / 2
        for c in n["children"]:
            place(c, start)
            start += c["sw"] + TREE_SPAN_GAP

    place(root, 0)

    max_depth = max(n["depth"] for n in nodes)
    depth_ext = [0.0] * (max_depth + 1)
    for n in nodes:
        depth_ext[n["depth"]] = max(depth_ext[n["depth"]], depth_size(n))

    title = d.get("title") or ""
    title_h = (lh(26 * S) + 30 * S) if title else 0.0
    margin = 40 * S

    starts, acc = [], margin + title_h
    for dd in range(max_depth + 1):
        starts.append(acc)
        acc += depth_ext[dd] + TREE_DEPTH_GAP
    depth_total = acc - TREE_DEPTH_GAP

    # span 轴补上前置留白：横向布局时 span 是 y 轴，要给标题让位
    off = margin if vertical else margin + title_h
    for n in nodes:
        n["s"] += off

    for n in nodes:
        if vertical:
            n["x"], n["y"] = n["s"], starts[n["depth"]]
        else:
            n["x"], n["y"] = starts[n["depth"]], n["s"]

    if vertical:
        W = off + root["sw"] + margin
        H = depth_total + margin
    else:
        W = depth_total + margin
        H = off + root["sw"] + margin

    img = Image.new("RGB", (max(320 * S, int(W)), max(200 * S, int(H))), BG)
    dr = ImageDraw.Draw(img)

    if title:
        dr.text((img.width / 2, margin / 2 + lh(26 * S) / 2), title, font=font(26 * S, True),
                fill=TITLE_C, anchor="mm")

    # 连线（正交折线）
    for n in nodes:
        for c in n["children"]:
            col = blend(accent(c["depth"]), 0.42)
            if vertical:
                px = n["x"] + n["bt"].w / 2
                py = n["y"] + n["bt"].h
                cx = c["x"] + c["bt"].w / 2
                cy = c["y"]
                mid = (py + cy) / 2
                dr.line([(px, py), (px, mid)], fill=col, width=2 * S)
                dr.line([(px, mid), (cx, mid)], fill=col, width=2 * S)
                dr.line([(cx, mid), (cx, cy)], fill=col, width=2 * S)
            else:
                px = n["x"] + n["bt"].w
                py = n["y"] + n["bt"].h / 2
                cx = c["x"]
                cy = c["y"] + c["bt"].h / 2
                mid = (px + cx) / 2
                dr.line([(px, py), (mid, py)], fill=col, width=2 * S)
                dr.line([(mid, py), (mid, cy)], fill=col, width=2 * S)
                dr.line([(mid, cy), (cx, cy)], fill=col, width=2 * S)

    for n in nodes:
        a = accent(n["depth"])
        fill = a if n["depth"] == 0 else blend(a, 0.93)
        txt_c = (255, 255, 255) if n["depth"] == 0 else TEXT_C
        outline = a if n["depth"] == 0 else blend(a, 0.35)
        n["bt"].draw(dr, n["x"], n["y"], fill, outline, a, radius=12 * S, text_c=txt_c)

    ratio = W / max(1.0, H)
    if ratio > 3.2 or ratio < 0.45:
        warn(f"结构图长宽比 {ratio:.2f} 偏极端，建议精简节点文字或合并层级。")
    return img


# ----------------------------------------------------------------------------
# 图 2：研究流程图（步骤链）
# ----------------------------------------------------------------------------
FLOW_SIZE = 22 * S
FLOW_MAXW = 620 * S
FLOW_PAD_X = 30 * S
FLOW_PAD_Y = 16 * S
FLOW_GAP = 34 * S


def render_flow(d: dict):
    steps = d.get("steps") or []
    if not steps:
        raise ValueError("flow 图缺少 steps 字段")

    horizontal = (d.get("direction") or "vertical").lower() in ("h", "horizontal", "row")

    boxes = []
    for st in steps:
        if isinstance(st, str):
            st = {"text": st}
        boxes.append(
            BoxText(
                st.get("text", ""),
                FLOW_SIZE,
                FLOW_MAXW,
                FLOW_PAD_X,
                FLOW_PAD_Y,
                bold=True,
                sub=st.get("detail"),
                sub_size=int(FLOW_SIZE * 0.82),
            )
        )

    title = d.get("title") or ""
    title_h = (lh(26 * S) + 30 * S) if title else 0.0
    margin = 40 * S
    badge = 34 * S          # 序号圆标占用
    badge_gap = 16 * S

    if not horizontal:
        W = max(b.w for b in boxes) + badge + badge_gap + 2 * margin
        H = margin + title_h + sum(b.h for b in boxes) + FLOW_GAP * (len(boxes) - 1) + margin
        img = Image.new("RGB", (int(W), int(H)), BG)
        dr = ImageDraw.Draw(img)
        if title:
            dr.text((W / 2, margin / 2 + lh(26 * S) / 2), title, font=font(26 * S, True),
                    fill=TITLE_C, anchor="mm")

        y = margin + title_h
        centers = []
        for i, b in enumerate(boxes):
            a = accent(i)
            bx = margin + badge + badge_gap
            b.draw(dr, bx, y, blend(a, 0.94), blend(a, 0.4), a, radius=14 * S, text_c=TEXT_C)
            # 序号圆标
            ccx = margin + badge / 2
            ccy = y + b.h / 2
            dr.ellipse((ccx - badge / 2, ccy - badge / 2, ccx + badge / 2, ccy + badge / 2),
                       fill=a)
            dr.text((ccx, ccy), str(i + 1), font=font(int(19 * S), True), fill=(255, 255, 255),
                    anchor="mm")
            centers.append((bx + b.w / 2, y, y + b.h))
            y += b.h
            if i < len(boxes) - 1:
                arrow(dr, (centers[-1][0], y), (centers[-1][0], y + FLOW_GAP), LINE_C,
                      width=3 * S, head=11 * S)
                y += FLOW_GAP
        return img

    # 横向：序号在上，盒子在下，箭头水平
    W = (margin + sum(b.w for b in boxes) + FLOW_GAP * (len(boxes) - 1) + margin)
    H = margin + title_h + max(b.h for b in boxes) + 2 * margin
    img = Image.new("RGB", (int(W), int(H)), BG)
    dr = ImageDraw.Draw(img)
    if title:
        dr.text((W / 2, margin / 2 + lh(26 * S) / 2), title, font=font(26 * S, True),
                fill=TITLE_C, anchor="mm")

    y = margin + title_h
    x = margin
    for i, b in enumerate(boxes):
        a = accent(i)
        b.draw(dr, x, y, blend(a, 0.94), blend(a, 0.4), a, radius=14 * S, text_c=TEXT_C)
        ccx, ccy = x + 20 * S, y + 20 * S
        dr.ellipse((ccx - badge * 0.35, ccy - badge * 0.35, ccx + badge * 0.35, ccy + badge * 0.35),
                   fill=a)
        dr.text((ccx, ccy), str(i + 1), font=font(int(18 * S), True), fill=(255, 255, 255),
                anchor="mm")
        x += b.w
        if i < len(boxes) - 1:
            my = y + b.h / 2
            arrow(dr, (x, my), (x + FLOW_GAP, my), LINE_C, width=3 * S, head=11 * S)
            x += FLOW_GAP
    return img


# ----------------------------------------------------------------------------
# 图 3：概念关系图（中心辐射）
# ----------------------------------------------------------------------------
CON_SIZE = 21 * S
CON_CENTER_SIZE = 24 * S
CON_MAXW = 200 * S
CON_PAD_X = 14 * S
CON_PAD_Y = 11 * S


def _ray_exit(cx, cy, tx, ty, box):
    """从盒心 (cx,cy) 射向 (tx,ty)，返回射线与该盒边界的交点。"""
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return cx, cy
    t = float("inf")
    if abs(dx) > 1e-9:
        for edge in (box[0], box[2]):
            tt = (edge - cx) / dx
            if tt > 0:
                yy = cy + tt * dy
                if box[1] - 1 <= yy <= box[3] + 1:
                    t = min(t, tt)
    if abs(dy) > 1e-9:
        for edge in (box[1], box[3]):
            tt = (edge - cy) / dy
            if tt > 0:
                xx = cx + tt * dx
                if box[0] - 1 <= xx <= box[2] + 1:
                    t = min(t, tt)
    if t == float("inf"):
        return cx, cy
    return cx + t * dx, cy + t * dy


def render_concept(d: dict):
    center_raw = d.get("center") or {"text": d.get("title", "核心概念")}
    nodes_raw = d.get("nodes") or []
    if not nodes_raw:
        raise ValueError("concept 图缺少 nodes 字段")

    c_mw = int(d.get("center_max_width", 260) * S)
    n_mw = int(d.get("node_max_width", CON_MAXW / S) * S)

    cb = BoxText(center_raw.get("text", ""), CON_CENTER_SIZE, c_mw,
                 CON_PAD_X * 1.3, CON_PAD_Y * 1.3, bold=True)
    nodes = []
    for i, nd in enumerate(nodes_raw):
        if isinstance(nd, str):
            nd = {"text": nd}
        bt = BoxText(nd.get("text", ""), CON_SIZE, n_mw, CON_PAD_X, CON_PAD_Y)
        nodes.append({
            "bt": bt,
            "text": str(nd.get("text", "")).strip(),
            "relation": nd.get("relation") or nd.get("label") or "",
            "accent": nd.get("accent", i),
            "pos": None,
        })

    n = len(nodes)
    max_w = max([nd["bt"].w for nd in nodes] + [cb.w])
    max_h = max([nd["bt"].h for nd in nodes] + [cb.h])

    # 圆环半径：保证弧长足够，且不小于中心盒尺度
    arc_need = max_w + 56 * S
    R = max(
        n * arc_need / (2 * math.pi),
        max_w * 1.05 + 60 * S,
        max_h + 160 * S,
    )

    title = d.get("title") or ""
    title_h = (lh(26 * S) + 30 * S) if title else 0.0
    margin = 40 * S

    W = 2 * R + max_w + 2 * margin
    H = 2 * R + max_h + 2 * margin + title_h
    img = Image.new("RGB", (int(W), int(H)), BG)
    dr = ImageDraw.Draw(img)

    if title:
        dr.text((W / 2, margin / 2 + lh(26 * S) / 2), title, font=font(26 * S, True),
                fill=TITLE_C, anchor="mm")

    ccx = W / 2
    ccy = margin + title_h + (H - margin - title_h) / 2

    # 淡淡的环，帮助视觉分组
    dr.ellipse((ccx - R, ccy - R, ccx + R, ccy + R), outline=blend(BORDER_C, 0.55),
               width=2 * S)

    # 圆环节点位置
    for i, nd in enumerate(nodes):
        ang = -math.pi / 2 + i * 2 * math.pi / n
        px = ccx + R * math.cos(ang)
        py = ccy + R * math.sin(ang)
        nd["pos"] = (px, py)

    cbox = (ccx - cb.w / 2, ccy - cb.h / 2, ccx + cb.w / 2, ccy + cb.h / 2)

    # 连线标签避让：标签沿线段滑动，挑第一个不与已有标签/中心盒重叠的位置
    LABEL_SIZE = int(17 * S)
    LABEL_PAD = 5 * S
    placed: list = [cbox]

    def _rect(x, y, w):
        h = lh(LABEL_SIZE) / 2 + LABEL_PAD * 0.5
        return (x - w / 2 - LABEL_PAD, y - h, x + w / 2 + LABEL_PAD, y + h)

    def _hit(r):
        for o in placed:
            if not (r[2] < o[0] or r[0] > o[2] or r[3] < o[1] or r[1] > o[3]):
                return True
        return False

    def put_label(text, p1, p2, ts):
        lf = font(LABEL_SIZE)
        w = lf.getlength(text)
        chosen = None
        for t in ts:
            mx = p1[0] + (p2[0] - p1[0]) * t
            my = p1[1] + (p2[1] - p1[1]) * t
            r = _rect(mx, my, w)
            if not _hit(r):
                chosen = (mx, my, r)
                break
        if chosen is None:
            mx = p1[0] + (p2[0] - p1[0]) * ts[0]
            my = p1[1] + (p2[1] - p1[1]) * ts[0]
            chosen = (mx, my, _rect(mx, my, w))
        mx, my, r = chosen
        placed.append(r)
        dr.rounded_rectangle(r, radius=5 * S, fill=(255, 255, 255),
                             outline=blend(BORDER_C, 0.4), width=1 * S)
        dr.text((mx, my), text, font=lf, fill=SUB_C, anchor="mm")

    # 中心 -> 节点 连线（带关系标签）
    NEAR_TS = (0.66, 0.58, 0.74, 0.50, 0.82, 0.42, 0.90)
    for i, nd in enumerate(nodes):
        a = accent(nd["accent"])
        tx, ty = nd["pos"]
        nbox = (tx - nd["bt"].w / 2, ty - nd["bt"].h / 2, tx + nd["bt"].w / 2, ty + nd["bt"].h / 2)
        p1 = _ray_exit(ccx, ccy, tx, ty, cbox)
        p2 = _ray_exit(tx, ty, ccx, ccy, nbox)
        arrow(dr, p1, p2, blend(a, 0.3), width=2 * S, head=10 * S)
        if nd["relation"]:
            put_label(nd["relation"], p1, p2, NEAR_TS)

    # 节点之间的交叉连线（端点按节点文字匹配，允许省略首尾空白）
    by_text = {nd["text"]: nd for nd in nodes}
    for lk in d.get("links") or []:
        a_node = by_text.get(str(lk.get("from", "")).strip())
        b_node = by_text.get(str(lk.get("to", "")).strip())
        if not a_node or not b_node:
            warn(f"概念图中未找到连线端点：{lk.get('from')} -> {lk.get('to')}")
            continue
        ax, ay = a_node["pos"]
        bx, by = b_node["pos"]
        abox = (ax - a_node["bt"].w / 2, ay - a_node["bt"].h / 2,
                ax + a_node["bt"].w / 2, ay + a_node["bt"].h / 2)
        bbox = (bx - b_node["bt"].w / 2, by - b_node["bt"].h / 2,
                bx + b_node["bt"].w / 2, by + b_node["bt"].h / 2)
        p1 = _ray_exit(ax, ay, bx, by, abox)
        p2 = _ray_exit(bx, by, ax, ay, bbox)
        arrow(dr, p1, p2, blend(LINE_C, 0.0), width=2 * S, head=10 * S)
        if lk.get("label"):
            put_label(lk["label"], p1, p2, (0.5, 0.58, 0.42, 0.66, 0.34, 0.74))

    # 节点
    for nd in nodes:
        a = accent(nd["accent"])
        tx, ty = nd["pos"]
        nd["bt"].draw(dr, tx - nd["bt"].w / 2, ty - nd["bt"].h / 2,
                      blend(a, 0.93), blend(a, 0.35), a, radius=12 * S)

    # 中心节点最后画，压住连线
    rrect(dr, cbox, 16 * S, fill=accent(0), outline=accent(0), width=2 * S)
    draw_lines(dr, cb.lines, cbox[0] + cb.pad_x, cbox[1] + cb.pad_y,
               CON_CENTER_SIZE, (255, 255, 255))
    return img


# ----------------------------------------------------------------------------
# 驱动
# ----------------------------------------------------------------------------
RENDERERS = {"tree": render_tree, "flow": render_flow, "concept": render_concept}


def pad_to_ratio(img, min_ratio: float):
    """横向补白，使 W/H >= min_ratio。

    Word 页宽约 14.6cm、可用高度约 21cm，即安全长宽比 >= 0.70。
    竖长的图若按页宽铺满会高出页面，这里先把画布补成足够宽，
    让文档端可以「按页宽放置」而不会溢出。
    """
    if min_ratio <= 0 or img.height <= 0:
        return img
    need_w = int(round(img.height * min_ratio))
    if img.width >= need_w:
        return img
    out = Image.new("RGB", (need_w, img.height), BG)
    out.paste(img, ((need_w - img.width) // 2, 0))
    return out


def render_one(d: dict, outdir: str, idx: int, fit_ratio: float = 0.70, out_scale: int = S):
    t = (d.get("type") or "").strip().lower()
    if t not in RENDERERS:
        raise ValueError(f"不支持的图表类型：{t!r}（可选：tree / flow / concept）")

    img = RENDERERS[t](d)

    # 画布已按 S 倍超采样绘制；输出到 out_scale 倍逻辑尺寸
    logical_w = max(1, img.width // S)
    logical_h = max(1, img.height // S)
    if out_scale != S:
        img = img.resize((logical_w * out_scale, logical_h * out_scale), Image.LANCZOS)

    if d.get("fit_ratio") is not None:
        img = pad_to_ratio(img, float(d["fit_ratio"]))
    elif fit_ratio:
        img = pad_to_ratio(img, fit_ratio)

    did = str(d.get("id") or f"fig{idx}")
    safe = "".join(c for c in did if c.isalnum() or c in "-_") or f"fig{idx}"
    path = os.path.join(outdir, f"{safe}_{t}.png")
    # 写入 300dpi 元数据：即使 HTML 里漏写 width 属性，转换引擎推出的宽度也接近版心
    img.save(path, "PNG", optimize=True, dpi=(300, 300))
    return {"id": did, "type": t, "path": os.path.abspath(path),
            "width": img.width, "height": img.height,
            "ratio": round(img.width / img.height, 3)}


def main():
    ap = argparse.ArgumentParser(description="文献阅读器 · 图表渲染器")
    ap.add_argument("spec", help="JSON 规格文件路径")
    ap.add_argument("--outdir", "-o", default=None, help="PNG 输出目录（默认与 spec 同目录）")
    ap.add_argument("--fit-ratio", type=float, default=0.70,
                    help="最小长宽比，低于该值则横向补白（默认 0.70，适配 A4 页宽/页高；0 表示不补白）")
    ap.add_argument("--out-scale", type=int, default=S,
                    help=f"输出分辨率倍数（默认 {S}，即逻辑尺寸的 {S} 倍；PNG 固定写入 300dpi）")
    args = ap.parse_args()

    try:
        with open(args.spec, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"无法读取 JSON 规格：{e}"}, ensure_ascii=False))
        return 1

    diagrams = spec.get("diagrams") if isinstance(spec, dict) and "diagrams" in spec else [spec]
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.spec))
    os.makedirs(outdir, exist_ok=True)

    images = []
    for i, d in enumerate(diagrams, 1):
        try:
            images.append(render_one(d, outdir, i, args.fit_ratio, args.out_scale))
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"第 {i} 张图渲染失败：{e}"}, ensure_ascii=False))
            return 1

    print(json.dumps({"ok": True, "images": images, "warnings": WARNINGS}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
