# Guía para editar el Reel (la sigue Claude)

La persona que te habla probablemente NO es programadora: es coach, mentora o creadora de contenido. Háblale en español, tuteando, con frases cortas y sin jerga técnica. No le muestres código, comandos ni errores técnicos: tú haces todo.

El motor está en `/tmp/editor-reels/motor/editor.py`. Los archivos de trabajo quedan en `/tmp/editor-reels-trabajo/` y el video final en `/mnt/user-data/outputs/`.

## El estilo que buscamos (sacado de los Reels de Santi Padilla)

- **La cara es la protagonista.** No hay b-roll de stock. Lo único que se pone encima son pruebas propias: capturas de resultados, testimonios, documentos, chats.
- **Subtítulos chiquitos y limpios**: de 1 a 3 palabras, letra blanca normal, a la altura del pecho. Algunas palabras clave van en negrita.
- **Títulos grandes de énfasis** para el gancho y los conceptos clave.
- **Encabezados de sección fijos arriba** cuando el video tiene pasos o puntos ("PASO 1", "#2") y para el llamado a la acción.
- **Ritmo rápido**: silencios cortados apretado y zoom alternado en cada corte.
- De vez en cuando, un momento en **blanco y negro** para marcar un contraste.

## 1. Encontrar lo que adjuntó

- Busca el video en `/mnt/user-data/uploads/` y `/mnt/user-data/attachments/` (mp4, mov, m4v, webm). Si no adjuntó video, pídeselo: el archivo original del celular, idealmente de menos de 90 segundos.
- Si adjuntó imágenes (capturas, testimonios), son recursos para mostrar como tarjetas. Ábrelas para ver qué muestran.
- Si adjuntó un audio (mp3, m4a, wav), es música de fondo.
- Si adjuntó un archivo `mi-estilo.json`, es su estilo guardado de un chat anterior: cópialo a `/tmp/editor-reels-trabajo/estilo.json` antes de preparar.
- Si escribió algo junto con el pedido ("sin títulos", "estilo serif", "no cortes los silencios", "subtítulos más grandes"), tenlo en cuenta.
- Si no adjuntó capturas, no las pidas: sigue sin ellas.

## 2. Preparar: transcribir y quitar silencios

```
cd /tmp/editor-reels/motor && python3 editor.py preparar "RUTA_DEL_VIDEO"
```

Agrega `--sin-cortes` si pidió no quitar silencios. Para elegir un estilo distinto al de Santi, antes ejecuta `python3 editor.py estilo NOMBRE` (santi, santi-serif, santi-minimal, neutro).

La primera vez en cada chat descarga el modelo de transcripción, que tarda un poco. Antes de ejecutarlo, avísale en una línea que vas a transcribir y cortar silencios y que puede tardar uno o dos minutos. Si el comando se corta por tiempo, vuelve a ejecutarlo en segundo plano (`nohup ... > /tmp/preparar.log 2>&1 &`) y revisa el log cada 30 segundos hasta que termine.

Si el script avisa de baja resolución (video que pasó por WhatsApp), díselo al final, en una línea, como consejo para la próxima.

## 3. Planear textos y tarjetas

Lee `/tmp/editor-reels-trabajo/transcripcion.txt`, que tiene los tiempos del Reel ya cortado, y entiende la estructura: gancho, puntos o pasos, prueba y llamado a la acción.

Revisa también `subtitulos.json`. Si ves palabras mal transcritas (nombres propios, marcas, palabras en inglés), corrígelas ahí. Cambia solo el campo `texto`, nunca los tiempos.

### 3a. Textos → escribe `/tmp/editor-reels-trabajo/textos.json`

Es una lista con cuatro tipos de elementos:

```json
[
  { "tipo": "titulo", "inicio": 0.0, "fin": 1.8, "texto": "¿Cómo hacerte\nviral?" },
  { "tipo": "seccion", "inicio": 12.4, "fin": 31.0, "texto": "Paso 1" },
  { "tipo": "enfasis", "inicio": 14.1, "fin": 14.6 },
  { "tipo": "blancoynegro", "inicio": 40.2, "fin": 42.0 }
]
```

- **titulo** (texto grande en el centro):
  - Siempre uno en el gancho, entre 0 y 2 segundos, con la promesa o pregunta del video en 2 a 5 palabras sacadas de lo que dice.
  - Después, más o menos uno cada 10 a 15 segundos, solo en el concepto más importante de ese momento (2 a 4 palabras). Que dure entre 1.5 y 4 segundos y coincida con cuando lo dice.
  - Usa `\n` para partirlo en dos líneas. Máximo unas 13 letras por línea.
  - Nunca al mismo tiempo que una tarjeta.
- **seccion** (encabezado fijo arriba):
  - Solo si el video enumera pasos, puntos o errores ("paso uno", "primero", "lo segundo", "error número tres"). Pon una sección por punto, desde que lo anuncia hasta que empieza el siguiente.
  - Usa el formato que la persona dice: "Paso 1", "#2", "Error 3".
  - Si al final pide comentar o dar clic, agrega una sección con el llamado, por ejemplo "↓ Dale Click ↓" o "Comenta MÉTODO" (con la palabra que dice), desde que lo pide hasta el final.
- **enfasis** (pone en negrita las palabras que se dicen en ese rango):
  - Úsalo en números, resultados, montos, contrastes y la palabra clave de cada idea.
  - Más o menos una cada 2 o 3 frases. Que el rango cubra solo esa palabra o dos.
- **blancoynegro**: máximo uno o dos por video, de 1 a 3 segundos, cuando habla de un error, del "antes" o de algo negativo. Si no hay un momento claro, no lo uses.

### 3b. Tarjetas → escribe `/tmp/editor-reels-trabajo/broll.json`

Solo si adjuntó imágenes. Ponlas donde habla de eso ("estos resultados", "mira lo que me escribió", "como este", cifras):

```json
[
  { "inicio": 18.2, "fin": 21.5, "imagen": "/mnt/user-data/uploads/dashboard.png", "motivo": "dice 'estos resultados'" }
]
```

Cada tarjeta dura entre 2 y 5 segundos. No pongas una tarjeta al mismo tiempo que un título. Si no hay imágenes, deja `[]`.

### 3c. Revisar antes de renderizar

Saca 2 o 3 cuadros de momentos clave para comprobar que nada se monta: el gancho, una tarjeta y un título.

```
python3 editor.py cuadro SEGUNDO
```

Abre las imágenes que genera (`/mnt/user-data/outputs/cuadro-*.png`) y míralas tú. Si algo tapa la cara o se monta, ajústalo. Después borra esos PNG para que no se le entreguen a la persona.

## 4. Mostrar el plan y pedir aprobación

Muéstrale un resumen corto antes de renderizar:
- Cuánto dura el Reel y cuánto silencio se quitó.
- Los títulos y secciones que pusiste, con el momento de cada uno.
- Dónde aparece cada captura y qué está diciendo ahí.

Pregúntale si quiere cambiar algo o si renderizas. Si no responde o dice que sí, renderiza.

## 5. Renderizar y entregar

```
python3 editor.py render
```

Agrega `--musica "RUTA_DEL_AUDIO"` si adjuntó música. Tarda más o menos lo mismo que dura el video.

Entrégale el archivo `/mnt/user-data/outputs/NOMBRE-editado.mp4` para que lo descargue. Dile que lo revise completo antes de publicarlo, sobre todo los subtítulos con nombres propios o palabras en inglés.

## Cambios después de verlo

La persona pide cambios en lenguaje normal. Haz el cambio y vuelve a renderizar. No hace falta volver a preparar, salvo para los cambios de cortes de silencio.

| Pide | Cambias |
|---|---|
| Subtítulos más grandes / más pequeños | `subtitulos.tamano` en `estilo.json` (52 normal, 62 grande, 44 pequeño) |
| Subtítulos más arriba / más abajo | `subtitulos.posicionVertical` (40 arriba, 52 normal, 68 abajo). "Un poco" = unos 5 puntos |
| Otra letra en subtítulos | `subtitulos.fuente`: Poppins, Montserrat, Inter, Rubik, PlayfairDisplay, Anton, BebasNeue, Oswald |
| Color de las negritas | `subtitulos.colorEnfasis` (hexadecimal, ej. "#FFD60A") |
| Resaltar la palabra que se va diciendo | `subtitulos.estilo` = "resaltado" (color en `colorPalabraActiva`) |
| Subtítulos en mayúsculas | `subtitulos.mayusculas` = true |
| Borde negro en subtítulos | `subtitulos.grosorBorde` (0 sin borde, 8 marcado) |
| Más o menos palabras a la vez | `subtitulos.palabrasPorBloque` (1 a 5) |
| Títulos más grandes, de otro color o letra | `titulos.tamano`, `titulos.color`, `titulos.fuente`, `titulos.peso` |
| Sin títulos / sin secciones | `titulos.activados` / `secciones.activados` = false |
| Sin zooms / zoom más suave o fuerte | `zooms.activados`, `zooms.intensidad` (1.08 suave, 1.15 normal, 1.22 fuerte) |
| Música más alta o más baja | `musica.volumen` (0.05 muy suave, 0.08 normal, 0.15 alta) |
| Otro estilo completo | `python3 editor.py estilo NOMBRE` |
| Cambiar, mover o quitar un título, sección, negrita o tarjeta | edita `textos.json` o `broll.json` |
| Corregir una palabra de los subtítulos | edita `texto` en `subtitulos.json` |
| Que corte menos silencios | sube `silencios.duracionMinima` (ej. 0.7) y vuelve a **preparar** (luego vuelve a planear los textos) |
| Que corte más | baja `silencios.duracionMinima` (ej. 0.25) o sube `silencios.sobreRuidoDb` (ej. 12) y vuelve a **preparar** |

Si mueves los subtítulos y quedan a menos de 8 puntos de `titulos.posicionVertical`, mueve también los títulos para que no se monten. Si pide un color por nombre ("azul", "verde menta"), elige tú un hexadecimal que se vea bien sobre video.

**Guardar su estilo:** si cambió algo del estilo, al entregar copia `/tmp/editor-reels-trabajo/estilo.json` a `/mnt/user-data/outputs/mi-estilo.json`, entrégaselo y dile: "Si quieres este mismo estilo la próxima vez, adjunta este archivo junto con tu video".

## Si algo falla

- Lee el error completo, explícale a la persona en una frase qué pasó, sin el error técnico, y arréglalo tú.
- Si el video no tiene audio o casi no se escucha la voz, díselo: la herramienta necesita que se escuche hablar.
- Si la transcripción sale con muchos errores, vuelve a preparar con `--modelo small` (si estabas en base). Si ya era small, sugiérele grabar con menos ruido o con micrófono.
- Si el video dura más de 3 minutos, avísale que puede tardar bastante y que conviene usar Reels de menos de 90 segundos.
