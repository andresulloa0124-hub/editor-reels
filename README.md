# Editor de Reels con IA (estilo Santi Padilla)

Skill para Claude que convierte un video hablado a cámara en un Reel vertical editado:
silencios cortados, subtítulos con palabras clave en negrita, títulos de énfasis, encabezados de sección,
zoom en los cortes, capturas propias como tarjetas y volumen parejo.

## Cómo instalarla (estudiantes)

1. En claude.ai ve a **Configuración → Capacidades** y activa **Ejecución de código y creación de archivos**.
2. Descarga `editor-reels.zip` desde la sección [Releases](../../releases/latest) de este repositorio.
3. En claude.ai ve a **Personalizar → Skills → "+" → Crear skill → Subir una skill** y sube el zip (sin descomprimir).
4. Abre un chat nuevo, adjunta tu video (el archivo original del celular, no el que pasó por WhatsApp) y escribe: **"Edítame este Reel"**.

## Cómo funciona

- `skill/editor-reels/SKILL.md`: la skill que sube cada estudiante. Solo descarga la última versión de este repo.
- `GUIA.md`: las instrucciones que sigue Claude (planeación de títulos, secciones, negritas, tarjetas).
- `motor/editor.py`: transcribe con whisper.cpp y renderiza con FFmpeg + subtítulos ASS.
- `motor/estilos/`: estilos listos (santi, santi-serif, santi-minimal, neutro).
- Release `modelos`: modelos de transcripción (`ggml-small-q5_1.bin`, `ggml-base-q5_1.bin`).

Cualquier cambio en `main` le llega a todos los estudiantes en su siguiente chat, sin reinstalar nada.
Si agregas archivos al motor, inclúyelos en `manifest.json`.
