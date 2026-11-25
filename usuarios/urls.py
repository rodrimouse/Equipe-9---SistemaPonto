from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    path('usuarios/', views.listar_usuarios, name='listar_usuarios'),
    path('usuarios/criar/', views.criar_usuario, name='criar_usuario'),
    path('usuarios/editar/<int:id>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/deletar/<int:id>/', views.deletar_usuario, name='deletar_usuario'),

    path('inicio/', views.inicio, name='inicio'),
    path('recuperar/', views.recuperar_senha, name='recuperar_senha'),
    path('redefinir/<str:token>/', views.redefinir_senha, name='redefinir_senha'),
    path('cursos/', views.listar_cursos, name='listar_cursos'),
    path('cursos/novo/', views.criar_curso, name='criar_curso'),

    path('cursos/editar/<int:id>/', views.editar_curso, name='editar_curso'),
    path('cursos/deletar/<int:id>/', views.deletar_curso, name='deletar_curso'),

    path('disciplinas/', views.listar_disciplinas, name='listar_disciplinas'),
    path('disciplinas/nova/', views.criar_disciplina, name='criar_disciplina'),
    path('disciplinas/editar/<int:id>/', views.editar_disciplina, name='editar_disciplina'),
    path('disciplinas/deletar/<int:id>/', views.deletar_disciplina, name='deletar_disciplina'),

    path('horarios/', views.listar_horarios, name='listar_horarios'),
    path('horarios/novo/', views.criar_horario, name='criar_horario'),
    path('horarios/previa/', views.previa_horario, name='previa_horario'),
    path('horarios/deletar/<int:id>/', views.deletar_horario, name='deletar_horario'),

    path('professores/', views.listar_professores, name='listar_professores'),
    path('professores/novo/', views.criar_professor, name='criar_professor'),
    path('professores/editar/<int:id>/', views.editar_professor, name='editar_professor'),
    path('professores/deletar/<int:id>/', views.deletar_professor, name='deletar_professor'),

    path('gerar-pdf/', views.gerar_pdf, name='gerar_pdf'),
    path('calendario/', views.calendario, name='calendario'),
    path('calendario/feriados/novo/', views.criar_feriado, name='criar_feriado'),
    path('calendario/feriados/deletar/<int:id>/', views.deletar_feriado, name='deletar_feriado'),
    path('calendario/ocorrencias/nova/', views.criar_ocorrencia, name='criar_ocorrencia'),
    path('calendario/ocorrencias/deletar/<int:id>/', views.deletar_ocorrencia, name='deletar_ocorrencia'),
    path('relatorios/', views.relatorios, name='relatorios'),

]