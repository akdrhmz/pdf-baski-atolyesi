"""Geçiş köprüsü: eski pencere öznitelik adlarını taşınmış nesnelere yönlendirir (2.9'da kalkar)."""

from __future__ import annotations


class forward:
    """Eski öznitelik adını ``self.<hedef>.<ad>``'a yönlendirir (geçiş köprüsü; okuma ve yazma)."""

    def __init__(self, target: str, name: str):
        self.target, self.name = target, name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return getattr(getattr(obj, self.target), self.name)

    def __set__(self, obj, value) -> None:
        setattr(getattr(obj, self.target), self.name, value)
