# -*- coding: utf-8 -*-
"""
T8.58 (2026-10-25): bars of a sloping slab. The slab's bars are worked out flat, level with the face references,
then every point is lifted onto the face it belongs to - its cover kept square to that face - so straight bars
stay straight and a set's bars stay in the slab's plane. No Revit: points are (x, y, z) tuples, faces
(origin, unit normal).
"""
import math

LEVEL = 1e-4          # |sin| of a face's tilt below which it is taken as level


def tilted(face):
    """A face (origin, normal) that is not level."""
    _o, n = face
    return math.hypot(n[0], n[1]) > LEVEL


def z_on(face, x, y):
    """The face's height over plan point (x, y)."""
    (ox, oy, oz), (nx, ny, nz) = face
    return oz - (nx * (x - ox) + ny * (y - oy)) / nz


def lift(point, bottom, top):
    """
    A point worked out flat (its height measured from the bottom face's origin, or down from the top face's) on
    the sloping slab: the nearer face's height there plus the same offset, square to that face.
    """
    x, y, z = point
    below = z - bottom[0][2]
    above = top[0][2] - z if top is not None else None
    if above is not None and above < below:
        return (x, y, z_on(top, x, y) - above / abs(top[1][2]))
    return (x, y, z_on(bottom, x, y) + below / abs(bottom[1][2]))


def gradient(face):
    """(dz/dx, dz/dy) of the face."""
    (_ox, _oy, _oz), (nx, ny, nz) = face
    return -nx / nz, -ny / nz


def set_direction(normal, bar_dir, face):
    """
    A set's distribution direction (level, unit) on the sloping face, square to its bars (bar_dir, already on the
    face, unit), and the factor its spacing and length take there: (unit direction, factor).
    """
    a, b = gradient(face)
    n = (normal[0], normal[1], a * normal[0] + b * normal[1])
    dot = n[0] * bar_dir[0] + n[1] * bar_dir[1] + n[2] * bar_dir[2]
    m = (n[0] - dot * bar_dir[0], n[1] - dot * bar_dir[1], n[2] - dot * bar_dir[2])
    size = math.sqrt(m[0] ** 2 + m[1] ** 2 + m[2] ** 2)
    if size < 1e-9:
        return normal, 1.0
    return (m[0] / size, m[1] / size, m[2] / size), size
