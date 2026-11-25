"""Testes do relatório mensal e da detecção de conflitos (lógica pura)."""
import unittest
from datetime import date, time

from usuarios.pdf_ponto import AulaPonto, OcorrenciaPonto
from usuarios.relatorio import conflitos_da_grade, grade_semanal, resumo_mensal

A = AulaPonto
AULAS = [A('ALP', 'Segunda', time(19, 0), time(20, 40)),
         A('ALP', 'Quarta', time(19, 0), time(20, 40)),
         A('ED', 'Quinta', time(21, 0), time(22, 40))]


class ResumoTests(unittest.TestCase):
    def test_novembro_2026_sem_nada(self):
        # segundas: 2,9,16,23,30 (5) | quartas: 4,11,18,25 (4) | quintas: 5,12,19,26 (4) -> (5+4+4) x 2
        r = resumo_mensal(AULAS, [], {}, 11, 2026)
        self.assertEqual((r['aulas_semana'], r['previstas'], r['ministradas']), (6, 26, 26))
        self.assertEqual(r['horas'], round(26 * 50 / 60, 1))

    def test_feriado_remove_aulas_previstas(self):
        r = resumo_mensal(AULAS, [], {date(2026, 11, 2): 'Finados'}, 11, 2026)
        self.assertEqual((r['previstas'], r['em_feriado']), (24, 2))

    def test_domingo_nunca_conta(self):
        r = resumo_mensal([A('X', 'Domingo', time(9, 0), time(10, 0))], [], {}, 11, 2026)
        self.assertEqual(r['previstas'], 0)

    def test_faltas_e_reposicao(self):
        oc = [OcorrenciaPonto(date(2026, 11, 9), 'FA', 'N'),            # 2 aulas perdidas
              OcorrenciaPonto(date(2026, 11, 18), 'LM', 'N', [2]),      # 1 aula perdida
              OcorrenciaPonto(date(2026, 11, 14), 'R', 'M', [1, 2])]    # 2 aulas extras
        r = resumo_mensal(AULAS, oc, {date(2026, 11, 2): 'Finados'}, 11, 2026)
        self.assertEqual((r['previstas'], r['perdidas'], r['extras'], r['ministradas']), (24, 3, 2, 23))
        self.assertEqual(r['por_codigo'], {'FA': 2, 'LM': 1, 'R': 2})

    def test_duas_ocorrencias_na_mesma_aula_nao_contam_em_dobro(self):
        oc = [OcorrenciaPonto(date(2026, 11, 9), 'FA', 'N'), OcorrenciaPonto(date(2026, 11, 9), 'FM', 'N')]
        self.assertEqual(resumo_mensal(AULAS, oc, {}, 11, 2026)['perdidas'], 2)

    def test_ocorrencia_de_outro_mes_e_ignorada(self):
        oc = [OcorrenciaPonto(date(2026, 11, 9), 'FA')]
        self.assertEqual(resumo_mensal(AULAS, oc, {}, 12, 2026)['perdidas'], 0)

    def test_aula_das_13h_nao_conta_em_dobro(self):
        """Regressão: aula 13:00-15:30 = 3 aulas (e não 4, contando a 6ª da manhã)."""
        g = grade_semanal([A('SO', 'Terça', time(13, 0), time(15, 30))])
        self.assertEqual(len(g[1]), 3)


class ConflitosTests(unittest.TestCase):
    def test_sem_conflito(self):
        self.assertEqual(conflitos_da_grade(AULAS), [])

    def test_com_conflito(self):
        aulas = AULAS + [A('Redes', 'Segunda', time(19, 0), time(19, 50))]
        c = conflitos_da_grade(aulas)
        self.assertEqual(len(c), 1)
        self.assertIn('Segunda', c[0])
        self.assertIn('ALP e Redes', c[0])

    def test_mesma_disciplina_duas_vezes_nao_e_conflito(self):
        aulas = AULAS + [A('ALP', 'Segunda', time(19, 0), time(20, 40))]
        self.assertEqual(conflitos_da_grade(aulas), [])


if __name__ == '__main__':
    unittest.main()
