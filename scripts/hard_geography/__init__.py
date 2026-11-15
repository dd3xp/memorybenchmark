"""Individually authored Hard landscapes; shared helpers never lay out a grid."""


def geography(theme):
    if theme == 'orcia':
        from .orcia import build
    elif theme == 'hampi':
        from .hampi import build
    elif theme == 'angkor':
        from .angkor import build
    else:
        raise ValueError('Unknown authored region')
    return build()
