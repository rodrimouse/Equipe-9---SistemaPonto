# Ponto Acadêmico — FATEC Ipiranga

Sistema web para **gerar automaticamente a folha de ponto (Anexo I)** dos professores da FATEC a partir do cadastro de cursos, disciplinas, professores e horários de aula.

O sistema preenche o **PDF oficial** (cabeçalho, grade horária semanal e folha de frequência do mês), considerando feriados, faltas, licenças e reposições, e ainda gera um relatório mensal de aulas.

![Painel inicial](docs/img/inicio.png)

## Funcionalidades

| Área | O que faz |
|------|-----------|
| **Cadastros** | Cursos, disciplinas, professores (com matrícula, regime, categoria, HAE etc.) e horários de aula. |
| **Horários** | Marca vários dias da semana de uma vez, com **prévia do PDF ao vivo** antes de salvar e aviso de conflito de horário. |
| **PDF de ponto** | Preenche o modelo oficial para **qualquer mês/ano**: dias, domingos, aulas por dia, feriados, faltas (FA, FM, LM...) e reposições (R, S, RCD). Gera um PDF, um PDF único com todos ou um `.zip` com um PDF por professor. |
| **Calendário** | Feriados e ocorrências, que saem automaticamente na folha. |
| **Relatório mensal** | Aulas previstas, perdidas, repostas e ministradas, e horas, por professor. Exporta CSV (abre no Excel). |
| **Segurança** | Senhas criptografadas, recuperação de senha por link com validade, login obrigatório, sessão com expiração. |
| **Carga de dados** | Comando `popular_banco` que importa tudo de um arquivo JSON, sem duplicar e validando antes de gravar. |

## Tecnologias

Python 3.12+ · Django 6 · SQLite (padrão) · ReportLab + pypdf (geração do PDF) · HTML/CSS/JS puros (sem frameworks de front-end).

## Integrantes e turno

| Nome completo | RA | Turno |
|---------------|----|-------|
| Rodrigo Miyahira Suguino | 2040482312003 | Vespertino |

**Equipe 9** · Laboratório de Engenharia de Software · Prof. Carlos Veríssimo

## Versões

Python 3.12 (no Docker; também roda em 3.13) · Django 6 · SQLite · Gunicorn · ReportLab 4 · pypdf 5.

## Pré-requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) ou Docker Engine + Compose (Linux)
- Git

## Como executar (Docker)

```bash
git clone https://github.com/rodrimouse/Equipe-9---SistemaPonto.git
cd Equipe-9---SistemaPonto
git checkout v1.0-mvp
docker compose up --build
```

Acesse <http://localhost:8000/>. Na primeira execução o contêiner aplica as migrações e carrega os dados de exemplo (cursos, disciplinas, professores, horários e usuários de teste). Os dados ficam no volume `ponto-dados`. Para parar: `Ctrl+C`; para apagar tudo: `docker compose down -v`.

### Sem Docker (alternativa)

```bash
python -m venv venv
venv\Scripts\activate            # Linux/Mac: source venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py popular_banco
python manage.py runserver
```

## Usuários e senhas de teste

| Perfil | Usuário | Senha |
|--------|---------|-------|
| Administrador | `admin` | `Admin@2026` |
| Funcionário | `funcionario` | `Func@2026` |

O administrador gerencia usuários; o funcionário não vê essa área. Senhas ficam gravadas apenas como hash PBKDF2.

## Como executar os testes

```bash
python manage.py test
```

Com Docker: `docker compose run --rm web python manage.py test`.
A suíte tem 83 testes automatizados (importador, geração do PDF, relatório e views). O plano com 48 casos manuais está na Documentação Final.

## Variáveis de ambiente

| Variável | Função | Padrão |
|----------|--------|--------|
| `DJANGO_SECRET_KEY` | Chave secreta (se vazia, é gerada e guardada em arquivo) | gerada |
| `DJANGO_DEBUG` | `0` desliga o modo debug | `1` (`0` no Docker) |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos, separados por vírgula | vazio (`localhost,127.0.0.1` no Docker) |
| `DJANGO_COOKIE_SECURE` | Cookies só por HTTPS | `1` se DEBUG=0 (`0` no Docker local) |
| `DJANGO_DB_PATH` | Caminho do banco SQLite | `db.sqlite3` (`/data/db.sqlite3` no Docker) |
| `PONTO_UNIDADE` | Texto de “Unidade:” no PDF | vazio |

Exemplo em `.env.example`. Nenhum segredo é versionado.

## Links

- **Vídeo de apresentação:** VIDEO_LINK_AQUI
- **Protótipo no Figma:** não elaborado (ver Documentação Final, seção 9)
- **Sistema publicado:** não há (execução local via Docker)

## Documentação

`docs/MANUAL_DO_USUARIO.md`, `docs/MODELO_DE_DADOS.md`, `docs/DEPLOY.md`.
