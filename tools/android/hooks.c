/* Proportional-text hooks for libapp.so (Android, arm64).
 *
 * The Android text engine always advances one fixed cell per character (as it does for Japanese). English (the "Release_en"
 * build on PC, and the Switch with a language other than Japanese) uses per-cell metrics (x0, width, ydisp; 6 bytes) for the
 * cells of the full-width Latin letters. This file reproduces that behaviour on top of the Android functions.
 *
 * It is compiled without a libc and linked at a fixed address inside the segment the build appends (tools/android/build_hooks.py
 * writes the result to riviera/android/data/). The shipped blob is code only: the engine's own tables below (metrics, character
 * string) are reserved, zero-filled, and the builder copies them from the executable of the user's own dump.
 *
 * Convention of the "cave" hooks: they receive `sp` (the hooked function's, already restored) and `fp` (x29).
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef short s16;
typedef unsigned int u32;
typedef int s32;

/* Table geometry of this game build (see riviera/builds.py): first cell and number of cells of each metrics table. */
#define M1_FIRST 251
#define M1_COUNT 82
#define M2_FIRST 2204
#define M2_COUNT 58
#define M3_FIRST 2378
#define M3_COUNT 9
#define CHARSET_MAX 7392        /* room for the engine's character string (7380 bytes plus the final zero, rounded up) */

/* Reserved data, filled when the library is built. Each metrics row is (x0, width, y offset). */
#define TABLE __attribute__((section(".tables"), used))
u16 M1[M1_COUNT][3] TABLE;
u16 M2[M2_COUNT][3] TABLE;
u16 M3[M3_COUNT][3] TABLE;
u8 charset_es[CHARSET_MAX] TABLE;   /* the extended character string; only referenced by the patched FNT_init */

/* game functions (their addresses are given at link time with --defsym) */
extern u16 GetFontSystemIndex(u32 code);                         /* _GetFontSystemIndex */
extern void GetUtf8Code(u32 *code, u32 *len, const char *s);     /* _GetUtf8Code */

#define RD(T, base, off) (*(T *)((char *)(base) + (off)))

/* metrics entry of a cell, or 0 if it has none */
static const u16 *metric(u32 cell)
{
    if (cell - M1_FIRST < M1_COUNT) return M1[cell - M1_FIRST];
    if (cell - M2_FIRST < M2_COUNT) return M2[cell - M2_FIRST];
    if (cell - M3_FIRST < M3_COUNT) return M3[cell - M3_FIRST];
    return 0;
}

/* ASCII -> the full-width character it stands for (same as the game's own conversion routine) */
static u32 to_full(u32 c)
{
    if (c == 0x27) return 0xe28099;
    if (c - 0x2b < 5) return c + 0xefbc60;
    if (c == 0x5b) return 0xe38090;
    if (c == 0x5d) return 0xe38091;
    if (c - 0x21 < 0x40) return c + 0xefbc60;
    if (c - 0x61 < 0x1f) return c + 0xefbd20;
    if (c == 0xe28892) return 0xefbc8d;
    return c;
}

/* ---- FNT_setCode: position and advance of every glyph ---- */

/* after the quad's x/y are computed: apply x0/ydisp and the case of two "＿" in a row */
void hk_code_pos(char *sp, char *fp)
{
    u32 cell = ((u32)RD(u16, sp, 0xae) / 68) * 58 + (u32)RD(u16, sp, 0xb0) / 68;
    const u16 *m = metric(cell);
    if (!m) return;
    float sc = RD(float, sp, 0x110);
    s16 x = RD(s16, sp, 0x7e), y = RD(s16, sp, 0x7c);
    if (cell == 0xff) {                       /* "＿＿": the second one is moved 5 * scale to the right (as on PC and Switch) */
        const u8 *p = RD(const u8 *, sp, 0x100);          /* pointer after the current character */
        if (p[-6] == 0xef && p[-5] == 0xbc && p[-4] == 0xbf) {
            s16 pen = RD(s16, fp, -0xfa);
            pen = (s16)(int)(sc * 5.0f + (float)(int)pen);
            RD(s16, fp, -0xfa) = pen;
            x = (s16)(int)((float)(int)pen - (sc + sc));
        }
    }
    x = (s16)(int)((float)(int)x - (float)m[0] * sc);
    y = (s16)(int)((float)(s16)m[2] * sc + (float)(int)y);
    RD(s16, sp, 0x7e) = x;
    RD(s16, sp, 0x7c) = y;
}

/* replaces `pen += (local_18a + 1) * scale * 4`: advance (width + 1) * scale, or 0x40 + 1 without metrics */
void hk_code_adv(char *sp, char *fp)
{
    u32 cell = ((u32)RD(u16, sp, 0xae) / 68) * 58 + (u32)RD(u16, sp, 0xb0) / 68;
    const u16 *m = metric(cell);
    float sc = RD(float, sp, 0x110);
    s16 pen = RD(s16, fp, -0xfa);
    u32 w = m ? m[1] : 0x40;
    RD(s16, fp, -0xfa) = (s16)(int)((float)(w + 1) * sc + (float)(int)pen);
}

/* ---- FNT_setSystem ---- */

/* before the vertices are written: shift the quad by (x0, ydisp); the pen is left alone */
void hk_sys_pos(char *sp, char *fp)
{
    const u16 *m = metric(RD(u16, sp, 0x78));
    if (!m) return;
    float sx = RD(float, fp, -0xc4), sy = RD(float, fp, -0xc8);
    s16 x = RD(s16, sp, 0x4a), y = RD(s16, sp, 0x48);
    RD(s16, sp, 0x4a) = (s16)(int)((float)(int)x - (float)m[0] * sx);
    RD(s16, sp, 0x48) = (s16)(int)((float)(s16)m[2] * sy + (float)(int)y);
}

/* replaces `pen += cellW + pitch` by `pen += width * scale + pitch` for cells that have metrics */
void hk_sys_adv(char *sp, char *fp)
{
    const u16 *m = metric(RD(u16, sp, 0x78));
    s16 pen = RD(s16, fp, -0xb2);
    s32 pitch = RD(s32, fp, -0xcc);
    if (m) {
        float sx = RD(float, fp, -0xc4);
        RD(u16, fp, -0xb2) = (u16)(int)((float)m[1] * sx + (float)pitch + (float)(int)pen);
    } else {
        RD(u16, fp, -0xb2) = (u16)((u32)(u16)pen + (u32)RD(u16, sp, 0x86) + (u32)pitch);
    }
}

/* ---- width functions (replaced whole; same prototypes as the game's) ---- */

/* FNT_getWidth(text, cell width, pitch, flags, scale): width of the first line */
int hk_getwidth(const char *s, int cellw, int pitch, unsigned flags, float scale)
{
    int w = 0;
    (void)flags;
    if (pitch < 0) pitch = 0;
    for (;;) {
        u32 c = 0xffff, len = 0;
        GetUtf8Code(&c, &len, s);
        s += len;
        if (c == 0 || c == 10 || c == 0x3b) return w;
        if (c == 0x20 || c == 0xe38080) { w += cellw / 2 + pitch; continue; }
        if (c - 0xefbda5 < 0xf9) {                      /* half-width katakana: consumes the following mark */
            GetUtf8Code(&c, &len, s);
            s += len;
        }
        u16 cell = GetFontSystemIndex(to_full(c));
        const u16 *m = metric(cell);
        if (m) w = (int)((float)m[1] * scale + (float)pitch + (float)w);
        else   w += cellw + pitch;
    }
}

/* fontPitch(code): advance in pixels of one character (calcStringWidth uses it: (pitch + 1) * scale) */
u16 hk_fontpitch(u32 code)
{
    const u16 *m = metric(GetFontSystemIndex(to_full(code)));
    if (m) return m[1] >> 2;
    return (code == 0 || code == 10 || code == 0x3b) ? 0 : 0x10;
}


/* ---- CConfMsg::disp: confirmation box fitted to its message (as on PC and Switch) ----
 * The Android design (made for Japanese) draws a fixed 905 px box against the right edge and centres the text (scale 0.75) in it: a
 * single line of about 1150 units at most. English and Spanish have wider messages (the widest is about 1500 units). The PC/Switch version computes width = max(905, message width + 40) and aligns the box to the right, text
 * centred. Two hooks and two one-instruction patches reproduce it (locals of the game: [fp-0x32] = animation offset, [fp-0x26] = x of
 * the box, [fp-0x2c] = a free slot where the width is left; `this` is at [sp+0x20] and the message at this+0x58). */
#define CAVE_FRAME 0x130
#define CONF_SCALE 0.75f

static int conf_msg_width(const char *s)
{
    int best = 0;
    for (;;) {
        int w = hk_getwidth(s, (int)(CONF_SCALE * 66.0f), 0, 1, CONF_SCALE);
        if (w > best) best = w;
        const char *p = s;
        while (*p && *p != 10 && *p != 0x3b) p++;
        if (!*p) return best;
        s = p + 1;
    }
}

/* after the box's x is computed: put it on the right with the width of the message */
void hk_conf_box(char *sp, char *fp)
{
    char *self = RD(char *, sp, 0x20);
    const char *msg = RD(const char *, self, 0x58);
    int bw = msg ? conf_msg_width(msg) + 40 : 905;
    if (bw < 905) bw = 905;
    RD(s16, fp, -0x26) = (s16)((int)RD(s16, fp, -0x32) + 1920 - bw);
    RD(u16, fp, -0x2c) = (u16)bw;
}

/* before the patched `add w2, w8, w10` (it replaces `add w2, w8, #0x1c4`): x10 = width / 2, to centre the text in the box */
void hk_conf_text(char *sp, char *fp)
{
    unsigned long long *regs = (unsigned long long *)(sp - CAVE_FRAME);
    regs[10] = RD(u16, fp, -0x2c) / 2;
}


/* ---- dialogue: scale the text to the width (FNT_setCodeSub: the `fmov s0,#1.0` right before `bl FNT_setCode`) ----
 * The dialogue box and the log (LOG) are made for 2 lines (English never goes past 2) and the text starts at x = 174 (window type 1,
 * portrait on the left), so about 1200 units are left on the right. Some Spanish pages need more than that even in 2 lines (up to
 * about 1440): instead of splitting them in 3 (the third line fell out of the bottom of the box and in the LOG it overlapped the next
 * entry) they are drawn **at a smaller scale**, just what makes the widest line reach the edge. The Switch does something similar in its
 * own way (it shifts the block to the left, over the portrait).
 * The page runs from `param_1` ([fp-0x20] of FNT_setCodeSub) up to the ASCII comma that separates pages or the NUL; its width is the one
 * FNT_setCode would use (each glyph (width + 1) units, a space 36, `cN` and `V(id)` take none). The hook replaces the `fmov` and leaves
 * the scale in s0 (the q0 saved by the cave). */
#define MSG_RIGHT 1900          /* right edge of the usable text area (the screen is 1920 units wide) */
#define MSG_MIN_SCALE 0.6f

static int msg_page_width(const char *s)
{
    int best = 0, w = 0;
    for (;;) {
        u32 c = 0xffff, len = 0;
        GetUtf8Code(&c, &len, s);
        s += len;
        if (c == 0 || c == 0x2c || c == 10 || c == 0x3b) {          /* end of a line (; or \n) or of the page (ASCII comma or NUL) */
            if (w > best) best = w;
            w = 0;
            if (c == 0 || c == 0x2c) return best;
            continue;
        }
        if ((c == 0x56 || c == 0x52) && *s == '(') {                /* V(id) / R(...): no width */
            while (*s && *s != ')') s++;
            if (*s) s++;
            continue;
        }
        if (c == 0x63 && *s >= '0' && *s <= '4') { s++; continue; }   /* cN: colour */
        if (c == 0x70 && *s >= '1' && *s <= '4') { s++; w += 200; continue; }   /* pN: a character's name (approximate) */
        if (c == 0x42 && *s >= '0' && *s <= '3') { s++; w += 68; continue; }    /* BN: button icon */
        if (c == 0x20 || c == 0xe38080) { w += 36; continue; }
        if (c == 0x21 && (*s == '!' || *s == '?')) { s++; w += 0x41; continue; }   /* "!!" and "!?": a single glyph */
        const u16 *m = metric(GetFontSystemIndex(to_full(c)));
        w += (m ? m[1] : 0x40) + 1;
    }
}

void hk_msg_scale(char *sp, char *fp)
{
    float *s0 = (float *)(sp - CAVE_FRAME + 0xa0);               /* q0 as saved by the cave */
    const char *page = RD(const char *, fp, -0x20);
    int x = (s16)RD(u16, fp, -0x2a);                             /* x of the text in PSP pixels (480 wide): x4 = units */
    int limit = MSG_RIGHT - 4 * x;
    float scale = 1.0f;
    if (page) {
        int w = msg_page_width(page);
        if (limit > 0 && w > limit) {
            scale = (float)limit / (float)w;
            if (scale < MSG_MIN_SCALE) scale = MSG_MIN_SCALE;
        }
    }
    *s0 = scale;
}
