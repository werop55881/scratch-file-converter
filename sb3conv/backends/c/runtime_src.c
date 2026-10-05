#include "runtime.h"

#include <SDL2/SDL.h>
#include <SDL2/SDL_image.h>
#include <SDL2/SDL_mixer.h>
#include <SDL2/SDL_ttf.h>
#include <stdarg.h>
#include <sys/stat.h>
#include <time.h>
#ifdef _WIN32
#include <timeapi.h>
#endif

/* vendored vector renderer for .svg costumes (public domain, see
   nanosvg-LICENSE.txt); silenced: third-party code, not ours */
#if defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wunused-variable"
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-variable"
#endif
#define NANOSVG_IMPLEMENTATION
#define NANOSVGRAST_IMPLEMENTATION
#include "nanosvg.h"
#include "nanosvgrast.h"
#if defined(__clang__)
#pragma clang diagnostic pop
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#endif

#define SB_FIBER_STACK (256 * 1024)
#define SB_ROUTE_CAP 256
/* supersample factor for vector costumes; must match RASTER_ZOOM in
   sb3conv/svg.py (the manifest resolution is scaled by the same amount) */
#define SB_SVG_RASTER_SCALE 2.0f

static int costume_load(Rt *rt, CostumeDef *c);

static void build_alpha_mask(CostumeDef *c, SDL_Surface *surface) {
  SDL_Surface *conv = SDL_ConvertSurfaceFormat(surface, SDL_PIXELFORMAT_RGBA32, 0);
  if (!conv) return;
  int w = conv->w, h = conv->h;
  Uint8 *alpha = (Uint8 *)malloc((size_t)w * (size_t)h);
  if (!alpha) {
    SDL_FreeSurface(conv);
    return;
  }
  int l = w, t = h, r = -1, b = -1;
  Uint8 *pixels = (Uint8 *)conv->pixels;
  int pitch = conv->pitch;
  for (int y = 0; y < h; y++) {
    Uint8 *row = pixels + (size_t)y * pitch;
    for (int x = 0; x < w; x++) {
      Uint8 a = row[x * 4 + 3];
      alpha[(size_t)y * w + x] = a ? 1 : 0;
      if (a) {
        if (x < l) l = x;
        if (x > r) r = x;
        if (y < t) t = y;
        if (y > b) b = y;
      }
    }
  }
  SDL_FreeSurface(conv);
  if (r < l) { /* fully transparent: keep full bounds so contact still registers */
    l = 0;
    t = 0;
    r = w - 1;
    b = h - 1;
  }
  free(c->alpha);
  c->alpha = alpha;
  c->tight_l = l;
  c->tight_t = t;
  c->tight_r = r + 1;
  c->tight_b = b + 1;
}

static char *xstrdup(const char *s) {
  size_t len = strlen(s) + 1;
  char *out = (char *)malloc(len);
  memcpy(out, s, len);
  return out;
}

/* ------------------------------------------------------------------ */
/* value helpers                                                       */
/* ------------------------------------------------------------------ */

static void format_double(double v, char *out, size_t cap) {
  if (isnan(v)) {
    snprintf(out, cap, "NaN");
    return;
  }
  if (isinf(v)) {
    snprintf(out, cap, v > 0 ? "Infinity" : "-Infinity");
    return;
  }
  if (v == floor(v) && fabs(v) < 1e15) {
    snprintf(out, cap, "%lld", (long long)v);
  } else {
    snprintf(out, cap, "%.15g", v);
  }
}

static void str_trim_copy(const char *src, char *dst, size_t cap) {
  while (*src == ' ' || *src == '\t' || *src == '\n' || *src == '\r') src++;
  size_t len = strlen(src);
  while (len > 0 && (src[len - 1] == ' ' || src[len - 1] == '\t' || src[len - 1] == '\n' || src[len - 1] == '\r')) len--;
  if (len >= cap) len = cap - 1;
  memcpy(dst, src, len);
  dst[len] = 0;
}

double s_numd(Value v) {
  if (v.type == VAL_NUM) return v.num;
  char text[SB_STR_CAP];
  str_trim_copy(v.str, text, sizeof text);
  if (text[0] == 0) return 0.0;
  if (strcmp(text, "NaN") == 0) return NAN;
  if (strcmp(text, "Infinity") == 0) return INFINITY;
  if (strcmp(text, "-Infinity") == 0) return -INFINITY;
  char *end = NULL;
  double out = strtod(text, &end);
  if (end == text) return 0.0;
  while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r') end++;
  if (*end != 0) return 0.0;
  if (isinf(out)) return 0.0;
  return out;
}

Value s_num(Value v) {
  if (v.type == VAL_NUM) return v;
  return N(s_numd(v));
}

Value mkstr(const char *s) {
  Value r;
  r.type = VAL_STR;
  r.num = 0.0;
  snprintf(r.str, SB_STR_CAP, "%s", s ? s : "");
  return r;
}

void s_str_into(Value v, char *out, size_t cap) {
  if (v.type == VAL_STR) {
    snprintf(out, cap, "%s", v.str);
    return;
  }
  format_double(v.num, out, cap);
}

Value s_str(Value v) {
  if (v.type == VAL_STR) return v;
  Value out;
  out.type = VAL_STR;
  out.num = 0.0;
  format_double(v.num, out.str, SB_STR_CAP);
  return out;
}

static int str_looks_numeric(const char *text) {
  if (text[0] == 0) return 0;
  if (strcmp(text, "NaN") == 0) return 1;
  char *end = NULL;
  strtod(text, &end);
  if (end == text) return 0;
  while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r') end++;
  return *end == 0;
}

static int looks_numeric(Value v) {
  if (v.type == VAL_NUM) return 1;
  char text[SB_STR_CAP];
  s_str_into(v, text, sizeof text);
  char trimmed[SB_STR_CAP];
  str_trim_copy(text, trimmed, sizeof trimmed);
  return str_looks_numeric(trimmed);
}

static int both_numeric(Value a, Value b) { return looks_numeric(a) && looks_numeric(b); }

int sb_truthy(Value v) {
  if (v.type == VAL_NUM) return v.num != 0 && !isnan(v.num);
  return v.str[0] != 0;
}

static int is_whole(Value v) {
  if (v.type == VAL_NUM) return !isnan(v.num) && !isinf(v.num) && v.num == floor(v.num);
  char text[SB_STR_CAP];
  s_str_into(v, text, sizeof text);
  char trimmed[SB_STR_CAP];
  str_trim_copy(text, trimmed, sizeof trimmed);
  if (trimmed[0] == 0) return 0;
  char *end = NULL;
  double n = strtod(trimmed, &end);
  if (end == trimmed) return 0;
  while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r') end++;
  if (*end != 0) return 0;
  return !isnan(n) && !isinf(n) && n == floor(n);
}

Value s_gt(Value a, Value b) {
  if (both_numeric(a, b)) return N(s_numd(a) > s_numd(b) ? 1 : 0);
  char sa[SB_STR_CAP], sb[SB_STR_CAP];
  s_str_into(s_str(a), sa, sizeof sa);
  s_str_into(s_str(b), sb, sizeof sb);
  return N(strcmp(sa, sb) > 0 ? 1 : 0);
}

Value s_lt(Value a, Value b) {
  if (both_numeric(a, b)) return N(s_numd(a) < s_numd(b) ? 1 : 0);
  char sa[SB_STR_CAP], sb[SB_STR_CAP];
  s_str_into(s_str(a), sa, sizeof sa);
  s_str_into(s_str(b), sb, sizeof sb);
  return N(strcmp(sa, sb) < 0 ? 1 : 0);
}

static int ci_eq(const char *a, const char *b) {
  while (*a && *b) {
    char ca = *a, cb = *b;
    if (ca >= 'A' && ca <= 'Z') ca = (char)(ca + 32);
    if (cb >= 'A' && cb <= 'Z') cb = (char)(cb + 32);
    if (ca != cb) return 0;
    a++;
    b++;
  }
  return *a == 0 && *b == 0;
}

Value s_eq(Value a, Value b) {
  if (both_numeric(a, b)) {
    double x = s_numd(a), y = s_numd(b);
    if (isnan(x) || isnan(y)) return N(0);
    return N(x == y ? 1 : 0);
  }
  char sa[SB_STR_CAP], sb[SB_STR_CAP];
  s_str_into(s_str(a), sa, sizeof sa);
  s_str_into(s_str(b), sb, sizeof sb);
  return N(ci_eq(sa, sb) ? 1 : 0);
}

Value s_add(Value a, Value b) { return N(s_numd(a) + s_numd(b)); }
Value s_sub(Value a, Value b) { return N(s_numd(a) - s_numd(b)); }
Value s_mul(Value a, Value b) { return N(s_numd(a) * s_numd(b)); }

Value s_div(Value a, Value b) {
  double bn = s_numd(b), an = s_numd(a);
  if (bn == 0) {
    if (isnan(an)) return S("NaN");
    return mkstr(an < 0 ? "-Infinity" : "Infinity");
  }
  return N(an / bn);
}

static double rand01(void) { return (double)rand() / ((double)RAND_MAX + 1.0); }

Value s_random(Value a, Value b) {
  double lo = s_numd(a), hi = s_numd(b), tmp;
  if (hi < lo) {
    tmp = lo;
    lo = hi;
    hi = tmp;
  }
  if (is_whole(a) && is_whole(b)) {
    return N(floor(rand01() * (floor(hi) - ceil(lo) + 1.0)) + ceil(lo));
  }
  return N(rand01() * (hi - lo) + lo);
}

Value s_and(Value a, Value b) { return N(sb_truthy(a) && sb_truthy(b) ? 1 : 0); }
Value s_or(Value a, Value b) { return N(sb_truthy(a) || sb_truthy(b) ? 1 : 0); }
Value s_not(Value v) { return N(sb_truthy(v) ? 0 : 1); }

Value s_join(Value a, Value b) {
  char sa[SB_STR_CAP], sb[SB_STR_CAP], out[SB_STR_CAP * 2];
  s_str_into(s_str(a), sa, sizeof sa);
  s_str_into(s_str(b), sb, sizeof sb);
  snprintf(out, sizeof out, "%s%s", sa, sb);
  Value r;
  r.type = VAL_STR;
  r.num = 0.0;
  snprintf(r.str, SB_STR_CAP, "%s", out);
  return r;
}

Value s_letter(Value index, Value text) {
  char str[SB_STR_CAP];
  s_str_into(s_str(text), str, sizeof str);
  double i = s_numd(index);
  Value r;
  r.type = VAL_STR;
  r.num = 0.0;
  r.str[0] = 0;
  if (!isfinite(i) || i < 1) return r;
  size_t len = strlen(str);
  if ((double)i > (double)len) return r;
  r.str[0] = str[(size_t)i - 1];
  r.str[1] = 0;
  return r;
}

Value s_length(Value v) {
  char str[SB_STR_CAP];
  s_str_into(s_str(v), str, sizeof str);
  return N((double)strlen(str));
}

static void lower_copy(const char *src, char *dst, size_t cap) {
  size_t i = 0;
  while (src[i] && i + 1 < cap) {
    char c = src[i];
    if (c >= 'A' && c <= 'Z') c = (char)(c + 32);
    dst[i] = c;
    i++;
  }
  dst[i] = 0;
}

Value s_contains(Value haystack, Value needle) {
  char h[SB_STR_CAP], n[SB_STR_CAP];
  s_str_into(s_str(haystack), h, sizeof h);
  s_str_into(s_str(needle), n, sizeof n);
  char hl[SB_STR_CAP], nl[SB_STR_CAP];
  lower_copy(h, hl, sizeof hl);
  lower_copy(n, nl, sizeof nl);
  return N(strstr(hl, nl) != NULL ? 1 : 0);
}

Value s_mod(Value a, Value b) {
  double an = s_numd(a), bn = s_numd(b);
  if (bn == 0) return N(NAN);
  return N(an - bn * floor(an / bn));
}

Value s_round(Value v) { return N(floor(s_numd(v) + 0.5)); }

Value s_mathop(Value op, Value value) {
  char o[SB_STR_CAP];
  s_str_into(s_str(op), o, sizeof o);
  double n = s_numd(value);
  double rad = n * 3.14159265358979323846 / 180.0;
  double deg = 180.0 / 3.14159265358979323846;
  if (strcmp(o, "abs") == 0) return N(fabs(n));
  if (strcmp(o, "ceiling") == 0) return N(ceil(n));
  if (strcmp(o, "floor") == 0) return N(floor(n));
  if (strcmp(o, "sqrt") == 0) return N(n >= 0 ? sqrt(n) : NAN);
  if (strcmp(o, "sin") == 0) return N(sin(rad));
  if (strcmp(o, "cos") == 0) return N(cos(rad));
  if (strcmp(o, "tan") == 0) return N(tan(rad));
  if (strcmp(o, "asin") == 0) return N(n >= -1 && n <= 1 ? asin(n) * deg : NAN);
  if (strcmp(o, "acos") == 0) return N(n >= -1 && n <= 1 ? acos(n) * deg : NAN);
  if (strcmp(o, "atan") == 0) return N(atan(n) * deg);
  if (strcmp(o, "ln") == 0) return N(n > 0 ? log(n) : NAN);
  if (strcmp(o, "log") == 0) return N(n > 0 ? log10(n) : NAN);
  if (strcmp(o, "e ^") == 0 || strcmp(o, "e^") == 0) return N(exp(n));
  if (strcmp(o, "10 ^") == 0 || strcmp(o, "10^") == 0) return N(pow(10, n));
  return N(0);
}

Value repeat_count(Value v) {
  double t = floor(s_numd(v) + 0.5);
  if (t < 0) t = 0;
  return N(t);
}

/* ------------------------------------------------------------------ */
/* warnings                                                            */
/* ------------------------------------------------------------------ */

void sb_warn(Rt *rt, const char *message) {
  if (rt == NULL) {
    fprintf(stderr, "warning: %s\n", message);
    return;
  }
  for (int i = 0; i < rt->nwarned; i++) {
    if (strcmp(rt->warned[i].text, message) == 0) return;
  }
  if (rt->nwarned >= rt->cap_warned) {
    rt->cap_warned = rt->cap_warned ? rt->cap_warned * 2 : 16;
    rt->warned = (WarnEntry *)realloc(rt->warned, (size_t)rt->cap_warned * sizeof(WarnEntry));
  }
  rt->warned[rt->nwarned].text = message;
  rt->nwarned++;
  fprintf(stderr, "warning: %s\n", message);
}

void sb_warnf(Rt *rt, const char *fmt, ...) {
  char buf[512];
  va_list ap;
  va_start(ap, fmt);
  vsnprintf(buf, sizeof buf, fmt, ap);
  va_end(ap);
  sb_warn(rt, xstrdup(buf));
}

Value sb_unsupported(Rt *rt, const char *opcode) {
  sb_warnf(rt, "block '%s' is not supported by this conversion", opcode);
  Value r;
  r.type = VAL_STR;
  r.num = 0.0;
  r.str[0] = 0;
  return r;
}

/* ------------------------------------------------------------------ */
/* list helpers                                                        */
/* ------------------------------------------------------------------ */

static int list_pos(ListSlot *list, Value index) {
  if (list == NULL) return -1;
  int size = list->count;
  char text[SB_STR_CAP];
  s_str_into(s_str(index), text, sizeof text);
  if (strcmp(text, "last") == 0) return size ? size - 1 : -1;
  double k = s_numd(index);
  if (!isfinite(k) || k == 0) return -1;
  int ki = (int)k;
  int pos = ki > 0 ? ki - 1 : size + ki;
  return (pos >= 0 && pos < size) ? pos : -1;
}

static void list_reserve(ListSlot *list, int need) {
  if (list->cap >= need) return;
  int cap = list->cap ? list->cap * 2 : 8;
  while (cap < need) cap *= 2;
  list->items = (Value *)realloc(list->items, (size_t)cap * sizeof(Value));
  list->cap = cap;
}

Value list_item(ListSlot *list, Value index) {
  int pos = list_pos(list, index);
  if (pos < 0) {
    Value r;
    r.type = VAL_STR;
    r.num = 0.0;
    r.str[0] = 0;
    return r;
  }
  return list->items[pos];
}

void list_delete(ListSlot *list, Value index) {
  if (list == NULL) return;
  char text[SB_STR_CAP];
  s_str_into(s_str(index), text, sizeof text);
  if (strcmp(text, "all") == 0) {
    list->count = 0;
    return;
  }
  int pos = list_pos(list, index);
  if (pos < 0) return;
  memmove(&list->items[pos], &list->items[pos + 1], (size_t)(list->count - pos - 1) * sizeof(Value));
  list->count--;
}

void list_clear(ListSlot *list) {
  if (list) list->count = 0;
}

void list_add(ListSlot *list, Value item) {
  if (list == NULL) return;
  list_reserve(list, list->count + 1);
  list->items[list->count++] = item;
}

void list_insert(ListSlot *list, Value index, Value item) {
  if (list == NULL) return;
  char text[SB_STR_CAP];
  s_str_into(s_str(index), text, sizeof text);
  if (strcmp(text, "last") == 0) {
    list_add(list, item);
    return;
  }
  double k = s_numd(index);
  if (!isfinite(k) || k < 1 || k > (double)list->count + 1) return;
  int at = (int)k - 1;
  list_reserve(list, list->count + 1);
  memmove(&list->items[at + 1], &list->items[at], (size_t)(list->count - at) * sizeof(Value));
  list->items[at] = item;
  list->count++;
}

void list_replace(ListSlot *list, Value index, Value item) {
  int pos = list_pos(list, index);
  if (pos >= 0) list->items[pos] = item;
}

Value list_index_of(ListSlot *list, Value item) {
  if (list == NULL) return S("");
  for (int i = 0; i < list->count; i++) {
    if (sb_truthy(s_eq(list->items[i], item))) return N((double)(i + 1));
  }
  return S("");
}

Value list_length(Value v) {
  if (v.type == VAL_STR) return N((double)strlen(v.str));
  return N(0);
}

Value list_contains(ListSlot *list, Value item) {
  if (list == NULL) return N(0);
  for (int i = 0; i < list->count; i++) {
    if (sb_truthy(s_eq(list->items[i], item))) return N(1);
  }
  return N(0);
}

Value list_contents(ListSlot *list) {
  Value r;
  r.type = VAL_STR;
  r.num = 0.0;
  r.str[0] = 0;
  if (list == NULL) return r;
  size_t used = 0;
  for (int i = 0; i < list->count; i++) {
    char part[SB_STR_CAP];
    s_str_into(s_str(list->items[i]), part, sizeof part);
    if (i > 0 && used + 2 < SB_STR_CAP) {
      r.str[used++] = ',';
      r.str[used++] = ' ';
    }
    size_t len = strlen(part);
    if (used + len >= SB_STR_CAP) len = SB_STR_CAP - 1 - used;
    memcpy(r.str + used, part, len);
    used += len;
    r.str[used] = 0;
    if (used >= SB_STR_CAP - 1) break;
  }
  return r;
}

/* ------------------------------------------------------------------ */
/* variable / list lookup                                              */
/* ------------------------------------------------------------------ */

Value *sb_var(Rt *rt, const char *name) {
  for (int i = 0; i < rt->stage_def->nvars; i++) {
    if (strcmp(rt->stage_def->vars[i].name, name) == 0) return &rt->stage_def->vars[i].value;
  }
  sb_warnf(rt, "variable '%s' not found (using scratch slot)", name);
  return &rt->orphan;
}

Value *sb_var_ctx(Actor *ctx, const char *name) {
  for (int i = 0; i < ctx->nvars; i++) {
    if (strcmp(ctx->vars[i].name, name) == 0) return &ctx->vars[i].value;
  }
  sb_warnf(ctx->rt, "variable '%s' not found (using scratch slot)", name);
  return &ctx->rt->orphan;
}

ListSlot *sb_list(Rt *rt, const char *name) {
  for (int i = 0; i < rt->stage_def->nlists; i++) {
    if (strcmp(rt->stage_def->lists[i].name, name) == 0) return &rt->stage_def->lists[i];
  }
  sb_warnf(rt, "list '%s' not found (using scratch slot)", name);
  return &rt->orphan_list;
}

ListSlot *sb_list_ctx(Actor *ctx, const char *name) {
  for (int i = 0; i < ctx->nlists; i++) {
    if (strcmp(ctx->lists[i].name, name) == 0) return &ctx->lists[i];
  }
  sb_warnf(ctx->rt, "list '%s' not found (using scratch slot)", name);
  return &ctx->rt->orphan_list;
}

/* ------------------------------------------------------------------ */
/* costume / actor geometry                                            */
/* ------------------------------------------------------------------ */

static CostumeDef *actor_costume(Actor *actor) {
  int n = actor->target->ncostumes;
  if (n <= 0) return NULL;
  int idx = (int)trunc(actor->current_costume);
  idx = ((idx % n) + n) % n;
  return &actor->target->costumes[idx];
}

static double costume_w(CostumeDef *c) {
  if (c->loaded && !c->missing && c->tex) return c->disp_w;
  return 32.0;
}

static double costume_h(CostumeDef *c) {
  if (c->loaded && !c->missing && c->tex) return c->disp_h;
  return 32.0;
}

static void actor_half_size(Actor *actor, double *hw, double *hh) {
  CostumeDef *c = actor_costume(actor);
  if (!c) {
    *hw = 0;
    *hh = 0;
    return;
  }
  double scale = actor->size / 100.0;
  *hw = costume_w(c) * scale / 2.0;
  *hh = costume_h(c) * scale / 2.0;
}

typedef struct {
  int left;
  int top;
  int width;
  int height;
  int right;
  int bottom;
} SbRect;

static SbRect actor_rect(Actor *actor) {
  CostumeDef *c = actor_costume(actor);
  if (c && c->loaded && c->alpha && c->tight_r > c->tight_l) {
    /* tight opaque bounds, like Scratch's pixel-based collision */
    double scale = actor->size / 100.0;
    double res = c->resolution > 0 ? c->resolution : 1;
    double tl = c->tight_l / res, tt = c->tight_t / res;
    double tr = c->tight_r / res, tb = c->tight_b / res;
    SbRect r;
    r.left = (int)(actor->x + (tl - c->cx) * scale);
    r.top = (int)(actor->y + (c->cy - tb) * scale);
    r.width = (int)((tr - tl) * scale);
    r.height = (int)((tb - tt) * scale);
    if (r.width < 1) r.width = 1;
    if (r.height < 1) r.height = 1;
    r.right = r.left + r.width;
    r.bottom = r.top + r.height;
    return r;
  }
  double hw, hh;
  actor_half_size(actor, &hw, &hh);
  SbRect r;
  r.left = (int)(actor->x - hw);
  r.top = (int)(actor->y - hh);
  r.width = (int)(hw * 2);
  r.height = (int)(hh * 2);
  if (r.width < 1) r.width = 1;
  if (r.height < 1) r.height = 1;
  r.right = r.left + r.width;
  r.bottom = r.top + r.height;
  return r;
}

static int costume_alpha_ready(Rt *rt, CostumeDef *c) {
  if (!c) return 0;
  if (!c->loaded) costume_load(rt, c);
  return c->alpha != NULL;
}

static int actor_opaque_at(Rt *rt, Actor *actor, double sx, double sy) {
  CostumeDef *c = actor_costume(actor);
  if (!costume_alpha_ready(rt, c)) return 0;
  double scale = actor->size / 100.0;
  if (scale <= 0) return 0;
  double res = c->resolution > 0 ? c->resolution : 1;
  int ix = (int)floor(((sx - actor->x) / scale + c->cx) * res);
  int iy = (int)floor((c->cy - (sy - actor->y) / scale) * res);
  if (ix < 0 || iy < 0 || ix >= c->tex_w || iy >= c->tex_h) return 0;
  return c->alpha[(size_t)iy * c->tex_w + ix];
}

static int actors_overlap(Rt *rt, Actor *a, Actor *b) {
  CostumeDef *ca = actor_costume(a);
  CostumeDef *cb = actor_costume(b);
  if (!costume_alpha_ready(rt, ca) || !costume_alpha_ready(rt, cb)) {
    SbRect ra = actor_rect(a);
    SbRect rb = actor_rect(b);
    return ra.left < rb.right && ra.right > rb.left && ra.top < rb.bottom && ra.bottom > rb.top;
  }
  double sa = a->size / 100.0;
  double sb = b->size / 100.0;
  if (sa <= 0 || sb <= 0) return 0;
  double resa = ca->resolution > 0 ? ca->resolution : 1;
  double ax = a->x - ca->cx * sa, ay = a->y + ca->cy * sa;
  double bx = b->x - cb->cx * sb, by = b->y + cb->cy * sb;
  double pitch = sa / resa;
  if (pitch <= 0) return 0;
  /* stage -> texel: b_texel = a_texel - d */
  int dx = (int)lround((bx - ax) / pitch);
  int dy = (int)lround((ay - by) / pitch);
  int x0 = ca->tight_l > dx + cb->tight_l ? ca->tight_l : dx + cb->tight_l;
  int x1 = ca->tight_r < dx + cb->tight_r ? ca->tight_r : dx + cb->tight_r;
  int y0 = ca->tight_t > dy + cb->tight_t ? ca->tight_t : dy + cb->tight_t;
  int y1 = ca->tight_b < dy + cb->tight_b ? ca->tight_b : dy + cb->tight_b;
  for (int y = y0; y < y1; y++) {
    const Uint8 *rowa = ca->alpha + (size_t)y * ca->tex_w;
    const Uint8 *rowb = cb->alpha + (size_t)(y - dy) * cb->tex_w;
    for (int x = x0; x < x1; x++) {
      if (rowa[x] && rowb[x - dx]) return 1;
    }
  }
  return 0;
}

/* ------------------------------------------------------------------ */
/* motion                                                              */
/* ------------------------------------------------------------------ */

double sb_norm_dir(double direction) {
  double d = fmod(direction + 180.0, 360.0);
  if (d < 0) d += 360.0;
  return d - 180.0;
}

void sb_move(Rt *rt, Actor *actor, Value steps) {
  (void)rt;
  double amount = s_numd(steps);
  double rad = actor->direction * 3.14159265358979323846 / 180.0;
  actor->x += amount * sin(rad);
  actor->y += amount * cos(rad);
}

static Actor *find_sprite(Rt *rt, const char *name) {
  for (int i = 0; i < rt->nlayers; i++) {
    Actor *a = rt->layers[i];
    if (!a->dead && strcmp(a->target->name, name) == 0) return a;
  }
  return NULL;
}

static Actor *visible_actor(Rt *rt, const char *name, Actor *exclude) {
  for (int i = rt->nlayers - 1; i >= 0; i--) {
    Actor *a = rt->layers[i];
    if (a == exclude || a->dead || !a->visible) continue;
    if (strcmp(a->target->name, name) == 0) return a;
  }
  return NULL;
}

double sb_tx(Rt *rt, Value ref) {
  char name[SB_STR_CAP];
  s_str_into(s_str(ref), name, sizeof name);
  if (strcmp(name, "_mouse_") == 0) return rt->mouse_x;
  Actor *t = find_sprite(rt, name);
  return t ? t->x : 0.0;
}

double sb_ty(Rt *rt, Value ref) {
  char name[SB_STR_CAP];
  s_str_into(s_str(ref), name, sizeof name);
  if (strcmp(name, "_mouse_") == 0) return rt->mouse_y;
  Actor *t = find_sprite(rt, name);
  return t ? t->y : 0.0;
}

void sb_point_towards(Rt *rt, Actor *actor, Value ref) {
  double tx = sb_tx(rt, ref), ty = sb_ty(rt, ref);
  actor->direction = sb_norm_dir(atan2(tx - actor->x, ty - actor->y) * 180.0 / 3.14159265358979323846);
}

void sb_goto(Rt *rt, Actor *actor, Value ref) {
  char name[SB_STR_CAP];
  s_str_into(s_str(ref), name, sizeof name);
  if (strcmp(name, "_mouse_") == 0) {
    actor->x = rt->mouse_x;
    actor->y = rt->mouse_y;
  } else if (strcmp(name, "_random_") == 0) {
    actor->x = rand01() * 480.0 - 240.0;
    actor->y = rand01() * 360.0 - 180.0;
  } else {
    Actor *target = find_sprite(rt, name);
    if (!target) {
      sb_warnf(rt, "goto target '%s' not found", name);
      return;
    }
    actor->x = target->x;
    actor->y = target->y;
  }
}

void sb_bounce(Rt *rt, Actor *actor) {
  (void)rt;
  double hw, hh;
  actor_half_size(actor, &hw, &hh);
  if (hw * 2 >= 480 || hh * 2 >= 360) return;
  double left = -240 + hw, right = 240 - hw;
  double bottom = -180 + hh, top = 180 - hh;
  int hit_x = actor->x < left || actor->x > right;
  int hit_y = actor->y < bottom || actor->y > top;
  if (!hit_x && !hit_y) return;
  actor->x = actor->x < left ? left : (actor->x > right ? right : actor->x);
  actor->y = actor->y < bottom ? bottom : (actor->y > top ? top : actor->y);
  double direction = actor->direction;
  if (hit_x) direction = -direction;
  if (hit_y) direction = 180 - direction;
  actor->direction = sb_norm_dir(direction);
}

/* ------------------------------------------------------------------ */
/* looks                                                               */
/* ------------------------------------------------------------------ */

Value sb_clamp_size(Value v) {
  double n = s_numd(v);
  if (n < 15) n = 15;
  if (n > 150) n = 150;
  return N(n);
}

Value sb_clamp_volume(Value v) {
  double n = s_numd(v);
  if (n < 0) n = 0;
  if (n > 100) n = 100;
  return N(n);
}

static double effect_get(Actor *actor, const char *effect) {
  if (strcmp(effect, "ghost") == 0) return actor->fx_ghost;
  if (strcmp(effect, "color") == 0) return actor->fx_color;
  if (strcmp(effect, "fisheye") == 0) return actor->fx_fisheye;
  if (strcmp(effect, "whirl") == 0) return actor->fx_whirl;
  if (strcmp(effect, "pixelate") == 0) return actor->fx_pixelate;
  if (strcmp(effect, "mosaic") == 0) return actor->fx_mosaic;
  if (strcmp(effect, "brightness") == 0) return actor->fx_brightness;
  return 0.0;
}

static void effect_set(Actor *actor, const char *effect, double value) {
  if (strcmp(effect, "ghost") == 0) actor->fx_ghost = value;
  else if (strcmp(effect, "color") == 0) actor->fx_color = value;
  else if (strcmp(effect, "fisheye") == 0) actor->fx_fisheye = value;
  else if (strcmp(effect, "whirl") == 0) actor->fx_whirl = value;
  else if (strcmp(effect, "pixelate") == 0) actor->fx_pixelate = value;
  else if (strcmp(effect, "mosaic") == 0) actor->fx_mosaic = value;
  else if (strcmp(effect, "brightness") == 0) actor->fx_brightness = value;
}

void sb_set_effect(Rt *rt, Actor *actor, Value effect, Value value) {
  char name[SB_STR_CAP];
  s_str_into(s_str(effect), name, sizeof name);
  effect_set(actor, name, s_numd(value));
  if (strcmp(name, "ghost") != 0) {
    sb_warnf(rt, "visual effect '%s' is stored but not rendered by this runtime", name);
  }
}

void sb_change_effect(Rt *rt, Actor *actor, Value effect, Value delta) {
  char name[SB_STR_CAP];
  s_str_into(s_str(effect), name, sizeof name);
  sb_set_effect(rt, actor, effect, N(effect_get(actor, name) + s_numd(delta)));
}

void sb_clear_effects(Rt *rt, Actor *actor) {
  (void)rt;
  actor->fx_ghost = actor->fx_color = actor->fx_fisheye = 0;
  actor->fx_whirl = actor->fx_pixelate = actor->fx_mosaic = actor->fx_brightness = 0;
}

static int layer_index(Rt *rt, Actor *actor) {
  for (int i = 0; i < rt->nlayers; i++) {
    if (rt->layers[i] == actor) return i;
  }
  return -1;
}

static void layers_reserve(Rt *rt) {
  if (rt->nlayers >= rt->cap_layers) {
    rt->cap_layers = rt->cap_layers ? rt->cap_layers * 2 : 32;
    rt->layers = (Actor **)realloc(rt->layers, (size_t)rt->cap_layers * sizeof(Actor *));
  }
}

void sb_go_to_front(Rt *rt, Actor *actor) {
  int i = layer_index(rt, actor);
  if (i == -1) return;
  memmove(&rt->layers[i], &rt->layers[i + 1], (size_t)(rt->nlayers - i - 1) * sizeof(Actor *));
  rt->layers[rt->nlayers - 1] = actor;
}

void sb_go_to_back(Rt *rt, Actor *actor) {
  int i = layer_index(rt, actor);
  if (i == -1) return;
  memmove(&rt->layers[1], &rt->layers[0], (size_t)i * sizeof(Actor *));
  rt->layers[0] = actor;
}

void sb_go_layer(Rt *rt, Actor *actor, Value delta) {
  int index = layer_index(rt, actor);
  if (index == -1) return;
  int new_index = index + (int)s_numd(delta);
  if (new_index < 0) new_index = 0;
  if (new_index > rt->nlayers - 1) new_index = rt->nlayers - 1;
  if (new_index == index) return;
  if (new_index > index) {
    memmove(&rt->layers[index], &rt->layers[index + 1], (size_t)(new_index - index) * sizeof(Actor *));
    rt->layers[new_index] = actor;
  } else {
    memmove(&rt->layers[index], &rt->layers[index + 1], (size_t)(rt->nlayers - index - 1) * sizeof(Actor *));
    memmove(&rt->layers[new_index + 1], &rt->layers[new_index], (size_t)(index - new_index) * sizeof(Actor *));
    rt->layers[new_index] = actor;
  }
}

static void fire_backdrop_hats(Rt *rt);

void sb_set_backdrop(Rt *rt, Value ref) {
  TargetDef *stage = rt->stage_def;
  if (stage->ncostumes <= 0) return;
  char text[SB_STR_CAP];
  s_str_into(s_str(ref), text, sizeof text);
  int previous = stage->current_costume;
  int found = 0;
  for (int i = 0; i < stage->ncostumes; i++) {
    if (strcmp(text, stage->costumes[i].name) == 0 || strcmp(text, stage->costumes[i].id) == 0) {
      stage->current_costume = i;
      found = 1;
      break;
    }
  }
  if (!found) {
    if (str_looks_numeric(text)) {
      int index = (int)strtod(text, NULL) - 1;
      if (index < 0) index = 0;
      if (index > stage->ncostumes - 1) index = stage->ncostumes - 1;
      stage->current_costume = index;
    } else {
      sb_warnf(rt, "unknown backdrop '%s'", text);
      return;
    }
  }
  if (stage->current_costume != previous) fire_backdrop_hats(rt);
}

void sb_next_backdrop(Rt *rt) {
  TargetDef *stage = rt->stage_def;
  if (stage->ncostumes <= 0) return;
  stage->current_costume = (stage->current_costume + 1) % stage->ncostumes;
  fire_backdrop_hats(rt);
}

void sb_set_costume(Rt *rt, Actor *actor, Value ref) {
  TargetDef *target = actor->target;
  if (target->ncostumes <= 0) return;
  char text[SB_STR_CAP];
  s_str_into(s_str(ref), text, sizeof text);
  for (int i = 0; i < target->ncostumes; i++) {
    if (strcmp(text, target->costumes[i].name) == 0 || strcmp(text, target->costumes[i].id) == 0) {
      actor->current_costume = i;
      return;
    }
  }
  if (str_looks_numeric(text)) {
    int index = (int)strtod(text, NULL) - 1;
    if (index < 0) index = 0;
    if (index > target->ncostumes - 1) index = target->ncostumes - 1;
    actor->current_costume = index;
    return;
  }
  sb_warnf(rt, "unknown costume '%s' for sprite '%s'", text, target->name);
}

void sb_next_costume(Actor *actor) {
  int n = actor->target->ncostumes;
  if (n > 0) {
    int idx = (int)trunc(actor->current_costume) + 1;
    actor->current_costume = idx % n;
  }
}

void sb_set_rotation_style(Actor *actor, Value style) {
  char text[SB_STR_CAP];
  s_str_into(s_str(style), text, sizeof text);
  if (strcmp(text, "all around") == 0) actor->rotation_style = "all around";
  else if (strcmp(text, "left-right") == 0) actor->rotation_style = "left-right";
  else if (strcmp(text, "don't rotate") == 0) actor->rotation_style = "don't rotate";
  else sb_warnf(actor->rt, "unknown rotation style '%s'", text);
}

void sb_set_volume(Actor *actor, Value v) { actor->volume = s_numd(sb_clamp_volume(v)); }

void sb_change_volume(Actor *actor, Value delta) {
  actor->volume = s_numd(sb_clamp_volume(N(actor->volume + s_numd(delta))));
}

void sb_set_say(Actor *actor, Value v) {
  actor->say = s_str(v);
  actor->has_say = 1;
}

void sb_say_off(Actor *actor) { actor->has_say = 0; }

void sb_set_think(Actor *actor, Value v) {
  actor->think = s_str(v);
  actor->has_think = 1;
}

void sb_think_off(Actor *actor) { actor->has_think = 0; }

/* ------------------------------------------------------------------ */
/* sound                                                               */
/* ------------------------------------------------------------------ */

static SoundDef *find_sound(TargetDef *target, const char *name) {
  for (int i = 0; i < target->nsounds; i++) {
    if (strcmp(target->sounds[i].name, name) == 0) return &target->sounds[i];
  }
  return NULL;
}

int sb_play_sound(Rt *rt, Actor *actor, Value name) {
  char text[SB_STR_CAP];
  s_str_into(s_str(name), text, sizeof text);
  SoundDef *sound = find_sound(actor->target, text);
  if (!sound) {
    sb_warnf(rt, "sound '%s' not found for '%s'", text, actor->target->name);
    return -1;
  }
  if (!sound->loaded) {
    sound->loaded = 1;
    char path[1024];
    if (asset_path(rt, sound->file, path, sizeof path)) {
      sound->chunk = Mix_LoadWAV(path);
      if (!sound->chunk) sb_warnf(rt, "sound file '%s' failed to load", sound->file);
    } else {
      sb_warnf(rt, "sound file '%s' not found", sound->file);
    }
  }
  if (!sound->chunk) return -1;
  int channel = Mix_PlayChannel(-1, sound->chunk, 0);
  if (channel >= 0) {
    int vol = (int)(actor->volume / 100.0 * MIX_MAX_VOLUME);
    Mix_Volume(channel, vol);
  }
  return channel;
}

void sb_play_until_done(Rt *rt, Actor *actor, Value name) {
  int channel = sb_play_sound(rt, actor, name);
  if (channel < 0) return;
  while (Mix_Playing(channel)) sb_yield(rt);
}

void sb_stop_all_sounds(Rt *rt) {
  (void)rt;
  Mix_HaltChannel(-1);
}

void sb_set_sound_effect(Rt *rt, Actor *actor, Value effect, Value value) {
  (void)rt;
  char name[SB_STR_CAP];
  s_str_into(s_str(effect), name, sizeof name);
  if (strcmp(name, "PITCH") == 0) actor->sx_pitch = s_numd(value);
  else if (strcmp(name, "PAN") == 0) actor->sx_pan = s_numd(value);
}

void sb_change_sound_effect(Rt *rt, Actor *actor, Value effect, Value delta) {
  char name[SB_STR_CAP];
  s_str_into(s_str(effect), name, sizeof name);
  sb_warnf(rt, "sound effect '%s' has no audible effect in this runtime", name);
  if (strcmp(name, "PITCH") == 0) actor->sx_pitch += s_numd(delta);
  else if (strcmp(name, "PAN") == 0) actor->sx_pan += s_numd(delta);
}

void sb_clear_sound_effects(Actor *actor) {
  actor->sx_pitch = 0;
  actor->sx_pan = 0;
}

/* ------------------------------------------------------------------ */
/* sensing                                                             */
/* ------------------------------------------------------------------ */

Value sb_key_down(Rt *rt, Value key) {
  char name[SB_STR_CAP];
  s_str_into(s_str(key), name, sizeof name);
  if (strcmp(name, "any") == 0) return N(rt->ndown_keys > 0 ? 1 : 0);
  for (int i = 0; i < rt->ndown_keys; i++) {
    if (strcmp(rt->down_keys[i], name) == 0) return N(1);
  }
  return N(0);
}

Value sb_touching(Rt *rt, Actor *actor, Value ref) {
  SbRect rect = actor_rect(actor);
  char name[SB_STR_CAP];
  s_str_into(s_str(ref), name, sizeof name);
  if (strcmp(name, "_edge_") == 0) {
    return N(rect.left <= -240 || rect.right >= 240 || rect.top >= 180 || rect.bottom <= -180 ? 1 : 0);
  }
  if (strcmp(name, "_mouse_") == 0) {
    return N(actor_opaque_at(rt, actor, rt->mouse_x, rt->mouse_y));
  }
  Actor *other = visible_actor(rt, name, actor);
  if (!other) return N(0);
  return N(actors_overlap(rt, actor, other));
}

static int parse_colour(Value text_v, int *r, int *g, int *b) {
  char text[SB_STR_CAP];
  s_str_into(s_str(text_v), text, sizeof text);
  size_t len = strlen(text);
  if (text[0] != '#') return 0;
  char h[3];
  h[2] = 0;
  if (len == 4) {
    h[0] = h[1] = text[1];
    *r = (int)strtol(h, NULL, 16);
    h[0] = h[1] = text[2];
    *g = (int)strtol(h, NULL, 16);
    h[0] = h[1] = text[3];
    *b = (int)strtol(h, NULL, 16);
    return 1;
  }
  if (len == 7) {
    h[0] = text[1];
    h[1] = text[2];
    *r = (int)strtol(h, NULL, 16);
    h[0] = text[3];
    h[1] = text[4];
    *g = (int)strtol(h, NULL, 16);
    h[0] = text[5];
    h[1] = text[6];
    *b = (int)strtol(h, NULL, 16);
    return 1;
  }
  return 0;
}

static SDL_Texture *probe_texture(Rt *rt) {
  if (!rt->probe_tex) {
    rt->probe_tex = SDL_CreateTexture((SDL_Renderer *)rt->renderer, SDL_PIXELFORMAT_RGBA32,
                                      SDL_TEXTUREACCESS_TARGET, 480, 360);
  }
  return (SDL_Texture *)rt->probe_tex;
}

static Uint8 *render_actor_buffer(Rt *rt, Actor *actor) {
  CostumeDef *c = actor_costume(actor);
  if (!c) return NULL;
  SDL_Texture *tex = costume_load(rt, c) ? (SDL_Texture *)c->tex : (SDL_Texture *)rt->fallback_tex;
  if (!tex) return NULL;
  SDL_Texture *probe = probe_texture(rt);
  if (!probe) return NULL;
  if (!rt->probe_buf) rt->probe_buf = malloc((size_t)480 * 360 * 4);
  SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
  SDL_Texture *prev = SDL_GetRenderTarget(r);
  SDL_SetRenderTarget(r, probe);
  SDL_SetRenderDrawColor(r, 0, 0, 0, 0);
  SDL_RenderClear(r);
  draw_actor(r, rt, actor, 1.0);
  SDL_RenderReadPixels(r, NULL, SDL_PIXELFORMAT_RGBA32, rt->probe_buf, 480 * 4);
  SDL_SetRenderTarget(r, prev);
  Uint8 *copy = (Uint8 *)malloc((size_t)480 * 360 * 4);
  memcpy(copy, rt->probe_buf, (size_t)480 * 360 * 4);
  return copy;
}

static Uint8 *render_backdrop_buffer(Rt *rt) {
  TargetDef *stage = rt->stage_def;
  if (stage->ncostumes <= 0) return NULL;
  CostumeDef *c = &stage->costumes[stage->current_costume];
  SDL_Texture *tex = costume_load(rt, c) ? (SDL_Texture *)c->tex : NULL;
  if (!tex) return NULL;
  SDL_Texture *probe = probe_texture(rt);
  if (!probe) return NULL;
  Uint8 *buf = (Uint8 *)malloc((size_t)480 * 360 * 4);
  SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
  SDL_Texture *prev = SDL_GetRenderTarget(r);
  SDL_SetRenderTarget(r, probe);
  SDL_SetRenderDrawColor(r, 0, 0, 0, 0);
  SDL_RenderClear(r);
  SDL_Rect dst = {0, 0, 480, 360};
  SDL_RenderCopy(r, tex, NULL, &dst);
  SDL_RenderReadPixels(r, NULL, SDL_PIXELFORMAT_RGBA32, buf, 480 * 4);
  SDL_SetRenderTarget(r, prev);
  return buf;
}

typedef struct {
  int r, g, b;
} Rgb;

typedef struct {
  Uint8 **buffers;
  int count;
} LayerBuffers;

static LayerBuffers render_layers(Rt *rt) {
  LayerBuffers out;
  out.count = rt->nlayers;
  out.buffers = (Uint8 **)malloc((size_t)(rt->nlayers > 0 ? rt->nlayers : 1) * sizeof(Uint8 *));
  for (int i = 0; i < rt->nlayers; i++) {
    Actor *other = rt->layers[i];
    if (other->dead || !other->visible) {
      out.buffers[i] = NULL;
      continue;
    }
    out.buffers[i] = render_actor_buffer(rt, other);
  }
  return out;
}

static void free_layers(LayerBuffers *lb) {
  for (int i = 0; i < lb->count; i++) free(lb->buffers[i]);
  free(lb->buffers);
}

static Rgb colour_at(Rt *rt, LayerBuffers *lb, int px, int py, const Uint8 *backdrop_buf) {
  Rgb miss = {-1, -1, -1};
  if (backdrop_buf) {
    const Uint8 *p = backdrop_buf + (py * 480 + px) * 4;
    if (p[3] >= 128) {
      Rgb c = {p[0], p[1], p[2]};
      return c;
    }
  }
  for (int i = lb->count - 1; i >= 0; i--) {
    Uint8 *buf = lb->buffers[i];
    if (!buf) continue;
    const Uint8 *p = buf + (py * 480 + px) * 4;
    if (p[3] >= 128) {
      Rgb c = {p[0], p[1], p[2]};
      return c;
    }
  }
  return miss;
}

static Value probe_impl(Rt *rt, Actor *actor, Rgb first, int has_second, Rgb second) {
  Uint8 *data = render_actor_buffer(rt, actor);
  if (!data) return N(0);
  Uint8 *backdrop = render_backdrop_buffer(rt);
  LayerBuffers layers = render_layers(rt);
  for (int py = 0; py < 360; py += 4) {
    for (int px = 0; px < 480; px += 4) {
      const Uint8 *p = data + (py * 480 + px) * 4;
      if (p[3] < 128) continue;
      if (!(p[0] == first.r && p[1] == first.g && p[2] == first.b)) continue;
      Rgb at = colour_at(rt, &layers, px, py, backdrop);
      if (at.r < 0) continue;
      int match = has_second ? (at.r == second.r && at.g == second.g && at.b == second.b)
                             : (at.r == first.r && at.g == first.g && at.b == first.b);
      if (match) {
        free(data);
        free(backdrop);
        free_layers(&layers);
        return N(1);
      }
    }
  }
  free(data);
  free(backdrop);
  free_layers(&layers);
  return N(0);
}

Value sb_touching_colour(Rt *rt, Actor *actor, Value colour) {
  int r, g, b;
  if (!parse_colour(colour, &r, &g, &b)) return N(0);
  Rgb want = {r, g, b};
  return probe_impl(rt, actor, want, 0, want);
}

Value sb_colour_touching_colour(Rt *rt, Actor *actor, Value first, Value second) {
  int r1, g1, b1, r2, g2, b2;
  if (!parse_colour(first, &r1, &g1, &b1) || !parse_colour(second, &r2, &g2, &b2)) return N(0);
  Rgb c1 = {r1, g1, b1}, c2 = {r2, g2, b2};
  return probe_impl(rt, actor, c1, 1, c2);
}

Value sb_distance_to(Rt *rt, Actor *actor, Value ref) {
  return N(hypot(sb_tx(rt, ref) - actor->x, sb_ty(rt, ref) - actor->y));
}

Value sb_timer(Rt *rt) { return N(rt->timer); }
Value sb_loudness(Rt *rt) { return N(rt->loudness); }
Value sb_username(Rt *rt) { return rt->username; }
Value sb_mouse_down(Rt *rt) { return N(rt->mouse_down ? 1 : 0); }
void sb_reset_timer(Rt *rt) { rt->timer = 0; }

Value sb_costume_name(Actor *actor) {
  CostumeDef *c = actor_costume(actor);
  if (!c) return S("");
  return mkstr(c->name);
}

Value sb_of(Rt *rt, Value attribute, Value obj) {
  char attr[SB_STR_CAP], name[SB_STR_CAP];
  s_str_into(s_str(attribute), attr, sizeof attr);
  s_str_into(s_str(obj), name, sizeof name);
  if (strcmp(name, "_mouse_") == 0) {
    if (strcmp(attr, "x position") == 0) return N(rt->mouse_x);
    if (strcmp(attr, "y position") == 0) return N(rt->mouse_y);
    return N(0);
  }
  if (strcmp(attr, "backdrop") == 0) {
    TargetDef *stage = rt->stage_def;
    if (stage->ncostumes <= 0) return S("");
    return mkstr(stage->costumes[stage->current_costume].name);
  }
  Actor *actor = visible_actor(rt, name, NULL);
  if (!actor) return S("");
  if (strcmp(attr, "x position") == 0) return N(actor->x);
  if (strcmp(attr, "y position") == 0) return N(actor->y);
  if (strcmp(attr, "direction") == 0) return N(actor->direction);
  if (strcmp(attr, "size") == 0) return N(actor->size);
  if (strcmp(attr, "volume") == 0) return N(actor->volume);
  if (strcmp(attr, "costume #") == 0) return N(actor->current_costume + 1);
  if (strcmp(attr, "costume name") == 0) {
    CostumeDef *c = actor_costume(actor);
    return c ? mkstr(c->name) : S("");
  }
  if (strcmp(attr, "loudness") == 0) return N(rt->loudness);
  return S("");
}

/* ------------------------------------------------------------------ */
/* monitors                                                            */
/* ------------------------------------------------------------------ */

void sb_set_monitor_visible(Rt *rt, Value id, Value visible) {
  char text[SB_STR_CAP];
  s_str_into(s_str(id), text, sizeof text);
  for (int i = 0; i < rt->proj->nmonitors; i++) {
    if (strcmp(rt->proj->monitors[i].id, text) == 0) {
      rt->proj->monitors[i].visible = sb_truthy(visible) ? 1 : 0;
      return;
    }
  }
  sb_warnf(rt, "no monitor for id '%s'", text);
}

void sb_set_list_visible(Rt *rt, Value id, Value visible) { sb_set_monitor_visible(rt, id, visible); }

/* ------------------------------------------------------------------ */
/* threads                                                             */
/* ------------------------------------------------------------------ */

#ifdef _WIN32
static void WINAPI fiber_entry(LPVOID param) {
  Thread *t = (Thread *)param;
  t->reg->fn(t->actor, t->rt);
  t->done = 1;
  SwitchToFiber(t->rt->main_fiber);
}
#endif

static void threads_push(Rt *rt, Thread *t) {
  if (rt->nthreads >= rt->cap_threads) {
    rt->cap_threads = rt->cap_threads ? rt->cap_threads * 2 : 32;
    rt->threads = (Thread **)realloc(rt->threads, (size_t)rt->cap_threads * sizeof(Thread *));
  }
  rt->threads[rt->nthreads++] = t;
}

static Thread *spawn(Rt *rt, const ScriptReg *reg, Actor *actor, int group) {
  if (actor->dead) return NULL;
  Thread *t = (Thread *)calloc(1, sizeof(Thread));
  t->actor = actor;
  t->reg = reg;
  t->rt = rt;
  t->group = group;
  t->stepped_frame = -1;
#ifdef _WIN32
  t->fiber = CreateFiber(SB_FIBER_STACK, fiber_entry, t);
  if (!t->fiber) {
    sb_warn(rt, "failed to create fiber for script");
    free(t);
    return NULL;
  }
#endif
  threads_push(rt, t);
  return t;
}

static void spawn_regs(Rt *rt, const ScriptReg **regs, int nregs, int group) {
  int nactors = rt->nactors;
  Actor **snapshot = (Actor **)malloc((size_t)(nactors > 0 ? nactors : 1) * sizeof(Actor *));
  for (int i = 0; i < nactors; i++) snapshot[i] = rt->actors[i];
  for (int i = 0; i < nregs; i++) {
    for (int j = 0; j < nactors; j++) {
      Actor *actor = snapshot[j];
      if (actor->dead || strcmp(actor->target->name, regs[i]->sprite) != 0) continue;
      spawn(rt, regs[i], actor, group);
    }
  }
  free(snapshot);
}

static int has_live_group(Rt *rt, int group) {
  for (int i = 0; i < rt->nthreads; i++) {
    if (rt->threads[i]->group == group && !rt->threads[i]->done) return 1;
  }
  return 0;
}

void sb_yield(Rt *rt) {
#ifdef _WIN32
  SwitchToFiber(rt->main_fiber);
#else
  (void)rt;
#endif
}

void sb_wait(Rt *rt, double seconds) {
  int frames = (int)floor(seconds * rt->fps + 0.5);
  if (frames < 1) frames = 1;
  for (int i = 0; i < frames; i++) sb_yield(rt);
}

void sb_glide(Rt *rt, Actor *actor, double seconds, double x, double y) {
  int frames = (int)floor(seconds * rt->fps + 0.5);
  if (frames < 1) frames = 1;
  double x0 = actor->x, y0 = actor->y;
  for (int i = 0; i < frames; i++) {
    double t = (double)(i + 1) / (double)frames;
    actor->x = x0 + (x - x0) * t;
    actor->y = y0 + (y - y0) * t;
    sb_yield(rt);
  }
}

void sb_ask(Rt *rt, Value question) {
  rt->ask_question = s_str(question);
  rt->ask_buffer[0] = 0;
  rt->asking = 1;
  SDL_StartTextInput();
  while (rt->asking) sb_yield(rt);
  SDL_StopTextInput();
}

/* ------------------------------------------------------------------ */
/* event routes                                                        */
/* ------------------------------------------------------------------ */

static void push_route(const ScriptReg ***arr, const char ***names, int *count, int *cap, const ScriptReg *reg,
                       const char *name) {
  if (*count >= *cap) {
    *cap = *cap ? *cap * 2 : 16;
    *arr = (const ScriptReg **)realloc((void *)*arr, (size_t)*cap * sizeof(const ScriptReg *));
    *names = (const char **)realloc((void *)*names, (size_t)*cap * sizeof(const char *));
  }
  (*arr)[*count] = reg;
  (*names)[*count] = name;
  (*count)++;
}

static void build_routes(Rt *rt, const ScriptReg *scripts, int nscripts) {
  for (int i = 0; i < nscripts; i++) {
    const ScriptReg *reg = &scripts[i];
    if (strcmp(reg->hat, "event_whenflagclicked") == 0) {
      if (rt->nroutes_flag >= rt->cap_flag_regs) {
        rt->cap_flag_regs = rt->cap_flag_regs ? rt->cap_flag_regs * 2 : 16;
        rt->routes_flag =
            (const ScriptReg **)realloc((void *)rt->routes_flag, (size_t)rt->cap_flag_regs * sizeof(const ScriptReg *));
      }
      rt->routes_flag[rt->nroutes_flag++] = reg;
    } else if (strcmp(reg->hat, "event_whenkeypressed") == 0) {
      push_route(&rt->routes_key, &rt->routes_key_names, &rt->nroutes_key, &rt->cap_routes_key, reg,
                 reg->key_option ? reg->key_option : "space");
    } else if (strcmp(reg->hat, "event_whenthisspriteclicked") == 0) {
      push_route(&rt->routes_click, &rt->routes_click_names, &rt->nroutes_click, &rt->cap_routes_click, reg,
                 reg->sprite);
    } else if (strcmp(reg->hat, "event_whenbroadcastreceived") == 0) {
      push_route(&rt->routes_broadcast, &rt->routes_broadcast_names, &rt->nroutes_broadcast, &rt->cap_routes_broadcast,
                 reg, reg->broadcast_option ? reg->broadcast_option : "");
    } else if (strcmp(reg->hat, "event_whenbackdroptoggles") == 0) {
      push_route(&rt->routes_backdrop, &rt->routes_backdrop_names, &rt->nroutes_backdrop, &rt->cap_routes_backdrop,
                 reg, reg->backdrop ? reg->backdrop : "");
    } else if (strcmp(reg->hat, "control_start_as_clone") == 0) {
      push_route(&rt->routes_clone, &rt->routes_clone_names, &rt->nroutes_clone, &rt->cap_routes_clone, reg,
                 reg->sprite);
    } else if (strcmp(reg->hat, "event_whengreaterthan") == 0) {
      if (rt->nroutes_greater >= rt->cap_routes_greater) {
        rt->cap_routes_greater = rt->cap_routes_greater ? rt->cap_routes_greater * 2 : 8;
        rt->routes_greater =
            (GreaterRoute *)realloc(rt->routes_greater, (size_t)rt->cap_routes_greater * sizeof(GreaterRoute));
      }
      GreaterRoute *gr = &rt->routes_greater[rt->nroutes_greater++];
      gr->reg = reg;
      gr->latched = 0;
    } else {
      sb_warnf(rt, "script hat '%s' (%s) is not routed and will never run", reg->hat, reg->sprite);
    }
  }
}

static int route_gather(const ScriptReg **arr, const char **names, int count, const char *key,
                        const ScriptReg **out, int cap) {
  int n = 0;
  for (int i = 0; i < count && n < cap; i++) {
    if (strcmp(names[i], key) == 0) out[n++] = arr[i];
  }
  return n;
}

void sb_broadcast(Rt *rt, Value name) {
  char text[SB_STR_CAP];
  s_str_into(s_str(name), text, sizeof text);
  const ScriptReg *buf[SB_ROUTE_CAP];
  int n = route_gather(rt->routes_broadcast, rt->routes_broadcast_names, rt->nroutes_broadcast, text, buf,
                       SB_ROUTE_CAP);
  spawn_regs(rt, buf, n, 0);
}

void sb_broadcast_wait(Rt *rt, Value name) {
  char text[SB_STR_CAP];
  s_str_into(s_str(name), text, sizeof text);
  const ScriptReg *buf[SB_ROUTE_CAP];
  int n = route_gather(rt->routes_broadcast, rt->routes_broadcast_names, rt->nroutes_broadcast, text, buf,
                       SB_ROUTE_CAP);
  if (!n) return;
  int group = ++rt->thread_group;
  spawn_regs(rt, buf, n, group);
  while (has_live_group(rt, group)) sb_yield(rt);
}

static void fire_backdrop_hats(Rt *rt) {
  TargetDef *stage = rt->stage_def;
  if (stage->ncostumes <= 0) return;
  const char *name = stage->costumes[stage->current_costume].name;
  const ScriptReg *buf[SB_ROUTE_CAP];
  int n =
      route_gather(rt->routes_backdrop, rt->routes_backdrop_names, rt->nroutes_backdrop, name, buf, SB_ROUTE_CAP);
  if (n) spawn_regs(rt, buf, n, 0);
}

void sb_stop_all(Rt *rt) {
  for (int i = 0; i < rt->nthreads; i++) rt->threads[i]->done = 1;
  sb_stop_all_sounds(rt);
}

void sb_stop_others(Rt *rt, Actor *actor) {
  for (int i = 0; i < rt->nthreads; i++) {
    Thread *t = rt->threads[i];
    if (t == rt->current_thread) continue;
    if (t->actor == actor && !t->done) t->done = 1;
  }
}

/* ------------------------------------------------------------------ */
/* clones                                                              */
/* ------------------------------------------------------------------ */

static void actor_init_data(Actor *actor, TargetDef *def);

void sb_create_clone(Rt *rt, Actor *actor, Value target_v) {
  char text[SB_STR_CAP];
  s_str_into(s_str(target_v), text, sizeof text);
  Actor *source = NULL;
  TargetDef *def = NULL;
  if (strcmp(text, "_myself_") == 0) {
    source = actor;
    def = actor->target;
  } else {
    for (int i = 0; i < rt->proj->ntargets; i++) {
      if (strcmp(rt->proj->targets[i].name, text) == 0) {
        def = &rt->proj->targets[i];
        break;
      }
    }
    if (!def || def->is_stage) {
      sb_warnf(rt, "cannot clone unknown sprite '%s'", text);
      return;
    }
    for (int i = 0; i < rt->nactors; i++) {
      Actor *existing = rt->actors[i];
      if (!existing->dead && strcmp(existing->target->name, text) == 0 && !existing->is_clone) {
        source = existing;
        break;
      }
    }
  }
  int clone_count = 0;
  for (int i = 0; i < rt->nactors; i++) {
    if (rt->actors[i]->is_clone && !rt->actors[i]->dead) clone_count++;
  }
  if (clone_count >= 300) {
    sb_warn(rt, "clone limit (300) reached");
    return;
  }
  Actor *clone = (Actor *)calloc(1, sizeof(Actor));
  clone->rt = rt;
  clone->target = def;
  clone->is_clone = 1;
  clone->visible = def->visible;
  clone->x = def->x;
  clone->y = def->y;
  clone->direction = def->direction;
  clone->size = def->size;
  clone->rotation_style = def->rotation_style;
  clone->volume = def->volume;
  clone->current_costume = def->current_costume;
  actor_init_data(clone, def);
  if (source) {
    clone->x = source->x;
    clone->y = source->y;
    clone->direction = source->direction;
    clone->size = source->size;
    clone->current_costume = source->current_costume;
    for (int i = 0; i < clone->nvars && i < source->nvars; i++) clone->vars[i].value = source->vars[i].value;
    for (int i = 0; i < clone->nlists && i < source->nlists; i++) {
      ListSlot *dst = &clone->lists[i];
      ListSlot *src = &source->lists[i];
      free(dst->items);
      int cap = src->cap > 0 ? src->cap : 1;
      dst->items = (Value *)malloc((size_t)cap * sizeof(Value));
      dst->cap = cap;
      dst->count = src->count;
      memcpy(dst->items, src->items, (size_t)src->count * sizeof(Value));
    }
  }
  if (rt->nactors >= rt->cap_actors) {
    rt->cap_actors = rt->cap_actors ? rt->cap_actors * 2 : 32;
    rt->actors = (Actor **)realloc(rt->actors, (size_t)rt->cap_actors * sizeof(Actor *));
  }
  rt->actors[rt->nactors++] = clone;
  int insert_at = source ? layer_index(rt, source) : -1;
  layers_reserve(rt);
  if (insert_at != -1) {
    memmove(&rt->layers[insert_at + 2], &rt->layers[insert_at + 1],
            (size_t)(rt->nlayers - insert_at - 1) * sizeof(Actor *));
    rt->layers[insert_at + 1] = clone;
    rt->nlayers++;
  } else {
    rt->layers[rt->nlayers++] = clone;
  }
  const ScriptReg *buf[SB_ROUTE_CAP];
  int n = route_gather(rt->routes_clone, rt->routes_clone_names, rt->nroutes_clone, def->name, buf, SB_ROUTE_CAP);
  for (int i = 0; i < n; i++) spawn(rt, buf[i], clone, 0);
}

void sb_remove_clone(Rt *rt, Actor *actor) {
  actor->dead = 1;
  int i = layer_index(rt, actor);
  if (i != -1) {
    memmove(&rt->layers[i], &rt->layers[i + 1], (size_t)(rt->nlayers - i - 1) * sizeof(Actor *));
    rt->nlayers--;
  }
  for (int j = 0; j < rt->nthreads; j++) {
    if (rt->threads[j]->actor == actor) rt->threads[j]->done = 1;
  }
}

/* ------------------------------------------------------------------ */
/* step / greater-than                                                 */
/* ------------------------------------------------------------------ */

static void check_greater_than(Rt *rt) {
  for (int i = 0; i < rt->nroutes_greater; i++) {
    GreaterRoute *route = &rt->routes_greater[i];
    int is_timer = route->reg->greater_op && strcmp(route->reg->greater_op, "timer") == 0;
    double value = is_timer ? rt->timer : rt->loudness;
    if (value > route->reg->greater_value) {
      if (!route->latched) {
        route->latched = 1;
        Actor *actor = NULL;
        for (int j = 0; j < rt->nactors; j++) {
          if (!rt->actors[j]->dead && strcmp(rt->actors[j]->target->name, route->reg->sprite) == 0) {
            actor = rt->actors[j];
            break;
          }
        }
        if (!actor) actor = rt->stage_actor;
        spawn(rt, route->reg, actor, 0);
      }
    } else {
      route->latched = 0;
    }
  }
}

static Actor *actor_for(Rt *rt, const char *sprite_name) {
  for (int i = 0; i < rt->nactors; i++) {
    if (!rt->actors[i]->dead && strcmp(rt->actors[i]->target->name, sprite_name) == 0) return rt->actors[i];
  }
  return rt->stage_actor;
}

static void step(Rt *rt) {
  rt->frame += 1;
  rt->timer += rt->frame_time;
  check_greater_than(rt);
  int steps = 0;
  size_t index = 0;
  while (index < (size_t)rt->nthreads) {
    Thread *t = rt->threads[index];
    index++;
    if (t->done || t->stepped_frame == rt->frame) continue;
    t->stepped_frame = rt->frame;
    steps++;
    if (steps > 20000) {
      sb_warn(rt, "frame step limit reached (possible broadcast loop)");
      break;
    }
    rt->current_thread = t;
#ifdef _WIN32
    SwitchToFiber(t->fiber);
#endif
    rt->current_thread = NULL;
  }
  int write = 0;
  for (int i = 0; i < rt->nthreads; i++) {
    Thread *t = rt->threads[i];
    if (t->done) {
#ifdef _WIN32
      if (t->fiber) DeleteFiber(t->fiber);
#endif
      free(t);
    } else {
      rt->threads[write++] = t;
    }
  }
  rt->nthreads = write;
}

/* ------------------------------------------------------------------ */
/* input                                                               */
/* ------------------------------------------------------------------ */

static const char *key_to_scratch(SDL_Keycode key) {
  switch (key) {
    case SDLK_SPACE:
      return "space";
    case SDLK_LEFT:
      return "left arrow";
    case SDLK_RIGHT:
      return "right arrow";
    case SDLK_UP:
      return "up arrow";
    case SDLK_DOWN:
      return "down arrow";
    case SDLK_RETURN:
    case SDLK_KP_ENTER:
      return "enter";
    default:
      break;
  }
  if (key >= SDLK_a && key <= SDLK_z) {
    static const char *letters[26] = {"a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l",
                                      "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "w", "x",
                                      "y", "z"};
    return letters[key - SDLK_a];
  }
  if (key >= SDLK_0 && key <= SDLK_9) {
    static const char *digits[10] = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9"};
    return digits[key - SDLK_0];
  }
  return NULL;
}

static void update_mouse(Rt *rt, int wx, int wy) {
  rt->mouse_x = (double)wx / rt->scale - 240.0;
  rt->mouse_y = 180.0 - (double)wy / rt->scale;
}

static void fire_click(Rt *rt) {
  for (int i = rt->nlayers - 1; i >= 0; i--) {
    Actor *actor = rt->layers[i];
    if (actor->dead || !actor->visible) continue;
    if (actor_opaque_at(rt, actor, rt->mouse_x, rt->mouse_y)) {
      const ScriptReg *buf[SB_ROUTE_CAP];
      int n = route_gather(rt->routes_click, rt->routes_click_names, rt->nroutes_click, actor->target->name, buf,
                           SB_ROUTE_CAP);
      for (int j = 0; j < n; j++) spawn(rt, buf[j], actor, 0);
      return;
    }
  }
}

/* fire scripted --click X,Y,FRAME events (1-based) just before their frame */
static void fire_pending_clicks(Rt *rt) {
  for (int i = 0; i < rt->nclicks; i++) {
    if (rt->click_frame[i] == rt->frame + 1) {
      rt->mouse_x = rt->click_x[i];
      rt->mouse_y = rt->click_y[i];
      rt->click_frame[i] = 0;
      fire_click(rt);
    }
  }
}

static void down_keys_add(Rt *rt, const char *name) {
  for (int i = 0; i < rt->ndown_keys; i++) {
    if (strcmp(rt->down_keys[i], name) == 0) return;
  }
  if (rt->ndown_keys >= rt->cap_down_keys) {
    rt->cap_down_keys = rt->cap_down_keys ? rt->cap_down_keys * 2 : 16;
    rt->down_keys = (const char **)realloc((void *)rt->down_keys, (size_t)rt->cap_down_keys * sizeof(const char *));
  }
  rt->down_keys[rt->ndown_keys++] = name;
}

static void down_keys_remove(Rt *rt, const char *name) {
  for (int i = 0; i < rt->ndown_keys; i++) {
    if (strcmp(rt->down_keys[i], name) == 0) {
      rt->down_keys[i] = rt->down_keys[--rt->ndown_keys];
      return;
    }
  }
}

static void spawn_key_routes(Rt *rt, const char *name) {
  const ScriptReg *buf[SB_ROUTE_CAP];
  int n = route_gather(rt->routes_key, rt->routes_key_names, rt->nroutes_key, name, buf, SB_ROUTE_CAP);
  for (int i = 0; i < n; i++) spawn(rt, buf[i], actor_for(rt, buf[i]->sprite), 0);
}

static void handle_key_down(Rt *rt, SDL_Keycode key, const char *text) {
  if (rt->asking) {
    if (key == SDLK_RETURN || key == SDLK_KP_ENTER) {
      Value answer;
      answer.type = VAL_STR;
      answer.num = 0.0;
      snprintf(answer.str, SB_STR_CAP, "%s", rt->ask_buffer);
      rt->answer = answer;
      rt->asking = 0;
    } else if (key == SDLK_BACKSPACE) {
      size_t len = strlen(rt->ask_buffer);
      if (len > 0) rt->ask_buffer[len - 1] = 0;
    } else if (text && text[0]) {
      size_t len = strlen(rt->ask_buffer);
      size_t add = strlen(text);
      if (len + add < SB_STR_CAP - 1) memcpy(rt->ask_buffer + len, text, add + 1);
    }
    return;
  }
  const char *name = key_to_scratch(key);
  if (name == NULL) return;
  down_keys_add(rt, name);
  spawn_key_routes(rt, name);
  spawn_key_routes(rt, "any");
}

static void handle_key_up(Rt *rt, SDL_Keycode key) {
  const char *name = key_to_scratch(key);
  if (name != NULL) down_keys_remove(rt, name);
}

static void handle_events(Rt *rt) {
  SDL_Event event;
  while (SDL_PollEvent(&event)) {
    switch (event.type) {
      case SDL_QUIT:
        rt->quitting = 1;
        break;
      case SDL_MOUSEMOTION:
        update_mouse(rt, event.motion.x, event.motion.y);
        break;
      case SDL_MOUSEBUTTONDOWN:
        update_mouse(rt, event.button.x, event.button.y);
        rt->mouse_down = 1;
        fire_click(rt);
        break;
      case SDL_MOUSEBUTTONUP:
        rt->mouse_down = 0;
        break;
      case SDL_KEYDOWN:
        handle_key_down(rt, event.key.keysym.sym, NULL);
        break;
      case SDL_KEYUP:
        handle_key_up(rt, event.key.keysym.sym);
        break;
      case SDL_TEXTINPUT:
        if (rt->asking) handle_key_down(rt, 0, event.text.text);
        break;
      default:
        break;
    }
  }
}

/* ------------------------------------------------------------------ */
/* assets / drawing                                                    */
/* ------------------------------------------------------------------ */

int asset_path(Rt *rt, const char *file, char *out, size_t cap) {
  if (file == NULL || file[0] == 0) return 0;
  if (rt->base_path && rt->base_path[0]) {
    snprintf(out, cap, "%s/%s/%s", rt->base_path, rt->proj->asset_dir, file);
    FILE *f = fopen(out, "rb");
    if (f) {
      fclose(f);
      return 1;
    }
  }
  snprintf(out, cap, "%s/%s", rt->proj->asset_dir, file);
  FILE *f = fopen(out, "rb");
  if (f) {
    fclose(f);
    return 1;
  }
  return 0;
}

static SDL_Surface *load_svg_surface(const char *path, float scale) {
  SDL_Surface *result = NULL;
  FILE *f = fopen(path, "rb");
  if (!f) return NULL;
  if (fseek(f, 0, SEEK_END) != 0) {
    fclose(f);
    return NULL;
  }
  long size = ftell(f);
  if (size <= 0 || fseek(f, 0, SEEK_SET) != 0) {
    fclose(f);
    return NULL;
  }
  char *data = (char *)malloc((size_t)size + 1);
  if (!data) {
    fclose(f);
    return NULL;
  }
  size_t got = fread(data, 1, (size_t)size, f);
  fclose(f);
  if (got != (size_t)size) {
    free(data);
    return NULL;
  }
  data[size] = '\0';
  NSVGimage *image = nsvgParse(data, "px", 96.0f);
  free(data);
  if (!image) return NULL;
  int w = (int)(image->width * scale + 0.5f);
  int h = (int)(image->height * scale + 0.5f);
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  size_t nbytes = (size_t)w * (size_t)h * 4;
  unsigned char *rgba = (unsigned char *)malloc(nbytes);
  if (rgba) {
    NSVGrasterizer *rast = nsvgCreateRasterizer();
    if (rast) {
      nsvgRasterize(rast, image, 0.0f, 0.0f, scale, rgba, w, h, w * 4);
      nsvgDeleteRasterizer(rast);
      SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormat(0, w, h, 32, SDL_PIXELFORMAT_RGBA32);
      if (surface) {
        if (surface->pitch == w * 4) {
          memcpy(surface->pixels, rgba, nbytes);
        } else {
          unsigned char *dst = (unsigned char *)surface->pixels;
          for (int row = 0; row < h; row++)
            memcpy(dst + (size_t)row * surface->pitch, rgba + (size_t)row * (size_t)w * 4,
                   (size_t)w * 4);
        }
        result = surface;
      }
    }
    free(rgba);
  }
  nsvgDelete(image);
  return result;
}

static int costume_load(Rt *rt, CostumeDef *c) {
  if (c->loaded) return c->tex != NULL;
  c->loaded = 1;
  if (c->file == NULL || c->file[0] == 0) {
    c->missing = 1;
    return 0;
  }
  char path[1024];
  if (!asset_path(rt, c->file, path, sizeof path)) {
    c->missing = 1;
    sb_warnf(rt, "costume file '%s' not found", c->file);
    return 0;
  }
  const char *ext = strrchr(path, '.');
  int is_svg = ext != NULL && SDL_strcasecmp(ext, ".svg") == 0;
  SDL_Surface *surface = NULL;
  if (is_svg) {
    surface = load_svg_surface(path, SB_SVG_RASTER_SCALE);
    if (surface) {
      /* the texture is supersampled; scale resolution by the same factor so
         display size and (already normalized) stage anchors stay correct */
      int res = c->resolution > 0 ? c->resolution : 1;
      c->resolution = (int)(res * SB_SVG_RASTER_SCALE + 0.5f);
    }
  } else {
    surface = IMG_Load(path);
  }
  if (!surface) {
    c->missing = 1;
    sb_warnf(rt, "costume file '%s' failed to load (%s)", c->file,
             is_svg ? "svg parse/render failed" : IMG_GetError());
    return 0;
  }
  c->tex = SDL_CreateTextureFromSurface((SDL_Renderer *)rt->renderer, surface);
  c->tex_w = surface->w;
  c->tex_h = surface->h;
  c->disp_w = surface->w / (double)c->resolution;
  c->disp_h = surface->h / (double)c->resolution;
  build_alpha_mask(c, surface);
  SDL_FreeSurface(surface);
  if (!c->tex) {
    c->missing = 1;
    return 0;
  }
  return 1;
}

static SbTexture *costume_texture(Rt *rt, CostumeDef *c) {
  if (costume_load(rt, c)) return (SbTexture *)c->tex;
  return (SbTexture *)rt->fallback_tex;
}

void draw_actor(void *renderer_v, Rt *rt, Actor *actor, double pixel_scale) {
  SDL_Renderer *r = (SDL_Renderer *)renderer_v;
  CostumeDef *c = actor_costume(actor);
  if (!c) return;
  SbTexture *tex = costume_texture(rt, c);
  if (!tex) return;
  double scale = (actor->size / 100.0) * pixel_scale;
  double cx = (actor->x + 240.0) * pixel_scale;
  double cy = (180.0 - actor->y) * pixel_scale;
  double w = costume_w(c) * scale;
  double h = costume_h(c) * scale;
  double ccx = c->cx * scale;
  double ccy = c->cy * scale;
  double angle = 0;
  SDL_RendererFlip flip = SDL_FLIP_NONE;
  SDL_FRect dst;
  int need_center = 0;
  SDL_FPoint center = {(float)ccx, (float)ccy};
  if (strcmp(actor->rotation_style, "all around") == 0) {
    angle = actor->direction - 90;
    dst.x = (float)(cx - ccx);
    need_center = 1;
  } else if (strcmp(actor->rotation_style, "left-right") == 0 && actor->direction < 0) {
    flip = SDL_FLIP_HORIZONTAL;
    dst.x = (float)(cx + ccx - w);
  } else {
    dst.x = (float)(cx - ccx);
  }
  dst.y = (float)(cy - ccy);
  dst.w = (float)w;
  dst.h = (float)h;
  double alpha = 1.0 - actor->fx_ghost / 100.0;
  if (alpha < 0) alpha = 0;
  if (alpha > 1) alpha = 1;
  SDL_SetTextureAlphaMod((SDL_Texture *)tex, (Uint8)(alpha * 255));
  SDL_RenderCopyExF(r, (SDL_Texture *)tex, NULL, &dst, angle, need_center ? &center : NULL, flip);
  SDL_SetTextureAlphaMod((SDL_Texture *)tex, 255);
}

static void measure_text(TTF_Font *font, const char *text, int *w, int *h) {
  int tw = 0, th = 0;
  TTF_SizeUTF8(font, text, &tw, &th);
  if (w) *w = tw;
  if (h) *h = th;
}

static void draw_text(Rt *rt, void *font_v, const char *text, double x, double baseline, int r, int g, int b) {
  TTF_Font *font = (TTF_Font *)font_v;
  if (!font || !text) return;
  SDL_Color color = {(Uint8)r, (Uint8)g, (Uint8)b, 255};
  SDL_Surface *surface = TTF_RenderUTF8_Blended(font, text, color);
  if (!surface) return;
  SDL_Texture *texture = SDL_CreateTextureFromSurface((SDL_Renderer *)rt->renderer, surface);
  if (!texture) {
    SDL_FreeSurface(surface);
    return;
  }
  SDL_Rect dst;
  dst.x = (int)x;
  dst.y = (int)baseline - TTF_FontAscent(font);
  dst.w = surface->w;
  dst.h = surface->h;
  SDL_RenderCopy((SDL_Renderer *)rt->renderer, texture, NULL, &dst);
  SDL_DestroyTexture(texture);
  SDL_FreeSurface(surface);
}

static int wrap_text(const char *text, int width, char lines[][SB_STR_CAP], int max_lines) {
  int n = 0;
  char words[64][SB_STR_CAP];
  int nwords = 0;
  const char *p = text;
  while (*p && nwords < 64) {
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (!*p) break;
    int len = 0;
    while (*p && *p != ' ' && *p != '\t' && *p != '\n' && *p != '\r' && len < SB_STR_CAP - 1) {
      words[nwords][len++] = *p++;
    }
    words[nwords][len] = 0;
    nwords++;
  }
  if (nwords == 0) {
    if (n < max_lines) lines[n++][0] = 0;
    return n;
  }
  char current[SB_STR_CAP];
  snprintf(current, sizeof current, "%s", words[0]);
  for (int i = 1; i < nwords; i++) {
    size_t cur_len = strlen(current);
    size_t word_len = strlen(words[i]);
    if ((int)(cur_len + 1 + word_len) <= width) {
      snprintf(current + cur_len, SB_STR_CAP - cur_len, " %s", words[i]);
    } else {
      if (n < max_lines) {
        snprintf(lines[n], SB_STR_CAP, "%s", current);
        n++;
      }
      snprintf(current, sizeof current, "%s", words[i]);
    }
  }
  if (n < max_lines) {
    snprintf(lines[n], SB_STR_CAP, "%s", current);
    n++;
  }
  return n;
}

static void draw_bubble(Rt *rt, Actor *actor) {
  Value text_v = actor->has_say ? actor->say : actor->think;
  char text[SB_STR_CAP];
  s_str_into(s_str(text_v), text, sizeof text);
  if (!text[0]) return;
  int scale = rt->scale;
  char lines[16][SB_STR_CAP];
  int nlines = wrap_text(text, 24, lines, 16);
  int line_h = 16 * scale;
  int width = 0;
  TTF_Font *font = (TTF_Font *)rt->font;
  for (int i = 0; i < nlines; i++) {
    int tw = 0;
    if (font) measure_text(font, lines[i], &tw, NULL);
    if (tw > width) width = tw;
  }
  width += 14 * scale;
  int height = line_h * nlines + 8 * scale;
  double hw, hh;
  actor_half_size(actor, &hw, &hh);
  double bx_raw = (actor->x + 240.0) * scale;
  double by_raw = (180.0 - (actor->y + hh)) * scale;
  double canvas_w = 480.0 * scale;
  double bx = bx_raw - width / 2.0;
  if (bx < 4) bx = 4;
  if (bx > canvas_w - width - 4) bx = canvas_w - width - 4;
  double by = by_raw - height - 12 * scale;
  if (by < 4) by = 4;
  SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
  SDL_Rect box = {(int)bx, (int)by, width, height};
  SDL_SetRenderDrawColor(r, 255, 255, 255, 255);
  SDL_RenderFillRect(r, &box);
  SDL_SetRenderDrawColor(r, 180, 180, 180, 255);
  SDL_RenderDrawRect(r, &box);
  for (int i = 0; i < nlines; i++) {
    draw_text(rt, font, lines[i], bx + 7 * scale, by + 4 * scale + (i + 0.8) * line_h, 20, 20, 20);
  }
  SDL_Vertex tail[3];
  memset(tail, 0, sizeof tail);
  SDL_Color white = {255, 255, 255, 255};
  tail[0].color = white;
  tail[1].color = white;
  tail[2].color = white;
  tail[0].position.x = (float)(bx + width / 2.0 - 6 * scale);
  tail[0].position.y = (float)(by + height);
  tail[1].position.x = (float)(bx + width / 2.0 + 6 * scale);
  tail[1].position.y = (float)(by + height);
  tail[2].position.x = (float)(bx + width / 2.0);
  tail[2].position.y = (float)(by + height + 8 * scale);
  SDL_RenderGeometry(r, NULL, tail, 3, NULL, 0);
}

static Value monitor_value(Rt *rt, const MonitorDef *monitor) {
  const char *label = monitor->label ? monitor->label : "";
  TargetDef *scope = NULL;
  if (monitor->target && monitor->target[0]) {
    for (int i = 0; i < rt->proj->ntargets; i++) {
      if (strcmp(rt->proj->targets[i].name, monitor->target) == 0) {
        scope = &rt->proj->targets[i];
        break;
      }
    }
  }
  if (scope) {
    if (monitor->is_list) {
      for (int j = 0; j < scope->nlists; j++) {
        if (strcmp(scope->lists[j].name, label) == 0) return list_contents(&scope->lists[j]);
      }
    } else {
      for (int j = 0; j < scope->nvars; j++) {
        if (strcmp(scope->vars[j].name, label) == 0) return scope->vars[j].value;
      }
    }
  } else {
    for (int i = 0; i < rt->proj->ntargets; i++) {
      TargetDef *def = &rt->proj->targets[i];
      if (monitor->is_list) {
        for (int j = 0; j < def->nlists; j++) {
          if (strcmp(def->lists[j].name, label) == 0) return list_contents(&def->lists[j]);
        }
      } else {
        for (int j = 0; j < def->nvars; j++) {
          if (strcmp(def->vars[j].name, label) == 0) return def->vars[j].value;
        }
      }
    }
  }
  if (monitor->is_list) {
    for (int i = 0; i < rt->proj->ntargets; i++) {
      TargetDef *def = &rt->proj->targets[i];
      for (int j = 0; j < def->nlists; j++) {
        if (strcmp(def->lists[j].name, label) == 0) return list_contents(&def->lists[j]);
      }
    }
    return S("");
  }
  for (int j = 0; j < rt->stage_def->nvars; j++) {
    if (strcmp(rt->stage_def->vars[j].name, label) == 0) return rt->stage_def->vars[j].value;
  }
  return monitor->initial;
}

static void draw_monitors(Rt *rt) {
  int scale = rt->scale;
  for (int i = 0; i < rt->proj->nmonitors; i++) {
    const MonitorDef *monitor = &rt->proj->monitors[i];
    if (!monitor->visible) continue;
    Value value = monitor_value(rt, monitor);
    double mx = (monitor->x + 240.0) * scale;
    double my = (180.0 - monitor->y) * scale;
    char text[SB_STR_CAP];
    s_str_into(s_str(value), text, sizeof text);
    if (monitor->mode && strcmp(monitor->mode, "large") == 0) {
      draw_text(rt, rt->big_font, text, mx - 2, my + 40 * scale, 255, 255, 255);
      draw_text(rt, rt->big_font, text, mx + 2, my + 40 * scale, 255, 255, 255);
      draw_text(rt, rt->big_font, text, mx, my + 40 * scale - 2, 255, 255, 255);
      draw_text(rt, rt->big_font, text, mx, my + 40 * scale + 2, 255, 255, 255);
      draw_text(rt, rt->big_font, text, mx, my + 40 * scale, 110, 230, 255);
      continue;
    }
    const char *label = monitor->label ? monitor->label : "";
    int label_w = 0, value_w = 0;
    if (rt->font) {
      measure_text((TTF_Font *)rt->font, label, &label_w, NULL);
      measure_text((TTF_Font *)rt->font, text, &value_w, NULL);
    }
    int box_w = label_w + value_w + 22 * scale;
    int box_h = 20 * scale;
    SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
    SDL_Rect box = {(int)mx, (int)my, box_w, box_h};
    SDL_SetRenderDrawColor(r, 245, 245, 245, 255);
    SDL_RenderFillRect(r, &box);
    SDL_SetRenderDrawColor(r, 176, 176, 176, 255);
    SDL_RenderDrawRect(r, &box);
    draw_text(rt, rt->font, label, mx + 6 * scale, my + box_h - 6 * scale, 60, 60, 60);
    draw_text(rt, rt->font, text, mx + box_w - value_w - 6 * scale, my + box_h - 6 * scale, 20, 20, 20);
  }
}

static void draw_ask(Rt *rt) {
  int scale = rt->scale;
  int height = 60 * scale;
  double y = 360.0 * scale - height;
  SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
  SDL_Rect bar = {0, (int)y, 480 * scale, height};
  SDL_SetRenderDrawColor(r, 245, 245, 245, 255);
  SDL_RenderFillRect(r, &bar);
  SDL_SetRenderDrawColor(r, 160, 160, 160, 255);
  SDL_RenderDrawRect(r, &bar);
  char question[SB_STR_CAP];
  s_str_into(s_str(rt->ask_question), question, sizeof question);
  if (strlen(question) > 90) question[90] = 0;
  draw_text(rt, rt->font, question, 10 * scale, y + 20 * scale, 20, 20, 20);
  char buffer[SB_STR_CAP];
  snprintf(buffer, sizeof buffer, "%s_", rt->ask_buffer);
  draw_text(rt, rt->font, buffer, 10 * scale, y + 44 * scale, 20, 20, 20);
}

static void draw(Rt *rt) {
  SDL_Renderer *r = (SDL_Renderer *)rt->renderer;
  SDL_SetRenderDrawColor(r, 15, 15, 30, 255);
  SDL_RenderClear(r);
  TargetDef *stage = rt->stage_def;
  if (stage->ncostumes > 0) {
    CostumeDef *backdrop = &stage->costumes[stage->current_costume];
    SbTexture *tex = costume_texture(rt, backdrop);
    if (tex) {
      SDL_Rect dst = {0, 0, 480 * rt->scale, 360 * rt->scale};
      SDL_RenderCopy(r, (SDL_Texture *)tex, NULL, &dst);
    }
  }
  for (int i = 0; i < rt->nlayers; i++) {
    Actor *actor = rt->layers[i];
    if (actor->dead || !actor->visible) continue;
    draw_actor(r, rt, actor, (double)rt->scale);
  }
  for (int i = 0; i < rt->nlayers; i++) {
    Actor *actor = rt->layers[i];
    if (actor->dead) continue;
    if (!actor->has_say && !actor->has_think) continue;
    draw_bubble(rt, actor);
  }
  if (rt->stage_actor && !rt->stage_actor->dead && (rt->stage_actor->has_say || rt->stage_actor->has_think)) {
    draw_bubble(rt, rt->stage_actor);
  }
  draw_monitors(rt);
  if (rt->asking) draw_ask(rt);
  SDL_RenderPresent(r);
}

/* ------------------------------------------------------------------ */
/* run loop                                                            */
/* ------------------------------------------------------------------ */

static TTF_Font *load_font(int px) {
  const char *env = getenv("SB3_FONT");
  if (env && env[0]) {
    TTF_Font *font = TTF_OpenFont(env, px);
    if (font) return font;
  }
  const char *windir = getenv("WINDIR");
  char path[1024];
  const char *names[] = {"arial.ttf", "segoeui.ttf", "tahoma.ttf", "calibri.ttf", "dejavu sans.ttf"};
  if (windir && windir[0]) {
    for (size_t i = 0; i < sizeof names / sizeof names[0]; i++) {
      snprintf(path, sizeof path, "%s/Fonts/%s", windir, names[i]);
      TTF_Font *font = TTF_OpenFont(path, px);
      if (font) return font;
    }
  }
  return TTF_OpenFont("assets/font.ttf", px);
}

static void actor_init_data(Actor *actor, TargetDef *def) {
  actor->nvars = def->nvars;
  actor->vars = (VarSlot *)malloc((size_t)(def->nvars > 0 ? def->nvars : 1) * sizeof(VarSlot));
  for (int i = 0; i < def->nvars; i++) actor->vars[i] = def->vars[i];
  actor->nlists = def->nlists;
  actor->lists = (ListSlot *)malloc((size_t)(def->nlists > 0 ? def->nlists : 1) * sizeof(ListSlot));
  for (int i = 0; i < def->nlists; i++) {
    actor->lists[i] = def->lists[i];
    int cap = def->lists[i].cap > 0 ? def->lists[i].cap : 1;
    actor->lists[i].items = (Value *)malloc((size_t)cap * sizeof(Value));
    actor->lists[i].cap = cap;
    actor->lists[i].count = def->lists[i].count;
    memcpy(actor->lists[i].items, def->lists[i].items, (size_t)def->lists[i].count * sizeof(Value));
  }
  actor->owns_data = 1;
}

static Actor *make_actor(Rt *rt, TargetDef *def) {
  Actor *actor = (Actor *)calloc(1, sizeof(Actor));
  actor->rt = rt;
  actor->target = def;
  actor->visible = def->visible;
  actor->direction = def->direction;
  actor->size = def->size;
  actor->rotation_style = def->rotation_style;
  actor->volume = def->volume;
  actor->current_costume = def->current_costume;
  actor->x = def->x;
  actor->y = def->y;
  actor->nvars = def->nvars;
  actor->vars = def->vars;
  actor->nlists = def->nlists;
  actor->lists = def->lists;
  return actor;
}

static void dump_state(Rt *rt) {
  for (int i = 0; i < rt->proj->ntargets; i++) {
    TargetDef *def = &rt->proj->targets[i];
    int live = 0;
    for (int j = 0; j < rt->nactors; j++) {
      if (!rt->actors[j]->dead && rt->actors[j]->target == def) live++;
    }
    printf("SBPOP %s %d\n", def->name, live);
    for (int j = 0; j < def->nvars; j++) {
      char value[SB_STR_CAP];
      s_str_into(def->vars[j].value, value, sizeof value);
      printf("SBVAR %s %s %s\n", def->name, def->vars[j].name, value);
    }
    for (int j = 0; j < def->nlists; j++) {
      printf("SBLIST %s %s %d\n", def->name, def->lists[j].name, def->lists[j].count);
    }
  }
}

static Value parse_scalar(const char *text) {
  char *end = NULL;
  double v = strtod(text, &end);
  Value out;
  if (end && end != text && *end == 0 && isfinite(v)) {
    out.type = VAL_NUM;
    out.num = v;
    out.str[0] = 0;
    return out;
  }
  out.type = VAL_STR;
  out.num = 0.0;
  snprintf(out.str, sizeof out.str, "%s", text);
  return out;
}

/* --set NAME=VALUE: write into the owning target (stage first) before actors spawn */
static void apply_set(Rt *rt, const char *spec) {
  const char *eq = strchr(spec, '=');
  if (eq == NULL || eq == spec) {
    fprintf(stderr, "warning: bad --set value (want NAME=VALUE)\n");
    return;
  }
  char name[SB_STR_CAP];
  size_t len = (size_t)(eq - spec);
  if (len >= sizeof name) len = sizeof name - 1;
  memcpy(name, spec, len);
  name[len] = 0;
  const char *value = eq + 1;
  for (int t = 0; t < rt->proj->ntargets; t++) {
    TargetDef *def = &rt->proj->targets[t];
    for (int v = 0; v < def->nvars; v++) {
      if (strcmp(def->vars[v].name, name) == 0) {
        def->vars[v].value = parse_scalar(value);
        return;
      }
    }
  }
  fprintf(stderr, "warning: variable '%s' not found for --set\n", name);
}

int sb_run(const SbProject *proj, int argc, char **argv, const ScriptReg *scripts, int nscripts) {
  Rt *rt = (Rt *)calloc(1, sizeof(Rt));
  rt->proj = proj;
  rt->stage_def = &proj->targets[0];
  rt->scale = proj->scale > 0 ? proj->scale : 2;
  rt->fps = proj->fps > 0 ? proj->fps : 30;
  rt->frame_time = 1.0 / rt->fps;
  rt->username = S("");
  rt->answer = S("");
  rt->ask_question = S("");
  rt->loudness = 100.0;
  srand((unsigned)time(NULL));

  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--smoke") == 0 && i + 1 < argc) {
      rt->smoke = atoi(argv[++i]);
    } else if (strcmp(argv[i], "--dump") == 0) {
      rt->dump_vars = 1;
    } else if (strcmp(argv[i], "--scale") == 0 && i + 1 < argc) {
      rt->scale = atoi(argv[++i]);
      if (rt->scale < 1) rt->scale = 1;
    } else if (strcmp(argv[i], "--fps") == 0 && i + 1 < argc) {
      rt->fps = atoi(argv[++i]);
      if (rt->fps < 1) rt->fps = 1;
      rt->frame_time = 1.0 / rt->fps;
    } else if (strcmp(argv[i], "--set") == 0 && i + 1 < argc) {
      apply_set(rt, argv[++i]);
    } else if (strcmp(argv[i], "--click") == 0 && i + 1 < argc) {
      double cx = 0.0;
      double cy = 0.0;
      long long cf = 0;
      if (sscanf(argv[++i], "%lf,%lf,%lld", &cx, &cy, &cf) == 3) {
        if (rt->nclicks < 16) {
          rt->click_x[rt->nclicks] = cx;
          rt->click_y[rt->nclicks] = cy;
          rt->click_frame[rt->nclicks] = (int64_t)cf;
          rt->nclicks++;
        } else {
          fprintf(stderr, "warning: too many --click events (max 16)\n");
        }
      } else {
        fprintf(stderr, "warning: bad --click value (want X,Y,FRAME)\n");
      }
    }
  }

  if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
    fprintf(stderr, "error: SDL_Init failed: %s\n", SDL_GetError());
    return 1;
  }
  IMG_Init(IMG_INIT_PNG);
  TTF_Init();
  Mix_OpenAudio(44100, MIX_DEFAULT_FORMAT, 2, 2048);

  Uint32 window_flags = rt->smoke ? SDL_WINDOW_HIDDEN : 0;
  SDL_Window *window =
      SDL_CreateWindow(proj->name ? proj->name : "Scratch project", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                       480 * rt->scale, 360 * rt->scale, window_flags);
  if (!window) {
    fprintf(stderr, "error: SDL_CreateWindow failed: %s\n", SDL_GetError());
    return 1;
  }
  SDL_Renderer *renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
  if (!renderer) renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE);
  if (!renderer) {
    fprintf(stderr, "error: SDL_CreateRenderer failed: %s\n", SDL_GetError());
    return 1;
  }
  SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
  rt->window = window;
  rt->renderer = renderer;

  char *base = SDL_GetBasePath();
  if (base) {
    for (size_t len = strlen(base); len > 0 && (base[len - 1] == '/' || base[len - 1] == '\\'); len--) {
      base[len - 1] = 0;
    }
    char probe[1024];
    snprintf(probe, sizeof probe, "%s/%s", base, proj->asset_dir);
    struct stat st;
    if (stat(probe, &st) == 0 && S_ISDIR(st.st_mode)) rt->base_path = base;
  }

  for (int t = 0; t < proj->ntargets; t++) {
    TargetDef *def = &proj->targets[t];
    for (int c = 0; c < def->ncostumes; c++) {
      double res = def->costumes[c].resolution > 0 ? def->costumes[c].resolution : 1;
      def->costumes[c].cx /= res;
      def->costumes[c].cy /= res;
    }
  }

  /* originals share the static list arrays emitted in main.c; move them to
     the heap so add/insert/realloc is well defined (cap stays >= count) */
  for (int t = 0; t < proj->ntargets; t++) {
    TargetDef *def = &proj->targets[t];
    for (int l = 0; l < def->nlists; l++) {
      ListSlot *slot = &def->lists[l];
      if (slot->count <= 0) continue;
      int cap = slot->cap > slot->count ? slot->cap : slot->count;
      Value *items = (Value *)malloc((size_t)cap * sizeof(Value));
      memcpy(items, slot->items, (size_t)slot->count * sizeof(Value));
      slot->items = items;
      slot->cap = cap;
    }
  }

  {
    SDL_Surface *fallback = SDL_CreateRGBSurfaceWithFormat(0, 32, 32, 32, SDL_PIXELFORMAT_RGBA32);
    SDL_FillRect(fallback, NULL, SDL_MapRGBA(fallback->format, 120, 120, 160, 255));
    rt->fallback_tex = SDL_CreateTextureFromSurface(renderer, fallback);
    SDL_FreeSurface(fallback);
  }

  rt->font = load_font(14 * rt->scale);
  rt->big_font = load_font(48 * rt->scale);

  rt->cap_actors = proj->ntargets + 8;
  rt->actors = (Actor **)malloc((size_t)rt->cap_actors * sizeof(Actor *));
  rt->stage_actor = make_actor(rt, &proj->targets[0]);
  rt->actors[rt->nactors++] = rt->stage_actor;
  for (int t = 1; t < proj->ntargets; t++) {
    rt->actors[rt->nactors++] = make_actor(rt, &proj->targets[t]);
  }
  rt->cap_layers = rt->nactors + 8;
  rt->layers = (Actor **)malloc((size_t)rt->cap_layers * sizeof(Actor *));
  Actor **unordered = (Actor **)malloc((size_t)rt->nactors * sizeof(Actor *));
  int nunordered = 0;
  for (int i = 0; i < rt->nactors; i++) {
    if (!rt->actors[i]->target->is_stage) unordered[nunordered++] = rt->actors[i];
  }
  for (int i = 1; i < nunordered; i++) {
    Actor *key = unordered[i];
    int j = i - 1;
    while (j >= 0 && unordered[j]->target->layer_order > key->target->layer_order) {
      unordered[j + 1] = unordered[j];
      j--;
    }
    unordered[j + 1] = key;
  }
  for (int i = 0; i < nunordered; i++) rt->layers[rt->nlayers++] = unordered[i];
  free(unordered);

  build_routes(rt, scripts, nscripts);

#ifdef _WIN32
  rt->main_fiber = ConvertThreadToFiber(NULL);
  /* SDL_Delay(1) quantizes to the system timer (~15.6ms) without this,
     dropping the frame loop to ~21fps when the resolution is degraded */
  timeBeginPeriod(1);
#endif

  spawn_regs(rt, rt->routes_flag, rt->nroutes_flag, 0);

  Uint32 interval = (Uint32)(1000.0 / rt->fps);
  if (interval == 0) interval = 1;
  Uint32 last = SDL_GetTicks();
  Uint32 acc = 0;
  while (!rt->quitting) {
    handle_events(rt);
    if (rt->quitting) break;
    if (rt->smoke) {
      fire_pending_clicks(rt);
      step(rt);
      draw(rt);
      if (rt->frame >= rt->smoke) break;
      continue;
    }
    Uint32 now = SDL_GetTicks();
    acc += now - last;
    last = now;
    if (acc >= interval) {
      acc = acc % interval;
      fire_pending_clicks(rt);
      step(rt);
      draw(rt);
    }
    SDL_Delay(1);
  }

#ifdef _WIN32
  timeEndPeriod(1);
#endif

  if (rt->smoke) {
    printf("SMOKE OK frames=%lld threads=%d\n", (long long)rt->frame, rt->nthreads);
  }
  if (rt->dump_vars) dump_state(rt);
  fflush(stdout);

  TTF_Quit();
  Mix_CloseAudio();
  Mix_Quit();
  IMG_Quit();
  SDL_Quit();
  return 0;
}
