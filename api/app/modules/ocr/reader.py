"""
reader.py (ocr) - Task 29: turns a photo of a GD copy into words, using OpenCV + Tesseract (FR-9).

Steps:
  1. prepare()  - OpenCV cleans the phone photo so Tesseract can read it:
                    grey scale -> about 2000 px on the long side -> shadows evened out
                    (the photo is divided by a blurred copy of itself) -> straightened (-6..+6 degrees)
  2. read()     - Tesseract reads Bangla + English ("ben+eng") and gives every word with how SURE it is
                  (0-100). The words are grouped into lines, top to bottom.

Tesseract reads printed text well and handwriting poorly (Design Revisions R10), so the parser
only keeps a field when Tesseract was sure enough.
"""
import os
import shutil
from pathlib import Path

import cv2
import numpy as np
import pytesseract

from app.config import settings


class OcrUnavailable(Exception):
    """Tesseract (or its Bangla/English language files) is not installed on this computer."""


def tesseract_cmd() -> str | None:
    """Where tesseract.exe is: TESSERACT_CMD in .env, else the PATH, else the normal Windows folder."""
    for candidate in (settings.tesseract_cmd, shutil.which("tesseract"), r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def tessdata_dir() -> str | None:
    """The folder with ben.traineddata + eng.traineddata: TESSDATA_DIR in .env, else ~/tessdata, else Tesseract's own."""
    for candidate in (settings.tessdata_dir, os.path.join(os.path.expanduser("~"), "tessdata")):
        if candidate and (Path(candidate) / "ben.traineddata").is_file():
            return Path(candidate).as_posix()  # forward slashes: no quoting problems on Windows
    return None


def available() -> bool:
    return tesseract_cmd() is not None


# ---------------------------------------------------------------- 1. clean the photo
def _skew_angle(grey: np.ndarray) -> float:
    """Find how many degrees the text lines lean: the angle whose rows are the most 'stripy'
    (text rows dark, gaps light) is the right one. Checked on a small copy, so it is quick."""
    small = cv2.resize(grey, None, fx=600 / max(grey.shape), fy=600 / max(grey.shape), interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    best, best_score = 0.0, -1.0
    for angle in np.arange(-6, 6.01, 0.5):
        turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rows = cv2.warpAffine(ink, turn, (w, h), flags=cv2.INTER_NEAREST).sum(axis=1).astype(np.float64)
        score = float(np.sum(np.diff(rows) ** 2))
        if score > best_score:
            best, best_score = float(angle), score
    return best


def prepare(jpeg: bytes) -> np.ndarray:
    grey = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_GRAYSCALE)
    if grey is None:
        raise ValueError("not an image")
    scale = 2000 / max(grey.shape)
    if abs(scale - 1) > 0.05:  # small photos are enlarged (Tesseract likes letters ~30 px high)
        grey = cv2.resize(grey, None, fx=scale, fy=scale,
                          interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
    # Even out shadows and yellow paper: divide by the "background" (the page without its letters)
    background = cv2.morphologyEx(grey, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    flat = cv2.divide(grey, background, scale=255)
    angle = _skew_angle(flat)
    if angle:
        h, w = flat.shape
        turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        flat = cv2.warpAffine(flat, turn, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)
    return flat


# ---------------------------------------------------------------- 2. read the words
BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _config(extra: str = "") -> str:
    folder = tessdata_dir()
    return extra + (f" --tessdata-dir {folder}" if folder else "")


class Reading:
    """What Tesseract read: lines of (word, confidence, box), plus the cleaned image for a second look."""

    def __init__(self, lines: list[list[tuple]], image: np.ndarray, timeout: float):
        self.lines = lines
        self.image = image
        self.timeout = timeout

    def reread_digits(self, box: tuple[int, int, int, int]) -> tuple[str, float]:
        """Read ONE small spot again as a number only (Design: the GD number is the most important field).
        Tried as Bangla digits and as English digits; the reading Tesseract is surer about wins.
        Returns (digits, confidence) or ("", 0)."""
        x, y, w, h = box
        pad = max(6, h // 3)
        crop = self.image[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad]
        if crop.size == 0:
            return "", 0.0
        crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        best = ("", 0.0)
        for lang, extra in (("ben", "--psm 7"), ("eng", "--psm 7 -c tessedit_char_whitelist=0123456789/")):
            data = pytesseract.image_to_data(crop, lang=lang, config=_config(extra),
                                             output_type=pytesseract.Output.DICT, timeout=self.timeout)
            words = [(t.strip().translate(BN_DIGITS), float(c)) for t, c in zip(data["text"], data["conf"])
                     if t and t.strip() and float(c) >= 0]
            words = [(t, c) for t, c in words if any(ch.isdigit() for ch in t)]
            if not words:
                continue
            text, conf = words[0]
            digits = "".join(ch for ch in text if ch.isdigit() or ch == "/").strip("/")
            if digits and conf > best[1]:
                best = (digits, conf)
        return best


def read(jpeg: bytes, timeout: float | None = None) -> Reading:
    """All lines of the photo, top to bottom. Raises OcrUnavailable, or RuntimeError on a timeout."""
    command = tesseract_cmd()
    if not command:
        raise OcrUnavailable("Tesseract is not installed")
    pytesseract.pytesseract.tesseract_cmd = command
    timeout = timeout or settings.ocr_timeout_seconds
    image = prepare(jpeg)
    data = pytesseract.image_to_data(image, lang="ben+eng", config=_config("--psm 3"),
                                     output_type=pytesseract.Output.DICT, timeout=timeout)
    lines: dict[tuple, list[tuple]] = {}
    for i, text in enumerate(data["text"]):
        word = (text or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        box = (data["left"][i], data["top"][i], data["width"][i], data["height"][i])
        lines.setdefault(key, []).append((word, conf, box))
    return Reading(list(lines.values()), image, timeout)  # Tesseract already gives them in reading order
