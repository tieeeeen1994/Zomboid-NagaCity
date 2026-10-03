"""Hand-planned landmarks. build_all() draws every landmark onto one buildkit.Canvas for generate.py."""
from buildkit import Canvas


def build_all():
    from landmarks import ateneo
    canvas = Canvas()
    ateneo.build(canvas)
    return canvas
