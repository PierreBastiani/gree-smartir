#!/usr/bin/env python3
"""Generate a SmartIR climate code file for the Whirlpool SPIS412L (Gree YAW1F protocol)
as Broadlink base64 frames. Fields verified against 76 frames learned from the real remote
and the Gree layout in IRremoteESP8266 (ir_Gree.h).

Usage: gree_gen.py [--no-screen] [out.json]   -> write the SmartIR file (default gree_yaw1f.json)
       gree_gen.py --frame MODE FAN SWING TEMP -> print one base64 frame (for remote.send_command b64:)
       gree_gen.py --decode B64                -> decode a Broadlink frame to Gree fields
"""
import base64, json, sys

MODE = {"auto": 0, "cool": 1, "dry": 2, "fan_only": 3, "heat": 4}
FAN = {"auto": 0, "low": 1, "medium": 2, "high": 3}
# HA "swing_mode" carries two things, because SmartIR 1.18 has no other free dimension:
#   swing off/auto  -> (SwingAuto bit in byte0, SwingV nibble in byte4)
#   "_screen_on"    -> Gree Light bit = 1 (display lit); without it the display stays dark,
#                      which is what the learned frames always sent. Verified live 2026-09-05.
SWING = {"off": (0, 0, 0), "auto": (1, 1, 0), "off_screen_on": (0, 0, 1), "auto_screen_on": (1, 1, 1)}
TEMPS = range(16, 31)
UNIT = 32.84                                     # Broadlink tick, µs
# Timings copied from the learned frames (Gree spec: 9000/4500/620/1600/540/19980)
HDR_MARK, HDR_SPACE, MARK, ONE, ZERO, MSG_GAP, END = 9650, 4820, 720, 1740, 570, 21543, 109456
CHECKSUM_BASE = 10
# Learned power-off frame from the remote (mode cool, T30, swing down, light off) — kept verbatim
OFF_FRAME = "JgCSAAABJpMVNhUTFRIVEhYSFhEWEhUTFRMVNhU2FjYVEhYSFRIWEhYSFRIWEhUSFhIVEhYSFTYWEhUSFhIVExU2FhIVNhYSFRIWNhUTFQACjxUSFjcVNhYSFRMVEhYSFRMZMhUSFhIVEhYSFTcVEhUTFRIVExUSFhIVEhYSFRMVEhUSFhIVEhYSFTcVNhYSFTYWAA0F"


def frame_bytes(mode, fan, swing, temp, power=1, light=None, turbo=0, sleep=0, xfan=0):
    m, f = MODE[mode], FAN[fan]
    if mode == "dry":
        f = 1                                    # remote locks fan to low in dry mode
    swa, swv, sw_light = SWING[swing]
    if light is None:
        light = sw_light
    b = bytearray(8)
    b[0] = m | (power << 3) | (f << 4) | (swa << 6) | (sleep << 7)
    b[1] = max(TEMPS[0], min(TEMPS[-1], temp)) - 16
    b[2] = (turbo << 4) | (light << 5) | (power << 6) | (xfan << 7)   # bit6 = ModelA (YAW1F): follows power
    b[3] = 0x50
    b[4] = swv
    b[5] = 0x22                                  # DisplayTemp=2, unknown2=0b100
    b[6] = 0
    s = CHECKSUM_BASE + sum(x & 0xF for x in b[:4]) + sum(x >> 4 for x in b[4:7])
    b[7] = (s & 0xF) << 4
    return bytes(b)


def encode(b):
    p = [HDR_MARK, HDR_SPACE]
    def emit(bits):
        for bit in bits:
            p.extend([MARK, ONE if bit else ZERO])
    def lsb(bs):
        return [(x >> j) & 1 for x in bs for j in range(8)]
    emit(lsb(b[:4])); emit([0, 1, 0]); p.extend([MARK, MSG_GAP]); emit(lsb(b[4:])); p.extend([MARK, END])
    raw = bytearray([0x26, 0x00, 0, 0])
    for d in p:
        v = round(d / UNIT)
        raw += bytes([v]) if v < 256 else bytes([0, v >> 8, v & 0xFF])
    n = len(raw) - 4
    raw[2], raw[3] = n & 0xFF, n >> 8
    while len(raw) % 16:
        raw.append(0)
    return base64.b64encode(bytes(raw)).decode()


def decode(b64):
    raw = base64.b64decode(b64); n = raw[2] | (raw[3] << 8); body = raw[4:4 + n]; p = []; i = 0
    while i < len(body):
        v = body[i]; i += 1
        if v == 0:
            v = (body[i] << 8) | body[i + 1]; i += 2
        p.append(v * UNIT)
    i = 0
    while p[i] < 2500: i += 1
    i += 2; bits = []
    while i + 1 < len(p):
        m, s = p[i], p[i + 1]; i += 2
        bits.append(None if s > 3000 else (1 if s > 2 * m else 0))
    s1, s2 = bits[:32], [x for x in bits[35:] if x is not None][:32]
    b = bytes(sum(bit << j for j, bit in enumerate(ch[k:k + 8])) for ch in (s1, s2) for k in range(0, 32, 8))
    inv = lambda d, v: next(k for k, x in d.items() if x == v)
    return dict(hex=b.hex(), mode=inv(MODE, b[0] & 7), power=(b[0] >> 3) & 1, fan=inv(FAN, (b[0] >> 4) & 3),
                swing_auto=(b[0] >> 6) & 1, sleep=b[0] >> 7, temp=16 + (b[1] & 0xF), turbo=(b[2] >> 4) & 1,
                light=(b[2] >> 5) & 1, xfan=b[2] >> 7, swingV=b[4] & 0xF, sum=b[7] >> 4,
                sum_ok=((CHECKSUM_BASE + sum(x & 0xF for x in b[:4]) + sum(x >> 4 for x in b[4:7])) & 0xF) == b[7] >> 4)


def build(screen=True):
    swings = [s for s in SWING if screen or not s.endswith("_screen_on")]
    cmds = {"off": OFF_FRAME}
    for mode in ("heat", "cool", "dry", "fan_only"):
        cmds[mode] = {}
        for fan in FAN:
            cmds[mode][fan] = {}
            for swing in swings:
                cmds[mode][fan][swing] = {str(t): encode(frame_bytes(mode, fan, swing, t)) for t in TEMPS}
    return {
        "manufacturer": "Whirlpool",
        "supportedModels": ["SPIS412L"],
        "supportedController": "Broadlink",
        "commandsEncoding": "Base64",
        "minTemperature": 16.0, "maxTemperature": 30.0, "precision": 1.0,
        "operationModes": ["heat", "cool", "dry", "fan_only"],
        "fanModes": list(FAN), "swingModes": swings,
        "commands": cmds,
    }


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] in (["-h"], ["--help"]):
        print(__doc__)
    elif a[:1] == ["--frame"]:
        print(encode(frame_bytes(a[1], a[2], a[3], int(a[4]))))
    elif a[:1] == ["--decode"]:
        print(json.dumps(decode(a[1])))
    else:
        screen = "--no-screen" not in a
        a = [x for x in a if x != "--no-screen"]
        out = a[0] if a else "gree_yaw1f.json"
        json.dump(build(screen), open(out, "w"), indent=1)
        print("wrote", out)
