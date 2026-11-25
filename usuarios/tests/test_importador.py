"""Testes do importador (popular_banco): validação e idempotência, sem banco de dados."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from usuarios.importador import gravar, ler_arquivo, validar

EXEMPLO = Path(__file__).resolve().parents[2] / 'dados_iniciais.json'


class _Obj:
    def __init__(self, **k):
        self.__dict__.update(k)


def _tabela_falsa():
    linhas = []

    class Modelo:
        class objects:
            @staticmethod
            def get_or_create(defaults=None, **k):
                for o in linhas:
                    if all(getattr(o, a) == b for a, b in k.items()):
                        return o, False
                o = _Obj(**k, **(defaults or {}))
                linhas.append(o)
                return o, True
    Modelo.linhas = linhas
    return Modelo


class ImportadorTests(unittest.TestCase):
    def setUp(self):
        self.dados = ler_arquivo(EXEMPLO)

    def test_arquivo_de_exemplo_e_valido(self):
        norm, erros, avisos = validar(self.dados)
        self.assertEqual((erros, avisos), ([], []))
        self.assertEqual((len(norm['cursos']), len(norm['disciplinas']), len(norm['professores'])), (2, 10, 5))

    def _com(self, alteracao):
        d = copy.deepcopy(self.dados)
        alteracao(d)
        return validar(d)

    def test_professor_inexistente(self):
        _, erros, _ = self._com(lambda d: d['horarios'].append(
            {'professor': 'Fulano', 'disciplina': 'Banco de Dados', 'dias': ['Segunda'], 'inicio': '19:00', 'fim': '20:40'}))
        self.assertEqual(len(erros), 1)
        self.assertIn('professor', erros[0])

    def test_acusa_todos_os_erros_de_uma_vez(self):
        _, erros, _ = self._com(lambda d: d['horarios'].append(
            {'professor': 'Ana Paula Ribeiro', 'disciplina': 'Banco de Dados', 'dias': ['Domingo'],
             'inicio': '20:40', 'fim': '19:00', 'tipo': 'x'}))
        self.assertEqual(len(erros), 3)

    def test_nomes_sem_acento_e_maiusculas_sao_aceitos(self):
        _, erros, _ = self._com(lambda d: d['horarios'].append(
            {'professor': 'ana paula ribeiro', 'disciplina': 'banco de dados', 'dias': ['sexta'],
             'inicio': '08:00', 'fim': '09:40'}))
        self.assertEqual(erros, [])

    def test_conflito_vira_aviso(self):
        _, erros, avisos = self._com(lambda d: d['horarios'].append(
            {'professor': 'Ana Paula Ribeiro', 'disciplina': 'Marketing', 'dias': ['Segunda'],
             'inicio': '19:00', 'fim': '19:50'}))
        self.assertEqual(erros, [])
        self.assertTrue(any('conflito' in a for a in avisos))

    def test_professor_sem_email_ganha_placeholder_e_aviso(self):
        norm, erros, avisos = self._com(lambda d: d['professores'].append({'nome': 'Sem Email Silva'}))
        self.assertEqual(erros, [])
        self.assertTrue(any('sem e-mail' in a for a in avisos))
        self.assertEqual(norm['professores'][-1]['email'], 'sem.email.silva@exemplo.com')

    def test_carga_horaria_invalida(self):
        _, erros, _ = self._com(lambda d: d['disciplinas'].append(
            {'nome': 'Nova', 'carga_horaria': 'abc', 'curso': 'Gestão Empresarial'}))
        self.assertEqual(len(erros), 1)

    def test_json_quebrado(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
            f.write('{"cursos": ["A",]}')
        with self.assertRaises(ValueError):
            ler_arquivo(f.name)

    def test_arquivo_salvo_com_bom_e_lido(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8-sig') as f:
            json.dump({'cursos': ['A']}, f)
        self.assertEqual(ler_arquivo(f.name), {'cursos': ['A']})

    def test_gravar_duas_vezes_nao_duplica(self):
        norm, _, _ = validar(self.dados)
        C, D, P, H = (_tabela_falsa() for _ in range(4))
        primeira = gravar(norm, C, D, P, H)
        segunda = gravar(norm, C, D, P, H)
        self.assertEqual(primeira['horario'], (16, 0))
        self.assertEqual(segunda, {'curso': (0, 2), 'disciplina': (0, 10), 'professor': (0, 5), 'horario': (0, 16)})
        self.assertEqual(len(H.linhas), 16)


if __name__ == '__main__':
    unittest.main()
