# -*- coding: utf-8 -*-
"""
Importa cursos, disciplinas, professores e horários de um arquivo JSON para o banco.

Não depende diretamente do Django: recebe as classes de model como argumento
(facilita testar). O comando `python manage.py popular_banco` usa este módulo.

Fluxo: ler_arquivo -> validar (acusa TODOS os erros antes de gravar) -> gravar.
Gravar usa get_or_create: rodar duas vezes não duplica nada e não sobrescreve
o que já existe no banco.
"""
import json
import re
import unicodedata
from datetime import datetime

from .pdf_ponto import dia_semana_para_indice, slots_da_aula

DIAS = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']
CAMPOS_PROFESSOR = ['matricula', 'regime_juridico', 'categoria', 'hora_atividade',
                    'hae_o', 'hae_c', 'carga_horaria_semanal']
NOME_PERIODO = {'M': 'manhã', 'T': 'tarde', 'N': 'noite'}


def chave(texto):
    """Comparação sem acento, sem maiúsculas e sem espaços repetidos."""
    s = unicodedata.normalize('NFKD', str(texto or '')).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s).strip().lower()


def ler_arquivo(caminho):
    with open(caminho, encoding='utf-8-sig') as f:   # utf-8-sig aceita arquivo salvo pelo Bloco de Notas
        try:
            dados = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f'O arquivo não é um JSON válido (linha {e.lineno}, coluna {e.colno}): {e.msg}')
    if not isinstance(dados, dict):
        raise ValueError('O arquivo deve começar com { } e ter as chaves cursos, disciplinas, professores e horarios.')
    return dados


def _hora(texto):
    for formato in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime(str(texto).strip(), formato).time()
        except ValueError:
            pass
    return None


def _texto(valor):
    return '' if valor is None else str(valor).strip()


def validar(dados):
    """Retorna (normalizado, erros, avisos). Se houver erros, nada deve ser gravado."""
    erros, avisos = [], []
    norm = {'cursos': [], 'disciplinas': [], 'professores': [], 'horarios': []}

    # ---------------- cursos
    cursos_vistos = {}
    for i, c in enumerate(dados.get('cursos') or [], start=1):
        nome = _texto(c.get('nome') if isinstance(c, dict) else c)
        if not nome:
            erros.append(f'cursos[{i}]: nome vazio.')
            continue
        if chave(nome) in cursos_vistos:
            avisos.append(f'curso repetido no arquivo: {nome!r} (ignorado).')
            continue
        cursos_vistos[chave(nome)] = nome
        norm['cursos'].append(nome)

    # ---------------- disciplinas
    disc_vistas = {}
    for i, d in enumerate(dados.get('disciplinas') or [], start=1):
        if not isinstance(d, dict):
            erros.append(f'disciplinas[{i}]: esperado um objeto com nome, carga_horaria e curso.')
            continue
        nome, curso = _texto(d.get('nome')), _texto(d.get('curso'))
        if not nome:
            erros.append(f'disciplinas[{i}]: nome vazio.')
            continue
        try:
            carga = int(d.get('carga_horaria', 80))
            if carga < 1:
                raise ValueError
        except (TypeError, ValueError):
            erros.append(f'disciplina {nome!r}: carga_horaria inválida ({d.get("carga_horaria")!r}).')
            continue
        if not curso:
            erros.append(f'disciplina {nome!r}: falta o campo "curso".')
            continue
        if chave(curso) not in cursos_vistos:
            cursos_vistos[chave(curso)] = curso
            norm['cursos'].append(curso)
            avisos.append(f'o curso {curso!r} não estava na lista de cursos; será criado.')
        if chave(nome) in disc_vistas:
            erros.append(f'disciplina repetida no arquivo: {nome!r} (use nomes diferentes).')
            continue
        disc_vistas[chave(nome)] = nome
        norm['disciplinas'].append({'nome': nome, 'carga_horaria': carga, 'curso': cursos_vistos[chave(curso)]})

    # ---------------- professores
    prof_vistos = {}
    for i, p in enumerate(dados.get('professores') or [], start=1):
        if not isinstance(p, dict):
            erros.append(f'professores[{i}]: esperado um objeto com nome, email...')
            continue
        nome = _texto(p.get('nome'))
        if not nome:
            erros.append(f'professores[{i}]: nome vazio.')
            continue
        if chave(nome) in prof_vistos:
            erros.append(f'professor repetido no arquivo: {nome!r}.')
            continue
        email = _texto(p.get('email'))
        if not email:
            slug = re.sub(r'[^a-z0-9]+', '.', chave(nome)).strip('.')
            email = f'{slug}@exemplo.com'
            avisos.append(f'professor {nome!r} sem e-mail: usei {email}.')
        prof_vistos[chave(nome)] = nome
        item = {'nome': nome, 'email': email}
        item.update({c: _texto(p.get(c)) for c in CAMPOS_PROFESSOR})
        norm['professores'].append(item)

    # ---------------- horários
    ocupacao = {}   # (professor, dia, periodo, aula) -> disciplina
    for i, h in enumerate(dados.get('horarios') or [], start=1):
        if not isinstance(h, dict):
            erros.append(f'horarios[{i}]: esperado um objeto.')
            continue
        prof, disc = _texto(h.get('professor')), _texto(h.get('disciplina'))
        rotulo = f'horário {i} ({prof or "?"} / {disc or "?"})'
        if chave(prof) not in prof_vistos:
            erros.append(f'{rotulo}: professor não está na lista de professores.')
            continue
        if chave(disc) not in disc_vistas:
            erros.append(f'{rotulo}: disciplina não está na lista de disciplinas.')
            continue

        dias_brutos = h.get('dias', h.get('dia'))
        if isinstance(dias_brutos, str):
            dias_brutos = [dias_brutos]
        dias = []
        for bruto in dias_brutos or []:
            idx = dia_semana_para_indice(bruto)
            if idx is None:
                erros.append(f'{rotulo}: dia da semana inválido {bruto!r} (use Segunda a Sábado).')
            elif DIAS[idx] not in dias:
                dias.append(DIAS[idx])
        if not dias_brutos:
            erros.append(f'{rotulo}: falta o campo "dias" (ex.: ["Segunda", "Quarta"]).')
        ini, fim = _hora(h.get('inicio')), _hora(h.get('fim'))
        if not ini or not fim or ini >= fim:
            erros.append(f'{rotulo}: inicio/fim inválidos ({h.get("inicio")!r}–{h.get("fim")!r}); use HH:MM com início antes do fim.')
        tipo = _texto(h.get('tipo')).lower() or 'presencial'
        if tipo not in ('presencial', 'online'):
            erros.append(f'{rotulo}: tipo deve ser "presencial" ou "online" (recebi {tipo!r}).')
        if not dias or not ini or not fim or ini >= fim or tipo not in ('presencial', 'online'):
            continue

        slots = slots_da_aula(ini, fim)
        if not slots:
            avisos.append(f'{rotulo}: {ini:%H:%M}–{fim:%H:%M} não coincide com nenhuma aula do modelo '
                          f'(não aparecerá no PDF).')
        for dia in dias:
            for periodo, numero in slots:
                k = (chave(prof), dia, periodo, numero)
                nome_disc = disc_vistas[chave(disc)]
                if k in ocupacao and ocupacao[k] != nome_disc:
                    avisos.append(f'conflito: {prof} tem {ocupacao[k]} e {nome_disc} na {numero}ª aula da '
                                  f'{NOME_PERIODO[periodo]} de {dia}.')
                ocupacao[k] = nome_disc
        norm['horarios'].append({'professor': prof_vistos[chave(prof)], 'disciplina': disc_vistas[chave(disc)],
                                 'dias': dias, 'inicio': ini, 'fim': fim, 'tipo': tipo})
    return norm, erros, avisos


def gravar(norm, Curso, Disciplina, Professor, HorarioAula):
    """Grava no banco sem duplicar. Retorna {'curso': (criados, existentes), ...}."""
    resumo = {k: [0, 0] for k in ('curso', 'disciplina', 'professor', 'horario')}

    def conta(chave_, criado):
        resumo[chave_][0 if criado else 1] += 1

    cursos = {}
    for nome in norm['cursos']:
        obj, criado = Curso.objects.get_or_create(nome=nome)
        cursos[chave(nome)] = obj
        conta('curso', criado)

    disciplinas = {}
    for d in norm['disciplinas']:
        obj, criado = Disciplina.objects.get_or_create(
            nome=d['nome'], curso=cursos[chave(d['curso'])], defaults={'carga_horaria': d['carga_horaria']})
        disciplinas[chave(d['nome'])] = obj
        conta('disciplina', criado)

    professores = {}
    for p in norm['professores']:
        defaults = {c: v for c, v in p.items() if c != 'nome'}
        obj, criado = Professor.objects.get_or_create(nome=p['nome'], defaults=defaults)
        professores[chave(p['nome'])] = obj
        conta('professor', criado)

    for h in norm['horarios']:
        for dia in h['dias']:
            _, criado = HorarioAula.objects.get_or_create(
                professor=professores[chave(h['professor'])],
                disciplina=disciplinas[chave(h['disciplina'])],
                dia_semana=dia, horario_inicio=h['inicio'], horario_fim=h['fim'],
                defaults={'tipo_aula': h['tipo']})
            conta('horario', criado)
    return {k: tuple(v) for k, v in resumo.items()}
