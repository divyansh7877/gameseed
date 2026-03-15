from __future__ import annotations

import colorsys
import io
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.models import LayerName


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    return tuple(int(cleaned[index : index + 2], 16) for index in (0, 2, 4))


def _rgb_to_hex(color: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*color)


def darken(hex_color: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = max(0.0, l - amount)
    result = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex(tuple(int(channel * 255) for channel in result))


def lighten(hex_color: str, amount: float) -> str:
    r, g, b = _hex_to_rgb(hex_color)
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    l = min(1.0, l + amount)
    result = colorsys.hls_to_rgb(h, l, s)
    return _rgb_to_hex(tuple(int(channel * 255) for channel in result))


def load_image_bytes(content: bytes) -> Image.Image:
    return Image.open(io.BytesIO(content)).convert("RGBA")


def fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    image = image.convert("RGBA")
    scale = max(width / max(image.width, 1), height / max(image.height, 1))
    resized = image.resize((max(1, int(image.width * scale)), max(1, int(image.height * scale))), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 2)
    return resized.crop((left, top, left + width, top + height))


def _vertical_fade_mask(height: int, width: int, stops: list[tuple[float, int]]) -> Image.Image:
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    normalized = sorted(stops, key=lambda item: item[0])
    for y in range(height):
        ratio = y / max(height - 1, 1)
        lower = normalized[0]
        upper = normalized[-1]
        for index in range(1, len(normalized)):
            if ratio <= normalized[index][0]:
                lower = normalized[index - 1]
                upper = normalized[index]
                break
        if upper[0] == lower[0]:
            alpha = upper[1]
        else:
            local = (ratio - lower[0]) / (upper[0] - lower[0])
            alpha = int(lower[1] * (1 - local) + upper[1] * local)
        draw.line((0, y, width, y), fill=max(0, min(255, alpha)))
    return mask


def _quantize_scene(image: Image.Image, tint_color: str, contrast: float) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    autocontrast = ImageOps.autocontrast(grayscale, cutoff=2)
    posterized = ImageOps.posterize(autocontrast.convert("RGB"), 3)
    monochrome = ImageOps.colorize(
        ImageOps.grayscale(posterized),
        black=darken(tint_color, 0.38),
        white=lighten(tint_color, contrast),
    ).convert("RGBA")
    return monochrome


def _silhouette_alpha(image: Image.Image, blur_radius: float, threshold: int) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    contrast = ImageOps.autocontrast(grayscale, cutoff=4)
    blurred = contrast.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    silhouette = blurred.point(lambda value: 255 if value < threshold else 0)
    return silhouette


def write_placeholder_sprite(path: Path, label: str, palette: Iterable[str], size: tuple[int, int] = (256, 256)) -> tuple[int, int]:
    colors = list(palette)
    bg = _hex_to_rgb(colors[1] if len(colors) > 1 else "#334155")
    accent = _hex_to_rgb(colors[3] if len(colors) > 3 else "#f59e0b")
    outline = _hex_to_rgb(colors[4] if len(colors) > 4 else "#f8fafc")
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    body_box = (size[0] * 0.22, size[1] * 0.14, size[0] * 0.78, size[1] * 0.86)
    draw.rounded_rectangle(body_box, radius=28, fill=bg + (255,), outline=outline + (255,), width=6)
    draw.rectangle((size[0] * 0.34, size[1] * 0.3, size[0] * 0.66, size[1] * 0.62), fill=accent + (180,))
    font = ImageFont.load_default()
    text = label[:18].upper()
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    draw.text(((size[0] - text_width) / 2, size[1] * 0.72), text, fill=outline + (255,), font=font)
    image.save(path)
    return size


def write_placeholder_background(path: Path, layer: LayerName, palette: Iterable[str], size: tuple[int, int]) -> tuple[int, int]:
    colors = list(palette)
    width, height = size
    sky_top = _hex_to_rgb(colors[0] if colors else "#0f172a")
    sky_bottom = _hex_to_rgb(colors[2] if len(colors) > 2 else "#1d4ed8")
    accent = _hex_to_rgb(colors[3] if len(colors) > 3 else "#f59e0b")
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        blended = tuple(int(sky_top[i] * (1 - ratio) + sky_bottom[i] * ratio) for i in range(3))
        draw.line((0, y, width, y), fill=blended + (255,))
    horizon = {"far": int(height * 0.6), "mid": int(height * 0.72), "near": int(height * 0.82)}[layer.value]
    shade = _hex_to_rgb(lighten(_rgb_to_hex(accent), -0.12 if layer == LayerName.NEAR else -0.24))
    step = {"far": 120, "mid": 80, "near": 56}[layer.value]
    for x in range(0, width + step, step):
        top = horizon - ((x // step) % 4) * (14 if layer == LayerName.FAR else 26 if layer == LayerName.MID else 34)
        draw.rectangle((x, top, x + step - 6, height), fill=shade + (220,))
    image.save(path)
    return size


def postprocess_background(image: Image.Image, layer: LayerName, palette: list[str], viewport: tuple[int, int]) -> Image.Image:
    width, height = viewport
    base = fit_cover(image, width, height)
    if layer == LayerName.FAR:
        blurred = base.filter(ImageFilter.GaussianBlur(radius=5.5))
        softened = _quantize_scene(blurred, palette[1] if len(palette) > 1 else "#5b7cfa", 0.12)
        mask = _vertical_fade_mask(
            height,
            width,
            [(0.0, 176), (0.48, 132), (0.78, 84), (1.0, 10)],
        )
        softened.putalpha(mask)
        return softened
    if layer == LayerName.MID:
        structured = _quantize_scene(base, palette[2] if len(palette) > 2 else "#7dd3fc", 0.18)
        alpha = _silhouette_alpha(base, blur_radius=1.4, threshold=156)
        vertical = _vertical_fade_mask(
            height,
            width,
            [(0.0, 0), (0.22, 58), (0.52, 126), (0.82, 162), (1.0, 72)],
        )
        structured.putalpha(ImageChops.multiply(alpha, vertical))
        return structured
    foreground = _quantize_scene(base, palette[4] if len(palette) > 4 else "#f8fafc", 0.06)
    alpha = _silhouette_alpha(base, blur_radius=0.8, threshold=132)
    vertical = _vertical_fade_mask(
        height,
        width,
        [(0.0, 0), (0.5, 0), (0.66, 110), (0.82, 224), (1.0, 255)],
    )
    foreground.putalpha(ImageChops.multiply(alpha, vertical))
    return foreground.filter(ImageFilter.SHARPEN)


def make_repeat_safe(image: Image.Image, viewport: tuple[int, int]) -> Image.Image:
    width, height = viewport
    image = fit_cover(image, width, height)
    canvas = Image.new("RGBA", (width * 2, height), (0, 0, 0, 0))
    canvas.paste(image, (0, 0), image)
    canvas.paste(ImageOps.mirror(image), (width, 0), ImageOps.mirror(image))
    return canvas
