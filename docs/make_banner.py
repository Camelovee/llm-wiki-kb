#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_banner.py — 用 Pillow 绘制 llm-wiki-obsidian 的 README 横幅(3200×2000)。

设计:暗色「知识苗圃」——左侧不可变的原始资料文档,经「编译」烬点,
右侧一张按成熟度(种子/发芽/常青)生长的 Obsidian 式图谱。
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

W, H = 3200, 2000
BASE = (16, 24, 18)          # #101812 深苔墨
JADE = (143, 199, 163)       # #8FC7A3
JADE_CORE = (191, 227, 204)  # #BFE3CC
AMBER = (217, 169, 78)       # #D9A94E
TRUNK = (138, 106, 51)       # #8A6A33
PAPER = (239, 235, 221)      # #EFEBDD
MUTED = (152, 160, 148)      # #98A094
FAINT = (110, 120, 108)      # #6E786C
FAINT2 = (126, 136, 124)     # #7E887C
SRC = (185, 178, 160)        # #B9B2A0
LAYER_JADE = (168, 205, 180) # #A8CDB4


def blend(fg, a, bg=BASE):
    return tuple(int(fg[i] * a + bg[i] * (1 - a)) for i in range(3))


def font_songti(size, bold=True):
    return ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", size, index=1 if bold else 3)


def font_sans(size, w6=True):
    idx = 2 if w6 else 0  # Hiragino Sans GB: 0=W3,2=W6(近似)
    return ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", size, index=idx)


def text_ls(d, xy, s, f, fill, ls=0, anchor_left=True):
    """逐字绘制以支持字距;返回总宽。"""
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + ls
    return x - xy[0] - (ls if s else 0)


def vtext(d, xy, s, f, fill, ls=0):
    """竖排文字(逐字向下)。"""
    x, y = xy
    for ch in s:
        d.text((x, y), ch, font=f, fill=fill)
        y += f.size + ls


def cubic(p0, p1, p2, p3, n=140):
    pts = []
    for i in range(n + 1):
        t = i / n
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def leaf(img, cx, cy, rx, ry, deg, color):
    pad = int(max(rx, ry) * 2 + 8)
    tile = Image.new("RGBA", (pad, pad), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.ellipse((pad / 2 - rx, pad / 2 - ry, pad / 2 + rx, pad / 2 + ry), fill=color + (255,))
    tile = tile.rotate(deg, resample=Image.BICUBIC, center=(pad / 2, pad / 2))
    img.paste(tile, (int(cx - pad / 2), int(cy - pad / 2)), tile)


def sprout(img, x, y, s, a):
    """双叶芽:(x,y) 为土面点,s 尺寸系数,a 不透明度。"""
    c = blend(JADE, a)
    d = ImageDraw.Draw(img)
    top = (x, y - 34 * s)
    d.line([(x, y), top], fill=c, width=int(4 * s))
    leaf(img, x - 13 * s, y - 40 * s, 15 * s, 8 * s, -28, c)
    leaf(img, x + 13 * s, y - 40 * s, 15 * s, 8 * s, 28, c)


def pine(img, x, y, s):
    """三层塔松:(x,y) 为土面点,s 尺寸系数。"""
    d = ImageDraw.Draw(img)
    d.ellipse((x - 34 * s, y - 7 * s, x + 34 * s, y + 7 * s), fill=blend(AMBER, 0.14))
    p = [(0, -96), (26, -48), (10, -48), (34, -12), (16, -12), (40, 0),
         (-40, 0), (-16, -12), (-34, -12), (-10, -48), (-26, -48)]
    d.polygon([(x + px * s, y + py * s) for px, py in p], fill=AMBER)
    d.rectangle((x - 4 * s, y, x + 4 * s, y + 12 * s), fill=TRUNK)


def main():
    img = Image.new("RGB", (W, H), BASE)
    d = ImageDraw.Draw(img)

    # ---- 微光底 ----
    for (cx, cy, rx, ry, color, amax) in [
        (2350, 880, 980, 760, JADE, 0.14),
        (560, 1750, 760, 460, AMBER, 0.07),
    ]:
        m = ImageOps.invert(Image.radial_gradient("L")).resize((rx * 2, ry * 2))
        m = m.point(lambda v: int((v / 255) ** 2 * 255 * amax))
        layer = Image.new("RGB", m.size, color)
        img.paste(layer, (cx - rx, cy - ry), m)
    d = ImageDraw.Draw(img)

    # ---- 颗粒 ----
    noise = Image.effect_noise((W, H), 30).point(lambda v: v // 26)
    img.paste(Image.new("RGB", (W, H), PAPER), (0, 0), noise)
    d = ImageDraw.Draw(img)

    # ---- 左:原始资料 ----
    docs = [("文章", 1440), ("笔记", 1628), ("论文", 1816)]
    for label, ty in docs:
        x = 240
        d.rounded_rectangle((x, ty, x + 330, ty + 148), radius=14,
                            fill=blend(SRC, 0.07), outline=blend(SRC, 0.38), width=2)
        d.polygon([(x + 300, ty), (x + 330, ty + 30), (x + 300, ty + 30)], fill=blend(SRC, 0.16))
        d.text((x + 40, ty + 20), label, font=font_sans(34), fill=SRC)
        d.text((x + 40, ty + 72), "source.md · 只增不改", font=font_sans(22), fill=blend(SRC, 0.5))

    # 源 → 烬
    for p0, p1, p2, p3, a in [
        ((570, 1514), (760, 1514), (820, 1560), (1005, 1610), 0.34),
        ((570, 1702), (780, 1702), (860, 1650), (1008, 1630), 0.42),
        ((570, 1890), (800, 1890), (880, 1700), (1010, 1650), 0.30),
    ]:
        d.line(cubic(p0, p1, p2, p3), fill=blend(JADE, a), width=3, joint="curve")

    # 编译烬
    m = ImageOps.invert(Image.radial_gradient("L")).resize((300, 300))
    m = m.point(lambda v: int((v / 255) ** 2.4 * 255 * 0.9))
    img.paste(Image.new("RGB", (300, 300), JADE), (1042 - 150, 1636 - 150), m)
    d = ImageDraw.Draw(img)
    d.ellipse((1031, 1625, 1053, 1647), fill=JADE_CORE)
    w = text_ls(d, (1042 - 33, 1568 - 15), "编", font_songti(30, bold=False), blend(JADE, 0.85))
    text_ls(d, (1042 - 33 + w + 10, 1568 - 15), "译", font_songti(30, bold=False), blend(JADE, 0.85))

    # ---- 右:图谱连线(wikilink) ----
    edges = [
        ((1500, 1000), (1600, 900), (1660, 800), (1750, 700), 0.30),
        ((1750, 700), (1900, 640), (2000, 600), (2100, 560), 0.20),
        ((2100, 560), (2260, 540), (2360, 540), (2450, 560), 0.16),
        ((2450, 560), (2560, 640), (2640, 760), (2700, 900), 0.26),
        ((2700, 900), (2740, 1010), (2730, 1090), (2700, 1150), 0.18),
        ((2700, 1150), (2600, 1260), (2500, 1340), (2400, 1400), 0.28),
        ((2400, 1400), (2220, 1450), (2080, 1450), (1950, 1450), 0.16),
        ((1950, 1450), (1800, 1380), (1720, 1320), (1650, 1240), 0.30),
        ((1650, 1240), (1560, 1150), (1520, 1080), (1500, 1000), 0.22),
        ((2100, 560), (2120, 700), (2110, 780), (2100, 850), 0.24),
        ((2100, 850), (2200, 920), (2300, 1000), (2400, 1080), 0.20),
        ((2400, 1080), (2460, 1160), (2440, 1300), (2400, 1400), 0.14),
        ((1500, 1000), (1580, 1120), (1610, 1180), (1650, 1240), 0.12),
        ((2350, 1400), (2400, 1290), (2420, 1180), (2450, 1050), 0.10),
    ]
    for p0, p1, p2, p3, a in edges:
        d.line(cubic(p0, p1, p2, p3), fill=blend(JADE, a), width=2, joint="curve")

    # [[ ]] 签名(旋转)
    tile = Image.new("RGBA", (220, 100), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    text_ls(td, (10, 10), "[[ ]]", font_sans(44), blend(JADE, 0.5), ls=6)
    tile = tile.rotate(7, resample=Image.BICUBIC, expand=True)
    img.paste(tile, (2036 - tile.width // 2, 1180 - tile.height // 2), tile)
    d = ImageDraw.Draw(img)

    # 种子
    for (x, y, r, a) in [(1500, 1000, 10, 1.0), (2100, 850, 9, 0.9), (2450, 1050, 8, 0.8),
                         (1650, 1240, 9, 0.85), (2700, 900, 8, 0.75), (2350, 1400, 7, 0.7)]:
        d.ellipse((x - r, y - r, x + r, y + r), fill=blend(JADE, a))

    # 发芽
    for (x, y, s, a) in [(1875, 790, 1.0, 0.95), (2280, 660, 0.88, 0.85), (2560, 760, 0.76, 0.75),
                         (1800, 1350, 0.88, 0.85), (2170, 1290, 0.70, 0.65)]:
        sprout(img, x, y, s, a)
    d = ImageDraw.Draw(img)

    # 常青
    for (x, y, s) in [(1750, 700, 1.0), (2450, 560, 0.88), (2700, 1150, 1.0), (1950, 1450, 0.92)]:
        pine(img, x, y, s)
    d = ImageDraw.Draw(img)

    # 类目微标注
    d.text((1646, 596), "概念", font=font_sans(30), fill=FAINT2)
    d.text((2558, 1210), "决策", font=font_sans(30), fill=FAINT2)
    d.text((1808, 1520), "主题枢纽", font=font_sans(30), fill=FAINT2)

    # 图例
    lg = 2480
    d.ellipse((lg - 8, 1844, lg + 8, 1860), fill=blend(JADE, 0.85))
    d.text((lg + 26, 1836), "种子", font=font_sans(28), fill=blend(MUTED, 0.95))
    sprout(img, lg + 196, 1856, 0.55, 0.95)
    d.text((lg + 224, 1836), "发芽", font=font_sans(28), fill=blend(MUTED, 0.95))
    pine(img, lg + 396, 1856, 0.3)
    d.text((lg + 424, 1836), "常青", font=font_sans(28), fill=blend(MUTED, 0.95))

    # ---- 文案 ----
    d.rounded_rectangle((200, 214, 226, 240), radius=7, fill=JADE)
    wname = text_ls(d, (252, 208), "llm-wiki-obsidian", font_sans(42, w6=True), PAPER, ls=3)
    d.text((252 + wname + 36, 216), "知识库初始化与养护", font=font_songti(28, bold=False), fill=FAINT2)

    f_h = font_songti(158, bold=True)
    y = 520
    for line in ["把读过的", "编译成一座", "会长大的知识库"]:
        text_ls(d, (200, y), line, f_h, PAPER, ls=8)
        y += int(158 * 1.32)

    f_s = font_sans(36)
    d.text((200, 1208), "Karpathy 的 LLM Wiki 工作流,装进一个 skill。", font=f_s, fill=blend(MUTED, 1.0))
    segs = [("你", MUTED), ("投喂来源、提问、做裁决", PAPER), (";知识库由 LLM 持续编译、养护。", MUTED)]
    x = 200
    for t, c in segs:
        x += text_ls(d, (x, 1208 + int(36 * 1.75)), t, f_s, c) + 2

    # 竖排层标注
    vtext(d, (128, 1470), "原始资料", font_songti(34, bold=False), MUTED, ls=14)
    vtext(d, (184, 1630), "不可变", font_songti(26, bold=False), FAINT, ls=10)
    vtext(d, (1300, 420), "知识库", font_songti(34, bold=False), LAYER_JADE, ls=14)
    vtext(d, (1356, 620), "LLM 养护", font_songti(26, bold=False), FAINT, ls=10)

    out = "docs/banner.jpg"
    img.convert("RGB").save(out, quality=90)
    print("saved", out, img.size)


if __name__ == "__main__":
    main()
