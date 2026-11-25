from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0005_professor_dados_ponto'),
    ]

    operations = [
        migrations.CreateModel(
            name='Feriado',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField(unique=True)),
                ('descricao', models.CharField(default='Feriado', max_length=60, verbose_name='Descrição')),
            ],
            options={
                'ordering': ['data'],
            },
        ),
        migrations.CreateModel(
            name='Ocorrencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data', models.DateField()),
                ('periodo', models.CharField(blank=True, choices=[('', 'Todos'), ('M', 'Manhã'), ('T', 'Tarde'), ('N', 'Noite')], default='', max_length=1, verbose_name='Período')),
                ('aulas', models.CharField(blank=True, default='', help_text='Ex.: 1-2 ou 1,3. Vazio = todas as aulas do período/dia.', max_length=30, verbose_name='Aulas')),
                ('codigo', models.CharField(choices=[('FA', 'FA – Falta aula'), ('FD', 'FD – Falta dia'), ('FM', 'FM – Falta médica'), ('LM', 'LM – Licença médica'), ('CRT', 'CRT – Convocação reunião/treinamento'), ('CPE', 'CPE – Convocação para eventos'), ('FAA', 'FAA – Falta auxílio alimentação'), ('FR', 'FR – Falta reunião'), ('PL', 'PL – Falta prevista em lei'), ('R', 'R – Reposição de aulas'), ('S', 'S – Substituição'), ('RCD', 'RCD – Reposição por claro docente'), ('AN', 'AN – Adicional noturno')], max_length=4, verbose_name='Código')),
                ('professor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='usuarios.professor')),
            ],
        ),
    ]
