# Riviera: The Promised Land, en tu idioma

[English](README.md) · **Español**

[![Descargar el parcheador](https://img.shields.io/badge/Descargar-parcheador%20para%20Windows%20%C2%B7%20macOS-2ea44f?style=for-the-badge&logo=github)](https://github.com/caribbeansc/riviera-i18n/releases/latest)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

**Riviera: The Promised Land** (Sting) no tiene español. La versión de Switch viene en inglés, japonés, coreano y chino; la app de
Android, solo en japonés.

**¿Solo quieres jugar?** Descarga el parcheador listo para usar para Windows o macOS de la
[**última versión**](https://github.com/caribbeansc/riviera-i18n/releases/latest). Sin Python, sin terminal. Mira
[Jugar, la forma fácil](#jugar-la-forma-fácil-sin-python-sin-terminal) más abajo.

**Para qué sirve este repositorio:** traducir el juego sin hacer ingeniería inversa. Lo apuntas a tu propia copia del juego y te
construye una versión en español para **Switch** (como mod de emulador, o para una consola con Atmosphère) y para **Android**
(español, y también inglés, que la app de Android nunca tuvo). Un idioma es una carpeta (`langs/<código>/`), no código.

| Plataforma | Idioma | Guion | Imágenes | Estado |
|---|---|---:|---:|---|
| Switch v1.0.0 | Español | 11 360 textos (16 723 filas) | 200 imágenes | jugable; probado desde el capítulo 1 en Ryujinx |
| Android v1.0.4 | Español | lo mismo + 121 textos solo de Android | 200 + 18 imágenes solo de Android | construido; comprobado en un móvil y en un emulador |
| Android v1.0.4 | English | el inglés oficial de Switch + 121 textos solo de Android | las imágenes oficiales en inglés de Switch + 18 solo de Android | construido; comprobado en un emulador |

PC (Steam) **todavía no está cubierto**.

> **Necesitas tu propia copia del juego.** Estas herramientas leen los archivos de tu propio volcado o app. No contienen el juego ni
> pueden conseguírtelo. Para Android necesitas **las dos**: la app de Android y un volcado de Switch (la app de Android no trae
> inglés; el texto y las imágenes en inglés salen del volcado de Switch).

## Qué significa «español» aquí: una traducción «spanglish»

A propósito, los menús, la interfaz, los rótulos, los banners y todos los **nombres** (personajes, enemigos, armas, objetos,
habilidades, lugares, nombres de las opciones) se quedan en el inglés original del juego. Lo que va en español es la historia y todo
lo que *explica* algo:

- diálogos, narración y las opciones que eliges dentro de un diálogo,
- descripciones de lugares, objetos y consejos de batalla,
- las ayudas de los menús, el texto de los efectos de habilidad, las instrucciones y la explicación de cada opción de configuración,
- las imágenes con texto que cuentan la historia: la intro, los títulos de escena, los pies de las CG, las tarjetas de capítulo y el poema.

*Magi* y *Diviner* son palabras inventadas del juego y no se traducen. Los acentos, la `ñ`, `¿` y `¡` se ven en el juego: la fuente del
juego no tiene `¿` ni `¡` y perdió las letras acentuadas en esta compilación, así que la herramienta las dibuja en la fuente.

## Jugar, la forma fácil (sin Python, sin terminal)

Descarga el parcheador de la [**última versión**](https://github.com/caribbeansc/riviera-i18n/releases/latest). Se construye solo a partir de
este repositorio y no contiene nada del juego. Elige el archivo para tu equipo:

- **Windows:** `Riviera-Patcher-Windows.exe`, haz doble clic. La primera vez Windows puede avisar de que no reconoce la aplicación (es
  software libre sin certificado de editor de pago): pulsa **Más información** y **Ejecutar de todas formas**. Todo el código está en este repositorio.
- **macOS:** `Riviera-Patcher-macOS-AppleSilicon.zip` para un Mac M1/M2/M3 o `…-Intel.zip` para uno más antiguo (menú → *Acerca de este Mac*).
  Descomprime, y la primera vez haz **clic derecho en la app → Abrir** (no está firmada con un certificado de Apple de pago).

Luego, en la pestaña **Switch**: apúntalo a tu propia copia (`.xci` / `.nsp`, que necesita tu `prod.keys`) o a las carpetas exefs y romfs
que extrajo tu emulador, elige un idioma y pulsa **Configurar**, **Crear el mod** e **Instalar en el emulador** (o **ZIP para consola**).
La pestaña **Android** hace lo mismo con la app de Android, pero además necesita las build-tools del SDK de Android y un JDK en tu equipo:
[docs/ANDROID.md](docs/ANDROID.md). Lo que crea el parcheador va a la carpeta **`Riviera-i18n`** dentro de tu carpeta de usuario
(`build/`, con la configuración y los archivos desempaquetados al lado).

## Jugar, desde el código

Necesitas Python 3.10 o superior ([python.org](https://www.python.org/downloads/); en Windows marca *Add python.exe to PATH*) y Pillow.

```
git clone https://github.com/caribbeansc/riviera-i18n
cd riviera-i18n
pip install -r requirements.txt
python rpl.py
```

`python rpl.py` abre un menú; cada opción también es un comando (`python rpl.py <comando> --help`). Los detalles de cada caso, con
dónde conseguir tus archivos, están en [docs/SETUP.md](docs/SETUP.md) (en inglés).

### Switch, en un emulador

1. Ten tu propio volcado. O bien una copia de seguridad (`.xci` o `.nsp`, que necesita **tu propio `prod.keys`** y
   [hactool](https://github.com/SciresM/hactool)) o el exefs y el romfs que extrae tu emulador (*Extract Data → ExeFS* y *RomFS*):
   sin claves.
2. Dile a la herramienta dónde está, una sola vez:
   ```
   python rpl.py setup --xci "Riviera.xci" --keys prod.keys
   # o:  python rpl.py setup --exefs ruta/al/exefs --romfs ruta/al/romfs
   ```
3. Construye e instala:
   ```
   python rpl.py switch build es
   python rpl.py switch install es          # encuentra solo Ryujinx, Eden, yuzu y derivados
   ```
   Otros sitios: `--to <carpeta de mods>` para cualquier emulador, `--adb` para Eden en un dispositivo Android.
4. En el emulador, activa el mod para el juego (clic derecho en el juego → *Complementos* / *Abrir ubicación de mods*) y pon el
   idioma del juego en **inglés**: el español ocupa el lugar del inglés.

**En una consola** con Atmosphère, `python rpl.py switch package es` escribe un ZIP para descomprimir en la raíz de la tarjeta SD.
Todavía no se ha probado en una consola real.

### Android

La app parcheada se firma con una clave que se crea en tu equipo, así que hay que desinstalar antes la original (firmada por Google
Play), y eso borra sus partidas locales. Lee [docs/ANDROID.md](docs/ANDROID.md) antes de empezar: dice qué necesitas, cómo sacar los
APK de tu móvil, cómo llevarte tus partidas y qué cambia la construcción dentro de la app.

```
python rpl.py setup --apk-dir ruta/a/los/apk
python rpl.py android build es            # o: en
python rpl.py android install es
```

Algo que hace la construcción y conviene que sepas: la app original lleva la comprobación de licencia de Google Play, y una copia firmada de
nuevo la suspende y se cierra al arrancar. Por eso, salvo que pases `--keep-license-check`, la construcción desactiva esa comprobación **en la copia
que parchea**. Es para una app que compraste, parcheada en tu equipo para tu móvil; [docs/ANDROID.md](docs/ANDROID.md) explica qué cambia exactamente.

### Tus partidas

El formato de partida es el mismo en Switch, Android y PC, así que puedes llevar una partida de uno a otro: [docs/SAVES.md](docs/SAVES.md).

## Sobre las traducciones

El español lo escribió un LLM (Claude), por lotes, a partir del inglés oficial del juego y con un glosario. Pasó comprobaciones
automáticas (marcadores, segmentos, caracteres, si cada línea cabe en su caja con el ancho real de los glifos y el corrector
ortográfico de macOS) y una revisión por muestreo de 600 textos al azar por otros revisores LLM, que encontraron cuatro problemas
pequeños que se corrigieron. Se ha jugado desde el principio del capítulo 1, pero **no se ha revisado línea por línea ni se ha jugado
el juego entero con ella**. Tómala como un buen punto de partida y ayuda a pulirla: corregir una línea lleva un minuto y cada
corrección llega a todos; mira [Corregir una línea o añadir un idioma](#corregir-una-línea-o-añadir-un-idioma).

## Corregir una línea o añadir un idioma

```
python rpl.py extract es          # work/switch/lang/es/units.jsonl: el inglés de tu volcado junto al español
# edita las listas "t" de ese archivo
python rpl.py validate es         # marcadores, segmentos, caracteres y si cabe en las cajas
python rpl.py sync es             # work/ -> langs/es/text.jsonl, solo claves y traducciones
python rpl.py switch build es
```

Un idioma nuevo: `python rpl.py newlang fr --name "Français" --like es`. Luego sube `langs/<código>/` en un pull request; los
pequeños se aceptan antes. Las reglas del texto y lo que necesita un idioma están en
[docs/ADDING_A_LANGUAGE.md](docs/ADDING_A_LANGUAGE.md) y, para el español, [langs/es/GLOSSARY.md](langs/es/GLOSSARY.md).

## Sin datos del juego, por diseño

Una traducción se guarda como una referencia a un texto más tu texto, nunca el original:

```json
{"k": "a9993e364706816a", "t": ["Pulsa el botón B1"]}
```

`k` es una huella (los 16 primeros dígitos hexadecimales del SHA-1 del texto tal como lo guarda el juego): sirve para encontrar el texto
en tu copia y no sirve para reconstruirlo. Las imágenes son texto que este proyecto dibuja en un lienzo vacío, o los píxeles que la
traducción cambia sobre una imagen que solo tú tienes. Una prueba revisa todos los paquetes en busca de japonés, coreano, chino y
caracteres de ancho completo y falla si encuentra alguno; `rpl.py sync` se niega a escribirlos.

En tu equipo no hay límites: `extract` te enseña el texto del juego junto a tu traducción y `unpack` abre los contenedores. Todo eso
vive en `work/`, que nunca se comparte.

## Para desarrolladores

Cómo guarda el juego su texto, fuentes e imágenes, las trampas y qué hace cada parte: [docs/PIPELINE.md](docs/PIPELINE.md). El
comportamiento importante está escrito como requisitos numerados en [docs/specs/](docs/specs/) y las pruebas nombran el requisito
que cubren.

```
pip install -r requirements-dev.txt
pytest -m "not game"     # no necesita archivos del juego (volcados sintéticos)
pytest                   # + las pruebas que necesitan tu volcado (antes: python rpl.py setup)
```

Con el volcado de Switch v1.0.0, el parche del ejecutable es byte a byte el que se jugó (una prueba fija su suma de control); las imágenes
son las mismas, salvo unos píxeles suavizados de un glifo de la fuente según tu versión de Pillow.

## Preguntas

**¿Romperá mi partida?** Cambia texto e imágenes, no la lógica del juego. Haz copia de tus partidas de todos modos. En Android, instalar
la app parcheada obliga a desinstalar la original, y eso borra sus partidas: [docs/ANDROID.md](docs/ANDROID.md) explica cómo conservarlas.

**¿Qué emuladores?** El mod de Switch se probó en Ryujinx. El instalador también conoce las carpetas de mods de Ryubing, Astris, yuzu,
sudachi, Eden, Citron y Suyu, que leen los mods igual, en Windows, Mac y Linux. Cualquier otro: `switch install es --to <carpeta de mods>`.
Eden en Android: `--adb`.

**¿Qué versiones del juego?** Switch v1.0.0 y Android v1.0.4. La herramienta reconoce la versión de tus archivos y avisa cuando no es
una que conoce: las direcciones que parchea son fijas para cada versión.

**¿Puedo volver atrás?** En Switch, borra la carpeta del mod (o desactívalo en *Complementos*): no se cambia nada del juego. En
Android, reinstala la original desde Google Play.

**¿Participó la IA?** Sí, en la traducción y en el código, y está escrito en lugar de maquillado: mira [Sobre las traducciones](#sobre-las-traducciones).

## Apoyo

Si esto te ayudó a poder jugar, puedes invitarme un café. Corregir una línea que se lee mal ayuda igual.

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20me%20a%20coffee-ffdd00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/caribbeansc)

## Proyectos hermanos

El mismo enfoque (una herramienta más paquetes de idioma que nunca guardan el texto del juego) mueve
[medarot-rb-i18n](https://github.com/caribbeansc/medarot-rb-i18n), [medarot9-i18n](https://github.com/caribbeansc/medarot9-i18n)
y [mdr-navi-i18n](https://github.com/caribbeansc/mdr-navi-i18n).

## Créditos

Sobre qué se apoya este proyecto, con detalle en [NOTICE](NOTICE) y [docs/EXTERNAL-REPOS.md](docs/EXTERNAL-REPOS.md):

- [SciresM/hactool](https://github.com/SciresM/hactool): abre una copia de seguridad de Switch (`.xci` / `.nsp`).
- [python-pillow/Pillow](https://github.com/python-pillow/Pillow): todas las imágenes que la herramienta lee, dibuja o compone.
- [Ryujinx](https://ryujinx.app/) y [Eden](https://eden-emu.dev/): donde se probó el mod de Switch.
- `apksigner` y `zipalign` del SDK de Android, y opcionalmente [apktool](https://apktool.org/): firmar y parchear la app.

## Licencia

Código MIT ([LICENSE](LICENSE)); traducciones CC BY-SA 4.0 ([LICENSE-TRANSLATIONS](LICENSE-TRANSLATIONS)). Proyecto de fans no oficial,
sin relación con Sting Entertainment, Nintendo ni Google ([NOTICE](NOTICE)). Por favor, no abras issues ni pull requests con archivos
del juego ni con el texto original del juego.
