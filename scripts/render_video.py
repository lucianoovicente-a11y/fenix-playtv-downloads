#!/usr/bin/env python3
# Gera o vídeo diário "AGENDA EM CAMPO" (jogos do dia) para o Pastor Luciano.
# Modelo editável: tudo que é marca/cor/texto está no CONFIG abaixo.
# Logo e fundo são puxados AO VIVO do painel (central_jogos2/fzstore), então
# trocar Logo/Fundo nas telas do painel muda o vídeo do dia seguinte.
import json, os, sys, math, argparse, urllib.request, datetime, re, unicodedata
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ================= MODELO (editável) =================
CONFIG = {
    "brand": "FÊNIX PLAY TV",          # topo esquerdo
    "titulo_a": "AGENDA",              # linha 1 (branco)
    "titulo_b": "EM CAMPO.",           # linha 2 (accent)
    "data_sufixo": " - HORÁRIO DE BRASÍLIA",
    "whatsapp": "WHATSAPP 21971877485",  # rodapé
    "rodape_credito": "DADOS E ESCUDOS: ESPN - HORÁRIO DE BRASÍLIA",
    "accent": (181, 230, 29),          # verde-lima (estilo referência)
    "accent_texto": (10, 14, 16),
    "rodape_cor": (10, 18, 28),
    "leagues": ["bra.1", "bra.2", "bra.3", "bra.copa_do_brazil",
                "conmebol.libertadores", "conmebol.sudamericana"],
    "liga_nome": {                     # nome PT em caixa alta no vídeo
        "Brazilian Serie A": "BRASILEIRÃO SÉRIE A",
        "Brazilian Serie B": "BRASILEIRÃO SÉRIE B",
        "Brazilian Serie C": "BRASILEIRÃO SÉRIE C",
        "Brazilian Copa do Brasil": "COPA DO BRASIL",
        "Copa Libertadores": "COPA LIBERTADORES",
        "Copa Sudamericana": "COPA SUL-AMERICANA",
    },
    # canal de TV por liga (texto "veja no canal tal"; mesmo mapa do painel Jogos do dia)
    "liga_canal": {
        "bra.1": "PREMIERE",
        "bra.2": "ESPN 1",
        "bra.3": "ESPN 2",
        "bra.copa_do_brazil": "SPORTV 1",
        "conmebol.libertadores": "ESPN 1",
        "conmebol.sudamericana": "ESPN 2",
    },
    "seg_pre": 1.2,     # página sem o selo de hora (s)
    "seg_full": 4.3,    # página completa (s)
    "fps": 30,
}

# Temas visuais (modelos de referência; tema ativo escolhido pelo Pastor via Instinct: usar o existente e manter trocável)
TEMAS = {
    "agenda": {  # estádio + faixas, acento verde-lima
        "titulo_a": "AGENDA", "titulo_b": "EM CAMPO.",
        "accent": (181, 230, 29), "fundo": "foto",
        "escudo_fill": (245, 247, 250, 255), "escudo_ring": (0, 0, 0, 60),
    },
    "noite": {   # fundo escuro + anéis dourados, acento dourado
        "titulo_a": "NOITE DE", "titulo_b": "FUTEBOL",
        "accent": (212, 175, 106), "fundo": "aneis",
        "escudo_fill": (0, 0, 0, 0), "escudo_ring": (212, 175, 106, 255),
    },
}
TEMA_ATIVO = "agenda"  # --tema sobrescreve
LOGO_URL = "https://streamflow.totalmente.online/central_jogos2/fzstore/logo/684c5bc6d288e.png"
FUNDO_URL = "https://streamflow.totalmente.online/central_jogos2/fzstore/Img/684c539768afa.jpg"
BASE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(BASE, "assets"); FR = os.path.join(BASE, "frames"); CR = os.path.join(BASE, "crest")
W, H = 2160, 3840  # render 4x da referência 540x960; saída 1080x1920
K = 4              # escala vs referência 540x960

def k(v): return int(round(v * K))

def fetch(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            f.write(r.read())
        return True
    except Exception as e:
        print("fetch falhou", url, e); return False

def font(name, size):
    return ImageFont.truetype(os.path.join(A, name), size)

def text_fit(draw, txt, fnt, maxw):
    while draw.textlength(txt, font=fnt) > maxw and fnt.size > 20:
        fnt = ImageFont.truetype(fnt.path, fnt.size - 4)
    return fnt

def jogos_do_dia(data_alvo):
    """ESPN scoreboard público, mesma fonte do painel. Filtra pela data em BRT."""
    brt = ZoneInfo("America/Sao_Paulo")
    jogos = {}
    for lg in CONFIG["leagues"]:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{lg}/scoreboard?dates={data_alvo:%Y%m%d}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            d = json.load(urllib.request.urlopen(req, timeout=25))
        except Exception as e:
            print("ESPN falhou", lg, e); continue
        lname = (d.get("leagues") or [{}])[0].get("name", "")
        for e in d.get("events", []):
            dt = datetime.datetime.fromisoformat(e["date"].replace("Z", "+00:00")).astimezone(brt)
            if dt.date() != data_alvo:  # só jogos do dia em Brasília
                continue
            comp = e["competitions"][0]
            home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
            away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
            key = (home["team"]["displayName"], away["team"]["displayName"], dt)
            jogos[key] = {
                "time1": home["team"]["displayName"], "time2": away["team"]["displayName"],
                "logo1": home["team"].get("logo"), "logo2": away["team"].get("logo"),
                "horario": dt.strftime("%H:%M"),
                "liga": CONFIG["liga_nome"].get(lname, lname.upper()),
                "canal": CONFIG["liga_canal"].get(lg, ""),
            }
    return [jogos[k] for k in sorted(jogos, key=lambda k: k[2])]

CACHE_URL = "https://streamflow.totalmente.online/central_jogos2/api/cache_jogos_admin.json"

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower())

def canais_verificados(data_alvo):
    """Canais confirmados pelo Pastor no cache do painel, por jogo (times+data).
    Chave: (time1_norm, time2_norm) -> lista de nomes de canal."""
    out = {}
    try:
        req = urllib.request.Request(CACHE_URL, headers={"User-Agent": "Mozilla/5.0"})
        d = json.load(urllib.request.urlopen(req, timeout=25))
    except Exception as e:
        print("cache do painel falhou", e); return out
    jogos = d if isinstance(d, list) else d.get("jogos", [])
    for j in jogos:
        dr = str(j.get("data_real") or j.get("data_jogo") or "")[:10]
        if dr != data_alvo.isoformat():
            continue
        canais = [c.get("nome", "").strip() for c in (j.get("canais") or []) if c.get("nome")]
        if canais:
            out[(_norm(str(j.get("time1", ""))), _norm(str(j.get("time2", ""))))] = canais
    return out

def expandir_linhas(jogos, verif):
    """Uma linha por jogo x canal. Verificado (cache) tem prioridade; sem dado,
    entra o canal do mapa por liga marcado como padrão a confirmar."""
    linhas = []
    for j in jogos:
        k1, k2 = _norm(j["time1"]), _norm(j["time2"])
        canais = None
        for (a, b), cs in verif.items():
            if a and b and ((a in k1 or k1 in a) and (b in k2 or k2 in b) or
                            (a in k2 or k2 in a) and (b in k1 or k1 in b)):
                canais = cs; break
        if canais:
            for c in canais:
                linhas.append({**j, "canal": c.upper(), "canal_verificado": True})
        else:
            linhas.append({**j, "canal_verificado": False})
    return linhas

def crest_circle(url, diam, tema):
    """Escudo em círculo (branco no tema agenda; aro dourado no tema noite)."""
    t = TEMAS[tema]
    out = Image.new("RGBA", (diam, diam), (0, 0, 0, 0))
    dd = ImageDraw.Draw(out)
    if t["escudo_fill"][3]:
        dd.ellipse([0, 0, diam - 1, diam - 1], fill=t["escudo_fill"])
    dd.ellipse([0, 0, diam - 1, diam - 1], outline=t["escudo_ring"], width=4)
    if url:
        fn = os.path.join(CR, url.rstrip("/").split("/")[-1])
        if not os.path.exists(fn): fetch(url, fn)
        try:
            c = Image.open(fn).convert("RGBA")
            m = int(diam * 0.16)
            c.thumbnail((diam - 2 * m, diam - 2 * m), Image.LANCZOS)
            out.alpha_composite(c, ((diam - c.width) // 2, (diam - c.height) // 2))
        except Exception as e:
            print("crest falhou", url, e)
    return out

def fundo_base(tema):
    if TEMAS[tema]["fundo"] == "aneis":
        f = Image.new("RGBA", (W, H), (10, 14, 22, 255))
        dd = ImageDraw.Draw(f)
        acc = TEMAS[tema]["accent"]
        cx, cy = W // 2, k(270)
        for r in range(k(90), k(560), k(48)):
            dd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=acc + (38,), width=3)
        return f
    f = Image.open(os.path.join(A, "fundo.jpg")).convert("RGB")
    # cover 2160x3840
    r = max(W / f.width, H / f.height)
    f = f.resize((int(f.width * r) + 1, int(f.height * r) + 1), Image.LANCZOS)
    x, y = (f.width - W) // 2, (f.height - H) // 2
    f = f.crop((x, y, x + W, y + H))
    # escurecer + vinheta
    f = Image.blend(f, Image.new("RGB", f.size, (4, 8, 12)), 0.55)
    # faixas diagonais (estilo referência)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(lay)
    for i in range(-4, 10):
        x0 = i * 560
        dd.polygon([(x0, -200), (x0 + 260, -200), (x0 + 260 - 1400, H + 200), (x0 - 1400, H + 200)],
                   fill=(8, 20, 12, 110))
    lay = lay.filter(ImageFilter.GaussianBlur(6))
    f = Image.alpha_composite(f.convert("RGBA"), lay)
    return f

def pagina(jogo, idx, total, data_alvo, completo=True, tema="agenda"):
    # coordenadas no espaço da referência 540x960, escaladas por K
    img = fundo_base(tema); dd = ImageDraw.Draw(img)
    acc = TEMAS[tema]["accent"]
    # marca topo
    dd.text((k(24), k(24)), CONFIG["brand"], font=font("BarlowCondensed-Bold.ttf", k(24)), fill=(255, 255, 255, 220))
    # título com medição real dos glifos (sem colisão)
    f_t = font("Anton-Regular.ttf", k(62))
    y = k(88)
    dd.text((k(52), y), TEMAS[tema]["titulo_a"], font=f_t, fill=(255, 255, 255))
    bb = dd.textbbox((k(52), y), TEMAS[tema]["titulo_a"], font=f_t)
    y = bb[3] + k(4)
    dd.text((k(52), y), TEMAS[tema]["titulo_b"], font=f_t, fill=acc)
    bb = dd.textbbox((k(52), y), TEMAS[tema]["titulo_b"], font=f_t)
    y = bb[3] + k(14)
    f_d = font("BarlowCondensed-Medium.ttf", k(13))
    dd.text((k(54), y), data_alvo.strftime("%d/%m/%Y") + CONFIG["data_sufixo"], font=f_d, fill=(230, 235, 240))
    bb = dd.textbbox((k(54), y), "Ag", font=f_d)
    crest_top = bb[3] + k(28)
    if jogo:
        # escudos + X
        diam = k(110)
        c1 = crest_circle(jogo["logo1"], diam, tema); c2 = crest_circle(jogo["logo2"], diam, tema)
        c1x, c2x, cy = k(160), k(270), crest_top
        img.alpha_composite(c1, (c1x, cy))
        img.alpha_composite(c2, (c2x, cy))
        f_x = font("Anton-Regular.ttf", k(52))
        xx = (c1x + diam + c2x) // 2
        dd.text((xx - dd.textlength("×", font=f_x) / 2, cy + diam // 2 - k(24)), "×", font=f_x, fill=acc)
        # nomes
        f_n = font("BarlowCondensed-Medium.ttf", k(23))
        names_bottom = cy + diam + k(30)
        for nome, xc in ((jogo["time1"], c1x + diam // 2), (jogo["time2"], c2x + diam // 2)):
            fn = text_fit(dd, nome, f_n, k(200))
            ny = cy + diam + k(30)
            dd.text((xc - dd.textlength(nome, font=fn) / 2, ny), nome, font=fn, fill=(255, 255, 255))
            names_bottom = max(names_bottom, dd.textbbox((0, ny), nome, font=fn)[3])
        if completo:
            # selo de hora
            bw, bh = k(170), k(52)
            bx, by = (W - bw) // 2, names_bottom + k(26)
            dd.rounded_rectangle([bx, by, bx + bw, by + bh], radius=k(12), fill=acc)
            f_h = font("Anton-Regular.ttf", k(34))
            hh = jogo["horario"]
            dd.text((W / 2 - dd.textlength(hh, font=f_h) / 2, by + k(6)), hh, font=f_h, fill=CONFIG["accent_texto"])
            f_l = font("BarlowCondensed-Medium.ttf", k(14))
            dd.text((W / 2 - dd.textlength(jogo["liga"], font=f_l) / 2, by + bh + k(14)), jogo["liga"], font=f_l, fill=(210, 218, 226))
            # "veja no canal tal, no horário tal" (pedido do Pastor 11/11: texto, não áudio)
            if jogo.get("canal"):
                vt = f"VEJA NO CANAL {jogo['canal']} - {hh}"
                if not jogo.get("canal_verificado", True):
                    vt += " (PADRÃO, A CONFIRMAR)"
                f_v = text_fit(dd, vt, font("BarlowCondensed-Bold.ttf", k(17)), W - k(60))
                dd.text((W / 2 - dd.textlength(vt, font=f_v) / 2, by + bh + k(34)), vt, font=f_v, fill=acc)
        # contador de página
        f_p = font("BarlowCondensed-Bold.ttf", k(14))
        pg = f"{idx:02d}/{total:02d}"
        dd.text((k(66), k(518)), pg, font=f_p, fill=acc)
    # rodapé
    dd.rectangle([0, k(888), W, H], fill=CONFIG["rodape_cor"])
    f_w = font("Anton-Regular.ttf", k(20))
    wt = CONFIG["whatsapp"]
    dd.text((W / 2 - dd.textlength(wt, font=f_w) / 2, k(898)), wt, font=f_w, fill=(255, 255, 255))
    f_c = font("BarlowCondensed-Medium.ttf", k(9))
    ct = CONFIG["rodape_credito"]
    dd.text((W / 2 - dd.textlength(ct, font=f_c) / 2, k(933)), ct, font=f_c, fill=(150, 160, 172))
    return img

FINAL_LINHAS = [
    "QUER ASSISTIR AO VIVO?",
    "NA CATEGORIA JOGOS DE HOJE",
    "ESCOLHA O CANAL DO JOGO DO SEU TIME.",
]
FINAL_AVISO = [
    "O CANAL SÓ ABRE 15 MIN ANTES DO HORÁRIO.",
    "CLICOU ANTES? VOLTE 15 MIN ANTES DO JOGO.",
]
FINAL_MUSICA_CRED = "MÚSICA: FULL ON - KEVIN MACLEOD (INCOMPETECH.COM) - CC BY 3.0"

def pagina_final(data_alvo, tema="agenda"):
    """Quadro final parado (5s): orienta a clicar na categoria dos canais-jogo."""
    img = fundo_base(tema); dd = ImageDraw.Draw(img)
    acc = TEMAS[tema]["accent"]
    dd.text((k(24), k(24)), CONFIG["brand"], font=font("BarlowCondensed-Bold.ttf", k(24)), fill=(255, 255, 255, 220))
    y = k(300)
    for i, ln in enumerate(FINAL_LINHAS):
        f_l = text_fit(dd, ln, font("Anton-Regular.ttf", k(40)), W - k(70))
        cor = acc if i == 1 else (255, 255, 255)
        dd.text((W / 2 - dd.textlength(ln, font=f_l) / 2, y), ln, font=f_l, fill=cor)
        y = dd.textbbox((0, y), ln, font=f_l)[3] + k(18)
    y += k(30)
    for ln in FINAL_AVISO:
        f_l = text_fit(dd, ln, font("BarlowCondensed-Bold.ttf", k(20)), W - k(70))
        dd.text((W / 2 - dd.textlength(ln, font=f_l) / 2, y), ln, font=f_l, fill=(235, 240, 245))
        y = dd.textbbox((0, y), ln, font=f_l)[3] + k(12)
    # rodapé
    dd.rectangle([0, k(888), W, H], fill=CONFIG["rodape_cor"])
    f_w = font("Anton-Regular.ttf", k(20))
    wt = CONFIG["whatsapp"]
    dd.text((W / 2 - dd.textlength(wt, font=f_w) / 2, k(898)), wt, font=f_w, fill=(255, 255, 255))
    f_c = font("BarlowCondensed-Medium.ttf", k(9))
    dd.text((W / 2 - dd.textlength(FINAL_MUSICA_CRED, font=f_c) / 2, k(927)), FINAL_MUSICA_CRED, font=f_c, fill=(150, 160, 172))
    ct = CONFIG["rodape_credito"]
    dd.text((W / 2 - dd.textlength(ct, font=f_c) / 2, k(941)), ct, font=f_c, fill=(150, 160, 172))
    return img

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="YYYY-MM-DD (data em Brasília)")
    ap.add_argument("--out", default=os.path.join(BASE, "out"))
    ap.add_argument("--tema", default=TEMA_ATIVO, choices=list(TEMAS))
    args = ap.parse_args()
    data_alvo = datetime.date.fromisoformat(args.date)
    os.makedirs(FR, exist_ok=True); os.makedirs(CR, exist_ok=True); os.makedirs(args.out, exist_ok=True)
    # assets ao vivo do painel (fallback: cópia local)
    fetch(LOGO_URL, os.path.join(A, "fenix_logo.png"))
    fetch(FUNDO_URL, os.path.join(A, "fundo.jpg"))
    jogos = expandir_linhas(jogos_do_dia(data_alvo), canais_verificados(data_alvo))
    print(f"{len(jogos)} linhas (jogo x canal) em {data_alvo:%d/%m/%Y} (BRT)")
    for j in jogos: print("  ", j["horario"], j["time1"], "x", j["time2"], "-", j.get("canal") or j["liga"], "" if j.get("canal_verificado") else "(padrão, a confirmar)")
    manifest = []
    if not jogos:
        # sem jogos: capa sem escudos + quadro final (o canal nunca fica parado)
        print("SEM JOGOS - renderiza capa generica")
        pre = pagina(None, 1, 1, data_alvo, completo=False, tema=args.tema)
        full = pagina(None, 1, 1, data_alvo, completo=True, tema=args.tema)
        p1 = os.path.join(FR, "p01_pre.png"); p2 = os.path.join(FR, "p01_full.png")
        pre.convert("RGB").save(p1); full.convert("RGB").save(p2)
        manifest += [(p1, CONFIG["seg_pre"]), (p2, CONFIG["seg_full"])]
    for i, j in enumerate(jogos, 1):
        pre = pagina(j, i, len(jogos), data_alvo, completo=False, tema=args.tema)
        full = pagina(j, i, len(jogos), data_alvo, completo=True, tema=args.tema)
        p1 = os.path.join(FR, f"p{i:02d}_pre.png"); p2 = os.path.join(FR, f"p{i:02d}_full.png")
        pre.convert("RGB").save(p1); full.convert("RGB").save(p2)
        manifest += [(p1, CONFIG["seg_pre"]), (p2, CONFIG["seg_full"])]
    # quadro final parado (pedido do Pastor 11/11: 5s com as orientações)
    pf = pagina_final(data_alvo, tema=args.tema)
    pfin = os.path.join(FR, "p99_final.png")
    pf.convert("RGB").save(pfin)
    manifest += [(pfin, 5.0)]
    with open(os.path.join(FR, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    print("frames:", len(manifest))

if __name__ == "__main__":
    main()
