#ifndef SB3_RUNTIME_H
#define SB3_RUNTIME_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifdef _WIN32
#include <windows.h>
#endif

#define SB_STAGE_W 480
#define SB_STAGE_H 360
#define SB_DEFAULT_FPS 30
#define SB_MAX_CLONES 300
#define SB_MAX_STEPS_PER_FRAME 20000
#define SB_STR_CAP 512

typedef struct SDL_Texture SbTexture;
typedef struct Mix_Chunk SbChunk;
struct Actor;
struct Rt;

typedef enum { VAL_NUM = 0, VAL_STR = 1 } ValType;

typedef struct {
  ValType type;
  double num;
  char str[SB_STR_CAP];
} Value;

#define N(x) ((Value){VAL_NUM, (double)(x), {0}})
#define S(text) ((Value){VAL_STR, 0.0, text})
#define SV_NIL ((Value){VAL_NUM, 0.0, {0}})

Value mkstr(const char *s);

typedef struct {
  const char *name;
  Value value;
} VarSlot;

typedef struct {
  const char *name;
  Value *items;
  int count;
  int cap;
} ListSlot;

typedef struct {
  const char *name;
  const char *id;
  const char *file;
  double cx;
  double cy;
  int resolution;
  SbTexture *tex;
  int tex_w;
  int tex_h;
  double disp_w;
  double disp_h;
  int loaded;
  int missing;
  unsigned char *alpha; /* 1 byte per texel; 1 = opaque (Scratch-style collision) */
  int tight_l, tight_t, tight_r, tight_b; /* opaque bounds, texel coords, r/b exclusive */
} CostumeDef;

typedef struct {
  const char *name;
  const char *file;
  SbChunk *chunk;
  int loaded;
} SoundDef;

typedef struct {
  const char *name;
  int is_stage;
  VarSlot *vars;
  int nvars;
  ListSlot *lists;
  int nlists;
  CostumeDef *costumes;
  int ncostumes;
  SoundDef *sounds;
  int nsounds;
  int current_costume;
  double volume;
  int layer_order;
  double x;
  double y;
  double direction;
  double size;
  int visible;
  const char *rotation_style;
} TargetDef;

typedef struct {
  const char *id;
  const char *label;
  const char *target;
  int is_list;
  double x;
  double y;
  const char *mode;
  int visible;
  Value initial;
} MonitorDef;

typedef struct {
  const char *sprite;
  const char *hat;
  const char *key_option;
  const char *broadcast_option;
  const char *backdrop;
  const char *greater_op;
  double greater_value;
  void (*fn)(struct Actor *ctx, struct Rt *rt);
} ScriptReg;

typedef struct {
  const char *name;
  const char *asset_dir;
  int scale;
  int fps;
  TargetDef *targets;
  int ntargets;
  MonitorDef *monitors;
  int nmonitors;
} SbProject;

struct Actor {
  struct Rt *rt;
  TargetDef *target;
  int is_clone;
  int dead;
  int visible;
  double x;
  double y;
  double direction;
  double size;
  int current_costume;
  const char *rotation_style;
  double volume;
  double fx_ghost;
  double fx_color;
  double fx_fisheye;
  double fx_whirl;
  double fx_pixelate;
  double fx_mosaic;
  double fx_brightness;
  double sx_pitch;
  double sx_pan;
  int has_say;
  int has_think;
  Value say;
  Value think;
  VarSlot *vars;
  int nvars;
  ListSlot *lists;
  int nlists;
  int owns_data;
};

typedef struct Actor Actor;

typedef struct Thread {
  Actor *actor;
  const ScriptReg *reg;
  struct Rt *rt;
#ifdef _WIN32
  LPVOID fiber;
#endif
  int done;
  int group;
  int64_t stepped_frame;
} Thread;

typedef struct {
  const ScriptReg *reg;
  int latched;
} GreaterRoute;

typedef struct {
  const char *text;
} WarnEntry;

typedef struct Rt {
  const SbProject *proj;
  TargetDef *stage_def;
  Actor *stage_actor;
  Actor **actors;
  int nactors;
  int cap_actors;
  Actor **layers;
  int nlayers;
  int cap_layers;
  Thread **threads;
  int nthreads;
  int cap_threads;
  Thread *current_thread;
  int64_t frame;
  double frame_time;
  double timer;
  double loudness;
  Value username;
  double mouse_x;
  double mouse_y;
  int mouse_down;
  const char **down_keys;
  int ndown_keys;
  int cap_down_keys;
  int asking;
  Value ask_question;
  char ask_buffer[SB_STR_CAP];
  Value answer;
  int quitting;
  int scale;
  int fps;
  int smoke;
  int dump_vars;
  double click_x[16];
  double click_y[16];
  int64_t click_frame[16];
  int nclicks;
  int thread_group;
  GreaterRoute *routes_greater;
  int nroutes_greater;
  int cap_routes_greater;
  const ScriptReg **routes_flag;
  int nroutes_flag;
  int cap_flag_regs;
  const ScriptReg **routes_key;
  const char **routes_key_names;
  int nroutes_key;
  int cap_routes_key;
  const ScriptReg **routes_click;
  const char **routes_click_names;
  int nroutes_click;
  int cap_routes_click;
  const ScriptReg **routes_broadcast;
  const char **routes_broadcast_names;
  int nroutes_broadcast;
  int cap_routes_broadcast;
  const ScriptReg **routes_backdrop;
  const char **routes_backdrop_names;
  int nroutes_backdrop;
  int cap_routes_backdrop;
  const ScriptReg **routes_clone;
  const char **routes_clone_names;
  int nroutes_clone;
  int cap_routes_clone;
  WarnEntry *warned;
  int nwarned;
  int cap_warned;
  Value orphan;
  ListSlot orphan_list;
#ifdef _WIN32
  LPVOID main_fiber;
#endif
  void *window;
  void *renderer;
  void *probe_tex;
  void *probe_buf;
  void *font;
  void *big_font;
  void *fallback_tex;
  const char *base_path;
} Rt;

typedef void (*SbScriptFn)(Actor *ctx, Rt *rt);

int sb_run(const SbProject *proj, int argc, char **argv, const ScriptReg *scripts, int nscripts);

void sb_yield(Rt *rt);
void sb_wait(Rt *rt, double seconds);
void sb_glide(Rt *rt, Actor *actor, double seconds, double x, double y);
void sb_ask(Rt *rt, Value question);
int sb_play_sound(Rt *rt, Actor *actor, Value name);
void sb_play_until_done(Rt *rt, Actor *actor, Value name);
void sb_stop_all_sounds(Rt *rt);

Value s_num(Value v);
Value s_str(Value v);
double s_numd(Value v);
void s_str_into(Value v, char *out, size_t cap);
Value s_add(Value a, Value b);
Value s_sub(Value a, Value b);
Value s_mul(Value a, Value b);
Value s_div(Value a, Value b);
Value s_random(Value a, Value b);
Value s_gt(Value a, Value b);
Value s_lt(Value a, Value b);
Value s_eq(Value a, Value b);
Value s_and(Value a, Value b);
Value s_or(Value a, Value b);
Value s_not(Value v);
Value s_join(Value a, Value b);
Value s_letter(Value index, Value text);
Value s_length(Value v);
Value s_contains(Value a, Value b);
Value s_mod(Value a, Value b);
Value s_round(Value v);
Value s_mathop(Value op, Value v);
Value repeat_count(Value v);
int sb_truthy(Value v);

Value list_item(ListSlot *list, Value index);
void list_delete(ListSlot *list, Value index);
void list_clear(ListSlot *list);
void list_add(ListSlot *list, Value item);
void list_insert(ListSlot *list, Value index, Value item);
void list_replace(ListSlot *list, Value index, Value item);
Value list_index_of(ListSlot *list, Value item);
Value list_length(Value v);
Value list_contains(ListSlot *list, Value item);
Value list_contents(ListSlot *list);

Value *sb_var(Rt *rt, const char *name);
Value *sb_var_ctx(Actor *ctx, const char *name);
ListSlot *sb_list(Rt *rt, const char *name);
ListSlot *sb_list_ctx(Actor *ctx, const char *name);

Value sb_unsupported(Rt *rt, const char *opcode);
void sb_warn(Rt *rt, const char *message);
void sb_warnf(Rt *rt, const char *fmt, ...);
int asset_path(Rt *rt, const char *file, char *out, size_t cap);
void draw_actor(void *renderer, Rt *rt, Actor *actor, double pixel_scale);

double sb_norm_dir(double direction);
void sb_move(Rt *rt, Actor *actor, Value steps);
void sb_point_towards(Rt *rt, Actor *actor, Value ref);
double sb_tx(Rt *rt, Value ref);
double sb_ty(Rt *rt, Value ref);
void sb_goto(Rt *rt, Actor *actor, Value ref);
void sb_bounce(Rt *rt, Actor *actor);
Value sb_clamp_size(Value v);
Value sb_clamp_volume(Value v);
void sb_set_effect(Rt *rt, Actor *actor, Value effect, Value value);
void sb_change_effect(Rt *rt, Actor *actor, Value effect, Value delta);
void sb_clear_effects(Rt *rt, Actor *actor);
void sb_go_to_front(Rt *rt, Actor *actor);
void sb_go_to_back(Rt *rt, Actor *actor);
void sb_go_layer(Rt *rt, Actor *actor, Value delta);
void sb_set_backdrop(Rt *rt, Value ref);
void sb_next_backdrop(Rt *rt);
void sb_set_say(Actor *actor, Value v);
void sb_say_off(Actor *actor);
void sb_set_think(Actor *actor, Value v);
void sb_think_off(Actor *actor);
void sb_set_costume(Rt *rt, Actor *actor, Value ref);
void sb_next_costume(Actor *actor);
void sb_set_rotation_style(Actor *actor, Value style);
void sb_set_volume(Actor *actor, Value v);
void sb_change_volume(Actor *actor, Value delta);
void sb_set_sound_effect(Rt *rt, Actor *actor, Value effect, Value value);
void sb_change_sound_effect(Rt *rt, Actor *actor, Value effect, Value delta);
void sb_clear_sound_effects(Actor *actor);
Value sb_key_down(Rt *rt, Value key);
Value sb_touching(Rt *rt, Actor *actor, Value ref);
Value sb_touching_colour(Rt *rt, Actor *actor, Value colour);
Value sb_colour_touching_colour(Rt *rt, Actor *actor, Value first, Value second);
Value sb_distance_to(Rt *rt, Actor *actor, Value ref);
Value sb_timer(Rt *rt);
Value sb_loudness(Rt *rt);
Value sb_username(Rt *rt);
Value sb_mouse_down(Rt *rt);
void sb_reset_timer(Rt *rt);
Value sb_of(Rt *rt, Value attribute, Value obj);
Value sb_costume_name(Actor *actor);
void sb_broadcast(Rt *rt, Value name);
void sb_broadcast_wait(Rt *rt, Value name);
void sb_create_clone(Rt *rt, Actor *actor, Value target);
void sb_remove_clone(Rt *rt, Actor *actor);
void sb_stop_all(Rt *rt);
void sb_stop_others(Rt *rt, Actor *actor);
void sb_set_monitor_visible(Rt *rt, Value id, Value visible);
void sb_set_list_visible(Rt *rt, Value id, Value visible);

#endif
