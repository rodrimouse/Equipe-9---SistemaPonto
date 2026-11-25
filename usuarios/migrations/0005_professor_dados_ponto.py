from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0004_horarioaula_professor_horarioaula_tipo_aula'),
    ]

    operations = [
        migrations.AddField(
            model_name='professor',
            name='matricula',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Matrícula'),
        ),
        migrations.AddField(
            model_name='professor',
            name='regime_juridico',
            field=models.CharField(blank=True, default='', max_length=30, verbose_name='Regime jurídico'),
        ),
        migrations.AddField(
            model_name='professor',
            name='categoria',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
        migrations.AddField(
            model_name='professor',
            name='hora_atividade',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Hora atividade'),
        ),
        migrations.AddField(
            model_name='professor',
            name='hae_o',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='HAE-O (Projeto)'),
        ),
        migrations.AddField(
            model_name='professor',
            name='hae_c',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='HAE-C (Coordenação)'),
        ),
        migrations.AddField(
            model_name='professor',
            name='carga_horaria_semanal',
            field=models.CharField(blank=True, default='', max_length=10, help_text='Deixe vazio para calcular pelo número de aulas cadastradas.', verbose_name='Carga horária semanal'),
        ),
    ]
