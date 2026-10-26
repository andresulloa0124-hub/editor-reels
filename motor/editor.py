#!/usr/bin/env python3
"""Editor de Reels — motor para Claude web (FFmpeg + whisper.cpp).

Comandos:
  python3 editor.py preparar VIDEO [--sin-cortes] [--modelo small|base]
  python3 editor.py render [--borrador] [--musica AUDIO] [--estilo NOMBRE]
  python3 editor.py cuadro SEGUNDO          (imagen de un momento del Reel, para revisar)
  python3 editor.py buscar "frase"          (en qué segundo se dice una frase)

Todo se guarda en la carpeta de trabajo (por defecto /tmp/editor-reels-trabajo):
  proyecto.json, subtitulos.json, transcripcion.txt, textos.json, broll.json, estilo.json
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
TRABAJO = os.environ.get("EDITOR_TRABAJO", "/tmp/editor-reels-trabajo")
MODELOS = os.environ.get("EDITOR_MODELOS", "/tmp/editor-reels-modelos")
SALIDAS = "/mnt/user-data/outputs" if os.path.isdir("/mnt/user-data") else os.path.join(TRABAJO, "salida")
REPO = os.environ.get("EDITOR_REPO", "andresulloa0124-hub/editor-reels")
URL_MODELO = "https://github.com/{repo}/releases/download/modelos/ggml-{nombre}-q5_1.bin"
FUENTES = os.path.join(AQUI, "fuentes")
FPS = 30
W, H = 1080, 1920


# ------------------------------------------------------------------ utilidades
def paso(texto):
    print(f"\n▶ {texto}", flush=True)


def ruta(nombre):
    return os.path.join(TRABAJO, nombre)


def leer(nombre, defecto=None):
    try:
        with open(ruta(nombre), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return defecto


def guardar(nombre, datos):
    os.makedirs(TRABAJO, exist_ok=True)
    with open(ruta(nombre), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)


def ff(args, mostrar_error=True):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", *args], capture_output=True, text=True)
    if p.returncode != 0 and mostrar_error:
        raise SystemExit(f"❌ FFmpeg falló:\n{p.stderr[-2500:]}")
    return p


def info_video(archivo):
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height:stream_tags=rotate:stream_side_data=rotation",
         "-of", "json", archivo], capture_output=True, text=True)
    d = json.loads(p.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
    ancho, alto = v.get("width", 0), v.get("height", 0)
    if abs(rot) in (90, 270):
        ancho, alto = alto, ancho
    return {
        "duracion": float(d.get("format", {}).get("duration", 0) or 0),
        "ancho": ancho,
        "alto": alto,
        "audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
    }


def estilo_actual(nombre=None):
    if nombre:
        base = os.path.join(AQUI, "estilos", f"{nombre}.json")
        if not os.path.exists(base):
            raise SystemExit(f"❌ No existe el estilo '{nombre}'. Disponibles: {', '.join(estilos_disponibles())}")
        shutil.copy(base, ruta("estilo.json"))
    e = leer("estilo.json")
    if not e:
        os.makedirs(TRABAJO, exist_ok=True)
        shutil.copy(os.path.join(AQUI, "estilos", "santi.json"), ruta("estilo.json"))
        e = leer("estilo.json")
    return e


def estilos_disponibles():
    return sorted(f[:-5] for f in os.listdir(os.path.join(AQUI, "estilos")) if f.endswith(".json"))


# ------------------------------------------------------------------ transcripción
def asegurar_modelo(nombre):
    os.makedirs(MODELOS, exist_ok=True)
    destino = os.path.join(MODELOS, f"ggml-{nombre}-q5_1.bin")
    if os.path.exists(destino) and os.path.getsize(destino) > 10_000_000:
        return destino
    url = URL_MODELO.format(repo=REPO, nombre=nombre)
    paso(f"Descargando el modelo de transcripción '{nombre}' (solo la primera vez en este chat)…")
    t0 = time.time()
    tmp = destino + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "editor-reels"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        bajado, ultimo = 0, -1
        while True:
            bloque = r.read(1 << 20)
            if not bloque:
                break
            f.write(bloque)
            bajado += len(bloque)
            if total:
                pct = int(bajado * 100 / total) // 20 * 20
                if pct != ultimo:
                    ultimo = pct
                    print(f"   {pct}%", flush=True)
    os.replace(tmp, destino)
    print(f"   Listo en {time.time() - t0:.0f}s", flush=True)
    return destino


def asegurar_whisper():
    try:
        import pywhispercpp  # noqa: F401
    except ImportError:
        paso("Instalando el motor de transcripción…")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "pywhispercpp"],
                       check=True)


def transcribir(wav, modelo, idioma):
    """Devuelve palabras con tiempos precisos (alineación DTW de whisper.cpp)."""
    asegurar_whisper()
    import _pywhispercpp as pw
    from pywhispercpp.model import Model

    preset = pw.WHISPER_AHEADS_SMALL if "small" in os.path.basename(modelo) else pw.WHISPER_AHEADS_BASE
    m = Model(modelo, n_threads=os.cpu_count() or 2, redirect_whispercpp_logs_to=None,
              print_progress=False, print_realtime=False,
              context_params={"dtw_token_timestamps": True, "dtw_aheads_preset": preset, "flash_attn": False})
    m.transcribe(wav, language=idioma, token_timestamps=True, suppress_nst=True)
    ctx = m._ctx
    eot = pw.whisper_token_eot(ctx)
    tokens = []
    for i in range(pw.whisper_full_n_segments(ctx)):
        fin_seg = pw.whisper_full_get_segment_t1(ctx, i) / 100
        for k in range(pw.whisper_full_n_tokens(ctx, i)):
            d = pw.whisper_full_get_token_data(ctx, i, k)
            if d.id >= eot:
                continue
            texto = pw.whisper_full_get_token_text(ctx, i, k)
            if isinstance(texto, bytes):
                texto = texto.decode("utf-8", "ignore")
            tokens.append({"texto": texto, "t": max(0, d.t_dtw) / 100, "fin_seg": fin_seg})
    # Unir tokens en palabras (una palabra nueva empieza con espacio)
    palabras = []
    for tk in tokens:
        if tk["texto"].startswith(" ") or not palabras:
            palabras.append({"texto": tk["texto"].strip(), "inicio": tk["t"], "fin_seg": tk["fin_seg"]})
        else:
            palabras[-1]["texto"] += tk["texto"]
    salida = []
    for n, p in enumerate(palabras):
        texto = p["texto"].strip()
        if not texto or re.fullmatch(r"\[.*\]|\(.*\)|[♪♫\s-]+", texto):
            continue
        siguiente = palabras[n + 1]["inicio"] if n + 1 < len(palabras) else p["fin_seg"]
        fin = min(max(siguiente, p["inicio"] + 0.08), p["inicio"] + 0.9)
        salida.append({"texto": texto, "inicio": round(p["inicio"], 3), "fin": round(fin, 3)})
    return salida


# ------------------------------------------------------------------ silencios (umbral adaptado al ruido)
def detectar_voz(wav, duracion, cfg):
    import numpy as np

    with open(wav, "rb") as f:
        datos = f.read()
    # WAV PCM 16-bit mono 16 kHz generado por nosotros: cabecera de 44 bytes
    muestras = np.frombuffer(datos[44:], dtype=np.int16).astype(np.float32) / 32768
    ventana = 320  # 20 ms
    n = len(muestras) // ventana
    if n == 0:
        return [[0, duracion]], None, None
    rms = np.sqrt(np.mean(muestras[: n * ventana].reshape(n, ventana) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    piso = float(np.percentile(db, 10))
    voz_alta = float(np.percentile(db, 90))
    umbral = piso + cfg.get("sobreRuidoDb", 9)
    # Si hay poca diferencia entre ruido y voz, no arriesgar cortes en medio de palabras
    umbral = min(umbral, voz_alta - 12)
    umbral = max(umbral, -55)
    es_voz = db > umbral
    # Suavizado: rellenar huecos menores a 120 ms dentro de la voz
    tramos, inicio = [], None
    for i, v in enumerate(es_voz):
        t = i * 0.02
        if v and inicio is None:
            inicio = t
        elif not v and inicio is not None:
            tramos.append([inicio, t])
            inicio = None
    if inicio is not None:
        tramos.append([inicio, duracion])
    return tramos, piso, umbral


def planear_cortes(tramos_voz, palabras, duracion, cfg):
    minimo = cfg.get("duracionMinima", 0.35)
    margen = cfg.get("margen", 0.1)
    # Las palabras de la transcripción también cuentan como voz (por si alguna es muy suave)
    intervalos = [list(t) for t in tramos_voz]
    # Palabras que no cayeron en ninguna zona de voz (dichas muy suave): se protegen igual
    for p in palabras:
        c = (p["inicio"] + p["fin"]) / 2
        if not any(a - 0.15 <= c <= b + 0.15 for a, b in tramos_voz):
            intervalos.append([p["inicio"], min(p["fin"], p["inicio"] + 0.5)])
    intervalos.sort()
    unidos = []
    for a, b in intervalos:
        if unidos and a - unidos[-1][1] < minimo:
            unidos[-1][1] = max(unidos[-1][1], b)
        else:
            unidos.append([a, b])
    con_margen = [[max(0, a - margen), min(duracion, b + margen)] for a, b in unidos if b - a > 0.12]
    final = []
    for a, b in con_margen:
        if final and a <= final[-1][1] + 0.04:
            final[-1][1] = max(final[-1][1], b)
        else:
            final.append([a, b])
    # Redondear a cuadros para que audio y video queden alineados
    final = [[round(a * FPS) / FPS, round(b * FPS) / FPS] for a, b in final]
    return [t for t in final if t[1] - t[0] >= 3 / FPS] or [[0, duracion]]


def a_salida(t, tramos):
    acumulado = 0.0
    for a, b in tramos:
        if a <= t < b:
            return acumulado + (t - a)
        acumulado += b - a
    return None


# ------------------------------------------------------------------ preparar
def preparar(video, sin_cortes=False, modelo="small"):
    if not os.path.exists(video):
        raise SystemExit(f"❌ No encuentro el video: {video}")
    os.makedirs(TRABAJO, exist_ok=True)
    estilo = estilo_actual()
    info = info_video(video)
    if not info["audio"]:
        raise SystemExit("❌ El video no tiene audio. Esta herramienta necesita que se escuche hablar.")
    print(f"🎬 {os.path.basename(video)} · {info['duracion']:.1f} s · {info['ancho']}x{info['alto']}")
    if min(info["ancho"], info["alto"]) < 900:
        print("⚠️  El video tiene baja resolución (¿pasó por WhatsApp?). Se verá mejor con el archivo original del celular.")
    if info["ancho"] > info["alto"]:
        print("⚠️  El video es horizontal: se recortará al centro para quedar vertical.")

    paso("Extrayendo el audio…")
    wav = ruta("audio-16k.wav")
    ff(["-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])

    paso("Transcribiendo palabra por palabra (es lo que más tarda)…")
    t0 = time.time()
    if os.environ.get("EDITOR_SIN_TRANSCRIBIR"):
        palabras = []
    else:
        archivo_modelo = asegurar_modelo(modelo)
        palabras = transcribir(wav, archivo_modelo, estilo.get("transcripcion", {}).get("idioma", "es"))
    print(f"   {len(palabras)} palabras en {time.time() - t0:.0f}s", flush=True)

    cfg = estilo.get("silencios", {})
    if sin_cortes:
        tramos = [[0, info["duracion"]]]
    else:
        paso("Buscando silencios (adaptado al ruido de fondo)…")
        voz, piso, umbral = detectar_voz(wav, info["duracion"], cfg)
        tramos = planear_cortes(voz, palabras, info["duracion"], cfg)
        if piso is not None:
            print(f"   Ruido de fondo ≈ {piso:.0f} dB · umbral de voz {umbral:.0f} dB")
    duracion_final = sum(b - a for a, b in tramos)
    print(f"   Largo final: {duracion_final:.1f} s (se quitaron {max(0, info['duracion'] - duracion_final):.1f} s en {len(tramos) - 1} cortes)")

    # Palabras al tiempo del Reel ya cortado (si una cae en un corte, se pega al tramo más cercano)
    def cercano(t):
        v = a_salida(t, tramos)
        if v is not None:
            return v
        acumulado = 0.0
        for a, b in tramos:
            if t < a:
                return acumulado
            acumulado += b - a
        return max(0.0, acumulado - 0.05)

    subtitulos = []
    for p in palabras:
        ini = cercano(p["inicio"])
        fin = cercano(max(p["inicio"], p["fin"] - 0.01))
        if fin <= ini:
            fin = ini + min(0.35, max(0.08, p["fin"] - p["inicio"]))
        if subtitulos and ini < subtitulos[-1]["inicio"]:
            ini = subtitulos[-1]["inicio"] + 0.01
        subtitulos.append({"texto": p["texto"], "inicio": round(ini, 3), "fin": round(max(fin, ini + 0.08), 3)})

    # Cortes para el zoom alternado (solo si el tramo anterior duró ≥ 1.2 s)
    cortes, acumulado, ultimo = [], 0.0, 0.0
    for a, b in tramos:
        if acumulado > 0 and acumulado - ultimo >= 1.2:
            cortes.append(round(acumulado, 3))
            ultimo = acumulado
        acumulado += b - a

    guardar("proyecto.json", {
        "video": os.path.abspath(video),
        "nombre": re.sub(r"[^\w-]+", "-", os.path.splitext(os.path.basename(video))[0]).strip("-")[:40] or "reel",
        "duracionOriginal": info["duracion"],
        "duracion": round(duracion_final, 3),
        "tramos": [[round(a, 3), round(b, 3)] for a, b in tramos],
        "cortes": cortes,
    })
    guardar("subtitulos.json", subtitulos)
    guardar("textos.json", [])
    guardar("broll.json", [])

    # Transcripción legible (para que Claude planee títulos y tarjetas)
    lineas, actual = [], None
    for s in subtitulos:
        if not actual or s["inicio"] - actual["fin"] > 0.7 or len(actual["texto"].split()) >= 14:
            if actual:
                lineas.append(actual)
            actual = dict(s)
        else:
            actual["texto"] += " " + s["texto"]
            actual["fin"] = s["fin"]
    if actual:
        lineas.append(actual)
    with open(ruta("transcripcion.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(f"[{l['inicio']:.1f}s – {l['fin']:.1f}s] {l['texto']}" for l in lineas))
    print(f"\n✅ Video preparado. Transcripción en {ruta('transcripcion.txt')}")


# ------------------------------------------------------------------ subtítulos y textos (ASS)
METRICAS = {}


def fuente(nombre, peso):
    global METRICAS
    if not METRICAS:
        with open(os.path.join(FUENTES, "metricas.json")) as f:
            METRICAS = json.load(f)
    disponibles = {k: int(k.split("-")[1]) for k in METRICAS if k.split("-")[0] == nombre}
    if not disponibles:
        disponibles = {k: int(k.split("-")[1]) for k in METRICAS if k.startswith("Poppins-")}
    clave = min(disponibles, key=lambda k: abs(disponibles[k] - peso))
    return clave, METRICAS[clave]


# Letras para variar según lo que se dice: (fuente, peso, multiplicador de tamaño frente al subtítulo)
ACENTOS = {
    "manuscrita": ("Caveat", 700, 2.2),
    "marcador": ("PermanentMarker", 400, 1.2),
    "serif": ("InstrumentSerif", 400, 1.9),
    "serif-italica": ("InstrumentSerifItalic", 400, 1.9),
    "grande": (None, 900, 1.5),
}


def color(hexa, alfa=0):
    hexa = (hexa or "#FFFFFF").lstrip("#")
    r, g, b = hexa[0:2], hexa[2:4], hexa[4:6]
    return f"&H{alfa:02X}{b}{g}{r}".upper()


def tiempo(seg):
    seg = max(0, seg)
    h = int(seg // 3600)
    m = int(seg % 3600 // 60)
    s = seg % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def limpiar(texto):
    return texto.replace("\\", "").replace("{", "(").replace("}", ")")


def armar_bloques(subs, por_bloque):
    bloques, actual = [], []
    for p in subs:
        anterior = actual[-1] if actual else None
        pausa = anterior and p["inicio"] - anterior["fin"] > 0.5
        fin_frase = anterior and re.search(r"[.?!,;:]$", anterior["texto"])
        if len(actual) >= por_bloque or pausa or fin_frase:
            bloques.append(actual)
            actual = []
        actual.append(p)
    if actual:
        bloques.append(actual)
    salida = []
    for i, b in enumerate(bloques):
        ini, fin = b[0]["inicio"], b[-1]["fin"] + 0.6
        if i + 1 < len(bloques):
            fin = min(fin, bloques[i + 1][0]["inicio"])
        salida.append({"inicio": ini, "fin": max(fin, ini + 0.15), "palabras": b})
    return salida


def generar_ass(estilo, subs, textos, ocultos):
    s, ti, se = estilo["subtitulos"], estilo["titulos"], estilo["secciones"]
    f_sub, k_sub = fuente(s["fuente"], s["peso"])
    f_enf, _ = fuente(s.get("fuenteEnfasis", s["fuente"]), s.get("pesoEnfasis", s["peso"]))
    f_tit, k_tit = fuente(ti["fuente"], ti["peso"])
    f_sec, k_sec = fuente(se["fuente"], se["peso"])
    tam_sub = round(s["tamano"] * k_sub)
    borde = s.get("grosorBorde", 0) / 2

    cab = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        (f"Style: Sub,{f_sub},{tam_sub},{color(s['colorTexto'])},{color(s['colorTexto'])},{color(s['fondoCaja'])},{color(s['fondoCaja'])},0,0,0,0,100,100,0,0,3,{s.get('rellenoCaja', 14)},0,5,70,70,0,1"
         if s.get("fondoCaja") else
         f"Style: Sub,{f_sub},{tam_sub},{color(s['colorTexto'])},{color(s['colorTexto'])},{color(s.get('colorBorde', '#000000'))},&H80000000,0,0,0,0,100,100,0,0,1,{borde},0,5,70,70,0,1"),
        f"Style: Tit,{f_tit},{round(ti['tamano'] * k_tit)},{color(ti['color'])},{color(ti['color'])},{color(ti.get('colorBorde', '#000000'))},&H80000000,0,0,0,0,100,100,0,0,1,{ti.get('grosorBorde', 0) / 2},0,5,60,60,0,1",
        f"Style: Sec,{f_sec},{round(se['tamano'] * k_sec)},{color(se['color'])},{color(se['color'])},{color(se.get('colorBorde', '#000000'))},&H80000000,0,0,0,0,100,100,0,0,1,{se.get('grosorBorde', 0) / 2},0,5,60,60,0,1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []

    def evento(ini, fin, estilo_ass, texto, sombra, capa=1):
        if fin - ini < 0.02:
            return
        if sombra:
            # Capa de sombra suave debajo del texto nítido
            ev.append(f"Dialogue: {capa - 1},{tiempo(ini)},{tiempo(fin)},{estilo_ass},,0,0,0,,{{\\1a&HFF&\\3a&HFF&\\bord0\\shad0\\xshad0\\yshad3\\4a&H70&\\blur7\\shad3}}{texto}")
        ev.append(f"Dialogue: {capa},{tiempo(ini)},{tiempo(fin)},{estilo_ass},,0,0,0,,{texto}")

    # --- Subtítulos
    enfasis = [t for t in textos if t.get("tipo") == "enfasis"]

    def es_enfasis(p):
        c = (p["inicio"] + p["fin"]) / 2
        return any(e["inicio"] <= c <= e["fin"] for e in enfasis)

    acentos = [t for t in textos if t.get("tipo") == "acento"]

    def acento_de(p):
        c = (p["inicio"] + p["fin"]) / 2
        return next((a for a in acentos if a["inicio"] <= c <= a["fin"]), None)

    if s.get("activados", True):
        y = round(H * s["posicionVertical"] / 100)
        for b in armar_bloques(subs, max(1, s.get("palabrasPorBloque", 3))):
            if any(o[0] <= b["inicio"] < o[1] for o in ocultos):
                continue
            cortes_tiempo = [b["inicio"]]
            if s.get("estilo") in ("resaltado", "caja"):
                for p in b["palabras"]:
                    cortes_tiempo += [p["inicio"], p["fin"]]
            cortes_tiempo = sorted({round(t, 3) for t in cortes_tiempo + [b["fin"]] if b["inicio"] <= t <= b["fin"]})
            for i in range(len(cortes_tiempo) - 1):
                a, z = cortes_tiempo[i], cortes_tiempo[i + 1]
                piezas = []
                for p in b["palabras"]:
                    txt = limpiar(p["texto"].upper() if s.get("mayusculas") else p["texto"])
                    activa = s.get("estilo") in ("resaltado", "caja") and p["inicio"] <= a < p["fin"]
                    tags = ""
                    ac = acento_de(p)
                    if ac:
                        nombre, peso, mult = ACENTOS.get(ac.get("estilo", "manuscrita"), ACENTOS["manuscrita"])
                        if nombre is None:
                            nombre, peso = s["fuente"], s.get("pesoEnfasis", 800)
                        f_ac, k_ac = fuente(nombre, peso)
                        if ac.get("estilo") in ("manuscrita", "marcador") or ac.get("mayusculas"):
                            txt = txt.upper() if ac.get("mayusculas", ac.get("estilo") == "marcador") else txt
                        tags += f"\\fn{f_ac}\\fs{round(s['tamano'] * mult * k_ac)}"
                        tags += f"\\1c{color(ac.get('color') or s.get('colorAcento') or s.get('colorEnfasis', s['colorTexto']))}"
                        if ac.get("subrayado"):
                            tags += "\\u1"
                    elif es_enfasis(p):
                        tags += f"\\fn{f_enf}\\1c{color(s.get('colorEnfasis', s['colorTexto']))}"
                    if activa:
                        tags += f"\\1c{color(s['colorPalabraActiva'])}"
                    # Al terminar la palabra se vuelve al estilo normal sin usar \\r (que borraría la capa de sombra)
                    volver = f"\\fn{f_sub}\\fs{tam_sub}\\1c{color(s['colorTexto'])}\\u0"
                    # Las letras manuscritas e itálicas se inclinan: un espacio extra evita que se peguen a la siguiente palabra
                    extra = "\\h" if ac else ""
                    piezas.append(f"{{{tags}}}{txt}{{{volver}}}{extra}" if tags else txt)
                anim = ""
                if i == 0 and s.get("animacionEntrada", True):
                    anim = "\\fscx88\\fscy88\\t(0,140,\\fscx100\\fscy100)\\fad(70,0)"
                evento(a, z, "Sub", f"{{\\an5\\pos(540,{y}){anim}}}" + " ".join(piezas),
                       s.get("sombra", True) and not s.get("fondoCaja"))

    # --- Títulos y secciones
    for t in textos:
        if not t.get("texto"):
            continue
        txt = limpiar(t["texto"])
        if t["tipo"] == "titulo" and ti.get("activados", True):
            if ti.get("mayusculas"):
                txt = txt.upper()
            lineas = txt.split("\n")
            factor = min(1, 13 / max(1, max(len(l) for l in lineas)))
            y = H * ti["posicionVertical"] / 100
            alto_linea = ti["tamano"] * factor * 0.98
            tam = f"\\fs{round(ti['tamano'] * k_tit * factor)}" if factor < 1 else ""
            if t.get("estilo") in ACENTOS and ACENTOS[t["estilo"]][0]:
                nombre, peso, mult = ACENTOS[t["estilo"]]
                f_x, k_x = fuente(nombre, peso)
                mult_t = {"serif": 1.3, "serif-italica": 1.3, "manuscrita": 1.35, "marcador": 0.95}.get(t["estilo"], 1)
                tam = f"\\fn{f_x}\\fs{round(ti['tamano'] * k_x * factor * mult_t)}"
                alto_linea *= 0.92 * mult_t
            # Cada línea va en su propio evento para controlar el interlineado (como en el diseño original)
            for n, linea in enumerate(lineas):
                yl = round(y + (n - (len(lineas) - 1) / 2) * alto_linea)
                evento(t["inicio"], t["fin"], "Tit",
                       f"{{\\an5\\q2\\org(540,{round(y)})\\pos(540,{yl}){tam}\\fscx70\\fscy70\\t(0,170,\\fscx100\\fscy100)\\fad(90,120)}}{linea}",
                       ti.get("sombra", True), capa=11)
        elif t["tipo"] == "seccion" and se.get("activados", True):
            if se.get("mayusculas"):
                txt = txt.upper()
            y = round(H * se["posicionVertical"] / 100)
            evento(t["inicio"], t["fin"], "Sec",
                   f"{{\\an5\\move(540,{y - 20},540,{y},0,160)\\fad(150,120)}}{txt}", se.get("sombra", True), capa=21)

    with open(ruta("subtitulos.ass"), "w", encoding="utf-8") as f:
        f.write("\n".join(cab + ev) + "\n")
    return ruta("subtitulos.ass")


# ------------------------------------------------------------------ tarjetas (capturas propias)
def preparar_tarjeta(origen, destino, ancho_px):
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.open(origen).convert("RGBA")
    alto_max = 760
    escala = min(ancho_px / img.width, alto_max / img.height)
    img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.LANCZOS)
    radio, pad = 22, 40
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radio, fill=255)
    lienzo = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle([pad, pad + 14, pad + img.width, pad + img.height + 14], radio, fill=(0, 0, 0, 140))
    sombra = sombra.filter(ImageFilter.GaussianBlur(18))
    lienzo.alpha_composite(sombra)
    fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
    fondo.alpha_composite(img)
    lienzo.paste(fondo, (pad, pad), mascara)
    lienzo.save(destino)
    return lienzo.size


# ------------------------------------------------------------------ capas (tarjetas y refuerzos)
def a_original(t, tramos):
    """Tiempo del Reel → tiempo del video original."""
    acumulado = 0.0
    for a, b in tramos:
        if t < acumulado + (b - a):
            return a + (t - acumulado)
        acumulado += b - a
    return tramos[-1][1] - 0.05


def construir_capas(estilo, textos, broll, proyecto):
    sys.path.insert(0, AQUI)
    import refuerzos

    capas = []
    # Capturas propias (broll.json)
    ancho_t = int(W * estilo.get("tarjetas", {}).get("ancho", 0.74))
    y_centro = H * estilo.get("tarjetas", {}).get("posicionVertical", 70) / 100
    for i, c in enumerate(broll):
        img = c.get("imagen") or c.get("archivo")
        if not img or not os.path.exists(img):
            print(f"⚠️  No encontré la imagen {img}: se omite.")
            continue
        destino = ruta(f"tarjeta-{i:02d}.png")
        w_t, h_t = preparar_tarjeta(img, destino, ancho_t)
        capas.append({"archivo": destino, "x": (W - w_t) // 2, "y": int(y_centro - h_t / 2),
                      "inicio": float(c["inicio"]), "fin": float(c["fin"]), "entrada": "subir"})

    # Refuerzos gráficos (textos.json)
    c = {**refuerzos.DEFECTO, **estilo.get("refuerzos", {})}
    if not c.get("activados", True):
        return capas
    carpeta = ruta("refuerzos")
    os.makedirs(carpeta, exist_ok=True)
    panel = None
    for i, t in enumerate(textos):
        tipo = t.get("tipo")
        if tipo not in ("lista", "checklist", "cita"):
            continue
        t = {**t, "inicio": float(t["inicio"]), "fin": float(t["fin"])}
        if t.get("fondo") and tipo != "cita":
            panel = panel or refuerzos.panel(os.path.join(carpeta, "panel.png"), c)
            capas.append({"archivo": panel, "x": 0, "y": 0, "inicio": t["inicio"], "fin": t["fin"], "entrada": "fade"})
        if tipo == "lista":
            capas += refuerzos.lista(t, carpeta, c, i)
        elif tipo == "checklist":
            capas += refuerzos.checklist(t, carpeta, c, i)
        elif tipo == "cita":
            foto = os.path.join(carpeta, f"foto{i:02d}.jpg")
            momento = t.get("momentoFoto", t["inicio"])
            ff(["-y", "-ss", f"{a_original(momento, proyecto['tramos']):.3f}", "-i", proyecto["video"], "-frames:v", "1",
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}", foto], mostrar_error=False)
            capas += refuerzos.cita(t, carpeta, c, i, foto)
    return capas


# ------------------------------------------------------------------ render
def entre(intervalos, var="t"):
    if not intervalos:
        return "0"
    return "+".join(f"between({var},{a:.3f},{b:.3f})" for a, b in intervalos)


def render(borrador=False, musica=None, estilo_nombre=None, hasta=None):
    proyecto = leer("proyecto.json")
    if not proyecto:
        raise SystemExit("❌ Primero hay que preparar el video (comando: preparar).")
    estilo = estilo_actual(estilo_nombre)
    subs = leer("subtitulos.json", [])
    textos = leer("textos.json", [])
    broll = leer("broll.json", [])
    tramos = proyecto["tramos"]
    dur = proyecto["duracion"]

    capas = construir_capas(estilo, textos, broll, proyecto)
    ass = generar_ass(estilo, subs, textos, [])

    # Zoom alternado por cortes
    zoom_on = estilo.get("zooms", {}).get("activados", True)
    k = estilo.get("zooms", {}).get("intensidad", 1.15)
    zonas_zoom, marcas = [], [0] + proyecto.get("cortes", []) + [dur]
    for i in range(len(marcas) - 1):
        if i % 2 == 1:
            zonas_zoom.append([marcas[i], marcas[i + 1]])
    bn = [[t["inicio"], t["fin"]] for t in textos if t.get("tipo") == "blancoynegro"]

    sel = "+".join(f"between(t,{a:.3f},{b - 0.0005:.3f})" for a, b in tramos)
    zw, zh = (int(W * k) // 2 * 2, int(H * k) // 2 * 2)
    g = [
        f"[0:v]fps={FPS},select='{sel}',setpts=N/{FPS}/TB,"
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=bicubic,crop={W}:{H},setsar=1,split=2[base][paraz]",
        f"[paraz]scale={zw}:{zh}:flags=bicubic,crop={W}:{H}:(iw-{W})/2:(ih-{H})*0.35[zoom]",
        f"[base][zoom]overlay=enable='{entre(zonas_zoom) if zoom_on else '0'}'[v0]",
    ]
    ultimo = "v0"
    if bn:
        g.append(f"[{ultimo}]hue=s=0:enable='{entre(bn)}',eq=contrast=1.08:enable='{entre(bn)}'[vbn]")
        ultimo = "vbn"
    entradas = ["-i", proyecto["video"]]
    idx = 1
    for j, cp in enumerate(capas):
        # Cada imagen se decodifica una sola vez y se repite en memoria (más rápido que -loop 1)
        entradas += ["-framerate", str(FPS), "-i", cp["archivo"]]
        ini, fin = cp["inicio"], cp["fin"]
        d = min(0.18, (fin - ini) / 3)
        cadena = f"[{idx}:v]format=rgba,loop=loop=-1:size=1:start=0,setpts=N/{FPS}/TB,trim=duration={dur:.3f}"
        if cp.get("entrada", "subir") != "corte":
            cadena += f",fade=t=in:st={ini:.3f}:d={d:.3f}:alpha=1"
        if cp.get("salida", True):
            cadena += f",fade=t=out:st={fin - d:.3f}:d={d:.3f}:alpha=1"
        g.append(cadena + f"[c{j}]")
        y = str(cp["y"])
        if cp.get("entrada", "subir") == "subir":
            y = f"{cp['y']}+46*max(0,1-(t-{ini:.3f})/0.22)"
        g.append(f"[{ultimo}][c{j}]overlay=x={cp['x']}:y='{y}':eval=frame:enable='between(t,{ini:.3f},{fin:.3f})':eof_action=pass[vc{j}]")
        ultimo = f"vc{j}"
        idx += 1
    g.append(f"[{ultimo}]subtitles=filename={ass}:fontsdir={FUENTES},format=yuv420p[vout]")

    asel = "+".join(f"between(t,{a:.3f},{b - 0.0005:.3f})" for a, b in tramos)
    g.append(f"[0:a]aselect='{asel}',asetpts=N/SR/TB,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[voz]")
    if musica:
        if not os.path.exists(musica):
            raise SystemExit(f"❌ No encuentro la música: {musica}")
        entradas += ["-stream_loop", "-1", "-i", musica]
        vol = estilo.get("musica", {}).get("volumen", 0.08)
        g.append(f"[{idx}:a]volume={vol},aresample=48000,afade=t=out:st={max(0, dur - 1.5):.3f}:d=1.5[mus]")
        g.append("[voz][mus]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        g.append("[voz]anull[aout]")

    script = ruta("filtro.txt")
    with open(script, "w", encoding="utf-8") as f:
        f.write(";\n".join(g))

    os.makedirs(SALIDAS, exist_ok=True)
    sufijo = "-borrador" if borrador else "-editado"
    salida = os.path.join(SALIDAS, f"{proyecto['nombre']}{sufijo}.mp4")
    limite = ["-t", f"{min(hasta, dur) if hasta else dur:.3f}"]
    args = ["-y", *entradas, "-filter_complex_script", script, "-map", "[vout]", "-map", "[aout]", "-r", str(FPS), *limite]
    if borrador:
        args += ["-s", "540x960", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-c:a", "aac", "-b:a", "128k"]
    else:
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k"]
    paso("Renderizando el Reel…" if not borrador else "Renderizando un borrador rápido…")
    t0 = time.time()
    ff([*args, "-movflags", "+faststart", salida])
    print(f"\n✅ Listo en {time.time() - t0:.0f}s: {salida}")
    return salida


def cuadro(segundo):
    """Imagen de un momento del Reel (rápido), para revisar textos y tarjetas sin renderizar todo."""
    salida = render(borrador=True, hasta=min(segundo + 0.1, leer("proyecto.json")["duracion"]))
    png = os.path.join(SALIDAS, f"cuadro-{segundo:.1f}s.png")
    ff(["-y", "-sseof", "-0.05", "-i", salida, "-frames:v", "1", png])
    os.remove(salida)
    print(f"🖼  {png}")


def buscar(frase):
    """Muestra en qué segundo del Reel se dice una frase (para planear refuerzos con tiempos exactos)."""
    import unicodedata

    def norm(x):
        x = unicodedata.normalize("NFD", x.lower())
        return "".join(ch for ch in x if ch.isalnum() and unicodedata.category(ch) != "Mn")

    subs = leer("subtitulos.json", [])
    objetivo = [norm(p) for p in frase.split() if norm(p)]
    hallados = 0
    for i in range(len(subs) - len(objetivo) + 1):
        if all(norm(subs[i + k]["texto"]).startswith(objetivo[k]) for k in range(len(objetivo))):
            fin = subs[i + len(objetivo) - 1]["fin"]
            print(f"{subs[i]['inicio']:.2f} – {fin:.2f}  " + " ".join(s["texto"] for s in subs[i:i + len(objetivo) + 4]))
            hallados += 1
    if not hallados:
        print(f"No encontré «{frase}». Prueba con menos palabras o revisa transcripcion.txt.")


# ------------------------------------------------------------------ CLI
if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "ayuda"):
        print(__doc__)
        print("Estilos:", ", ".join(estilos_disponibles()))
        sys.exit(0)
    cmd = a[0]

    def opcion(nombre, defecto=None):
        return a[a.index(nombre) + 1] if nombre in a and a.index(nombre) + 1 < len(a) else defecto

    if cmd == "preparar":
        if len(a) < 2:
            raise SystemExit("Uso: editor.py preparar VIDEO")
        preparar(a[1], sin_cortes="--sin-cortes" in a, modelo=opcion("--modelo", "small"))
    elif cmd == "render":
        render(borrador="--borrador" in a, musica=opcion("--musica"), estilo_nombre=opcion("--estilo"))
    elif cmd == "cuadro":
        cuadro(float(a[1]))
    elif cmd == "buscar":
        buscar(" ".join(a[1:]))
    elif cmd == "estilo":
        estilo_actual(a[1] if len(a) > 1 else None)
        print(f"✅ Estilo activo guardado en {ruta('estilo.json')}")
    else:
        raise SystemExit(f"Comando desconocido: {cmd}")
