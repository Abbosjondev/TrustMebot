from __future__ import annotations


class DocGuardError(Exception):
    pass


class InvalidImageError(DocGuardError):
    pass


class ImageTooLargeError(DocGuardError):
    pass


class ImageTooSmallError(DocGuardError):
    pass


class ConfigError(DocGuardError):
    pass


class ReedSolomonError(DocGuardError):
    pass
