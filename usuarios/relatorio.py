# -*- coding: utf-8 -*-
"""
Resumo mensal de aulas por professor (módulo puro, sem Django).

Regras:
  * "previstas" = aulas da grade semanal em cada dia do mês, exceto domingos e feriados;
  * "perdidas"  = aulas previstas marcadas com FA, FD, FM, LM ou PL;
  * "extras"    = aulas de reposição/substituição (R, S, RCD) que NÃO estavam na grade naquele dia;
  * "ministradas" = previstas - perdidas + extras;
  * horas = ministradas x 50 min / 60 (hora-relógio).
"""
import calendar
from collections import Counter
from datetime import date
from typing import Dict, Iterable, List

from .pdf_ponto import CODIGOS_EXTRAS, AulaPonto, OcorrenciaPonto, dia_semana_para_indice, slots_da_aula

AULAS_PERDIDAS = {"FA", "FD", "FM", "LM", "PL"}
MINUTOS_AULA = 50


def grade_semanal(aulas: Iterable[AulaPonto]) -> Dict[int, set]:
    """{dia(0=seg..5=sáb): {(periodo, numero), ...}} (ignora o que não cabe nas aulas do modelo)."""
    grade: Dict[int, set] = {}
    for a in aulas:
        dia = dia_semana_para_indice(a.dia_semana)
        if dia is None:
            continue
        for periodo, numero in slots_da_aula(a.inicio, a.fim):
            grade.setdefault(dia, set()).add((periodo, numero))
    return grade


def resumo_mensal(aulas: Iterable[AulaPonto], ocorrencias: Iterable[OcorrenciaPonto],
                  feriados: Dict[date, str], mes: int, ano: int) -> dict:
    grade = grade_semanal(aulas)
    ocorrencias = [o for o in ocorrencias if o.data.year == ano and o.data.month == mes]
    previstas = perdidas = extras = em_feriado = 0
    por_codigo = Counter()

    for d in range(1, calendar.monthrange(ano, mes)[1] + 1):
        data = date(ano, mes, d)
        wd = data.weekday()
        if wd == 6:
            continue
        slots = grade.get(wd, set())
        if data in feriados:
            em_feriado += len(slots)
            continue
        previstas += len(slots)

        afetadas_perda = set()
        for o in (x for x in ocorrencias if x.data == data):
            alvo = {(p, n) for (p, n) in slots
                    if o.periodo in ("", p) and (not o.aulas or n in o.aulas)}
            if o.codigo in AULAS_PERDIDAS:
                afetadas_perda |= alvo
                por_codigo[o.codigo] += len(alvo)
            elif o.codigo in CODIGOS_EXTRAS:
                if o.periodo and o.aulas:
                    novas = {(o.periodo, n) for n in o.aulas} - slots
                    extras += len(novas)
                    por_codigo[o.codigo] += len(novas)
            else:
                por_codigo[o.codigo] += 1
        perdidas += len(afetadas_perda)

    ministradas = previstas - perdidas + extras
    return {
        "aulas_semana": sum(len(v) for v in grade.values()),
        "previstas": previstas,
        "perdidas": perdidas,
        "extras": extras,
        "ministradas": ministradas,
        "horas": round(ministradas * MINUTOS_AULA / 60, 1),
        "em_feriado": em_feriado,
        "por_codigo": dict(por_codigo),
    }


DIAS_NOME = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]
PERIODO_NOME = {"M": "manhã", "T": "tarde", "N": "noite"}


def conflitos_da_grade(aulas: Iterable[AulaPonto]) -> List[str]:
    """Lista textos como 'Segunda, 1ª aula da noite: Banco de Dados e Redes' para aulas sobrepostas."""
    ocupacao: Dict[tuple, list] = {}
    for a in aulas:
        dia = dia_semana_para_indice(a.dia_semana)
        if dia is None:
            continue
        for periodo, numero in slots_da_aula(a.inicio, a.fim):
            ocupacao.setdefault((dia, periodo, numero), []).append(a.disciplina)
    saida = []
    for (dia, periodo, numero), nomes in sorted(ocupacao.items(), key=lambda kv: (kv[0][0], "MTN".index(kv[0][1]), kv[0][2])):
        distintos = sorted(set(nomes))
        if len(distintos) > 1:
            saida.append(f"{DIAS_NOME[dia]}, {numero}ª aula da {PERIODO_NOME[periodo]}: {' e '.join(distintos)}")
    return saida
