from __future__ import annotations

import re


_RE_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_RE_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}\b")
_RE_PORT = re.compile(r"\b(?:port|tcp|udp)?\s*[:=]?\s*(\d{1,5})\b", re.IGNORECASE)
_RE_IMEI = re.compile(r"\b\d{15}\b")
_RE_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")
_RE_CRC = re.compile(r"\bcrc(?:16|32)?\b", re.IGNORECASE)
_RE_HEX = re.compile(r"\b0x[0-9A-Fa-f]+\b")


def extract_entities_regex(text: str) -> list[tuple[str, str]]:
    """
    Minimal NER (regex layer), per spec:
    IP, MAC, PORT, IMEI, versions, crc, hex payload.
    """
    t = text or ""
    out: list[tuple[str, str]] = []

    for m in _RE_IPV4.finditer(t):
        out.append(("ip", m.group(0)))
    for m in _RE_MAC.finditer(t):
        out.append(("mac", m.group(0)))
    for m in _RE_IMEI.finditer(t):
        out.append(("imei", m.group(0)))
    for m in _RE_VERSION.finditer(t):
        out.append(("version", m.group(0)))
    for m in _RE_CRC.finditer(t):
        out.append(("crc", m.group(0).lower()))
    for m in _RE_HEX.finditer(t):
        out.append(("hex", m.group(0).lower()))

    # Ports: capture group to avoid "port" keyword noise.
    for m in _RE_PORT.finditer(t):
        p = int(m.group(1))
        if 0 <= p <= 65535:
            out.append(("port", str(p)))

    # Dedup while keeping order.
    seen = set()
    dedup = []
    for et, name in out:
        k = (et, name)
        if k in seen:
            continue
        seen.add(k)
        dedup.append(k)
    return dedup

