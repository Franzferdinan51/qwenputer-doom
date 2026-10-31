// Doom on the Qwenputer RV32 machine (the CPU compiled into Qwen3.5-4B's weights).
//
// Platform layer for doomgeneric. The machine has:
//   - no timer   -> the clock is the frame counter: one rendered frame = one 35 Hz tic
//   - no files   -> the WAD is served from read-only data (DROM) by w_file_qwenputer.c
//   - no keyboard-> a scripted key sequence (title -> menu -> new game -> play),
//                   plus a key-state cell the runner can poke between steps
//   - putchar    -> ecall a7=1 (the machine's only output), wired up in the rv env's sys.c
//
// The framebuffer lives in guest RAM. The runner reads it (and qwen_frame_count)
// out of the machine state to display frames; nothing about the display is
// computed on the host -- the guest CPU renders every pixel.

#include <stdio.h>
#include <string.h>

#include "doomgeneric.h"
#include "doomkeys.h"

// ---------------------------------------------------------------- framebuffer

static pixel_t qwen_screen[DOOMGENERIC_RESX * DOOMGENERIC_RESY];
// DG_ScreenBuffer itself is defined by doomgeneric.c; DG_Init points it here.

// Polled by the runner: number of frames the guest has rendered so far.
volatile unsigned int qwen_frame_count = 0;

// Key-state cell the runner may write between steps (bit set = key held).
// Bit layout matches the scripted keys below: 0 up, 1 down, 2 left, 3 right,
// 4 fire, 5 use, 6 enter, 7 escape.
volatile unsigned int qwen_key_state = 0;

void DG_Init(void)
{
    DG_ScreenBuffer = qwen_screen;
    printf("qwenputer-doom: framebuffer %dx%d at %p\n",
           DOOMGENERIC_RESX, DOOMGENERIC_RESY, (void *)qwen_screen);
}

// ---------------------------------------------------------------- clock
// One frame = one tic (1000/35 ms). DG_SleepMs just advances the same clock,
// so the game runs exactly as fast as the CPU can render -- on the in-weights
// circuit that is the honest speed, whatever it turns out to be.

static uint32_t qwen_ticks_ms = 0;

uint32_t DG_GetTicksMs(void)
{
    return qwen_ticks_ms;
}

void DG_SleepMs(uint32_t ms)
{
    qwen_ticks_ms += ms;
}

void DG_DrawFrame(void)
{
    qwen_frame_count++;
    qwen_ticks_ms += 1000 / 35;
}

// ---------------------------------------------------------------- input
// Scripted key events, keyed by frame number: {frame, key, pressed}.
// Tune the frame numbers against the frame dumps from the qemu shakeout.

typedef struct { unsigned int frame; unsigned char key; int pressed; } qwen_key_event_t;

static const qwen_key_event_t qwen_script[] = {
    {  40, KEY_ENTER,     1 }, {  42, KEY_ENTER,     0 },  // title -> main menu
    {  50, KEY_ENTER,     1 }, {  52, KEY_ENTER,     0 },  // New Game
    {  60, KEY_ENTER,     1 }, {  62, KEY_ENTER,     0 },  // episode (shareware: Knee-Deep)
    {  70, KEY_ENTER,     1 }, {  72, KEY_ENTER,     0 },  // skill
    { 120, KEY_UPARROW,   1 },                            // walk forward
    { 200, KEY_FIRE,      1 }, { 206, KEY_FIRE,      0 },
    { 260, KEY_RIGHTARROW,1 },
    { 320, KEY_RIGHTARROW,0 },
    { 400, KEY_UPARROW,   0 },
    { 0, 0, 0 },
};

static unsigned int qwen_script_pos = 0;
static int qwen_live_key = 0;  // script index of a live (runner-poked) key being reported

int DG_GetKey(int *pressed, unsigned char *key)
{
    // Scripted events first.
    if (qwen_script[qwen_script_pos].frame != 0 &&
        qwen_frame_count >= qwen_script[qwen_script_pos].frame)
    {
        *key = qwen_script[qwen_script_pos].key;
        *pressed = qwen_script[qwen_script_pos].pressed;
        qwen_script_pos++;
        return 1;
    }

    // Runner-poked keys: report transitions of qwen_key_state.
    static const unsigned char keymap[8] = {
        KEY_UPARROW, KEY_DOWNARROW, KEY_LEFTARROW, KEY_RIGHTARROW,
        KEY_FIRE, KEY_USE, KEY_ENTER, KEY_ESCAPE,
    };
    static unsigned int reported_state = 0;
    unsigned int changed = qwen_key_state ^ reported_state;
    if (changed)
    {
        int bit = 0;
        while (!(changed & (1u << bit))) bit++;
        reported_state ^= (1u << bit);
        *key = keymap[bit];
        *pressed = (qwen_key_state >> bit) & 1;
        return 1;
    }

    return 0;
}

void DG_SetWindowTitle(const char *title)
{
    printf("qwenputer-doom: %s\n", title);
}

// ---------------------------------------------------------------- main

int main(void)
{
    char *argv[] = {
        "doom",
        "-iwad", "DOOM.WAD",
        "-nosound",
        "-nomusic",
        NULL,
    };
    doomgeneric_Create(5, argv);
    for (;;)
        doomgeneric_Tick();
    return 0;
}
