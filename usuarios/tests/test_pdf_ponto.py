"""Testes do gerador de PDF (lógica pura, sem banco de dados)."""
import io
import unittest
from datetime import date, time
from pathlib import Path

from pypdf import PdfReader

from usuarios.pdf_ponto import (AulaPonto, OcorrenciaPonto, ProfessorPonto, dia_semana_para_indice,
                                gerar_pdf_ponto, gerar_siglas, parse_aulas, slots_da_aula)

MODELO = Path(__file__).resolve().parents[2] / 'documentos' / 'Modelo de Ponto.pdf'


class SlotsTests(unittest.TestCase):
    def test_noite_completa(self):
        self.assertEqual(slots_da_aula('19:00', '22:40'), [('N', 1), ('N', 2), ('N', 3), ('N', 4)])

    def test_horario_aceita_objeto_time(self):
        self.assertEqual(slots_da_aula(time(19, 0), time(20, 40)), [('N', 1), ('N', 2)])

    def test_intervalo_nao_e_aula(self):
        self.assertEqual(slots_da_aula('10:30', '11:00'), [])

    def test_aula_das_13h_conta_so_na_tarde(self):
        """Regressão: manhã termina 13:30 e tarde começa 13:00; a aula não pode contar nos dois."""
        self.assertEqual(slots_da_aula('13:00', '15:30'), [('T', 1), ('T', 2), ('T', 3)])

    def test_ultima_aula_da_manha(self):
        self.assertEqual(slots_da_aula('12:40', '13:30'), [('M', 6)])

    def test_manha_inteira(self):
        self.assertEqual(slots_da_aula('08:00', '13:30'), [('M', n) for n in range(1, 7)])


class AuxiliaresTests(unittest.TestCase):
    def test_dia_da_semana_aceita_variacoes(self):
        for texto, esperado in [('Segunda', 0), ('terça-feira', 1), ('QUA', 2), ('quinta', 3),
                                ('Sexta', 4), ('Sábado', 5), ('sab', 5)]:
            self.assertEqual(dia_semana_para_indice(texto), esperado)

    def test_domingo_e_lixo_sao_invalidos(self):
        self.assertIsNone(dia_semana_para_indice('Domingo'))
        self.assertIsNone(dia_semana_para_indice('banana'))

    def test_parse_aulas(self):
        self.assertEqual(parse_aulas('1-3'), [1, 2, 3])
        self.assertEqual(parse_aulas('1, 3'), [1, 3])
        self.assertEqual(parse_aulas(''), [])
        self.assertEqual(parse_aulas(None), [])

    def test_parse_aulas_invalido(self):
        for ruim in ('abc', '7', '0-2'):
            with self.assertRaises(ValueError):
                parse_aulas(ruim)

    def test_siglas(self):
        s = gerar_siglas(['Banco de Dados', 'Algoritmos', 'Sistemas Operacionais'])
        self.assertEqual(s, {'Banco de Dados': 'BD', 'Algoritmos': 'ALG', 'Sistemas Operacionais': 'SO'})

    def test_siglas_repetidas_nao_colidem(self):
        s = gerar_siglas(['Banco de Dados', 'Bases de Dados'])
        self.assertEqual(len(set(s.values())), 2)


class GeracaoTests(unittest.TestCase):
    def setUp(self):
        self.prof = ProfessorPonto('Ana Paula Ribeiro', '100201', 'CLT', 'Prof. I', aulas=[
            AulaPonto('Algoritmos', 'Segunda', time(19, 0), time(20, 40)),
            AulaPonto('Estrutura de Dados', 'Quinta', time(21, 0), time(22, 40), online=True)])

    def _texto(self, pdf, pagina=0):
        return PdfReader(io.BytesIO(pdf)).pages[pagina].extract_text()

    def test_gera_duas_paginas_por_professor(self):
        pdf, avisos = gerar_pdf_ponto(MODELO, [self.prof, self.prof], 11, 2026)
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertEqual(len(PdfReader(io.BytesIO(pdf)).pages), 4)
        self.assertEqual(avisos, [])

    def test_cabecalho_e_mes_aparecem(self):
        pdf, _ = gerar_pdf_ponto(MODELO, [self.prof], 11, 2026)
        texto = self._texto(pdf)
        self.assertIn('NOVEMBRO/2026', texto)
        self.assertIn('Ana Paula Ribeiro', texto)
        self.assertIn('100201', texto)
        self.assertIn('* aula online', texto)

    def test_mes_invalido(self):
        with self.assertRaises(ValueError):
            gerar_pdf_ponto(MODELO, [self.prof], 13, 2026)

    def test_feriado_sai_na_folha(self):
        pdf, _ = gerar_pdf_ponto(MODELO, [self.prof], 11, 2026, feriados={date(2026, 11, 2): 'Finados'})
        self.assertIn('FINADOS', self._texto(pdf))

    def test_falta_substitui_a_marca_da_aula(self):
        prof = ProfessorPonto('Ana', aulas=self.prof.aulas,
                              ocorrencias=[OcorrenciaPonto(date(2026, 11, 9), 'FA', 'N')])
        pdf, avisos = gerar_pdf_ponto(MODELO, [prof], 11, 2026)
        self.assertEqual(avisos, [])
        self.assertIn('FA', self._texto(pdf))

    def test_ocorrencia_em_dia_sem_aula_gera_aviso(self):
        prof = ProfessorPonto('Ana', aulas=self.prof.aulas,
                              ocorrencias=[OcorrenciaPonto(date(2026, 11, 10), 'FA')])   # terça: sem aula
        _, avisos = gerar_pdf_ponto(MODELO, [prof], 11, 2026)
        self.assertEqual(len(avisos), 1)
        self.assertIn('10/11/2026', avisos[0])

    def test_reposicao_em_dia_sem_aula_e_marcada(self):
        prof = ProfessorPonto('Ana', aulas=self.prof.aulas,
                              ocorrencias=[OcorrenciaPonto(date(2026, 11, 14), 'R', 'M', [1, 2])])
        _, avisos = gerar_pdf_ponto(MODELO, [prof], 11, 2026)
        self.assertEqual(avisos, [])

    def test_aula_fora_do_modelo_gera_aviso(self):
        prof = ProfessorPonto('Ana', aulas=[AulaPonto('Palestra', 'Terça', time(10, 30), time(11, 0)),
                                            AulaPonto('Aula', 'Domingo', time(9, 0), time(10, 0))])
        _, avisos = gerar_pdf_ponto(MODELO, [prof], 11, 2026)
        self.assertEqual(len(avisos), 2)

    def test_conflito_gera_aviso(self):
        prof = ProfessorPonto('Ana', aulas=[AulaPonto('A', 'Segunda', time(19, 0), time(20, 40)),
                                            AulaPonto('B', 'Segunda', time(19, 0), time(19, 50))])
        _, avisos = gerar_pdf_ponto(MODELO, [prof], 11, 2026)
        self.assertTrue(any('conflito' in a for a in avisos))

    def test_qualquer_mes_gera(self):
        for mes in range(1, 13):
            pdf, _ = gerar_pdf_ponto(MODELO, [self.prof], mes, 2027)
            self.assertTrue(pdf.startswith(b'%PDF'))


if __name__ == '__main__':
    unittest.main()
