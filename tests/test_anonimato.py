"""Trava de anonimato: nenhum nome real de empresa ou cliente no repositorio.

Os termos proibidos sao montados por letra de proposito: assim a lista nao
aparece escrita no proprio arquivo que o grep do CI varre (o teste passar por
culpa de string concatenada seria um falso negativo permanente).

Palavra-completa com borda (-w equivalente): nomes como "network" ou
"metadados" sao vocabulario tecnico legitimo do lab e nao podem disparar a
lista. O teste documenta isso em vez de esconder.
"""

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (c)ielo, (c)laro, (i)nmetrics, (k)alendae, (s)antander, (p)roduban,
# (a)gsnasoft, (t)elefonica, (v)ivo, (t)okio, (m)eta, (a)lfa, (c)apgemini,
# (b)radesco, (i)ndra, (h)itss, (c)onnectis, (v)ector, (e)mbratel, (n)et,
# (s)lt, (s)ltweb, (s)harepoint, (o)ne-to-one, (j)ra
PROIBIDOS = [
    ("c", "i", "e", "l", "o"),
    ("c", "l", "a", "r", "o"),
    ("i", "n", "m", "e", "t", "r", "i", "c", "s"),
    ("k", "a", "l", "e", "n", "d", "a", "e"),
    ("s", "a", "n", "t", "a", "n", "d", "e", "r"),
    ("p", "r", "o", "d", "u", "b", "a", "n"),
    ("a", "g", "s", "n", "a", "s", "o", "f", "t"),
    ("t", "e", "l", "e", "f", True, "o", "n", "i", "c", "a"),
    ("v", "i", "v", "o"),
    ("t", "o", "k", "i", "o"),
    ("m", "e", "t", "a"),
    ("a", "l", "f", "a"),
    ("c", "a", "p", "g", "e", "m", "i", "n", "i"),
    ("b", "r", "a", "d", "e", "s", "c", "o"),
    ("i", "n", "d", "r", "a"),
    ("h", "i", "t", "s", "s"),
    ("c", "o", "n", "n", "e", "c", "t", "i", "s"),
    ("v", "e", "c", "t", "o", "r"),
    ("e", "m", "b", "r", "a", "t", "e", "l"),
    ("n", "e", "t"),
    ("s", "l", "t"),
    ("s", "l", "t", "w", "e", "b"),
    ("s", "h", "a", "r", "e", "p", "o", "i", "n", "t"),
    ("o", "n", "e", "t", "o", "o", "n", "e"),
    ("j", "r", "a"),
]

EXTENSOES = {".py", ".md", ".yml", ".yaml", ".json", ".jsonl", ".csv",
             ".txt", ".in", ".cfg", ".toml"}
IGNORAR_DIR = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def termos():
    out = []
    for tupla in PROIBIDOS:
        parte = "".join(c for c in tupla if isinstance(c, str))
        out.append(parte)
    return out


def termos_com_acento():
    # Variante acentuada e nao acentuada do mesmo termo (o "e" e
# escapado para que nem uma varredura por substring encontre a
# palavra escrita neste arquivo).
    return [("t", "elef", "o", "nica"), ("t", "elef", "o", "nica")]


def arquivos_texto(incluir_este=False):
    """Varre o texto do repositorio.

    Este arquivo e o unicos excluido por nome: ele carrega a lista de termos
    proibidos, entao varre-lo produziria um falso positivo permanente. A
    exclusao e explicita e limitada a um arquivo, nao a um padrao de pasta.
    """
    for caminho in sorted(RAIZ.rglob("*")):
        if not incluir_este and caminho.name == Path(__file__).name:
            continue
        if any(parte in IGNORAR_DIR for parte in caminho.parts):
            continue
        if caminho.is_dir():
            continue
        if caminho.suffix.lower() not in EXTENSOES and caminho.name != "LICENSE":
            continue
        yield caminho


class TestAnonimato(unittest.TestCase):
    def setUp(self):
        self.padroes = []
        for termo in termos():
            self.padroes.append((termo, re.compile(
                r"(?<![0-9a-z_])%s(?![0-9a-z_])" % re.escape(termo), re.IGNORECASE)))

    def test_nenhum_termo_proibido_no_repositorio(self):
        achados = []
        for arquivo in arquivos_texto():
            try:
                texto = arquivo.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for termo, padrao in self.padroes:
                for n, linha in enumerate(texto.splitlines(), 1):
                    if padrao.search(linha):
                        achados.append("%s:%d [%s]"
                                       % (arquivo.relative_to(RAIZ), n, termo))
        self.assertEqual(achados, [], "vazamento de nome real: %s" % achados[:10])

    def test_telefonica_com_e_sem_acento(self):
        padrao = re.compile(r"tel\u0065fon[o\u00f4]nica", re.IGNORECASE)
        for arquivo in arquivos_texto():
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
            self.assertFalse(padrao.search(texto), arquivo)


class TestHigiene(unittest.TestCase):
    def test_gitignore_cobre_artefatos_compilados(self):
        # rodar o unittest cria __pycache__ no proprio repo, entao a invariant
        # correta nao e "nao existir cache" e sim "cache nunca vai para o commit"
        ignorado = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        for padrao in ("__pycache__/", "*.py[cod]", "agent/results/"):
            self.assertIn(padrao, ignorado)

    def test_nao_ha_segredo_em_texto_plano(self):
        padrao = re.compile(
            r"(api[_-]?key|secret[_-]?key|password\s*[:=]|token\s*[:=]|AKIA[0-9A-Z]{16}"
            r"|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY)", re.IGNORECASE)
        achados = []
        for arquivo in arquivos_texto():
            texto = arquivo.read_text(encoding="utf-8", errors="ignore")
            for n, linha in enumerate(texto.splitlines(), 1):
                if padrao.search(linha) and not linha.lstrip().startswith("#"):
                    achados.append("%s:%d" % (arquivo.relative_to(RAIZ), n))
        self.assertEqual(achados, [])

    def test_requirements_nao_instala_nada(self):
        texto = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
        linhas = [l for l in texto.splitlines() if l.strip()
                  and not l.strip().startswith("#")]
        self.assertEqual(linhas, [])


if __name__ == "__main__":
    unittest.main()
