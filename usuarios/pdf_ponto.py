# -*- coding: utf-8 -*-
"""
Gerador do PDF de ponto (Anexo I - FATEC).

Preenche o modelo oficial (documentos/Modelo de Ponto.pdf) escrevendo o texto
nas posições exatas de cada célula. Não depende do Django: recebe dados simples
(dataclasses) e devolve os bytes do PDF.

    pdf_bytes, avisos = gerar_pdf_ponto(caminho_modelo, [professor1, professor2], mes=11, ano=2026)

O que é preenchido:
  * cabeçalho (nome, matrícula, regime, categoria, disciplinas, carga, HAE...)
  * grade horária semanal (sigla da disciplina em cada aula)
  * folha de frequência do mês escolhido (qualquer mês/ano: dias, dia da
    semana e domingos são redesenhados), com a sigla em cada aula do dia.
A coluna "Assinatura" fica em branco, para assinatura à mão.
"""
import calendar
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, time
from typing import List, Optional, Tuple

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# DADOS DE ENTRADA
# ---------------------------------------------------------------------------


@dataclass
class AulaPonto:
    disciplina: str
    dia_semana: str          # texto livre: "Segunda", "terça-feira", "sab"...
    inicio: time
    fim: time
    online: bool = False


@dataclass
class OcorrenciaPonto:
    """Falta, licença, reposição... (códigos da legenda do cartão de ponto)."""
    data: date
    codigo: str                    # FA, FD, FM, LM, CRT, CPE, FAA, FR, PL, R, S, RCD, AN
    periodo: str = ""              # "M", "T", "N" ou "" (= todos)
    aulas: List[int] = field(default_factory=list)   # vazio = todas as aulas do dia/período


@dataclass
class ProfessorPonto:
    nome: str
    matricula: str = ""
    regime: str = ""
    categoria: str = ""
    hora_atividade: str = ""
    hae_o: str = ""
    hae_c: str = ""
    carga_semanal: str = ""   # vazio = calcula pelo número de aulas da grade
    aulas: List[AulaPonto] = field(default_factory=list)
    ocorrencias: List[OcorrenciaPonto] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HORÁRIOS OFICIAIS DAS AULAS (50 min)  --  ajuste aqui se a unidade mudar
#   Manhã 08h00-13h30 | Tarde 13h00-18h30 | Noite 19h00-22h40
#   (intervalo de 30 min nos turnos manhã/tarde e de 20 min à noite)
# ---------------------------------------------------------------------------
HORARIOS_AULA = {
    "M": [("08:00", "08:50"), ("08:50", "09:40"), ("09:40", "10:30"),
          ("11:00", "11:50"), ("11:50", "12:40"), ("12:40", "13:30")],
    "T": [("13:00", "13:50"), ("13:50", "14:40"), ("14:40", "15:30"),
          ("16:00", "16:50"), ("16:50", "17:40"), ("17:40", "18:30")],
    "N": [("19:00", "19:50"), ("19:50", "20:40"),
          ("21:00", "21:50"), ("21:50", "22:40")],
}
NOME_PERIODO = {"M": "manhã", "T": "tarde", "N": "noite"}
MIN_SOBREPOSICAO = 25  # minutos de sobreposição para considerar a aula "dentro" do slot

# ---------------------------------------------------------------------------
# GEOMETRIA DO MODELO (pontos PDF; "top" = distância do topo da página)
# Medida em Modelo de Ponto.pdf (A4 595.32 x 841.92). Se o layout do modelo
# mudar, ajuste somente esta seção.
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = 595.32, 841.92

GRADE_COLS = {
    "M": [85.1, 106.3, 134.7, 156.0, 177.3, 198.5, 219.8],
    "T": [283.6, 304.9, 326.2, 347.5, 368.7, 390.0, 411.2],
    "N": [467.9, 489.2, 510.5, 531.7, 553.0],
}
GRADE_ROWS = [166.3, 174.9, 183.4, 191.9, 200.5, 209.1, 217.6, 226.2]  # seg..sáb, obs
OBS_BOX = {"M": (52.0, 219.0), "T": (244.0, 411.0), "N": (435.5, 553.0)}  # x ini/fim do texto do "Obs."
OBS_BASE_TOP = 224.3

FREQ_TOP, FREQ_BOTTOM = 266.8, 603.2
FREQ_PITCH = (FREQ_BOTTOM - FREQ_TOP) / 31.0
FREQ_SIG = {"M": (63.7, 113.3), "T": (241.1, 297.8), "N": (425.4, 482.0)}
FREQ_COLS = {
    "M": [113.3, 134.5, 155.8, 177.2, 198.4, 219.6, 241.1],
    "T": [297.8, 319.0, 340.3, 361.5, 382.9, 404.1, 425.4],
    "N": [482.0, 503.3, 524.6, 545.9, 567.1],
}
# Linhas verticais internas da tabela de frequência
FREQ_VLINES_DIA = [49.6, 63.7]  # valem para todas as linhas (dia | letra | assinatura)
FREQ_VLINES_RESTO = [113.3, 134.5, 155.8, 177.2, 198.4, 219.6, 241.1, 297.8, 319.0, 340.3,
                     361.5, 382.9, 404.1, 425.4, 482.0, 503.3, 524.6, 545.9, 567.1]
FREQ_X_ESQ, FREQ_X_DIR = 28.3, 567.1      # a faixa cinza à direita do modelo não é mexida
FREQ_CINZA_X0, FREQ_CINZA_X1 = 64.0, 566.9
LINHA = 0.48
CINZA = 0.502

TITULO_BOX = (200.0, 400.0, 235.2, 244.7)   # x0, x1, top, bottom do título (para antes da borda em y=244.8)
TITULO_CENTRO_X = 299.95
TITULO_BASE_TOP = 242.9

MESES = ["JANEIRO", "FEVEREIRO", "MARÇO", "ABRIL", "MAIO", "JUNHO", "JULHO",
         "AGOSTO", "SETEMBRO", "OUTUBRO", "NOVEMBRO", "DEZEMBRO"]
LETRA_DIA = ["S", "T", "Q", "Q", "S", "S", "D"]  # segunda..domingo

# Cabeçalho: (x inicial, x máximo, baseline_top, tamanho preferido)
HDR = {
    "prof":      (58.5, 311.0, 86.4, 8.0),
    "matricula": (362.0, 391.0, 86.4, 7.5),
    "regime":    (448.0, 490.0, 86.4, 7.5),
    "categoria": (537.5, 587.0, 86.4, 7.5),
    "disc":      (94.0, 440.0, 96.0, 8.0),
    "carga":     (519.0, 587.0, 94.8, 8.0),
    "hora_at":   (95.5, 235.0, 105.8, 8.0),
    "hae_o":     (292.0, 398.0, 105.8, 8.0),
    "hae_c":     (473.0, 587.0, 105.8, 8.0),
}
UNIDADE_BOX = (306.0, 380.0, 31.5, 44.0)

# ---------------------------------------------------------------------------
# UTILIDADES
# ---------------------------------------------------------------------------


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return s.strip().lower()


def dia_semana_para_indice(texto) -> Optional[int]:
    """'Segunda', 'terça-feira', 'sab' -> 0..5 ; domingo/inválido -> None."""
    k = _norm(texto)[:3]
    return {"seg": 0, "ter": 1, "qua": 2, "qui": 3, "sex": 4, "sab": 5}.get(k)


def _minutos(t) -> int:
    if isinstance(t, str):
        h, m = t.split(":")[:2]
        return int(h) * 60 + int(m)
    return t.hour * 60 + t.minute


def slots_da_aula(inicio, fim) -> List[Tuple[str, int]]:
    """
    Converte um intervalo de horário em [(periodo, nº_da_aula)], ex.: [('N',1),('N',2)].

    Atenção: no modelo a manhã termina às 13:30 e a tarde começa às 13:00, então a 6ª aula da manhã
    e a 1ª da tarde se sobrepõem. Cada trecho de tempo vale para UM slot só: ganha o slot com
    maior sobreposição (empate: o que vem primeiro).
    """
    ini, fi = _minutos(inicio), _minutos(fim)
    candidatos = []   # (sobreposição, ordem, periodo, numero, s_ini, s_fim)
    for ordem_p, (periodo, slots) in enumerate(HORARIOS_AULA.items()):
        for numero, (s_ini, s_fim) in enumerate(slots, start=1):
            a, b = _minutos(s_ini), _minutos(s_fim)
            sobre = min(fi, b) - max(ini, a)
            if sobre >= MIN_SOBREPOSICAO:
                candidatos.append((sobre, ordem_p, periodo, numero, a, b))
    escolhidos = []
    for sobre, ordem_p, periodo, numero, a, b in sorted(candidatos, key=lambda c: (-c[0], c[1], c[3])):
        if all(b <= ea or a >= eb for (_, _, ea, eb) in escolhidos):   # não pode sobrepor um já escolhido
            escolhidos.append((periodo, numero, a, b))
    return sorted(((p, n) for p, n, _, _ in escolhidos), key=lambda x: ("MTN".index(x[0]), x[1]))


def parse_aulas(texto) -> List[int]:
    """'1-3' -> [1,2,3]; '1,2,4' -> [1,2,4]; vazio -> []. Levanta ValueError se não entender."""
    if texto is None or str(texto).strip() == "":
        return []
    if isinstance(texto, (int, float)):
        return [int(texto)]
    saida = []
    for parte in re.split(r"[,;\s]+", _norm(texto).replace(" a ", "-")):
        if not parte:
            continue
        m = re.fullmatch(r"(\d+)-(\d+)", parte)
        if m:
            saida.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif parte.isdigit():
            saida.append(int(parte))
        else:
            raise ValueError(f"Não entendi as aulas {texto!r} (exemplos: 1-3 ou 1,2,4).")
    if any(n < 1 or n > 6 for n in saida):
        raise ValueError("As aulas vão de 1 a 6 (a noite tem de 1 a 4).")
    return sorted(set(saida))


# Códigos de aula EXTRA (acontece fora da grade normal): marcamos mesmo em dia sem aula prevista.
CODIGOS_EXTRAS = {"R", "S", "RCD"}

_STOP = {"de", "da", "do", "das", "dos", "e", "em", "a", "o", "para", "com", "na", "no", "ao"}


def _sigla_base(nome: str) -> str:
    palavras = [w for w in re.findall(r"[^\W_]+", nome, re.UNICODE)]
    uteis = [w for w in palavras if _norm(w) not in _STOP]
    if not uteis:
        uteis = palavras or ["?"]
    if len(uteis) == 1:
        base = uteis[0][:3]
    else:
        base = "".join(w[0] for w in uteis)[:4]
    return unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode().upper() or "?"


def gerar_siglas(nomes) -> dict:
    """{'Banco de Dados': 'BD', 'Algoritmos': 'ALG'}; evita siglas repetidas (BD, BD2...)."""
    usadas, resultado = set(), {}
    for nome in nomes:
        if nome in resultado:
            continue
        sigla, n = _sigla_base(nome), 2
        base = sigla
        while sigla in usadas:
            sigla, n = f"{base}{n}", n + 1
        usadas.add(sigla)
        resultado[nome] = sigla
    return resultado


def _ajusta_tamanho(texto, fonte, tamanho, largura, minimo=4.5):
    while tamanho > minimo and stringWidth(texto, fonte, tamanho) > largura:
        tamanho -= 0.25
    return tamanho


# ---------------------------------------------------------------------------
# DESENHO
# ---------------------------------------------------------------------------


class _Pintor:
    def __init__(self):
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(PAGE_W, PAGE_H))

    def _y(self, top):
        return PAGE_H - top

    def texto_esq(self, x0, x1, base_top, texto, tam=8.0, fonte="Helvetica"):
        if not texto:
            return
        tam = _ajusta_tamanho(texto, fonte, tam, x1 - x0)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.setFont(fonte, tam)
        self.c.drawString(x0, self._y(base_top), texto)

    def texto_centro(self, x0, x1, top, bottom, texto, tam=6.5, fonte="Helvetica-Bold"):
        if not texto:
            return
        tam = _ajusta_tamanho(texto, fonte, tam, (x1 - x0) - 1.6)
        self.c.setFillColorRGB(0, 0, 0)
        self.c.setFont(fonte, tam)
        self.c.drawCentredString((x0 + x1) / 2.0, self._y((top + bottom) / 2.0) - tam * 0.35, texto)

    def retangulo(self, x0, x1, top, bottom, cinza=1.0):
        self.c.setFillColorRGB(cinza, cinza, cinza)
        self.c.rect(x0, self._y(bottom), x1 - x0, bottom - top, stroke=0, fill=1)
        self.c.setFillColorRGB(0, 0, 0)

    def linha_v(self, x, top, bottom):
        self.retangulo(x - LINHA / 2, x + LINHA / 2, top, bottom, cinza=0)

    def linha_h(self, y, x0, x1):
        self.retangulo(x0, x1, y - LINHA / 2, y + LINHA / 2, cinza=0)

    def pagina(self):
        self.c.showPage()
        self.c.save()
        self.buf.seek(0)
        return PdfReader(self.buf).pages[0]


def _desenha_frequencia(p: _Pintor, mes: int, ano: int):
    """Redesenha o corpo da tabela de frequência (dias, letras, domingos) para o mês/ano."""
    # título mensal
    x0, x1, t, b = TITULO_BOX
    p.retangulo(x0, x1, t, b)
    titulo = f"FOLHA DE FREQÜÊNCIA – {MESES[mes - 1]}/{ano}"
    p.c.setFillColorRGB(0, 0, 0)
    p.c.setFont("Helvetica-Bold", 9)
    p.c.drawCentredString(TITULO_CENTRO_X, p._y(TITULO_BASE_TOP), titulo)

    # apaga o corpo antigo (mantém bordas externas, cabeçalho e a faixa cinza da direita)
    p.retangulo(FREQ_X_ESQ + 0.5, FREQ_X_DIR - 0.3, FREQ_TOP + 0.3, FREQ_BOTTOM - 0.3)

    dias_mes = calendar.monthrange(ano, mes)[1]
    for d in range(1, 32):
        top = FREQ_TOP + (d - 1) * FREQ_PITCH
        bottom = top + FREQ_PITCH
        existe = d <= dias_mes
        domingo = existe and date(ano, mes, d).weekday() == 6

        if not existe or domingo:
            p.retangulo(FREQ_CINZA_X0, FREQ_CINZA_X1, top + 0.3, bottom - 0.3, cinza=CINZA)
            xs = FREQ_VLINES_DIA  # sem divisórias dentro da barra cinza
        else:
            xs = FREQ_VLINES_DIA + FREQ_VLINES_RESTO
        for x in xs:
            p.linha_v(x, top, bottom)
        if existe:
            p.texto_centro(FREQ_X_ESQ, FREQ_VLINES_DIA[0], top, bottom, f"{d:02d}",
                           tam=9, fonte="Helvetica")
            p.texto_centro(FREQ_VLINES_DIA[0], FREQ_VLINES_DIA[1], top, bottom,
                           LETRA_DIA[date(ano, mes, d).weekday()], tam=9, fonte="Helvetica")
        if d < 31:  # linha horizontal abaixo da linha d
            p.linha_h(bottom, FREQ_X_ESQ, FREQ_X_DIR)


def _overlay(prof: ProfessorPonto, mes, ano, unidade, marca, avisos, feriados=None) -> object:
    p = _Pintor()

    if unidade:
        x0, x1, t, b = UNIDADE_BOX
        p.retangulo(x0, x1, t, b)
        p.c.setFont("Helvetica-Bold", 10)
        p.c.drawString(x0 + 0.7, p._y(40.6), unidade)

    # --- interpreta as aulas do professor (só entram as que couberem na grade do modelo)
    validas = []   # (aula, dia, slots)
    for a in prof.aulas:
        dia = dia_semana_para_indice(a.dia_semana)
        if dia is None:
            avisos.append(f"{prof.nome}: dia da semana não reconhecido ({a.dia_semana!r}) em "
                          f"{a.disciplina}; a aula foi ignorada.")
            continue
        slots = slots_da_aula(a.inicio, a.fim)
        if not slots:
            avisos.append(f"{prof.nome}: {a.disciplina} ({a.inicio:%H:%M}-{a.fim:%H:%M}) não "
                          f"coincide com nenhuma aula do modelo; ignorada.")
            continue
        validas.append((a, dia, slots))

    siglas = gerar_siglas([a.disciplina for a, _, _ in validas])
    grade = {}          # (dia, periodo, numero) -> [rótulos]
    online_em = set()   # períodos com aula online
    for a, dia, slots in validas:
        rotulo = siglas[a.disciplina] + ("*" if a.online else "")
        for periodo, numero in slots:
            lista = grade.setdefault((dia, periodo, numero), [])
            if rotulo not in lista:
                lista.append(rotulo)
            if a.online:
                online_em.add(periodo)
    for (dia, periodo, numero), lista in grade.items():
        if len(lista) > 1:
            avisos.append(f"{prof.nome}: conflito de horário na {numero}ª aula da {NOME_PERIODO[periodo]} "
                          f"({', '.join(lista)}).")

    # --- cabeçalho
    carga = prof.carga_semanal or (str(len(grade)) if grade else "")
    texto_disc = "; ".join(f"{n} ({s})" for n, s in siglas.items())
    x0, x1, base, tam = HDR["disc"]
    if texto_disc and stringWidth(texto_disc, "Helvetica", 5.5) > x1 - x0:
        texto_disc = "; ".join(siglas.values())   # não coube: só as siglas
    for campo, valor in [("prof", prof.nome), ("matricula", prof.matricula),
                         ("regime", prof.regime), ("categoria", prof.categoria),
                         ("disc", texto_disc), ("carga", carga),
                         ("hora_at", prof.hora_atividade), ("hae_o", prof.hae_o),
                         ("hae_c", prof.hae_c)]:
        a0, a1, b0, t0 = HDR[campo]
        p.texto_esq(a0, a1, b0, valor, t0)

    # --- grade horária
    for (dia, periodo, numero), lista in grade.items():
        cols = GRADE_COLS[periodo]
        p.texto_centro(cols[numero - 1], cols[numero], GRADE_ROWS[dia], GRADE_ROWS[dia + 1],
                       "/".join(lista))
    for periodo in online_em:
        x0, x1 = OBS_BOX[periodo]
        p.texto_esq(x0, x1, OBS_BASE_TOP, "* aula online", 6.5)

    # --- folha de frequência
    _desenha_frequencia(p, mes, ano)
    feriados = feriados or {}
    dias_mes = calendar.monthrange(ano, mes)[1]
    do_mes = [o for o in prof.ocorrencias if o.data.year == ano and o.data.month == mes]
    usadas = set()
    for d in range(1, dias_mes + 1):
        data = date(ano, mes, d)
        wd = data.weekday()
        if wd == 6:
            continue
        top = FREQ_TOP + (d - 1) * FREQ_PITCH
        bottom = top + FREQ_PITCH
        slots_dia = [(periodo, numero, lista) for (dia, periodo, numero), lista in grade.items() if dia == wd]

        if data in feriados:                       # feriado: sem aula, descrição na assinatura
            descricao = (feriados[data] or "FERIADO").upper().strip()
            for periodo in sorted({s_[0] for s_ in slots_dia}, key="MTN".index):
                x0, x1 = FREQ_SIG[periodo]
                if stringWidth(descricao, "Helvetica-Oblique", 5.5) > (x1 - x0) - 1.6:
                    descricao = "FERIADO"
                p.texto_centro(x0, x1, top, bottom, descricao, tam=6, fonte="Helvetica-Oblique")
            for o in do_mes:
                if o.data == data:
                    usadas.add(id(o))
            continue

        ocs = [o for o in do_mes if o.data == data]
        for periodo, numero, lista in slots_dia:
            cols = FREQ_COLS[periodo]
            texto = "X" if marca == "x" else "/".join(r.rstrip("*") for r in lista)
            for o in ocs:
                if o.periodo in ("", periodo) and (not o.aulas or numero in o.aulas):
                    texto = o.codigo
                    usadas.add(id(o))
            p.texto_centro(cols[numero - 1], cols[numero], top, bottom, texto)

        # reposição/substituição: aula extra, vale mesmo sem aula na grade naquele dia
        for o in ocs:
            if id(o) in usadas or o.codigo not in CODIGOS_EXTRAS or not o.periodo or not o.aulas:
                continue
            cols = FREQ_COLS[o.periodo]
            for numero in o.aulas:
                if 1 <= numero < len(cols):
                    p.texto_centro(cols[numero - 1], cols[numero], top, bottom, o.codigo)
            usadas.add(id(o))

    for o in do_mes:
        if id(o) not in usadas:
            avisos.append(f"{prof.nome}: a ocorrência {o.codigo} de {o.data:%d/%m/%Y} não coincide com "
                          f"nenhuma aula do dia e não aparece no PDF (para reposição/substituição, informe "
                          f"período e aulas).")
    return p.pagina()


# ---------------------------------------------------------------------------
# API PÚBLICA
# ---------------------------------------------------------------------------


def gerar_pdf_ponto(caminho_modelo, professores: List[ProfessorPonto], mes: int, ano: int,
                    unidade: str = "", marca: str = "sigla",
                    feriados: Optional[dict] = None) -> Tuple[bytes, List[str]]:
    """
    Gera um PDF com 2 páginas por professor (as duas do modelo oficial).
    marca: "sigla" (sigla da disciplina em cada aula) ou "x".
    feriados: {date: "descrição"}; nesses dias não há aula e a descrição sai na coluna Assinatura.
    Retorna (bytes_do_pdf, lista_de_avisos).
    """
    if not 1 <= mes <= 12:
        raise ValueError("mês inválido")
    with open(caminho_modelo, "rb") as f:
        modelo_bytes = f.read()

    avisos: List[str] = []
    saida = PdfWriter()
    for prof in professores:
        overlay = _overlay(prof, mes, ano, unidade, (marca or "sigla").lower(), avisos, feriados)
        modelo = PdfReader(io.BytesIO(modelo_bytes))
        modelo.pages[0].merge_page(overlay)
        for pagina in modelo.pages:
            saida.add_page(pagina)
    buf = io.BytesIO()
    saida.write(buf)
    return buf.getvalue(), avisos
