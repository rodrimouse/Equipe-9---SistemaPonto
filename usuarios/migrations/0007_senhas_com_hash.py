from django.contrib.auth.hashers import identify_hasher, make_password
from django.db import migrations


def converter_senhas(apps, schema_editor):
    """Transforma as senhas que ainda estão em texto puro em hashes (as já protegidas não mudam)."""
    Usuario = apps.get_model('usuarios', 'Usuario')
    for usuario in Usuario.objects.all():
        try:
            identify_hasher(usuario.senha)
        except ValueError:
            usuario.senha = make_password(usuario.senha)
            usuario.save(update_fields=['senha'])


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0006_feriado_ocorrencia'),
    ]

    operations = [
        # Sem volta: um hash não pode ser desfeito (e não deveria).
        migrations.RunPython(converter_senhas, migrations.RunPython.noop),
    ]
