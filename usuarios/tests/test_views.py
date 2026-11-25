"""
Testes de integração (precisam do Django): login, segurança de senhas, recuperação de senha,
cadastros, calendário, PDF/ZIP e relatório.

Rodar:  python manage.py test
"""
import io
import json
import re
import zipfile
from datetime import date, time
from urllib.parse import unquote

from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from usuarios.models import Curso, Disciplina, Feriado, HorarioAula, Ocorrencia, Professor, Usuario


def criar_usuario(username='admin', senha='segredo1', tipo='admin'):
    u = Usuario(username=username, email=f'{username}@teste.com', tipo=tipo)
    u.definir_senha(senha)
    u.save()
    return u


class BaseTestCase(TestCase):
    def entrar(self, username='admin', senha='segredo1'):
        return self.client.post(reverse('login'), {'username': username, 'senha': senha})

    def mensagens(self, resposta):
        return [str(m) for m in get_messages(resposta.wsgi_request)]


class AutenticacaoTests(BaseTestCase):
    def test_login_correto_vai_para_o_inicio(self):
        criar_usuario()
        r = self.entrar()
        self.assertRedirects(r, reverse('inicio'))

    def test_senha_errada_nao_entra(self):
        criar_usuario()
        r = self.entrar(senha='errada')
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('user_id', self.client.session)

    def test_senha_nao_fica_em_texto_puro(self):
        u = criar_usuario(senha='segredo1')
        self.assertNotEqual(u.senha, 'segredo1')
        self.assertTrue(Usuario.senha_e_hash(u.senha))

    def test_senha_antiga_em_texto_puro_e_convertida_no_primeiro_login(self):
        Usuario.objects.create(username='antigo', email='a@teste.com', senha='abc123', tipo='funcionario')
        r = self.entrar('antigo', 'abc123')
        self.assertRedirects(r, reverse('inicio'))
        self.assertTrue(Usuario.senha_e_hash(Usuario.objects.get(username='antigo').senha))

    def test_paginas_exigem_login(self):
        nomes = ['inicio', 'listar_usuarios', 'listar_cursos', 'listar_disciplinas', 'listar_horarios',
                 'listar_professores', 'criar_curso', 'criar_disciplina', 'criar_professor', 'criar_horario',
                 'calendario', 'relatorios']
        for nome in nomes:
            with self.subTest(pagina=nome):
                r = self.client.get(reverse(nome))
                self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)

    def test_gerar_pdf_exige_login(self):
        r = self.client.get(reverse('gerar_pdf'), {'professor': 'todos'})
        self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)

    def test_funcionario_nao_cria_usuario(self):
        criar_usuario('func', tipo='funcionario')
        self.entrar('func')
        self.client.post(reverse('criar_usuario'), {'username': 'novo', 'email': 'n@t.com', 'senha': 'abcdef', 'tipo': 'admin'})
        self.assertFalse(Usuario.objects.filter(username='novo').exists())

    def test_admin_cria_usuario_com_senha_criptografada(self):
        criar_usuario()
        self.entrar()
        self.client.post(reverse('criar_usuario'), {'username': 'novo', 'email': 'n@t.com', 'senha': 'abcdef', 'tipo': 'funcionario'})
        novo = Usuario.objects.get(username='novo')
        self.assertTrue(Usuario.senha_e_hash(novo.senha))
        self.assertTrue(novo.conferir_senha('abcdef'))

    def test_senha_curta_e_recusada(self):
        criar_usuario()
        self.entrar()
        self.client.post(reverse('criar_usuario'), {'username': 'novo', 'email': 'n@t.com', 'senha': '123', 'tipo': 'funcionario'})
        self.assertFalse(Usuario.objects.filter(username='novo').exists())

    def test_usuario_duplicado_e_recusado(self):
        criar_usuario()
        self.entrar()
        r = self.client.post(reverse('criar_usuario'), {'username': 'admin', 'email': 'outro@t.com', 'senha': 'abcdef', 'tipo': 'funcionario'})
        self.assertEqual(Usuario.objects.filter(username='admin').count(), 1)
        self.assertTrue(any('Já existe' in m for m in self.mensagens(r)))

    def test_editar_sem_senha_mantem_a_senha(self):
        admin = criar_usuario()
        outro = criar_usuario('outro', 'minhasenha', 'funcionario')
        self.entrar()
        self.client.post(reverse('editar_usuario', args=[outro.id]),
                         {'username': 'outro2', 'email': 'outro@teste.com', 'senha': '', 'tipo': 'funcionario'})
        outro.refresh_from_db()
        self.assertEqual(outro.username, 'outro2')
        self.assertTrue(outro.conferir_senha('minhasenha'))

    def test_nao_pode_excluir_a_si_mesmo(self):
        admin = criar_usuario()
        self.entrar()
        self.client.post(reverse('deletar_usuario', args=[admin.id]))
        self.assertTrue(Usuario.objects.filter(pk=admin.id).exists())

    def test_excluir_exige_post(self):
        criar_usuario()
        outro = criar_usuario('outro', tipo='funcionario')
        self.entrar()
        self.client.get(reverse('deletar_usuario', args=[outro.id]))
        self.assertTrue(Usuario.objects.filter(pk=outro.id).exists())


class RecuperacaoDeSenhaTests(BaseTestCase):
    def _pedir_link(self, email='admin@teste.com'):
        self.client.post(reverse('recuperar_senha'), {'email': email})
        return re.search(r'http://testserver(/redefinir/\S+?/)', mail.outbox[-1].body).group(1)

    def test_fluxo_completo(self):
        criar_usuario()
        link = self._pedir_link()
        self.assertEqual(self.client.get(link).status_code, 200)

        r = self.client.post(link, {'senha': 'novasenha1', 'confirmar': 'novasenha1'})
        self.assertRedirects(r, reverse('login'), fetch_redirect_response=False)
        self.assertRedirects(self.entrar(senha='novasenha1'), reverse('inicio'))

    def test_link_so_funciona_uma_vez(self):
        criar_usuario()
        link = self._pedir_link()
        self.client.post(link, {'senha': 'novasenha1', 'confirmar': 'novasenha1'})
        r = self.client.get(link)
        self.assertRedirects(r, reverse('recuperar_senha'), fetch_redirect_response=False)

    def test_senhas_diferentes_nao_trocam(self):
        criar_usuario()
        link = self._pedir_link()
        self.client.post(link, {'senha': 'novasenha1', 'confirmar': 'outra-coisa'})
        self.assertTrue(Usuario.objects.get(username='admin').conferir_senha('segredo1'))

    def test_link_invalido(self):
        r = self.client.get(reverse('redefinir_senha', args=['token-falso']))
        self.assertRedirects(r, reverse('recuperar_senha'), fetch_redirect_response=False)

    def test_nao_revela_se_o_email_existe(self):
        criar_usuario()
        r1 = self.client.post(reverse('recuperar_senha'), {'email': 'admin@teste.com'})
        n_enviados = len(mail.outbox)
        r2 = self.client.post(reverse('recuperar_senha'), {'email': 'naoexiste@teste.com'})
        self.assertEqual(len(mail.outbox), n_enviados)     # nada enviado para e-mail desconhecido
        self.assertEqual(self.mensagens(r1)[0], self.mensagens(r2)[0])   # mesma resposta


class CadastrosTests(BaseTestCase):
    def setUp(self):
        criar_usuario()
        self.entrar()
        self.prof = Professor.objects.create(nome='Ana Paula', email='ana@teste.com', matricula='100')
        curso = Curso.objects.create(nome='ADS')
        self.disc = Disciplina.objects.create(nome='Algoritmos', carga_horaria=80, curso=curso)
        self.disc2 = Disciplina.objects.create(nome='Banco de Dados', carga_horaria=80, curso=curso)

    def _horario(self, disciplina, dias, inicio='19:00', fim='20:40', tipo='presencial'):
        return self.client.post(reverse('criar_horario'), {
            'professor': self.prof.id, 'disciplina': disciplina.id, 'dias': dias,
            'inicio': inicio, 'fim': fim, 'tipo': tipo})

    def test_varios_dias_criam_varios_horarios(self):
        self._horario(self.disc, ['Segunda', 'Quarta', 'Sexta'])
        self.assertEqual(HorarioAula.objects.count(), 3)

    def test_repetir_nao_duplica(self):
        self._horario(self.disc, ['Segunda'])
        self._horario(self.disc, ['Segunda'])
        self.assertEqual(HorarioAula.objects.count(), 1)

    def test_sem_dia_ou_horario_invertido_nao_cria(self):
        self._horario(self.disc, [])
        self._horario(self.disc, ['Segunda'], inicio='21:00', fim='20:00')
        self.assertEqual(HorarioAula.objects.count(), 0)

    def test_dia_invalido_e_ignorado(self):
        self._horario(self.disc, ['Domingo', 'Banana'])
        self.assertEqual(HorarioAula.objects.count(), 0)

    def test_conflito_gera_aviso(self):
        self._horario(self.disc, ['Segunda'])
        r = self._horario(self.disc2, ['Segunda'], inicio='19:00', fim='19:50')
        self.assertTrue(any('Conflito' in m for m in self.mensagens(r)))

    def test_disciplina_com_carga_invalida_e_recusada(self):
        r = self.client.post(reverse('criar_disciplina'), {'nome': 'X', 'carga': 'abc', 'curso': Curso.objects.first().id})
        self.assertFalse(Disciplina.objects.filter(nome='X').exists())

    def test_excluir_exige_post(self):
        self.client.get(reverse('deletar_professor', args=[self.prof.id]))
        self.assertTrue(Professor.objects.filter(pk=self.prof.id).exists())
        self.client.post(reverse('deletar_professor', args=[self.prof.id]))
        self.assertFalse(Professor.objects.filter(pk=self.prof.id).exists())

    def test_editar_professor_salva_dados_do_ponto(self):
        self.client.post(reverse('editar_professor', args=[self.prof.id]), {
            'nome': 'Ana Paula', 'email': 'ana@teste.com', 'matricula': '999', 'regime_juridico': 'CLT',
            'categoria': 'Prof. I', 'hora_atividade': '6', 'hae_o': '', 'hae_c': '', 'carga_horaria_semanal': ''})
        self.prof.refresh_from_db()
        self.assertEqual((self.prof.matricula, self.prof.regime_juridico), ('999', 'CLT'))


class CalendarioTests(BaseTestCase):
    def setUp(self):
        criar_usuario()
        self.entrar()
        self.prof = Professor.objects.create(nome='Ana', email='ana@teste.com')

    def test_cria_e_atualiza_feriado(self):
        self.client.post(reverse('criar_feriado'), {'data': '2026-11-02', 'descricao': 'Finados'})
        self.client.post(reverse('criar_feriado'), {'data': '2026-11-02', 'descricao': 'Finados (nacional)'})
        self.assertEqual(Feriado.objects.count(), 1)
        self.assertEqual(Feriado.objects.get().descricao, 'Finados (nacional)')

    def test_feriado_com_data_invalida(self):
        self.client.post(reverse('criar_feriado'), {'data': 'ontem', 'descricao': 'X'})
        self.assertEqual(Feriado.objects.count(), 0)

    def test_cria_ocorrencia(self):
        self.client.post(reverse('criar_ocorrencia'), {
            'professor': self.prof.id, 'data': '2026-11-09', 'codigo': 'FA', 'periodo': 'N', 'aulas': '1-2'})
        o = Ocorrencia.objects.get()
        self.assertEqual((o.codigo, o.periodo, o.aulas), ('FA', 'N', '1,2'))

    def test_ocorrencia_invalida_nao_grava(self):
        base = {'professor': self.prof.id, 'data': '2026-11-09', 'codigo': 'FA', 'periodo': '', 'aulas': ''}
        for ruim in ({'codigo': 'XYZ'}, {'aulas': '9'}, {'periodo': 'Z'}, {'data': ''}, {'professor': '999'}):
            with self.subTest(ruim=ruim):
                self.client.post(reverse('criar_ocorrencia'), {**base, **ruim})
        self.assertEqual(Ocorrencia.objects.count(), 0)

    def test_excluir_exige_post(self):
        f = Feriado.objects.create(data=date(2026, 11, 2), descricao='Finados')
        self.client.get(reverse('deletar_feriado', args=[f.id]))
        self.assertEqual(Feriado.objects.count(), 1)
        self.client.post(reverse('deletar_feriado', args=[f.id]))
        self.assertEqual(Feriado.objects.count(), 0)


class PdfERelatorioTests(BaseTestCase):
    def setUp(self):
        criar_usuario()
        self.entrar()
        curso = Curso.objects.create(nome='ADS')
        self.disc = Disciplina.objects.create(nome='Algoritmos', carga_horaria=80, curso=curso)
        self.ana = Professor.objects.create(nome='Ana Paula', email='ana@teste.com', matricula='100')
        self.carlos = Professor.objects.create(nome='Carlos Souza', email='carlos@teste.com')
        HorarioAula.objects.create(professor=self.ana, disciplina=self.disc, dia_semana='Segunda',
                                   horario_inicio=time(19, 0), horario_fim=time(20, 40), tipo_aula='presencial')

    def test_gera_pdf_de_um_professor(self):
        r = self.client.get(reverse('gerar_pdf'), {'professor': self.ana.id, 'mes': 11, 'ano': 2026})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertTrue(r.content.startswith(b'%PDF'))
        self.assertIn('inline', r['Content-Disposition'])

    def test_professor_sem_horario_gera_aviso_no_cabecalho(self):
        r = self.client.get(reverse('gerar_pdf'), {'professor': self.carlos.id, 'mes': 11, 'ano': 2026})
        avisos = json.loads(unquote(r['X-Avisos']))
        self.assertTrue(any('nenhum horário' in a for a in avisos))

    def test_zip_traz_um_pdf_por_professor(self):
        r = self.client.get(reverse('gerar_pdf'), {'professor': 'todos', 'mes': 11, 'ano': 2026, 'formato': 'zip'})
        self.assertEqual(r['Content-Type'], 'application/zip')
        nomes = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        self.assertEqual(len(nomes), 2)
        self.assertTrue(all(n.endswith('.pdf') for n in nomes))

    def test_mes_invalido_devolve_400(self):
        r = self.client.get(reverse('gerar_pdf'), {'professor': self.ana.id, 'mes': 13})
        self.assertEqual(r.status_code, 400)

    def test_previa_inclui_o_que_ainda_nao_foi_salvo(self):
        r = self.client.get(reverse('previa_horario'), {
            'professor': self.carlos.id, 'disciplina': self.disc.id, 'dias': ['Terça', 'Quinta'],
            'inicio': '19:00', 'fim': '20:40', 'mes': 11, 'ano': 2026})
        self.assertEqual(r['Content-Type'], 'application/pdf')
        self.assertEqual(HorarioAula.objects.filter(professor=self.carlos).count(), 0)   # nada foi salvo

    def test_previa_sem_login_devolve_401(self):
        self.client.get(reverse('logout'))
        r = self.client.get(reverse('previa_horario'), {'professor': self.ana.id})
        self.assertEqual(r.status_code, 401)

    def test_relatorio_desconta_feriado_e_falta(self):
        Feriado.objects.create(data=date(2026, 11, 2), descricao='Finados')           # segunda
        Ocorrencia.objects.create(professor=self.ana, data=date(2026, 11, 9), codigo='FA', periodo='N')
        r = self.client.get(reverse('relatorios'), {'mes': 11, 'ano': 2026})
        linha = [l for l in r.context['linhas'] if l['professor'] == self.ana][0]
        # segundas de nov/2026: 2 (feriado), 9, 16, 23, 30 -> 4 dias x 2 aulas = 8 previstas; falta em 9/11 = -2
        self.assertEqual((linha['previstas'], linha['perdidas'], linha['ministradas']), (8, 2, 6))

    def test_relatorio_csv(self):
        r = self.client.get(reverse('relatorios'), {'mes': 11, 'ano': 2026, 'csv': 1})
        self.assertIn('text/csv', r['Content-Type'])
        texto = r.content.decode('utf-8-sig')
        self.assertIn('Professor;Matrícula', texto)
        self.assertIn('Ana Paula', texto)
