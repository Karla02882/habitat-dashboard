# -*- coding: utf-8 -*-
"""EL RELOJ DEL TABLERO."""
from datetime import datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5))

FORMATO = "%Y-%m-%d %H:%M"


def ahora() -> datetime:
    """El momento actual en hora de Huancayo."""
    return datetime.now(LIMA).replace(tzinfo=None)


def sello(formato: str = FORMATO) -> str:
    """La hora de Huancayo ya escrita, para publicar en el tablero."""
    return ahora().strftime(formato)


def de_marca(mtime: float) -> datetime:
    """La fecha de un archivo, en hora de Huancayo."""
    return datetime.fromtimestamp(mtime, LIMA).replace(tzinfo=None)
