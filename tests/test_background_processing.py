from PIL import Image, ImageDraw

from app.image_utils import postprocess_background
from app.models import LayerName


def _synthetic_scene() -> Image.Image:
    image = Image.new("RGBA", (1024, 1024), (110, 90, 130, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((120, 120, 420, 860), fill=(180, 150, 120, 255))
    draw.rectangle((560, 220, 860, 920), fill=(70, 110, 140, 255))
    draw.ellipse((420, 120, 700, 400), fill=(220, 210, 180, 255))
    return image


def test_background_layers_get_distinct_alpha_profiles():
    scene = _synthetic_scene()
    palette = ["#111827", "#264653", "#2a9d8f", "#e9c46a", "#f4f1de"]
    far = postprocess_background(scene, LayerName.FAR, palette, (1280, 720))
    mid = postprocess_background(scene, LayerName.MID, palette, (1280, 720))
    near = postprocess_background(scene, LayerName.NEAR, palette, (1280, 720))

    far_top = far.getpixel((640, 60))[3]
    far_bottom = far.getpixel((640, 680))[3]
    mid_top = mid.getpixel((640, 60))[3]
    mid_bottom = mid.getpixel((640, 680))[3]
    near_top = near.getpixel((640, 60))[3]
    near_bottom = near.getpixel((640, 680))[3]

    assert far_top > far_bottom
    assert mid_bottom > mid_top
    assert near_bottom > 0
    assert near_top == 0
