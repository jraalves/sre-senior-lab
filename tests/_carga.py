"""Carrega modulos dos labs por caminho, sem transformar o repo em pacote.

Os labs sao scripts independentes (each one runs alone), entao nao ha
__init__.py nem instalacao. O unittest precisa importar de fora: importlib
resolve isso sem mexer no sys.path global de forma agressiva.
"""

import importlib.util
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_module(nome, caminho):
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError("modulo nao existe: %s" % caminho)
    pai = str(caminho.parent)
    if pai not in sys.path:
        sys.path.insert(0, pai)
    tools = str(RAIZ / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    espec = importlib.util.spec_from_file_location(nome, str(caminho))
    mod = importlib.util.module_from_spec(espec)
    sys.modules[nome] = mod
    espec.loader.exec_module(mod)
    return mod


def caminho_lab(*partes):
    return RAIZ.joinpath("labs", *partes)


RAIZ_LAB = RAIZ
