import csv
import io
import json
import logging
import zipfile
import hashlib
from collections import defaultdict
from functools import wraps
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.core import signing
from django.core.mail import send_mail
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils.text import slugify

from .models import Usuario, Disciplina, Curso, HorarioAula, Professor, Feriado, Ocorrencia
from .pdf_ponto import AulaPonto, OcorrenciaPonto, ProfessorPonto, gerar_pdf_ponto, parse_aulas
from .relatorio import conflitos_da_grade, resumo_mensal

logger = logging.getLogger(__name__)

SENHA_MIN = 6
SAL_RESET = 'ponto.redefinir-senha'
VALIDADE_RESET = 3600   # segundos


def login_obrigatorio(view):
    """Redireciona para o login se não houver usuário na sessão."""
    @wraps(view)
    def interno(request, *args, **kwargs):
        if 'user_id' not in request.session:
            return redirect('login')
        return view(request, *args, **kwargs)
    return interno


def login_view(request):
    if request.method == 'POST':
        username = (request.POST.get('username') or '').strip()
        senha = request.POST.get('senha') or ''

        user = Usuario.objects.filter(username=username).first()
        if user and user.conferir_senha(senha):
            request.session.cycle_key()          # nova sessão a cada login
            request.session['user_id'] = user.id
            request.session['tipo'] = user.tipo
            request.session['username'] = user.username
            return redirect('inicio')
        messages.error(request, 'Usuário ou senha inválidos')

    return render(request, 'usuarios/login.html')


@login_obrigatorio
def inicio(request):
    return render(request, 'usuarios/inicio.html', {
        'total_professores': Professor.objects.count(),
        'total_disciplinas': Disciplina.objects.count(),
        'total_cursos': Curso.objects.count(),
        'total_horarios': HorarioAula.objects.count(),
        'sem_horario': Professor.objects.filter(horarioaula__isnull=True).order_by('nome'),
    })


def logout_view(request):
    request.session.flush()
    return redirect('login')


@login_obrigatorio
def listar_usuarios(request):
    if 'user_id' not in request.session:
        return redirect('login')

    usuarios = Usuario.objects.all()
    return render(request, 'usuarios/usuarios.html', {'usuarios': usuarios})


def _erro_usuario(username, email, senha, id_atual=None, senha_obrigatoria=True):
    """Devolve a mensagem de erro (ou None se estiver tudo certo)."""
    if not username or not email:
        return 'Informe usuário e e-mail.'
    if senha_obrigatoria or senha:
        if len(senha) < SENHA_MIN:
            return f'A senha deve ter pelo menos {SENHA_MIN} caracteres.'
    outros = Usuario.objects.exclude(pk=id_atual) if id_atual else Usuario.objects.all()
    if outros.filter(username=username).exists():
        return f'Já existe um usuário "{username}".'
    if outros.filter(email__iexact=email).exists():
        return f'Já existe um usuário com o e-mail {email}.'
    return None


@login_obrigatorio
def criar_usuario(request):
    if request.session.get('tipo') != 'admin':
        messages.error(request, "Apenas administradores podem criar usuários.")
        return redirect('listar_usuarios')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('senha', '')
        tipo = request.POST.get('tipo')
        if tipo not in dict(Usuario.TIPOS):
            tipo = 'funcionario'

        erro = _erro_usuario(username, email, senha)
        if erro:
            messages.error(request, erro)
            return redirect('criar_usuario')

        usuario = Usuario(username=username, email=email, tipo=tipo)
        usuario.definir_senha(senha)
        usuario.save()
        messages.success(request, f'Usuário {username} criado.')
        return redirect('listar_usuarios')

    return render(request, 'usuarios/criar_usuario.html')


@login_obrigatorio
def editar_usuario(request, id):
    if request.session.get('tipo') != 'admin':
        messages.error(request, "Apenas administradores podem editar usuários.")
        return redirect('listar_usuarios')

    user = get_object_or_404(Usuario, pk=id)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        senha = request.POST.get('senha', '')          # vazio = manter a atual
        tipo = request.POST.get('tipo')
        if tipo not in dict(Usuario.TIPOS):
            tipo = user.tipo

        erro = _erro_usuario(username, email, senha, id_atual=user.id, senha_obrigatoria=False)
        if not erro and user.id == request.session.get('user_id') and tipo != 'admin':
            erro = 'Você não pode tirar o seu próprio acesso de administrador.'
        if erro:
            messages.error(request, erro)
            return redirect('editar_usuario', id=user.id)

        user.username, user.email, user.tipo = username, email, tipo
        if senha:
            user.definir_senha(senha)
        user.save()
        if user.id == request.session.get('user_id'):
            request.session['username'] = user.username
        messages.success(request, 'Usuário atualizado.')
        return redirect('listar_usuarios')

    return render(request, 'usuarios/editar_usuario.html', {'user': user})


@login_obrigatorio
def deletar_usuario(request, id):
    if request.session.get('tipo') != 'admin':
        messages.error(request, "Apenas administradores podem excluir usuários.")
        return redirect('listar_usuarios')

    if request.method == 'POST':
        if id == request.session.get('user_id'):
            messages.error(request, 'Você não pode excluir o seu próprio usuário.')
        else:
            Usuario.objects.filter(pk=id).delete()
            messages.success(request, 'Usuário excluído.')
    return redirect('listar_usuarios')


def _selo(user):
    """Muda quando a senha muda: o link de redefinição só funciona uma vez."""
    return hashlib.sha256(user.senha.encode()).hexdigest()[:16]


def recuperar_senha(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        user = Usuario.objects.filter(email__iexact=email).first()
        if user:
            token = signing.dumps({'u': user.id, 'v': _selo(user)}, salt=SAL_RESET)
            link = request.build_absolute_uri(reverse('redefinir_senha', args=[token]))
            try:
                send_mail(
                    'Ponto Acadêmico - redefinição de senha',
                    f'Olá, {user.username}.\n\nPara criar uma nova senha, acesse o link abaixo '
                    f'(vale por 1 hora e só pode ser usado uma vez):\n\n{link}\n\n'
                    'Se você não pediu isso, ignore este e-mail.',
                    None, [user.email])
            except Exception:
                logger.exception('Falha ao enviar o e-mail de redefinição de senha')
                messages.error(request, 'Não foi possível enviar o e-mail agora. Fale com o administrador.')
                return redirect('recuperar_senha')
        # mesma resposta exista ou não o e-mail (não revela quem tem conta)
        messages.success(request, 'Se esse e-mail estiver cadastrado, enviamos um link para criar uma nova senha (vale por 1 hora).')
        if settings.DEBUG and 'console' in getattr(settings, 'EMAIL_BACKEND', ''):
            messages.info(request, 'Ambiente de desenvolvimento: o e-mail foi impresso no terminal onde o servidor está rodando.')
        return redirect('recuperar_senha')

    return render(request, 'usuarios/recuperar_senha.html')


def _usuario_do_token(token):
    try:
        dados = signing.loads(token, salt=SAL_RESET, max_age=VALIDADE_RESET)
    except signing.BadSignature:          # inclui link expirado
        return None
    user = Usuario.objects.filter(pk=dados.get('u')).first()
    if not user or _selo(user) != dados.get('v'):
        return None
    return user


def redefinir_senha(request, token):
    user = _usuario_do_token(token)
    if not user:
        messages.error(request, 'Link inválido ou expirado. Peça um novo.')
        return redirect('recuperar_senha')

    if request.method == 'POST':
        nova = request.POST.get('senha', '')
        confirmar = request.POST.get('confirmar', '')
        if len(nova) < SENHA_MIN:
            messages.error(request, f'A senha deve ter pelo menos {SENHA_MIN} caracteres.')
        elif nova != confirmar:
            messages.error(request, 'As senhas não conferem.')
        else:
            user.definir_senha(nova)
            user.save()
            messages.success(request, 'Senha alterada. Entre com a nova senha.')
            return redirect('login')

    return render(request, 'usuarios/redefinir_senha.html', {'token': token})


@login_obrigatorio
def listar_cursos(request):
    cursos = Curso.objects.annotate(total_disciplinas=Count('disciplina')).order_by('nome')
    return render(request, 'usuarios/cursos.html', {'cursos': cursos})


@login_obrigatorio
def criar_curso(request):
    if request.method == 'POST':
        nome = request.POST.get('nome')
        Curso.objects.create(nome=nome)
        return redirect('listar_cursos')

    return render(request, 'usuarios/criar_curso.html')

@login_obrigatorio
def editar_curso(request, id):
    curso = Curso.objects.get(id=id)

    if request.method == 'POST':
        curso.nome = request.POST.get('nome')
        curso.save()
        return redirect('listar_cursos')

    return render(request, 'usuarios/editar_curso.html', {'curso': curso})


@login_obrigatorio
def deletar_curso(request, id):
    if request.method == 'POST':
        Curso.objects.filter(pk=id).delete()
        messages.success(request, 'Curso excluído.')
    return redirect('listar_cursos')


@login_obrigatorio
def listar_disciplinas(request):
    disciplinas = Disciplina.objects.select_related('curso').order_by('nome')
    return render(request, 'usuarios/disciplinas.html', {'disciplinas': disciplinas})


@login_obrigatorio
def criar_disciplina(request):
    cursos = Curso.objects.all().order_by('nome')

    if request.method == 'POST':
        try:
            carga = int(request.POST.get('carga'))
            if carga < 1:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Informe uma carga horária válida (número maior que zero).')
            return redirect('criar_disciplina')

        Disciplina.objects.create(
            nome=request.POST.get('nome', '').strip(),
            carga_horaria=carga,
            curso_id=request.POST.get('curso'),
        )
        messages.success(request, 'Disciplina cadastrada.')
        return redirect('listar_disciplinas')

    return render(request, 'usuarios/criar_disciplina.html', {'cursos': cursos})


@login_obrigatorio
def editar_disciplina(request, id):
    disciplina = get_object_or_404(Disciplina, pk=id)
    cursos = Curso.objects.all().order_by('nome')

    if request.method == 'POST':
        try:
            carga = int(request.POST.get('carga'))
            if carga < 1:
                raise ValueError
        except (TypeError, ValueError):
            messages.error(request, 'Informe uma carga horária válida (número maior que zero).')
            return redirect('editar_disciplina', id=id)

        disciplina.nome = request.POST.get('nome', '').strip()
        disciplina.carga_horaria = carga
        disciplina.curso_id = request.POST.get('curso')
        disciplina.save()
        messages.success(request, 'Disciplina atualizada.')
        return redirect('listar_disciplinas')

    return render(request, 'usuarios/criar_disciplina.html', {'disciplina': disciplina, 'cursos': cursos})


@login_obrigatorio
def deletar_disciplina(request, id):
    if request.method == 'POST':
        Disciplina.objects.filter(pk=id).delete()
        messages.success(request, 'Disciplina excluída (e os horários dela).')
    return redirect('listar_disciplinas')


DIAS_SEMANA = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado']


def _parse_hora(texto):
    """'19:00' ou '19:00:00' -> time; inválido -> None."""
    for formato in ('%H:%M', '%H:%M:%S'):
        try:
            return datetime.strptime((texto or '').strip(), formato).time()
        except ValueError:
            pass
    return None


@login_obrigatorio
def criar_horario(request):
    professores = Professor.objects.all().order_by('nome')
    disciplinas = Disciplina.objects.all().order_by('nome')

    if request.method == 'POST':
        dias = [d for d in request.POST.getlist('dias') if d in DIAS_SEMANA]
        inicio = _parse_hora(request.POST.get('inicio'))
        fim = _parse_hora(request.POST.get('fim'))

        if not dias:
            messages.error(request, 'Marque pelo menos um dia da semana.')
            return redirect('criar_horario')
        if not inicio or not fim or inicio >= fim:
            messages.error(request, 'Informe um horário de início e fim válidos (início antes do fim).')
            return redirect('criar_horario')

        criados = 0
        for dia in dias:
            dados = dict(
                professor_id=request.POST.get('professor'),
                disciplina_id=request.POST.get('disciplina'),
                dia_semana=dia,
                horario_inicio=inicio,
                horario_fim=fim,
                tipo_aula=request.POST.get('tipo'),
            )
            if not HorarioAula.objects.filter(**dados).exists():   # evita duplicar
                HorarioAula.objects.create(**dados)
                criados += 1
        messages.success(request, f'{criados} horário(s) cadastrado(s).')
        aulas_prof = [AulaPonto(h.disciplina.nome, h.dia_semana, h.horario_inicio, h.horario_fim)
                      for h in HorarioAula.objects.filter(professor_id=request.POST.get('professor'))
                      .select_related('disciplina')]
        for conflito in conflitos_da_grade(aulas_prof)[:5]:
            messages.warning(request, f'Conflito de horário do professor: {conflito}.')
        return redirect('listar_horarios')

    hoje = date.today()
    return render(request, 'usuarios/criar_horario.html', {
        'professores': professores,
        'disciplinas': disciplinas,
        'dias_semana': DIAS_SEMANA,
        'mes_atual': hoje.month,
        'ano_atual': hoje.year,
    })


@login_obrigatorio
def listar_horarios(request):
    horarios = list(HorarioAula.objects.select_related('professor', 'disciplina'))

    def ordem(h):
        dia = DIAS_SEMANA.index(h.dia_semana) if h.dia_semana in DIAS_SEMANA else 99
        return ((h.professor.nome if h.professor else '').lower(), dia, h.horario_inicio)

    horarios.sort(key=ordem)
    return render(request, 'usuarios/horarios.html', {'horarios': horarios})


@login_obrigatorio
def deletar_horario(request, id):
    if request.method == 'POST':
        HorarioAula.objects.filter(pk=id).delete()
    return redirect('listar_horarios')


@login_obrigatorio
def listar_professores(request):
    professores = Professor.objects.annotate(total_horarios=Count('horarioaula')).order_by('nome')
    return render(request, 'usuarios/professores.html', {'professores': professores})


@login_obrigatorio
def deletar_professor(request, id):
    if request.method == 'POST':
        Professor.objects.filter(pk=id).delete()
        messages.success(request, 'Professor excluído (e os horários dele).')
    return redirect('listar_professores')


CAMPOS_PROFESSOR = ['nome', 'email', 'matricula', 'regime_juridico', 'categoria',
                    'hora_atividade', 'hae_o', 'hae_c', 'carga_horaria_semanal']


@login_obrigatorio
def criar_professor(request):
    if request.method == 'POST':
        Professor.objects.create(**{c: request.POST.get(c, '').strip() for c in CAMPOS_PROFESSOR})
        return redirect('listar_professores')

    return render(request, 'usuarios/criar_professor.html')


@login_obrigatorio
def editar_professor(request, id):
    professor = get_object_or_404(Professor, pk=id)

    if request.method == 'POST':
        for c in CAMPOS_PROFESSOR:
            setattr(professor, c, request.POST.get(c, '').strip())
        professor.save()
        return redirect('listar_professores')

    return render(request, 'usuarios/criar_professor.html', {'professor': professor})


TEXTO = 'text/plain; charset=utf-8'


def _mes_ano(params):
    hoje = date.today()
    try:
        mes = int(params.get('mes') or hoje.month)
        ano = int(params.get('ano') or hoje.year)
    except ValueError:
        return None
    if mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        return None
    return mes, ano


def _professores_da_escolha(escolha):
    """'todos' -> todos os professores; id -> [professor]; inválido -> None."""
    if escolha == 'todos':
        return list(Professor.objects.all().order_by('nome'))
    try:
        return [Professor.objects.get(pk=escolha)]
    except (TypeError, ValueError, Professor.DoesNotExist):
        return None


def _aulas_lista(texto):
    try:
        return parse_aulas(texto)
    except ValueError:
        return []


def _carregar_dados(professores, mes, ano, extras=None):
    """
    Lê do banco o que o PDF e o relatório precisam.
    Retorna (aulas_por_professor, ocorrencias_por_professor, feriados{data: descrição}).
    `extras` = {id_professor: [AulaPonto]} com aulas ainda não salvas (prévia).
    """
    aulas = defaultdict(list)
    for h in (HorarioAula.objects.filter(professor__in=professores)
              .select_related('disciplina').order_by('horario_inicio')):
        aulas[h.professor_id].append(AulaPonto(
            disciplina=h.disciplina.nome, dia_semana=h.dia_semana,
            inicio=h.horario_inicio, fim=h.horario_fim, online=(h.tipo_aula == 'online')))
    for pid, lista in (extras or {}).items():
        aulas[pid].extend(lista)

    ocorrencias = defaultdict(list)
    for o in Ocorrencia.objects.filter(professor__in=professores, data__year=ano, data__month=mes):
        ocorrencias[o.professor_id].append(OcorrenciaPonto(
            data=o.data, codigo=o.codigo, periodo=o.periodo, aulas=_aulas_lista(o.aulas)))

    feriados = {f.data: f.descricao for f in Feriado.objects.filter(data__year=ano, data__month=mes)}
    return aulas, ocorrencias, feriados


def _professor_ponto(p, aulas, ocorrencias):
    return ProfessorPonto(
        nome=p.nome, matricula=p.matricula, regime=p.regime_juridico, categoria=p.categoria,
        hora_atividade=p.hora_atividade, hae_o=p.hae_o, hae_c=p.hae_c,
        carga_semanal=p.carga_horaria_semanal,
        aulas=aulas.get(p.id, []), ocorrencias=ocorrencias.get(p.id, []))


def _modelo_pdf():
    return Path(__file__).resolve().parent.parent / 'documentos' / 'Modelo de Ponto.pdf'


def _pdf_response(professores, mes, ano, extras=None, baixar=False, como_zip=False):
    """
    Monta o PDF (ou um .zip com um PDF por professor). `extras` = aulas ainda não salvas (prévia).
    Os avisos vão no cabeçalho X-Avisos (JSON codificado).
    """
    modelo = _modelo_pdf()
    if not modelo.exists():
        return HttpResponse('O arquivo "Modelo de Ponto.pdf" não foi encontrado na pasta documentos.',
                            status=500, content_type=TEXTO)

    aulas, ocorrencias, feriados = _carregar_dados(professores, mes, ano, extras)
    dados = [_professor_ponto(p, aulas, ocorrencias) for p in professores]
    unidade = getattr(settings, 'PONTO_UNIDADE', '')

    try:
        if como_zip:
            avisos, buf = [], io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
                for p, d in zip(professores, dados):
                    pdf, av = gerar_pdf_ponto(modelo, [d], mes, ano, unidade=unidade, feriados=feriados)
                    avisos.extend(av)
                    z.writestr(f'ponto_{slugify(p.nome) or "professor"}_{mes:02d}_{ano}.pdf', pdf)
            conteudo, tipo, nome_arquivo = buf.getvalue(), 'application/zip', f'pontos_{mes:02d}_{ano}.zip'
        else:
            conteudo, avisos = gerar_pdf_ponto(modelo, dados, mes, ano, unidade=unidade, feriados=feriados)
            tipo = 'application/pdf'
            if len(professores) == 1:
                nome_arquivo = f'ponto_{slugify(professores[0].nome) or "professor"}_{mes:02d}_{ano}.pdf'
            else:
                nome_arquivo = f'ponto_todos_{mes:02d}_{ano}.pdf'
    except Exception:
        logger.exception('Falha ao gerar o PDF de ponto')
        return HttpResponse('Não foi possível gerar o PDF. Veja o log do servidor.',
                            status=500, content_type=TEXTO)

    for p in professores:
        if not aulas.get(p.id):
            avisos.append(f'{p.nome}: nenhum horário cadastrado (a folha sai só com o cabeçalho).')
    if len(avisos) > 10:
        avisos = avisos[:10] + [f'... e mais {len(avisos) - 10} aviso(s).']

    response = HttpResponse(conteudo, content_type=tipo)
    forma = 'attachment' if (baixar or como_zip) else 'inline'
    response['Content-Disposition'] = f'{forma}; filename="{nome_arquivo}"'
    response['X-Avisos'] = quote(json.dumps(avisos, ensure_ascii=False))
    return response


def gerar_pdf(request):
    """
    Sem parâmetros: mostra a tela (a prévia do PDF aparece sozinha ao escolher professor e mês).
    Com ?professor=ID|todos&mes=&ano= : devolve o PDF (&baixar=1 força o download,
    &formato=zip devolve um .zip com um PDF por professor).
    """
    if 'user_id' not in request.session:
        return redirect('login')

    escolha = request.GET.get('professor')
    if not escolha:
        hoje = date.today()
        return render(request, 'usuarios/gerar_pdf.html', {
            'professores': Professor.objects.all().order_by('nome'),
            'mes_atual': hoje.month,
            'ano_atual': hoje.year,
        })

    periodo = _mes_ano(request.GET)
    professores = _professores_da_escolha(escolha)
    if periodo is None:
        return HttpResponse('Mês ou ano inválido.', status=400, content_type=TEXTO)
    if not professores:
        return HttpResponse('Professor não encontrado.', status=400, content_type=TEXTO)
    return _pdf_response(professores, periodo[0], periodo[1], baixar=bool(request.GET.get('baixar')),
                         como_zip=(request.GET.get('formato') == 'zip'))


def previa_horario(request):
    """
    Prévia ao vivo da tela "Novo Horário": o PDF do professor com os horários já salvos
    MAIS o que está marcado no formulário (ainda não salvo).
    """
    if 'user_id' not in request.session:
        return HttpResponse('Sessão expirada. Faça login novamente.', status=401, content_type=TEXTO)

    periodo = _mes_ano(request.GET)
    professores = _professores_da_escolha(request.GET.get('professor'))
    if periodo is None:
        return HttpResponse('Mês ou ano inválido.', status=400, content_type=TEXTO)
    if not professores:
        return HttpResponse('Selecione um professor.', status=400, content_type=TEXTO)

    extras = {}
    try:
        disciplina = Disciplina.objects.get(pk=request.GET.get('disciplina'))
    except (TypeError, ValueError, Disciplina.DoesNotExist):
        disciplina = None
    dias = [d for d in request.GET.getlist('dias') if d in DIAS_SEMANA]
    inicio = _parse_hora(request.GET.get('inicio'))
    fim = _parse_hora(request.GET.get('fim'))
    if disciplina and dias and inicio and fim and inicio < fim:
        extras[professores[0].id] = [AulaPonto(
            disciplina=disciplina.nome, dia_semana=d, inicio=inicio, fim=fim,
            online=(request.GET.get('tipo') == 'online'),
        ) for d in dias]
    return _pdf_response(professores, periodo[0], periodo[1], extras=extras)


# ---------------------------------------------------------------------------
# Calendário: feriados e ocorrências
# ---------------------------------------------------------------------------

@login_obrigatorio
def calendario(request):
    return render(request, 'usuarios/calendario.html', {
        'feriados': Feriado.objects.all(),
        'ocorrencias': Ocorrencia.objects.select_related('professor').order_by('-data', 'professor__nome')[:150],
        'professores': Professor.objects.all().order_by('nome'),
        'codigos': Ocorrencia.CODIGOS,
        'periodos': Ocorrencia.PERIODOS,
    })


def _data_do_form(texto):
    try:
        return date.fromisoformat((texto or '').strip())
    except ValueError:
        return None


@login_obrigatorio
def criar_feriado(request):
    if request.method == 'POST':
        data = _data_do_form(request.POST.get('data'))
        descricao = request.POST.get('descricao', '').strip() or 'Feriado'
        if not data:
            messages.error(request, 'Informe uma data válida para o feriado.')
        else:
            _, criado = Feriado.objects.update_or_create(data=data, defaults={'descricao': descricao[:60]})
            messages.success(request, 'Feriado cadastrado.' if criado else 'Feriado atualizado.')
    return redirect('calendario')


@login_obrigatorio
def deletar_feriado(request, id):
    if request.method == 'POST':
        Feriado.objects.filter(pk=id).delete()
        messages.success(request, 'Feriado excluído.')
    return redirect('calendario')


@login_obrigatorio
def criar_ocorrencia(request):
    if request.method == 'POST':
        data = _data_do_form(request.POST.get('data'))
        codigo = request.POST.get('codigo')
        periodo = request.POST.get('periodo', '')
        try:
            aulas = parse_aulas(request.POST.get('aulas'))
        except ValueError as e:
            messages.error(request, str(e))
            return redirect('calendario')
        if not data:
            messages.error(request, 'Informe uma data válida.')
        elif codigo not in dict(Ocorrencia.CODIGOS):
            messages.error(request, 'Escolha o código da ocorrência.')
        elif periodo not in dict(Ocorrencia.PERIODOS):
            messages.error(request, 'Período inválido.')
        elif not Professor.objects.filter(pk=request.POST.get('professor')).exists():
            messages.error(request, 'Escolha o professor.')
        else:
            Ocorrencia.objects.create(
                professor_id=request.POST.get('professor'), data=data, periodo=periodo,
                aulas=','.join(str(n) for n in aulas), codigo=codigo)
            messages.success(request, 'Ocorrência registrada.')
    return redirect('calendario')


@login_obrigatorio
def deletar_ocorrencia(request, id):
    if request.method == 'POST':
        Ocorrencia.objects.filter(pk=id).delete()
        messages.success(request, 'Ocorrência excluída.')
    return redirect('calendario')


# ---------------------------------------------------------------------------
# Relatório mensal
# ---------------------------------------------------------------------------

@login_obrigatorio
def relatorios(request):
    periodo = _mes_ano(request.GET)
    if periodo is None:
        messages.error(request, 'Mês ou ano inválido.')
        hoje = date.today()
        periodo = (hoje.month, hoje.year)
    mes, ano = periodo

    professores = list(Professor.objects.all().order_by('nome'))
    aulas, ocorrencias, feriados = _carregar_dados(professores, mes, ano)

    linhas = []
    for p in professores:
        r = resumo_mensal(aulas.get(p.id, []), ocorrencias.get(p.id, []), feriados, mes, ano)
        r['professor'] = p
        r['detalhe'] = ', '.join(f'{c}: {n}' for c, n in sorted(r['por_codigo'].items()))
        linhas.append(r)
    totais = {k: sum(l[k] for l in linhas) for k in ('previstas', 'perdidas', 'extras', 'ministradas')}
    totais['horas'] = round(sum(l['horas'] for l in linhas), 1)

    if request.GET.get('csv'):
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = f'attachment; filename="relatorio_{ano}_{mes:02d}.csv"'
        resp.write('\ufeff')   # o Excel em português abre acentos corretamente
        w = csv.writer(resp, delimiter=';')
        w.writerow(['Professor', 'Matrícula', 'Aulas por semana', 'Previstas no mês', 'Perdidas',
                    'Reposição/substituição', 'Ministradas', 'Horas', 'Ocorrências'])
        for l in linhas:
            w.writerow([l['professor'].nome, l['professor'].matricula, l['aulas_semana'], l['previstas'],
                        l['perdidas'], l['extras'], l['ministradas'], str(l['horas']).replace('.', ','),
                        l['detalhe']])
        return resp

    return render(request, 'usuarios/relatorios.html', {
        'linhas': linhas, 'totais': totais, 'mes': mes, 'ano': ano, 'mes_atual': mes, 'ano_atual': ano,
        'feriados_mes': sorted(feriados.items()),
    })
