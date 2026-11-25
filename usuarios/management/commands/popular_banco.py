# -*- coding: utf-8 -*-
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from usuarios.importador import gravar, ler_arquivo, validar
from usuarios.models import Curso, Disciplina, HorarioAula, Professor


class Command(BaseCommand):
    help = ('Popula o banco com cursos, disciplinas, professores e horários a partir de um JSON '
            '(padrão: dados_iniciais.json na pasta do projeto). Pode rodar várias vezes sem duplicar.')

    def add_arguments(self, parser):
        parser.add_argument('--arquivo', help='caminho de outro arquivo JSON')
        parser.add_argument('--limpar', action='store_true',
                            help='APAGA cursos, disciplinas, professores e horários antes de importar '
                                 '(usuários são mantidos). Pede confirmação.')

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes['arquivo']) if opcoes['arquivo'] else Path(settings.BASE_DIR) / 'dados_iniciais.json'
        try:
            dados = ler_arquivo(caminho)
        except OSError:
            raise CommandError(f'Não consegui abrir o arquivo: {caminho}')
        except ValueError as e:
            raise CommandError(str(e))

        norm, erros, avisos = validar(dados)
        for a in avisos:
            self.stdout.write(self.style.WARNING(f'aviso: {a}'))
        if erros:
            for e in erros:
                self.stderr.write(self.style.ERROR(f'erro: {e}'))
            raise CommandError(f'{len(erros)} erro(s) no arquivo. Corrija e rode de novo (nada foi gravado).')

        if opcoes['limpar']:
            if input('Isso APAGA todos os cursos, disciplinas, professores e horários. Digite SIM para continuar: ').strip() != 'SIM':
                raise CommandError('Cancelado, nada foi alterado.')

        with transaction.atomic():
            if opcoes['limpar']:
                HorarioAula.objects.all().delete()
                Disciplina.objects.all().delete()
                Professor.objects.all().delete()
                Curso.objects.all().delete()
            resumo = gravar(norm, Curso, Disciplina, Professor, HorarioAula)

        nomes = {'curso': 'cursos', 'disciplina': 'disciplinas', 'professor': 'professores', 'horario': 'horários'}
        self.stdout.write(self.style.SUCCESS('Importação concluída:'))
        for k, (novos, existentes) in resumo.items():
            self.stdout.write(f'  {nomes[k]}: {novos} novo(s), {existentes} já existia(m)')
