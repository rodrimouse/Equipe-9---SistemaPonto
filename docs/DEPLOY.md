# Publicação (deploy)

Guia geral para colocar o sistema no ar. Os nomes de menus de cada serviço podem variar um pouco.

## Checklist antes de publicar

1. Gere uma chave secreta e **não** a coloque no código:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```
2. Defina as variáveis de ambiente:
   ```
   DJANGO_SECRET_KEY=<a chave gerada>
   DJANGO_DEBUG=0
   DJANGO_ALLOWED_HOSTS=seudominio.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://seudominio.com
   ```
3. Confira as configurações de produção:
   ```bash
   python manage.py check --deploy
   ```
4. Aplique as migrações e crie o primeiro usuário (veja o README):
   ```bash
   python manage.py migrate
   ```
5. Garanta que o arquivo `documentos/Modelo de Ponto.pdf` foi enviado junto.

Com `DJANGO_DEBUG=0` os cookies de sessão passam a ser enviados **somente por HTTPS**, então o site precisa estar em HTTPS.

## E-mail (recuperação de senha)

Sem configuração, o e-mail com o link aparece no terminal do servidor (serve para demonstração). Para enviar de verdade:

```
EMAIL_HOST=smtp.seuprovedor.com
EMAIL_PORT=587
EMAIL_HOST_USER=usuario
EMAIL_HOST_PASSWORD=senha
DEFAULT_FROM_EMAIL=Ponto Acadêmico <ponto@seudominio.com>
```

## Exemplo: PythonAnywhere (plano gratuito)

1. Envie o projeto (por `git clone` no console ou pelo upload de arquivos).
2. No console: crie o ambiente virtual e instale as dependências.
   ```bash
   mkvirtualenv ponto --python=python3.12
   pip install -r requirements.txt
   ```
3. Na aba **Web**: *Add a new web app* → *Manual configuration* (mesma versão do Python).
   - **Source code**: a pasta do projeto (onde está o `manage.py`).
   - **Virtualenv**: o caminho do ambiente criado.
4. Abra o arquivo **WSGI** do site e, **antes** de `get_wsgi_application()`, defina as variáveis:
   ```python
   import os, sys
   sys.path.insert(0, '/home/SEUUSUARIO/Ponto-Academico')
   os.environ['DJANGO_SETTINGS_MODULE'] = 'sistema_ponto.settings'
   os.environ['DJANGO_SECRET_KEY'] = '...'
   os.environ['DJANGO_DEBUG'] = '0'
   os.environ['DJANGO_ALLOWED_HOSTS'] = 'SEUUSUARIO.pythonanywhere.com'
   os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = 'https://SEUUSUARIO.pythonanywhere.com'
   ```
5. No console, na pasta do projeto: `python manage.py migrate` e crie o usuário.
6. Clique em **Reload** na aba Web.

O sistema não usa arquivos estáticos próprios (o CSS está dentro das páginas). Só precisaria configurar `/static/` se você passar a usar o `/admin/` do Django.

## Backup

Com SQLite, todo o banco é o arquivo `db.sqlite3`: copie-o periodicamente. Para volume maior de uso, troque para PostgreSQL ajustando `DATABASES` em `sistema_ponto/settings.py`.
