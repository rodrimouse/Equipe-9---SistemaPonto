import hmac

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.db import models


class Curso(models.Model):
    nome = models.CharField(max_length=100)

    def __str__(self):
        return self.nome


class Professor(models.Model):
    nome = models.CharField(max_length=100)
    email = models.EmailField()

    # Dados usados no cabeçalho do PDF de ponto (todos opcionais)
    matricula = models.CharField('Matrícula', max_length=30, blank=True, default='')
    regime_juridico = models.CharField('Regime jurídico', max_length=30, blank=True, default='')
    categoria = models.CharField(max_length=30, blank=True, default='')
    hora_atividade = models.CharField('Hora atividade', max_length=20, blank=True, default='')
    hae_o = models.CharField('HAE-O (Projeto)', max_length=20, blank=True, default='')
    hae_c = models.CharField('HAE-C (Coordenação)', max_length=20, blank=True, default='')
    carga_horaria_semanal = models.CharField(
        'Carga horária semanal', max_length=10, blank=True, default='',
        help_text='Deixe vazio para calcular pelo número de aulas cadastradas.')

    def __str__(self):
        return self.nome


class Disciplina(models.Model):
    nome = models.CharField(max_length=100)
    carga_horaria = models.IntegerField()
    curso = models.ForeignKey(Curso, on_delete=models.CASCADE)

    def __str__(self):
        return self.nome


class HorarioAula(models.Model):
    professor = models.ForeignKey(Professor, on_delete=models.CASCADE, null=True)
    disciplina = models.ForeignKey(Disciplina, on_delete=models.CASCADE)

    dia_semana = models.CharField(max_length=20)
    horario_inicio = models.TimeField()
    horario_fim = models.TimeField()

    tipo_aula = models.CharField(
        max_length=20,
        choices=[('presencial', 'Presencial'), ('online', 'Online')]
    )

    def __str__(self):
        return f"{self.disciplina} - {self.dia_semana}"


class Usuario(models.Model):
    TIPOS = (
        ('admin', 'Administrador'),
        ('funcionario', 'Funcionário'),
    )

    username = models.CharField(max_length=100, unique=True)
    email = models.EmailField(unique=True)
    senha = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPOS)

    def __str__(self):
        return self.username

    @staticmethod
    def senha_e_hash(valor):
        """True se o valor guardado já é um hash do Django (False = senha antiga em texto puro)."""
        try:
            identify_hasher(valor)
            return True
        except ValueError:
            return False

    def definir_senha(self, senha_bruta):
        self.senha = make_password(senha_bruta)

    def conferir_senha(self, senha_bruta):
        """Confere a senha. Senhas antigas (texto puro) são aceitas uma última vez e já convertidas em hash."""
        if self.senha_e_hash(self.senha):
            return check_password(senha_bruta, self.senha)
        if hmac.compare_digest(self.senha.encode(), (senha_bruta or '').encode()):
            self.definir_senha(senha_bruta)
            self.save(update_fields=['senha'])
            return True
        return False


class Feriado(models.Model):
    data = models.DateField(unique=True)
    descricao = models.CharField('Descrição', max_length=60, default='Feriado')

    class Meta:
        ordering = ['data']

    def __str__(self):
        return f"{self.data:%d/%m/%Y} - {self.descricao}"


class Ocorrencia(models.Model):
    """Falta, licença, reposição etc. de um professor em um dia (códigos da legenda do cartão de ponto)."""
    CODIGOS = [('FA', 'FA – Falta aula'),
        ('FD', 'FD – Falta dia'),
        ('FM', 'FM – Falta médica'),
        ('LM', 'LM – Licença médica'),
        ('CRT', 'CRT – Convocação reunião/treinamento'),
        ('CPE', 'CPE – Convocação para eventos'),
        ('FAA', 'FAA – Falta auxílio alimentação'),
        ('FR', 'FR – Falta reunião'),
        ('PL', 'PL – Falta prevista em lei'),
        ('R', 'R – Reposição de aulas'),
        ('S', 'S – Substituição'),
        ('RCD', 'RCD – Reposição por claro docente'),
        ('AN', 'AN – Adicional noturno')]
    PERIODOS = [('', 'Todos'), ('M', 'Manhã'), ('T', 'Tarde'), ('N', 'Noite')]

    professor = models.ForeignKey(Professor, on_delete=models.CASCADE)
    data = models.DateField()
    periodo = models.CharField('Período', max_length=1, choices=PERIODOS, blank=True, default='')
    aulas = models.CharField('Aulas', max_length=30, blank=True, default='',
                             help_text='Ex.: 1-2 ou 1,3. Vazio = todas as aulas do período/dia.')
    codigo = models.CharField('Código', max_length=4, choices=CODIGOS)

    def __str__(self):
        return f"{self.professor} - {self.data:%d/%m/%Y} - {self.codigo}"
