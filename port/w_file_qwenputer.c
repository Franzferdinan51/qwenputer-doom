// WAD file class for the Qwenputer machine: the WAD is a byte array in
// read-only data (the machine's DROM). wad_file_t.mapped points straight at
// it, so the engine's lump cache can read textures/geometry in place --
// the same trick flash-based Doom ports use, no RAM copies of lumps.
//
// Registered under the name `stdc_wad_file` so the stock w_file.c dispatch
// links unchanged (w_file_stdc.o is left out of the build).

#include <string.h>

#include "doomtype.h"
#include "w_file.h"

// Provided by wad_data.c (generated at build time from the WAD file).
extern const unsigned char qwen_wad_data[];
extern const unsigned int qwen_wad_length;

static wad_file_t qwen_the_file;

extern wad_file_class_t stdc_wad_file;  // this file's class, defined below

static wad_file_t *QW_OpenFile(char *path)
{
    (void)path;  // one WAD, built in; the -iwad name is ignored
    qwen_the_file.file_class = &stdc_wad_file;
    qwen_the_file.mapped = (byte *)qwen_wad_data;
    qwen_the_file.length = qwen_wad_length;
    return &qwen_the_file;
}

static void QW_CloseFile(wad_file_t *file)
{
    (void)file;
}

static size_t QW_Read(wad_file_t *file, unsigned int offset,
                      void *buffer, size_t buffer_len)
{
    if (offset >= file->length)
        return 0;
    if (offset + buffer_len > file->length)
        buffer_len = file->length - offset;
    memcpy(buffer, qwen_wad_data + offset, buffer_len);
    return buffer_len;
}

wad_file_class_t stdc_wad_file =
{
    QW_OpenFile,
    QW_CloseFile,
    QW_Read,
};
