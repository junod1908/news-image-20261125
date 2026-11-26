#!/usr/bin/env python3
"""news-image-20261125 -- "The World in One Day": Wednesday, 25 November 2026.

A one-page broadsheet poster summing up 25 November 2026's world news:
48 date-audited stories across 8 regions, 3 illustrated lead stories, a
numbered world map, a UTC timeline and a DATE CHECK footer naming the
stories that were left out because they happened on an earlier day.

Standard library only. No network. Deterministic: two runs write the
same bytes. Reads font_atlas.png / font_atlas.json (anti-aliased DejaVu
glyphs rendered at build time) from this repository at run time.

Usage:  mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
Output: $MAKEFUN_OUTPUT_DIR/entry.png  (1024x1024, under 1 MiB)
"""

import json
import math
import os
import struct
import sys
import zlib

W, H = 1024, 1024

# ---------------------------------------------------------------- palette
PAPER = (247, 243, 234)   # newsprint cream
PAPER2 = (255, 253, 247)  # card white
INK = (22, 21, 19)
GREY = (96, 92, 84)
LGREY = (178, 172, 160)
RED = (179, 39, 30)
NAVY = (30, 58, 95)
SLATE = (51, 86, 107)     # map land
TEAL = (15, 118, 110)
ORANGE = (199, 123, 33)
GREEN = (46, 125, 50)
PURPLE = (109, 40, 217)
BROWN = (107, 91, 30)
RULE = (60, 56, 48)
DARK = (20, 38, 63)       # footer navy
FOOTGREY = (176, 184, 196)
AMBER = (217, 158, 24)

# ---------------------------------------------------------------- PNG codec
# Minimal stdlib PNG reader (8-bit, colour types 0/2/6) and writer.
# Only used for the glyph atlas (input) and the poster (output).


def _chunk(ctype, data):
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(
        ">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def decode_png(raw):
    """Return (width, height, rgba bytearray)."""
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, w, h, bitdepth, ctype, idat = 8, 0, 0, 0, 0, b""
    while pos < len(raw):
        ln = struct.unpack(">I", raw[pos:pos + 4])[0]
        typ = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bitdepth, ctype = struct.unpack(">IIBB", data[:10])
        elif typ == b"IDAT":
            idat += data
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if bitdepth != 8 or ctype not in (0, 2, 6):
        raise ValueError("unsupported atlas PNG (need 8-bit grey/RGB/RGBA)")
    nch = {0: 1, 2: 3, 6: 4}[ctype]
    px = zlib.decompress(idat)
    stride = w * nch
    out = bytearray(w * h * 4)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = px[p]
        p += 1
        line = bytearray(px[p:p + stride])
        p += stride
        if f == 1:
            for i in range(nch, stride):
                line[i] = (line[i] + line[i - nch]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - nch] if i >= nch else 0
                b = prev[i]
                c = prev[i - nch] if i >= nch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif f != 0:
            raise ValueError("bad PNG filter %d" % f)
        prev = line
        for x in range(w):
            o = (y * w + x) * 4
            s = x * nch
            if ctype == 6:
                out[o:o + 4] = line[s:s + 4]
            elif ctype == 2:
                out[o:o + 3] = line[s:s + 3]
                out[o + 3] = 255
            else:
                out[o] = out[o + 1] = out[o + 2] = line[s]
                out[o + 3] = 255
    return w, h, out


def encode_png(w, h, rgb):
    """Encode an RGB bytearray as a deterministic PNG (filter 0, level 9)."""
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw += rgb[y * stride:(y + 1) * stride]
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))


# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 3)
        self.fill_rect(0, 0, w, h, bg)

    def _off(self, x, y):
        return (y * self.w + x) * 3

    def fill_rect(self, x, y, w, h, c):
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + w), min(self.h, y + h)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(c) * (x1 - x0)
        for yy in range(y0, y1):
            o = self._off(x0, yy)
            self.px[o:o + len(row)] = row

    def rect(self, x, y, w, h, c, t=1):
        self.fill_rect(x, y, w, t, c)
        self.fill_rect(x, y + h - t, w, t, c)
        self.fill_rect(x, y, t, h, c)
        self.fill_rect(x + w - t, y, t, h, c)

    def hline(self, x0, x1, y, c, t=1):
        self.fill_rect(x0, y, x1 - x0, t, c)

    def vline(self, x, y0, y1, c, t=1):
        self.fill_rect(x, y0, t, y1 - y0, c)

    def line(self, x0, y0, x1, y1, c, t=1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err, x, y = dx - dy, x0, y0
        while True:
            self.fill_rect(x - t // 2, y - t // 2, t, t, c)
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    def fill_circle(self, cx, cy, r, c):
        for yy in range(cy - r, cy + r + 1):
            dx = int((r * r - (yy - cy) ** 2) ** 0.5)
            self.fill_rect(cx - dx, yy, 2 * dx + 1, 1, c)

    def ring(self, cx, cy, r, c, t=1):
        for yy in range(cy - r - t, cy + r + t + 1):
            for xx in range(cx - r - t, cx + r + t + 1):
                d = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5
                if abs(d - r) <= t / 2 + 0.4:
                    if 0 <= xx < self.w and 0 <= yy < self.h:
                        o = self._off(xx, yy)
                        self.px[o:o + 3] = bytes(c)

    def fill_poly(self, pts, c):
        # even-odd scanline fill
        ys = [p[1] for p in pts]
        for y in range(max(0, min(ys)), min(self.h - 1, max(ys)) + 1):
            xs = []
            n = len(pts)
            for i in range(n):
                x0, y0 = pts[i]
                x1, y1 = pts[(i + 1) % n]
                if (y0 <= y < y1) or (y1 <= y < y0):
                    xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.fill_rect(int(round(xs[i])), y,
                               int(round(xs[i + 1])) - int(round(xs[i])) + 1, 1, c)

    def blend_px(self, x, y, c, a):
        if not (0 <= x < self.w and 0 <= y < self.h) or a == 0:
            return
        o = self._off(x, y)
        if a == 255:
            self.px[o:o + 3] = bytes(c)
            return
        for k in range(3):
            self.px[o + k] = (c[k] * a + self.px[o + k] * (255 - a)) // 255


# ---------------------------------------------------------------- atlas type
WARN = "\u26a0"  # drawn as a triangle, never as a font glyph


class Atlas:
    def __init__(self, base):
        with open(os.path.join(base, "font_atlas.json"), "r") as fh:
            self.meta = json.load(fh)
        with open(os.path.join(base, "font_atlas.png"), "rb") as fh:
            self.aw, self.ah, self.px = decode_png(fh.read())

    def _spec(self, family, weight, size):
        return self.meta["%s-%s-%d" % (family, weight, size)]

    def width(self, text, family, weight, size):
        spec = self._spec(family, weight, size)
        tot = 0.0
        for ch in text:
            if ch == WARN:
                tot += 13
            else:
                g = spec["chars"].get(ch)
                tot += g[4] if g else spec["chars"]["?"][4]
        return tot

    def draw(self, cv, x, y_top, text, family, weight, size, color):
        """Draw text; y_top is the top of the em box. Returns width drawn."""
        spec = self._spec(family, weight, size)
        asc = spec["ascent"]
        baseline = y_top + asc
        pen = float(x)
        for ch in text:
            if ch == WARN:
                self._warn(cv, int(round(pen)), y_top, size, color)
                pen += 13
                continue
            g = spec["chars"].get(ch)
            if g is None:
                g = spec["chars"]["?"]
            dx, dy, iw, ih, adv, ix, iy = g
            if iw and ih:
                dest_x = int(round(pen)) + dx
                dest_y = baseline + dy
                for yy in range(ih):
                    sy = iy + yy
                    dy = dest_y + yy
                    if dy < 0 or dy >= cv.h:
                        continue
                    for xx in range(iw):
                        a = self.px[((sy * self.aw) + ix + xx) * 4 + 3]
                        if a:
                            cv.blend_px(dest_x + xx, dy, color, a)
            pen += adv
        return pen - x

    def _warn(self, cv, x, y_top, size, color):
        # small amber triangle with "!" -- the borderline flag
        s = max(9, min(14, size + 2))
        cx = x + s // 2
        cv.fill_poly([(cx, y_top), (x + s, y_top + s), (x, y_top + s)], AMBER)
        cv.fill_rect(cx - 1, y_top + 2, 2, s - 6, INK)
        cv.fill_rect(cx - 1, y_top + s - 3, 2, 2, INK)

    def draw_center(self, cv, cx, y_top, text, family, weight, size, color):
        w = self.width(text, family, weight, size)
        return self.draw(cv, int(round(cx - w / 2)), y_top, text,
                         family, weight, size, color)

    def wrap(self, text, family, weight, size, max_w):
        """Greedy word wrap; returns list of lines."""
        words, lines, cur = text.split(" "), [], ""
        for wd in words:
            trial = (cur + " " + wd).strip()
            if self.width(trial, family, weight, size) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
        return lines

# ---------------------------------------------------------------- data
# 48 stories, all happened or first reported on Wed 25 Nov 2026 (UTC).
# #13 (Mexico / Ines Gomez Mont extradition) from the research file was
# dropped: it was only corroborated between rival posters, never from a
# primary source. It is replaced by C2 (Australia apologises to LGBTQ
# veterans), fully verified (Reuters + Defence). Numbers below are the
# poster's own; regions: NA, LATAM, EU, AF, ME, ASIA, OC, GL.
# meta = "source time · CONFIDENCE" ; conf in OFFICIAL / REPORTED / CLAIM.
STORIES = [
    ("NA",  "US proposes tariffs on 14 economies", "Reuters 13:15 UTC · OFFICIAL"),
    ("NA",  "Army blows up 5 tons of lead azide in Iowa", "AP · EPA · OFFICIAL"),
    ("NA",  "Dow erases a 1,100-point loss", "Barron's · AP · REPORTED"),
    ("NA",  "US GDP revised up to 4.3%", "BEA via Reuters · OFFICIAL"),
    ("NA",  "FCC clears 1m SpaceX satellites", "FCC 18:00 UTC · OFFICIAL"),
    ("NA",  "Rutte meets Trump at Mar-a-Lago", "Scripps 19:53 UTC · REPORTED"),
    ("NA",  "Abrego Garcia lands in Spain", "BBC 01:51 UTC · REPORTED"),
    ("NA",  "Tiny robots deliver drugs to the brain", "Caltech 19:02 UTC · OFFICIAL"),
    ("LATAM", "Brazil recalls ambassador from Argentina", "El País 10:00 UTC · REPORTED"),
    ("LATAM", "Cartagena supermarket hostages freed " + WARN, "Reuters · freed Wed, siege began Tue · REPORTED"),
    ("LATAM", "Paraná storm kills 6", "AFP 16:14 UTC · REPORTED"),
    ("LATAM", "Mexico freezes Sinaloa governor's accounts", "Infobae 12:56 UTC · REPORTED"),
    ("EU",  "UK energy cap to rise 26%", "Ofgem 12:00 UTC · OFFICIAL"),
    ("EU",  "Poundland collapses, 11,000 jobs at risk", "BBC 15:46 UTC · REPORTED"),
    ("EU",  "EU launches €50bn tech fund", "Reuters 05:00 UTC · OFFICIAL"),
    ("EU",  "Poland plans a no-fly zone", "PAP 14:19 UTC · REPORTED"),
    ("EU",  "Merz: Russia wants more than Ukraine", "Reuters · REPORTED"),
    ("EU",  "Eurostar strike cancels Paris–London trains", "AP 10:02 UTC · REPORTED"),
    ("EU",  "Met Police still institutionally racist", "Guardian 00:01 UTC · REPORTED"),
    ("EU",  "Greek general strike halts ferries, flights", "eKathimerini 15:22 UTC · REPORTED"),
    ("EU",  "Kyiv hits two refineries in Samara", "Kyiv Independent 01:08 UTC · REPORTED"),
    ("EU",  "Champions League: Liverpool & Lille win", "UEFA 22:40 UTC · OFFICIAL"),
    ("AF",  "Cairo tanker fire kills 30+", "AP 19:14 UTC · REPORTED"),
    ("AF",  "Court sets aside Phala Phala report", "Reuters · REPORTED"),
    ("AF",  "RSF drone kills 19 in Blue Nile " + WARN, "Reported Wed; strike Tue night · REPORTED"),
    ("AF",  "Ebola: 11,700 cases, workers evacuated " + WARN, "AP 18:50 UTC · REPORTED"),
    ("AF",  "Nollywood actor Pete Edochie dies at 79", "BBC 05:13 UTC · REPORTED"),
    ("AF",  "Proteas sweep Bangladesh 2–0", "ICC 13:04 UTC · OFFICIAL"),
    ("ME",  "Houthis claim Ras Tanura refinery hit", "Reuters · CLAIM"),
    ("ME",  "Coalition bombs Hodeidah port", "Democracy Now! · REPORTED"),
    ("ME",  "Israeli strike kills Hamas official in Gaza", "Reuters · REPORTED"),
    ("ME",  "Iraq court: Baghdad controls Kurdish borders", "Reuters 19:00 UTC · REPORTED"),
    ("ME",  "Lebanon to open second airport at Kleiat", "Reuters · REPORTED"),
    ("ME",  "Iran VP: US blockade “not concerning”", "Reuters · REPORTED"),
    ("ME",  "Libya vows revenge on Kyiv " + WARN, "AP · vow reported Wed; officers died Tue night · REPORTED"),
    ("ASIA", "Shenzhou-24 carries Pakistani astronaut", "AP 00:30 UTC · REPORTED"),
    ("ASIA", "Kospi plunges 6.2% on AI doubts", "AP 04:05 UTC · REPORTED"),
    ("ASIA", "West Java gold-mine flood kills 9", "AP 07:10 UTC · REPORTED"),
    ("ASIA", "Dhaka garment wages up 36%", "AFP · REPORTED"),
    ("ASIA", "Malaysia sues Google for RM600m", "Malaysiakini 06:52 UTC · REPORTED"),
    ("ASIA", "M5.1 quake jolts Antique, Philippines", "Inquirer 00:14 UTC · REPORTED"),
    ("ASIA", "Karachi building collapse kills 3", "Dawn 09:23 UTC · REPORTED"),
    ("ASIA", "N. Korea expels Swiss diplomat in 48 hours", "AP 03:30 UTC · REPORTED"),
    ("OC",  "Solomons–Australia sign security pact", "ABC 01:22 UTC · REPORTED"),
    ("OC",  "Australia inflation jumps to 4.9%", "ABS via Reuters · OFFICIAL"),
    ("OC",  "Australia passes Digital Duty of Care", "AP 09:14 UTC · REPORTED"),
    ("OC",  "Australia apologises to LGBTQ veterans", "Reuters · REPORTED"),
    ("GL",  "Hera finds giant crater left by DART", "ESA 18:00 UTC · OFFICIAL"),
]

REGIONS = [
    ("NORTH AMERICA", "NA", RED),
    ("LATIN AMERICA", "LATAM", ORANGE),
    ("EUROPE", "EU", NAVY),
    ("AFRICA", "AF", BROWN),
    ("MIDDLE EAST", "ME", TEAL),
    ("ASIA", "ASIA", GREEN),
    ("OCEANIA", "OC", PURPLE),
    ("GLOBAL", "GL", GREY),
]
REGION_COLOR = {code: col for _, code, col in REGIONS}
# columns of the numbered index: (region, first story, last story) 1-based
COLUMNS = [
    [("NORTH AMERICA", 1, 8), ("LATIN AMERICA", 9, 12), ("EUROPE", 13, 16)],
    [("EUROPE", 17, 22), ("AFRICA", 23, 28), ("MIDDLE EAST", 29, 32)],
    [("MIDDLE EAST", 33, 35), ("ASIA", 36, 43), ("OCEANIA", 44, 47),
     ("GLOBAL", 48, 48)],
]

# hero stories: (kicker, headline, body, meta, art)
HEROES = [
    ("AMERICAS · TRADE · #1",
     "US proposes tariffs on 14 economies",
     "China 20%, EU 15%, India 25%, Vietnam up to 35%. USTR cites excess "
     "capacity; hearings in January.",
     "Reuters 13:15 UTC · OFFICIAL", "bars"),
    ("ASIA · SPACE · #36",
     "Shenzhou-24 carries a Pakistani astronaut",
     "Zeeshan Ali, 40, is the first Pakistani — and first foreigner — "
     "aboard Tiangong. Docked 03:56 UTC.",
     "AP 00:30 UTC · launch, docked 03:56 · REPORTED", "rocket"),
    ("ASIA · MARKETS · #37",
     "Kospi plunges 6.2% as AI doubts spread",
     "SK Hynix −11.1%, Samsung −9.9%. Seoul's worst day since January; "
     "Taiwan −4.8%, Nikkei −2.8%.",
     "Korea Exchange close 06:30 UTC · REPORTED", "chart"),
]

TIMELINE = [
    [("00:18", "Shenzhou lifts off"), ("00:30", "AP reports launch"),
     ("03:56", "Tiangong docking"), ("04:05", "Asian stocks slide"),
     ("06:30", "Kospi closes −6.2%"), ("07:10", "Bogor mine flood"),
     ("10:02", "Eurostar strike"), ("12:00", "Ofgem raises cap")],
    [("13:15", "US tariffs unveiled"), ("14:19", "Poland no-fly zone"),
     ("15:46", "Poundland collapses"), ("18:00", "FCC clears SpaceX"),
     ("19:00", "Iraq court rules"), ("19:14", "Cairo tanker fire"),
     ("19:53", "Rutte meets Trump"), ("22:40", "UCL round-up")],
]

FOOT_L1 = ("DATE CHECK — Every story here happened, or was first reported, "
           "on Wednesday, 25 November 2026 (UTC).")
FOOT_L2 = ("LEFT OUT — they happened earlier: Huawei guilty verdict (Tue 24) · "
           "Chen Jining probe (Tue 24) · Houthi drone on Riyadh PIF tower, 11 hurt "
           "(Tue 24) · UN: 47,000 women killed (Tue 24) · Venezuela's $237.5bn debt "
           "(Tue 24) · 490,334 Russian soldiers leak (Tue 24) · UNAIDS report "
           "(Tue 24) · Sarkozy sent to trial (Tue 24) · Microsoft “Code Red” "
           "(Tue 24) · Nepal M5.6 quake (Tue 24) · Suryavanshi's 204 (Tue 24) · "
           "COP31 collapse (Sun 22) · Dow tops 50,000 (Tue 24).")
FOOT_L3 = ("FLAGGED " + WARN + " #10 Cartagena — siege began Tue, hostages freed Wed · "
           "#25 Blue Nile — strike Tue night, first reported Wed · #26 Ebola, Ituri — "
           "first mention Tue 23:58 UTC, authoritative report Wed 18:50 UTC · "
           "#35 Libya — officers died Tue night, LNA vow reported Wed. "
           "NOT YET: Spain votes Sun 29 Nov · Dhaka rise takes effect Dec · "
           "UK cap applies 1 Jan 2027.")
FOOT_L4 = ("Sources: Reuters · AP · BBC · AFP · ESA · FCC · Ofgem · BEA · Caltech · "
           "UEFA · ICC · WHO. OFFICIAL = authority statement · REPORTED = press "
           "report · CLAIM = one-sided claim.")

# ---------------------------------------------------------------- world map
# Coarse land mask, equirectangular grid 96 x 48 (3.75 deg cells).
# Row r covers lat 90-3.75r .. 90-3.75(r+1); spans are inclusive columns.
MAP_ROWS = {
    1: [(26, 28), (33, 42)],
    2: [(18, 30), (31, 44)],
    3: [(3, 10), (13, 31), (33, 43), (52, 52), (58, 60), (63, 66)],
    4: [(2, 10), (13, 33), (36, 42), (49, 52), (56, 95)],
    5: [(2, 11), (13, 34), (43, 43), (49, 53), (55, 95)],
    6: [(3, 12), (14, 35), (48, 55), (56, 95)],
    7: [(4, 10), (13, 38), (46, 47), (49, 56), (57, 95)],
    8: [(13, 40), (46, 47), (50, 53), (54, 95)],
    9: [(0, 3), (14, 24), (28, 41), (45, 48), (50, 56), (57, 93)],
    10: [(0, 4), (13, 41), (44, 48), (49, 58), (59, 88)],
    11: [(12, 42), (44, 57), (58, 88)],
    12: [(12, 42), (44, 57), (58, 88)],
    13: [(12, 41), (44, 46), (50, 51), (54, 58), (59, 88)],
    14: [(12, 40), (44, 58), (59, 64), (65, 72), (73, 78), (79, 88)],
    15: [(13, 40), (44, 58), (59, 63), (64, 77), (78, 86)],
    16: [(15, 22), (23, 40), (44, 58), (59, 62), (63, 70), (70, 75), (76, 85)],
    17: [(15, 28), (43, 58), (59, 62), (63, 70), (70, 74), (75, 84)],
    18: [(17, 28), (42, 59), (59, 61), (69, 73), (75, 83)],
    19: [(20, 27), (41, 60), (69, 71), (74, 82)],
    20: [(22, 28), (28, 37), (41, 60), (74, 81)],
    21: [(25, 28), (29, 39), (41, 59), (69, 69), (74, 81)],
    22: [(28, 40), (41, 58), (69, 69), (73, 80), (83, 88)],
    23: [(28, 40), (41, 57), (74, 79), (83, 88)],
    24: [(28, 39), (42, 58), (73, 78), (83, 88)],
    25: [(28, 38), (42, 58), (73, 78), (83, 88)],
    26: [(28, 37), (51, 58), (74, 90)],
    27: [(28, 36), (51, 58), (59, 61), (78, 90)],
    28: [(28, 35), (51, 57), (59, 61), (78, 89)],
    29: [(29, 34), (51, 57), (59, 61), (78, 89)],
    30: [(29, 33), (52, 56), (59, 60), (78, 88)],
    31: [(29, 32), (52, 56), (79, 88)],
    32: [(29, 31), (53, 55), (80, 86), (94, 95)],
    33: [(29, 31), (53, 55), (81, 87), (93, 94)],
    34: [(29, 30), (85, 87), (92, 94)],
    35: [(29, 30), (86, 87), (92, 93)],
    36: [(29, 29), (92, 93)],
    37: [(29, 29)],
    38: [(29, 29)],
}
# pin positions (lon, lat) for stories 1..48
PINS = [
    (-77, 39), (-93, 42), (-74, 41), (-77, 39), (-80.5, 28.5), (-80, 26.7),
    (-3.7, 40.4), (-118.1, 34.1), (-58.4, -34.6), (-75.5, 10.4),
    (-52, -24), (-107, 24.8), (-0.1, 51.5), (-2, 53.5), (4.35, 50.85),
    (21, 52.2), (13.4, 52.5), (-0.5, 50.9), (-0.1, 51.5), (23.7, 38),
    (50, 53.2), (-2.98, 53.4), (31.2, 30), (28.2, -25.7), (34.5, 11.8),
    (29.5, 1.5), (7.5, 6.5), (28, -26.2), (50, 26.6), (42.8, 14.8),
    (34.5, 31.5), (44.4, 33.3), (35.9, 34.5), (51.4, 35.7), (20, 32.1),
    (100.3, 41), (127, 37.5), (106.8, -6.6), (90.4, 23.8), (101.7, 3.1),
    (122, 11), (67, 24.9), (125.8, 39), (160, -9.4), (149.1, -35.3),
    (151.2, -33.9), (149.1, -35.3), (8.6, 49.9),
]

# ---------------------------------------------------------------- drawing
def conf_color(meta):
    if meta.endswith("CLAIM"):
        return RED
    if meta.endswith("OFFICIAL"):
        return NAVY
    return (70, 66, 58)


def draw_masthead(cv, at):
    cv.fill_rect(0, 0, W, 4, INK)
    at.draw_center(cv, W // 2, 8, "THE WORLD IN ONE DAY",
                   "serif", "bold", 40, INK)
    at.draw_center(cv, W // 2, 56, "WEDNESDAY, 25 NOVEMBER 2026",
                   "sans", "bold", 15, INK)
    at.draw_center(cv, W // 2, 72,
                   "Shenzhou-24 carries a Pakistani astronaut  ·  "
                   "US plans tariffs on 14 economies  ·  Kospi sinks 6.2%  ·  "
                   "Cairo tanker fire kills 30+",
                   "sans", "regular", 11, RED)
    cv.hline(16, W - 16, 88, INK, 2)
    cv.hline(16, W - 16, 91, INK, 1)


def draw_strip(cv, at, y):
    cells = [
        ("48", "STORIES — ALL DATED 25 NOV"),
        ("8", "REGIONS COVERED"),
        ("16", "MOMENTS ON THE UTC TIMELINE"),
        ("4", "BORDERLINE CASES, FLAGGED " + WARN),
        ("0", "STORIES FROM BEFORE 25 NOV"),
    ]
    cw = (W - 32) // 5
    for i, (big, small) in enumerate(cells):
        cx = 16 + i * cw + cw // 2
        at.draw_center(cv, cx, y, big, "sans", "bold", 20, RED)
        at.draw_center(cv, cx, y + 21, small, "sans", "regular", 8, GREY)
        if i:
            cv.vline(16 + i * cw, y + 2, y + 28, LGREY, 1)
    cv.hline(16, W - 16, y + 32, RULE, 1)


def hero_art_bars(cv, at, x, y, w, h):
    cv.fill_rect(x, y, w, h, (239, 231, 216))
    vals = [("CHINA", 20), ("EU", 15), ("INDIA", 25), ("VIETNAM", 35)]
    bw = 34
    gap = (w - 4 * bw) // 5
    base = y + h - 16
    for i, (lab, v) in enumerate(vals):
        bx = x + gap + i * (bw + gap)
        bh = int((h - 30) * v / 35)
        cv.fill_rect(bx, base - bh, bw, bh, RED if i in (0, 3) else NAVY)
        at.draw_center(cv, bx + bw // 2, base - bh - 11, "%d%%" % v,
                       "sans", "bold", 9, INK)
        at.draw_center(cv, bx + bw // 2, base + 2, lab,
                       "sans", "bold", 8, GREY)


def hero_art_rocket(cv, at, x, y, w, h):
    cv.fill_rect(x, y, w, h, (20, 38, 63))
    for sx, sy in [(18, 10), (52, 22), (88, 8), (150, 14), (200, 26),
                   (250, 10), (290, 20), (120, 30), (230, 34)]:
        cv.fill_rect(x + sx, y + sy, 2, 2, (255, 255, 255))
    rx, ry = x + 52, y + 2
    cv.fill_poly([(rx + 14, ry), (rx + 22, ry + 12), (rx + 6, ry + 12)],
                 (255, 255, 255))                       # nose
    cv.fill_rect(rx + 6, ry + 12, 16, 20, (255, 255, 255))  # body
    cv.fill_poly([(rx + 6, ry + 18), (rx - 4, ry + 34), (rx + 6, ry + 30)],
                 RED)                                     # fin L
    cv.fill_poly([(rx + 22, ry + 18), (rx + 32, ry + 34), (rx + 22, ry + 30)],
                 RED)                                     # fin R
    cv.fill_poly([(rx + 10, ry + 32), (rx + 18, ry + 32), (rx + 14, ry + 44)],
                 (255, 176, 32))                          # flame
    cv.fill_circle(rx + 14, ry + 19, 3, NAVY)             # window
    at.draw(cv, x + 96, y + 8, "00:18 UTC", "sans", "bold", 13, (255, 255, 255))
    at.draw(cv, x + 96, y + 26, "LIFTOFF · JIUQUAN", "sans", "bold", 9,
            (176, 184, 196))
    at.draw(cv, x + 96, y + 40, "DOCKED 03:56 UTC", "sans", "bold", 9,
            (176, 184, 196))


def hero_art_chart(cv, at, x, y, w, h):
    cv.fill_rect(x, y, w, h, (246, 232, 228))
    pts = [(x + 14, y + 12), (x + 70, y + 18), (x + 120, y + 16),
           (x + 170, y + 30), (x + 215, y + 26), (x + 258, y + 42),
           (x + 296, y + 46)]
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], RED, 2)
    for px, py in pts:
        cv.fill_circle(px, py, 3, RED)
    at.draw(cv, x + 12, y + 4, "KOSPI  4,697.51", "sans", "bold", 9, INK)
    at.draw(cv, x + w - 72, y + 20, "−6.2%", "sans", "bold", 17, RED)


def draw_heroes(cv, at, y):
    hw = (W - 32 - 2 * 12) // 3
    for i, (kicker, head, body, meta, art) in enumerate(HEROES):
        x = 16 + i * (hw + 12)
        cv.rect(x, y, hw, 140, RULE, 1)
        cv.fill_rect(x + 1, y + 1, hw - 2, 139, PAPER2)
        if art == "bars":
            hero_art_bars(cv, at, x + 1, y + 1, hw - 2, 50)
        elif art == "rocket":
            hero_art_rocket(cv, at, x + 1, y + 1, hw - 2, 50)
        else:
            hero_art_chart(cv, at, x + 1, y + 1, hw - 2, 50)
        cv.fill_rect(x, y + 51, hw, 3, RED if i == 0 else NAVY)
        at.draw(cv, x + 10, y + 58, kicker, "sans", "bold", 9, RED if i == 0 else NAVY)
        lines = at.wrap(head, "serif", "bold", 17, hw - 20)
        yy = y + 71
        for ln in lines[:2]:
            at.draw(cv, x + 10, yy, ln, "serif", "bold", 17, INK)
            yy += 18
        blines = at.wrap(body, "sans", "regular", 10, hw - 20)
        for ln in blines[:2]:
            at.draw(cv, x + 10, yy, ln, "sans", "regular", 10, INK)
            yy += 11
        at.draw(cv, x + 10, y + 130, meta, "sans", "regular", 8, GREY)


def draw_map(cv, at, y):
    at.draw(cv, 16, y, "WHERE IT HAPPENED", "sans", "bold", 10, INK)
    at.draw(cv, W - 16 - int(at.width("pins are story numbers", "sans", "regular", 9)),
            y, "pins are story numbers", "sans", "regular", 9, GREY)
    top = y + 14
    mh = 170
    lat_top, lat_bot = 78.0, -61.0
    span = lat_top - lat_bot

    def proj(lon, lat):
        return ((lon + 180.0) / 360.0 * W,
                top + (lat_top - lat) / span * mh)

    # graticule
    for lon in (-120, -60, 0, 60, 120):
        gx, _ = proj(lon, 0)
        cv.vline(int(gx), top, top + mh, (224, 218, 204), 1)
    for lat in (60, 30, 0, -30):
        _, gy = proj(0, lat)
        cv.hline(0, W, int(gy), (224, 218, 204), 1)
    # land: solid cells
    for r, spans in MAP_ROWS.items():
        lat_c = 90.0 - (r + 0.5) * 3.75
        if lat_c > lat_top or lat_c < lat_bot:
            continue
        _, cy = proj(0, lat_c)
        chh = max(3, int(3.75 / span * mh) + 1)
        for a, b in spans:
            for c in range(a, b + 1):
                lon_c = -180.0 + (c + 0.5) * 3.75
                cx, _ = proj(lon_c, 0)
                cv.fill_rect(int(cx - 5), int(cy - chh // 2), 11, chh, SLATE)
    # ocean labels
    at.draw(cv, 96, top + 118, "PACIFIC OCEAN", "sans", "bold", 8, (140, 148, 152))
    at.draw(cv, 392, top + 132, "ATLANTIC OCEAN", "sans", "bold", 8, (140, 148, 152))
    at.draw(cv, 690, top + 140, "INDIAN OCEAN", "sans", "bold", 8, (140, 148, 152))
    # pins, with radial collision nudges: candidates on expanding rings
    # around the true position; take the first >=17px from every placed
    # pin, else the candidate farthest from its nearest neighbour, so no
    # two numbers ever stack. (The old 9-offset list silently fell back
    # to (0, 0) when all 9 failed, and pins 13/18/19 — three London
    # stories within ~2px of each other — collapsed into one blob
    # reading "19". A nudged pin keeps a dot + leader line at its true
    # position.)
    placed = []
    ring = [(0, 0)]
    for r in (11, 16, 22, 28, 34, 42, 50):
        for k in range(8):
            a = k * math.pi / 4
            ring.append((int(round(r * math.cos(a))),
                         int(round(-r * math.sin(a)))))
    for n, (lon, lat) in enumerate(PINS, 1):
        px, py = proj(lon, lat)
        px, py = int(round(px)), int(round(py))
        ox, oy = 0, 0
        best, best_d = (0, 0), -1
        for dx, dy in ring:
            d = min(((px + dx - qx) ** 2 + (py + dy - qy) ** 2
                     for qx, qy in placed), default=10 ** 9)
            if d >= 17 ** 2:
                ox, oy = dx, dy
                break
            if d > best_d:
                best, best_d = (dx, dy), d
        else:
            ox, oy = best
        if (ox, oy) != (0, 0):
            cv.fill_circle(px, py, 2, RED)
            cv.line(px, py, px + ox, py + oy, RED, 1)
        px, py = px + ox, py + oy
        placed.append((px, py))
        cv.fill_circle(px, py, 7, RED)
        cv.ring(px, py, 7, (255, 255, 255), 1)
        num = str(n)
        nw = at.width(num, "sans", "bold", 8)
        at.draw(cv, int(px - nw / 2), py - 5, num, "sans", "bold", 8,
                (255, 255, 255))


def draw_list(cv, at, y):
    col_w = 321
    xs = [16, 351, 686]
    code_of = {"NORTH AMERICA": "NA", "LATIN AMERICA": "LATAM",
               "EUROPE": "EU", "AFRICA": "AF", "MIDDLE EAST": "ME",
               "ASIA": "ASIA", "OCEANIA": "OC", "GLOBAL": "GL"}
    for ci, col in enumerate(COLUMNS):
        x = xs[ci]
        yy = y
        for region, first, last in col:
            code = code_of[region]
            cnt = last - first + 1
            at.draw(cv, x, yy, "%s — %d" % (region, cnt), "sans", "bold", 10,
                    REGION_COLOR[code])
            cv.hline(x, x + col_w, yy + 11, LGREY, 1)
            yy += 14
            for n in range(first, last + 1):
                region_code, title, meta = STORIES[n - 1]
                num = "%d" % n
                nw = at.width(num, "sans", "bold", 10)
                at.draw(cv, x, yy, num, "sans", "bold", 10, RED)
                at.draw(cv, x + nw + 5, yy, title, "sans", "regular", 10, INK)
                at.draw(cv, x + nw + 5, yy + 11, meta, "sans", "regular", 8, GREY)
                yy += 23
    cv.hline(16, W - 16, y + 436, RULE, 1)


def draw_timeline(cv, at, y):
    at.draw(cv, 16, y, "THE DAY IN UTC", "sans", "bold", 9, GREY)
    for ri, row in enumerate(TIMELINE):
        yy = y + 12 + ri * 15
        cell = (W - 32) // 8
        for i, (t, txt) in enumerate(row):
            x = 16 + i * cell
            tw = at.width(t, "sans", "bold", 8)
            at.draw(cv, x, yy, t, "sans", "bold", 8, RED)
            at.draw(cv, x + tw + 4, yy, txt, "sans", "regular", 8, INK)
            if i:
                cv.fill_circle(x - 5, yy + 4, 1, LGREY)


def draw_footer(cv, at, y):
    cv.fill_rect(0, y, W, H - y, DARK)
    yy = y + 6
    at.draw(cv, 16, yy, FOOT_L1, "sans", "bold", 11, (255, 255, 255))
    yy += 13
    for ln in at.wrap(FOOT_L2, "sans", "regular", 8, W - 32):
        at.draw(cv, 16, yy, ln, "sans", "regular", 8, (232, 236, 240))
        yy += 10
    for ln in at.wrap(FOOT_L3, "sans", "regular", 8, W - 32):
        at.draw(cv, 16, yy, ln, "sans", "regular", 8, (232, 236, 240))
        yy += 10
    at.draw(cv, 16, yy + 1, FOOT_L4, "sans", "regular", 8, FOOTGREY)


def build():
    base = os.path.dirname(os.path.abspath(__file__))
    at = Atlas(base)
    cv = Canvas(W, H, PAPER)
    draw_masthead(cv, at)
    draw_strip(cv, at, 96)
    draw_heroes(cv, at, 132)
    draw_map(cv, at, 280)
    draw_list(cv, at, 472)
    draw_timeline(cv, at, 914)
    draw_footer(cv, at, 952)
    return encode_png(W, H, cv.px)


def main():
    outdir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(outdir, exist_ok=True)
    data = build()
    path = os.path.join(outdir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(data)
    sys.stderr.write("wrote %s (%d bytes)\n" % (path, len(data)))


if __name__ == "__main__":
    main()
