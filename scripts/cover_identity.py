"""Conservative evidence for unattended resolution upgrades, never edition recognition.

Visual similarity cannot establish publisher/market identity. Automatic replacement
requires a supported same-asset URL transform AND a full-frame colour comparison.
"""
from __future__ import annotations
import io
from PIL import Image, ImageChops, ImageStat, ImageOps

POLICY_VERSION = 'same-asset-rgb-v1'


def visual_identity(reference: bytes, candidate: bytes) -> dict:
    """Compare the entire cover, including publisher marks and borders.

    No crop, grayscale conversion, registration or colour normalization: those
    operations erase exactly the evidence that distinguishes regional editions.
    Thresholds are conservative rejection rules, not a claim of 100% accuracy.
    """
    try:
        with Image.open(io.BytesIO(reference)) as a, Image.open(io.BytesIO(candidate)) as b:
            if getattr(a, 'n_frames', 1) != 1 or getattr(b, 'n_frames', 1) != 1:
                return {'ok': False, 'reason': 'animated'}
            a = ImageOps.exif_transpose(a).convert('RGB')
            b = ImageOps.exif_transpose(b).convert('RGB')
            if min(a.size) < 96:
                return {'ok': False, 'reason': 'reference_too_small'}
            if abs((a.width / a.height) / (b.width / b.height) - 1) > .02:
                return {'ok': False, 'reason': 'geometry_changed'}
            size = (min(a.width, 192), min(a.height, 256))
            a = a.resize(size, Image.Resampling.LANCZOS)
            b = b.resize(size, Image.Resampling.LANCZOS)
            if ImageStat.Stat(a.convert('L')).stddev[0] < 20:
                return {'ok': False, 'reason': 'uninformative_reference'}
            diff = ImageChops.difference(a, b)
            mean = max(ImageStat.Stat(diff).mean)
            worst = 0.0
            for y in range(8):
                for x in range(8):
                    tile = diff.crop((x*size[0]//8, y*size[1]//8,
                                      (x+1)*size[0]//8, (y+1)*size[1]//8))
                    worst = max(worst, max(ImageStat.Stat(tile).mean))
            ok = mean <= 8 and worst <= 22
            return {'ok': ok, 'reason': 'match' if ok else 'local_or_colour_change',
                    'max_channel_mae': round(mean, 3), 'worst_tile_mae': round(worst, 3)}
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return {'ok': False, 'reason': 'unreadable'}


def same_asset_url(old_url: str, new_url: str) -> bool:
    # Lazy import avoids the retrofit's import cycle with this policy module.
    try:
        from scripts.retrofit.upgrade_image_resolution import derive_original_url
    except ModuleNotFoundError:
        from retrofit.upgrade_image_resolution import derive_original_url
    from urllib.parse import urlsplit, parse_qsl
    a, b = urlsplit(old_url), urlsplit(new_url)
    if a.scheme not in {'http', 'https'} or b.scheme not in {'http', 'https'}:
        return False
    if a.hostname != b.hostname or old_url == new_url:
        return False
    # Magento cache removal can point to a different product image. Visual
    # similarity alone cannot certify it; leave the existing cover intact.
    if '/media/catalog/product/cache/' in a.path:
        return False
    # Removing unknown query parameters can change SKU/ISBN/token, not size.
    removed = set(parse_qsl(a.query)) - set(parse_qsl(b.query))
    allowed = {'width', 'height', 'w', 'h', 'quality', 'q', 'fit', 'fit_mode',
               'canvas', 'bg-color', 'bg_color', 'background', 'format', 'auto',
               'dpr', 'crop', 'gravity', 'resize', 'upscale', 'bounds',
               '_ex', 'downsize', 'fitin', 'composite-to'}
    if any(k.lower() not in allowed for k, _ in removed):
        return False
    return derive_original_url(old_url) == new_url


def automatic_upgrade(old_url: str, new_url: str, reference: bytes, candidate: bytes) -> dict:
    if not same_asset_url(old_url, new_url):
        return {'ok': False, 'reason': 'unproven_asset_identity', 'policy': POLICY_VERSION}
    return {**visual_identity(reference, candidate), 'policy': POLICY_VERSION}
