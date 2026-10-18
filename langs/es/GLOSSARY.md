# Guía y glosario del español (es-419)

Reglas para traducir y corregir `text.jsonl`. El español sale del **inglés oficial** del juego: el japonés no se usa.

## Alcance «spanglish»

Se traducen los diálogos, la narración, las descripciones y los textos que **explican** algo; los menús, la interfaz, los rótulos, los
banners y los **nombres** (personajes, enemigos, armas, objetos, habilidades, lugares, nombres de opciones de menú) se quedan en el
inglés original. Criterio práctico: lo que se lee como frase (explica, instruye o habla; mayúscula de frase) va en español; un nombre
o una etiqueta (Title Case, una o dos palabras) se queda. Un texto que cita una opción de menú («Practice», «Config», «Item», «Save»,
«Hard») la escribe en inglés tal como sale en pantalla.

Los botones con forma de píldora son interfaz aunque se lean como frase (los cuatro botones «Check …» del menú de información de
batalla): no se traducen. Las ayudas de menú que los acompañan sí.

## Formato (el validador lo comprueba)

- Cada traducción es una **lista de segmentos** con exactamente los mismos segmentos que el original, en el mismo orden. Un segmento es un
  clip de voz o un bloque de texto del juego. Si el inglés parte una frase entre dos segmentos, parte la tuya en el mismo punto. Nunca
  dejes un segmento vacío ni fusiones dos.
- Un segmento que **continúa** la frase del anterior (pasa en los textos fijos de la interfaz) no puede acabar en coma: el juego ya dibuja
  la coma que los separa.
- **Conserva idénticos**: `p1`, `p2`, `%d`, `%s`, `{}`, `[Nightmare]`, `B1`, `B3` (iconos de botón), `c1`, `￥` (una gotita de sudor)
  y los símbolos `♪ ★ ∩ ∪ ⊂ ⊃ ↑ ↓ ← →`. «Press the B1 Button» → «Pulsa el botón B1».
- **Silencios**: un segmento que solo es puntos suspensivos o signos (`…`, `…………`, `…?`) se copia tal cual.
- No uses `;`, `|`, tabuladores ni saltos de línea: el programa reparte el texto en líneas con el ancho real de cada glifo.
- Puntos suspensivos: el carácter `…`. Comillas rectas `"`. Sin rayas largas ni comillas angulares (coma, paréntesis o guion corto solo
  para tartamudeos: «S-Sí»). No uses `[` ni `]`: salen como corchetes japoneses de ancho completo.
- Ortografía completa: acentos, `ñ`, `¿?`, `¡!`, `ü`. Pon `¿` y `¡` siempre que corresponda. Se dibujan en la fuente del juego.
- Los pensamientos van entre paréntesis en el inglés; conserva los paréntesis. Los efectos como `*sigh*` se traducen y siguen entre
  asteriscos: `*suspiro*`. Las mayúsculas de énfasis se mantienen.
- Un `%` seguido de espacio y letra («75% del») lo toma el motor por un formato; el programa lo escribe en su variante de ancho completo, no hace
  falta que lo evites.
- Tics de personaje: Mursya acaba en «nya» (y cambia «not» por «nyot»): conserva el tic («¡Nyada mal!»).

## Estilo

- **Español neutro latinoamericano**: tuteo, «ustedes» para el plural, sin «vosotros» ni «vos» ni modismos regionales. Tono natural de RPG
  de fantasía, con humor ligero cuando lo hay.
- Fiel al sentido y a la personalidad de cada voz; no suavices ni añadas notas del traductor.
- **Género**: Ein, Ledah, Hector, Seth y Hades son varones; Lina, Fia, Serene, Cierra, Ursula y Malice, mujeres. Si quien habla no se
  deduce del contexto, redacta sin marcar género.
- **Brevedad**: las cajas de texto son pequeñas. Apunta a que el español no pase de ~1,3 veces los caracteres del inglés.
- Tratamiento: «tú» entre compañeros; «usted» solo ante ancianos o nobles cuando el inglés suena claramente ceremonioso.

## Glosario (obligatorio, para que todo coincida)

**Se quedan en inglés, tal cual**: nombres de personajes (Ein, Lina, Fia, Serene, Cierra, Ledah, Ursula, Hector, Seth, Malice, Hades,
Mursya, Rebecca, Beth, Regina, Gateau, Soala, Claude, Ritz, Aghart, Cefiro), lugares exóticos (Riviera, Elendia, Asgard, Yggdrasil,
Utgard, Tetyth, Mireno, Nelde, Wiese, Wilheim) y los términos de interfaz que el jugador ve en inglés («Over Skill», «Look Mode»,
«Move Mode», TP, HP, MP, «Mana Wisp», «Einherjar»).

| Inglés | Español |
|---|---|
| Grim Angel(s) | Ángel(es) de la Muerte |
| Accursed | Maldito(s) («los Malditos») |
| Retribution | la Retribución |
| Sealed One | el Ser Sellado |
| Dark Progenitor | Progenitor Oscuro |
| Sprite(s) | espíritu(s) |
| Fairy / Fairies | hada(s) |
| Diviner(s) (el arma de cada Ángel de la Muerte) | **Diviner**, igual: es un nombre inventado del juego y no se traduce. Masculino («un Diviner», «mi Diviner»); plural «los Diviners». Nunca «espada divina» ni «arma divina». |
| Arc(s) (pueblo) | los Arc |
| Familiar | familiar |
| Grandfather / Elder | Abuelo / el Anciano |
| Underworld | el Inframundo |
| Maze of Shadows (the Maze) | Laberinto de las Sombras (el Laberinto) |
| Heaven's Gate | Puerta del Cielo |
| Rosalina Island | Isla Rosalina |
| Magic Guild | Gremio de Magia |
| Aquarium(s) | Acuario(s) |
| Golem | gólem |
| Potion | poción |
| Magi (los 7 Magi, enviados de los dioses) | **Magi**, igual (plural invariable: «los Magi», «los 7 Magi»). Nunca «Magos». |

Si aparece un término recurrente que no está aquí, elige una traducción natural y úsala siempre igual; anótala aquí en el mismo cambio.

## Comprobar un cambio

```
python rpl.py validate es          # marcadores, segmentos, caracteres, y que quepa en su caja (con tu volcado)
python rpl.py switch build es      # y míralo en el juego
```
