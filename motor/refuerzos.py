"""Refuerzos gráficos para el Reel: tarjetas de lista, checklist, cita tipo foto y panel de fondo.

Cada función dibuja PNG transparentes con Pillow y devuelve "capas" que editor.py superpone con FFmpeg:
  {"archivo", "x", "y", "inicio", "fin", "entrada": "subir"|"fade", "salida": True/False}
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "fuentes")

DEFECTO = {
    "activados": True,
    "fuente": "Montserrat-800",
    "fuenteTitulo": "Montserrat-900",
    "colorTarjeta": "#EEE8F2",
    "colorBorde": "#5E4B7A",
    "colorBase": "#B8A6CC",
    "colorTexto": "#2B2233",
    "colorResaltado": "#6A5180",
    "colorTextoResaltado": "#FFFFFF",
    "colorPanel": "#173F3E",
    "colorPapel": "#F4F0E6",
}


def _rgb(hexa, alfa=255):
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i:i + 2], 16) for i in (0, 2, 4)) + (alfa,)


def _fuente(nombre, tam):
    ruta = os.path.join(FUENTES, f"{nombre}.ttf")
    if not os.path.exists(ruta):
        ruta = os.path.join(FUENTES, "Montserrat-800.ttf")
    return ImageFont.truetype(ruta, tam)


def _partir(texto, fuente, ancho_max, draw):
    """Parte el texto en líneas que quepan en ancho_max."""
    palabras, lineas, actual = texto.split(), [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if draw.textlength(prueba, font=fuente) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def _caja_3d(ancho, alto, c, radio=26, borde=5, base=10, relleno=None):
    """Tarjeta con borde y "base" desplazada abajo (efecto botón), como en las referencias."""
    img = Image.new("RGBA", (ancho, alto + base), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, base, ancho - 1, alto + base - 1], radio, fill=_rgb(c["colorBase"]))
    d.rounded_rectangle([0, 0, ancho - 1, alto - 1], radio, fill=_rgb(relleno or c["colorTarjeta"]),
                        outline=_rgb(c["colorBorde"]), width=borde)
    return img


def _con_sombra(img, radio=22, opacidad=110, desplazamiento=16):
    pad = 40
    lienzo = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
    sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    alfa = img.split()[3].point(lambda v: opacidad if v > 0 else 0)
    sombra.paste((0, 0, 0, 255), (pad, pad + desplazamiento), alfa)
    sombra = sombra.filter(ImageFilter.GaussianBlur(radio))
    lienzo.alpha_composite(sombra)
    lienzo.alpha_composite(img, (pad, pad))
    return lienzo, pad


# ------------------------------------------------------------------ panel de fondo (cuadrícula)
def panel(destino, c):
    img = Image.new("RGBA", (W, H), _rgb(c["colorPanel"]))
    d = ImageDraw.Draw(img)
    linea = tuple(min(255, v + 16) for v in _rgb(c["colorPanel"])[:3]) + (255,)
    for x in range(0, W, 54):
        d.line([(x, 0), (x, H)], fill=linea, width=2)
    for y in range(0, H, 54):
        d.line([(0, y), (W, y)], fill=linea, width=2)
    # Viñeta suave abajo
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(max(0, (y - H * 0.6) / (H * 0.4)) * 120))
    oscuro = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    oscuro.putalpha(grad.resize((W, H)))
    img.alpha_composite(oscuro)
    img.save(destino)
    return destino


# ------------------------------------------------------------------ lista de opciones (grid de tarjetas)
def lista(item, carpeta, c, idx):
    items = [i for i in item.get("items", []) if i.get("texto")]
    if not items:
        return []
    n = len(items)
    columnas = item.get("columnas") or (2 if n >= 4 or all(len(i["texto"]) <= 14 for i in items) and n > 1 else 1)
    columnas = max(1, min(3, int(columnas)))
    margen, hueco = 70, 34
    ancho = int((W - 2 * margen - (columnas - 1) * hueco) / columnas)
    if columnas == 1:
        ancho = min(ancho, 820)
    tam = 58 if columnas == 2 else (46 if columnas == 3 else 60)
    f = _fuente(c["fuente"], tam)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    bloques = [_partir(i["texto"], f, ancho - 60, tmp) for i in items]
    alto = max(180, max(len(b) for b in bloques) * int(tam * 1.18) + 80)
    filas = (n + columnas - 1) // columnas
    alto_total = filas * (alto + 10) + (filas - 1) * hueco
    centro = H * (0.40 if item.get("fondo") else 0.74)
    y0 = int(centro - alto_total / 2)
    capas = []
    for k, (it, lineas) in enumerate(zip(items, bloques)):
        img = _caja_3d(ancho, alto, c)
        d = ImageDraw.Draw(img)
        alto_txt = len(lineas) * int(tam * 1.18)
        y = (alto - alto_txt) / 2 - tam * 0.08
        for linea in lineas:
            d.text((ancho / 2, y), linea, font=f, fill=_rgb(c["colorTexto"]), anchor="ma")
            y += int(tam * 1.18)
        img, pad = _con_sombra(img, radio=14, opacidad=90, desplazamiento=10)
        archivo = os.path.join(carpeta, f"lista{idx:02d}-{k}.png")
        img.save(archivo)
        fila, col = divmod(k, columnas)
        # La última fila incompleta se centra
        en_fila = min(columnas, n - fila * columnas)
        x_ini = (W - (en_fila * ancho + (en_fila - 1) * hueco)) / 2
        x = int(x_ini + col * (ancho + hueco)) - pad
        y = y0 + fila * (alto + 10 + hueco) - pad
        aparece = float(it.get("aparece", item["inicio"]))
        aparece = min(max(aparece, item["inicio"]), item["fin"] - 0.3)
        capas.append({"archivo": archivo, "x": x, "y": y, "inicio": aparece, "fin": item["fin"], "entrada": "subir"})
    return capas


# ------------------------------------------------------------------ checklist / encuesta
def checklist(item, carpeta, c, idx):
    items = [i for i in item.get("items", []) if i.get("texto")]
    if not items:
        return []
    ancho = 780
    f_tit = _fuente(c["fuenteTitulo"], 68)
    f_it = _fuente(c["fuente"], 54)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    titulo = item.get("titulo", "")
    lineas_tit = _partir(titulo, f_tit, ancho - 80, tmp) if titulo else []
    alto_tit = len(lineas_tit) * 80 + (40 if titulo else 0)
    alto_fila = 104
    alto = 34 + alto_tit + len(items) * alto_fila + 24
    centro = H * (0.33 if item.get("fondo") else 0.72)
    y_pos = int(centro - alto / 2)
    capas = []
    tiempos = [min(max(float(i.get("aparece", item["inicio"])), item["inicio"]), item["fin"] - 0.2) for i in items]
    for k in range(len(items)):
        img = _caja_3d(ancho, alto, {**c, "colorBorde": c.get("colorBordeChecklist", "#CDB8E8"),
                                     "colorBase": c.get("colorBaseChecklist", "#CDB8E8"), "colorTarjeta": "#FBFAFC"},
                       radio=34, borde=6, base=14)
        d = ImageDraw.Draw(img)
        y = 34
        for linea in lineas_tit:
            d.text((44, y), linea, font=f_tit, fill=_rgb(c["colorTexto"]))
            y += 80
        if titulo:
            y += 16
            d.line([(40, y), (ancho - 40, y)], fill=_rgb("#E6DCEF"), width=3)
            y += 12
        for j, it in enumerate(items[: k + 1]):
            activo = j == k and item.get("resaltar", True)
            if activo:
                d.rounded_rectangle([14, y + 4, ancho - 14, y + alto_fila - 6], 22, fill=_rgb(c["colorResaltado"]))
            color_txt = _rgb(c["colorTextoResaltado"] if activo else c["colorTexto"])
            cy = y + alto_fila / 2
            d.ellipse([44, cy - 19, 82, cy + 19], outline=_rgb("#FFFFFF" if activo else "#9A90A3"), width=4)
            d.text((106, cy), it["texto"], font=f_it, fill=color_txt, anchor="lm")
            if j < len(items) - 1 and not activo and j + 1 != k:
                d.line([(40, y + alto_fila), (ancho - 40, y + alto_fila)], fill=_rgb("#EDE6F3"), width=3)
            y += alto_fila
        img, pad = _con_sombra(img, radio=20, opacidad=100, desplazamiento=14)
        archivo = os.path.join(carpeta, f"check{idx:02d}-{k}.png")
        img.save(archivo)
        fin = tiempos[k + 1] if k + 1 < len(items) else item["fin"]
        capas.append({"archivo": archivo, "x": (W - img.width) // 2, "y": y_pos - pad, "inicio": tiempos[k], "fin": fin,
                      "entrada": "subir" if k == 0 else "corte", "salida": k == len(items) - 1})
    return capas


# ------------------------------------------------------------------ cita tipo foto (polaroid)
def cita(item, carpeta, c, idx, foto):
    ancho, ventana_h = 520, 600
    f_txt = _fuente("InstrumentSerifItalic-400", 44)
    f_meta = _fuente("Montserrat-600", 20)
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    lineas = _partir(f"“{item.get('texto', '').strip()}”", f_txt, ancho - 56, tmp)[:4]
    alto = 24 + ventana_h + 50 + len(lineas) * 50 + 30
    hoja = Image.new("RGBA", (ancho, alto), _rgb(c["colorPapel"]))
    d = ImageDraw.Draw(hoja)
    d.rectangle([0, 0, ancho - 1, alto - 1], outline=_rgb("#DDD6C6"), width=2)
    if foto and os.path.exists(foto):
        f = Image.open(foto).convert("RGBA")
        escala = max((ancho - 48) / f.width, ventana_h / f.height)
        f = f.resize((int(f.width * escala), int(f.height * escala)), Image.LANCZOS)
        x0, y0 = (f.width - (ancho - 48)) // 2, (f.height - ventana_h) // 2
        f = f.crop((x0, y0, x0 + ancho - 48, y0 + ventana_h))
        hoja.paste(f, (24, 24))
    else:
        d.rectangle([24, 24, ancho - 24, 24 + ventana_h], fill=_rgb("#1E1E1E"))
    y = 24 + ventana_h
    d.rectangle([24, y, ancho - 24, y + 34], fill=_rgb("#1F3A2E"))
    d.text((40, y + 17), item.get("etiqueta", "").upper(), font=f_meta, fill=_rgb("#E9E3D3"), anchor="lm")
    y += 50
    for linea in lineas:
        d.text((ancho / 2, y), linea, font=f_txt, fill=_rgb("#2A2A2A"), anchor="ma")
        y += 50
    # Hojas apiladas detrás
    pila = Image.new("RGBA", (ancho + 30, alto + 30), (0, 0, 0, 0))
    for k, off in enumerate([(16, 18), (8, 9)]):
        atras = Image.new("RGBA", (ancho, alto), _rgb("#EAE4D6" if k == 0 else "#F0EBDF"))
        ImageDraw.Draw(atras).rectangle([0, 0, ancho - 1, alto - 1], outline=_rgb("#D8D0BE"), width=2)
        pila.alpha_composite(atras, off)
    pila.alpha_composite(hoja, (0, 0))
    pila = pila.rotate(item.get("giro", 2.5), resample=Image.BICUBIC, expand=True)
    img, pad = _con_sombra(pila, radio=18, opacidad=110, desplazamiento=12)
    archivo = os.path.join(carpeta, f"cita{idx:02d}.png")
    img.save(archivo)
    lado = item.get("lado", "derecha")
    x = W - img.width + pad - 40 if lado == "derecha" else 40 - pad
    return [{"archivo": archivo, "x": x, "y": 110 - pad, "inicio": item["inicio"], "fin": item["fin"], "entrada": "subir"}]
