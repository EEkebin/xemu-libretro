/* SPDX-License-Identifier: GPL-2.0-or-later
 * Included by xemu.c to reuse the existing display and QEMU lifecycle.
 * Initial desktop prototype: private GL contexts, software video presentation,
 * and one machine lifetime per process. No frontend callback runs on workers.
 */
#include "libretro.h"
#include "xemu-libretro-version.h"
#include "xemu-retro-io.h"
#include <pthread.h>
#include <sys/stat.h>

static retro_environment_t retro_environment;
static retro_video_refresh_t retro_video;
static retro_audio_sample_t retro_sample;
static retro_audio_sample_batch_t retro_batch;
static retro_input_poll_t retro_poll;
static retro_input_state_t retro_input;
static retro_log_printf_t retro_log;
static struct retro_rumble_interface retro_rumble;
static bool retro_loaded;
static bool retro_connected[4] = { true, true, true, true };

enum RetroMachineStatus {
    RETRO_MACHINE_FRESH,
    RETRO_MACHINE_STARTING,
    RETRO_MACHINE_READY,
    RETRO_MACHINE_FAILED,
    RETRO_MACHINE_FINISHED,
};

static struct {
    pthread_mutex_t lock;
    pthread_cond_t wake;
    enum RetroMachineStatus status;
    bool request, stop, reset;
    unsigned completed;
    char error[1024];
    char *bootrom, *bios, *hdd, *eeprom, *disc, *settings;
    QemuThread worker;
    XemuRetroPad pads[4];
    uint16_t rumble[4][2];
    uint32_t *pixels, *readback;
    unsigned width, height;
} retro_machine = {
    .lock = PTHREAD_MUTEX_INITIALIZER,
    .wake = PTHREAD_COND_INITIALIZER,
};
static XemuRetroAudio retro_audio = { .lock = PTHREAD_MUTEX_INITIALIZER };
static __thread bool retro_rcu_registered;

#ifdef _WIN32
static bool retro_module_pinned;

/* QEMU starts an RCU worker in a library constructor. Pin even metadata-only
 * loads, before a frontend can release the DLL after a failed preflight. */
static void __attribute__((constructor)) retro_pin_module(void)
{
    HMODULE module;
    retro_module_pinned = GetModuleHandleExA(
        GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
        (LPCSTR)&retro_machine, &module);
}
#endif

static void retro_notify(const char *text)
{
    struct retro_message message = { text, 600 };
    if (retro_log) {
        retro_log(RETRO_LOG_INFO, "%s\n", text);
    }
    if (retro_environment) {
        retro_environment(RETRO_ENVIRONMENT_SET_MESSAGE, &message);
    }
}

void xemu_retro_report_error(const char *message)
{
    pthread_mutex_lock(&retro_machine.lock);
    snprintf(retro_machine.error, sizeof(retro_machine.error), "%s", message);
    pthread_mutex_unlock(&retro_machine.lock);
    fprintf(stderr, "xemu-libretro: %s\n", message);
}

static void retro_set_status(enum RetroMachineStatus status)
{
    pthread_mutex_lock(&retro_machine.lock);
    /* A late startup must not revive a machine retired by a frontend timeout.
     */
    if (status != RETRO_MACHINE_READY ||
        retro_machine.status == RETRO_MACHINE_STARTING) {
        retro_machine.status = status;
    }
    pthread_cond_broadcast(&retro_machine.wake);
    pthread_mutex_unlock(&retro_machine.lock);
}

/* QEMU assumes it owns the process. Catch explicit exit calls in this linked
 * image, preserve the host, and retire the instance. The DSO is NODELETE
 * because QEMU's global workers and partially initialized devices cannot safely
 * unload. This does not intercept assertions, signals, or third-party-library
 * exits. */
G_NORETURN void __wrap_exit(int status);
G_NORETURN void __wrap_exit(int status)
{
    char message[128];
    snprintf(
        message, sizeof(message),
        "xemu exited with status %d; restart RetroArch before loading again.",
        status);
    xemu_retro_report_error(message);
    retro_set_status(RETRO_MACHINE_FAILED);
    if (retro_rcu_registered) {
        rcu_unregister_thread();
        retro_rcu_registered = false;
    }
    qemu_thread_exit(NULL);
}

#ifdef _WIN32
/* MinGW can call exit through its import pointer instead of a direct symbol.
 * Wrap both forms so an initialization failure cannot close the frontend. */
void (*__wrap___imp_exit)(int) = __wrap_exit;
#endif

void xemu_retro_audio_push(const int16_t *samples, size_t frames)
{
    xemu_retro_audio_write(&retro_audio, samples, frames);
}

size_t xemu_retro_audio_queued(void)
{
    size_t count;
    pthread_mutex_lock(&retro_audio.lock);
    count = retro_audio.count;
    pthread_mutex_unlock(&retro_audio.lock);
    return count;
}

static enum RetroMachineStatus retro_status(void)
{
    enum RetroMachineStatus status;
    pthread_mutex_lock(&retro_machine.lock);
    status = retro_machine.status;
    pthread_mutex_unlock(&retro_machine.lock);
    return status;
}

static bool retro_wait(bool startup, unsigned previous, int seconds)
{
    struct timespec deadline;
    clock_gettime(CLOCK_REALTIME, &deadline);
    deadline.tv_sec += seconds;
    pthread_mutex_lock(&retro_machine.lock);
    while ((startup && retro_machine.status == RETRO_MACHINE_STARTING) ||
           (!startup && retro_machine.status == RETRO_MACHINE_READY &&
            retro_machine.completed == previous)) {
        if (pthread_cond_timedwait(&retro_machine.wake, &retro_machine.lock,
                                   &deadline) == ETIMEDOUT) {
            snprintf(retro_machine.error, sizeof(retro_machine.error),
                     "xemu worker timed out; restart RetroArch.");
            retro_machine.status = RETRO_MACHINE_FAILED;
            pthread_mutex_unlock(&retro_machine.lock);
            return false;
        }
    }
    bool ready = retro_machine.status == RETRO_MACHINE_READY;
    pthread_mutex_unlock(&retro_machine.lock);
    return ready;
}

static void retro_capture_frame(struct xemu_console *scon)
{
    SDL_GL_MakeCurrent(scon->real_window, scon->winctx);
    GLuint texture = nv2a_get_framebuffer_surface();
    bool fallback = texture == 0;
    if (fallback) {
        xemu_main_loop_lock();
        xb_surface_gl_create_texture(scon->surface);
        texture = scon->surface->texture;
        xemu_main_loop_unlock();
    }
    glBindTexture(GL_TEXTURE_2D, texture);
    GLint width = 0, height = 0;
    glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_WIDTH, &width);
    glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_HEIGHT, &height);
    if (width > 0 && width <= 1920 && height > 0 && height <= 1080) {
        size_t bytes = (size_t)width * height * sizeof(uint32_t);
        retro_machine.readback = g_realloc(retro_machine.readback, bytes);
        retro_machine.pixels = g_realloc(retro_machine.pixels, bytes);
        glPixelStorei(GL_PACK_ALIGNMENT, 4);
        glPixelStorei(GL_PACK_ROW_LENGTH, 0);
        glGetTexImage(GL_TEXTURE_2D, 0, GL_BGRA, GL_UNSIGNED_BYTE,
                      retro_machine.readback);
        for (int y = 0; y < height; y++) {
            int source_y = fallback ? y : height - 1 - y;
            memcpy(retro_machine.pixels + y * width,
                   retro_machine.readback + source_y * width,
                   width * sizeof(uint32_t));
        }
        retro_machine.width = width;
        retro_machine.height = height;
    }
    if (fallback) {
        xemu_main_loop_lock();
        xb_surface_gl_destroy_texture(scon->surface);
        xemu_main_loop_unlock();
    }
    nv2a_release_framebuffer_surface();
}

static void *retro_worker(void *opaque)
{
    QemuThread machine_thread;
    char program[] = "xemu-libretro";
    char paused[] = "-S";
    char accel[] = "-accel";
    char tcg[] = "tcg";
    char audiodev[] = "-audio";
    char no_host_audio[] = "none,id=libretro";
    char *args[] = {
        program, paused, accel, tcg, audiodev, no_host_audio, NULL
    };
    (void)opaque;

    rcu_register_thread();
    retro_rcu_registered = true;
    xemu_settings_set_path(retro_machine.settings);
    xemu_settings_load_defaults();
    xemu_settings_set_string(&g_config.sys.files.bootrom_path,
                             retro_machine.bootrom);
    xemu_settings_set_string(&g_config.sys.files.flashrom_path,
                             retro_machine.bios);
    xemu_settings_set_string(&g_config.sys.files.hdd_path, retro_machine.hdd);
    xemu_settings_set_string(&g_config.sys.files.eeprom_path,
                             retro_machine.eeprom);
    xemu_settings_set_string(&g_config.sys.files.dvd_path, retro_machine.disc);
    g_config.general.show_welcome = false;
    g_config.general.updates.check = false;
    g_config.display.window.vsync = false;
    g_config.net.enable = false;
    g_config.perf.cache_shaders = false;

    gArgc = 6;
    gArgv = args;
    display_very_early_init(NULL);
    qemu_sem_init(&display_init_sem, 0);
    qemu_sem_init(&display_shutdown_sem, 0);
    qemu_thread_create(&machine_thread, "xemu-qemu", qemu_main, NULL,
                       QEMU_THREAD_JOINABLE);
    while (qemu_sem_timedwait(&display_init_sem, 100) != 0) {
        if (retro_status() == RETRO_MACHINE_FAILED) {
            rcu_unregister_thread();
            retro_rcu_registered = false;
            return NULL;
        }
    }
    tcg_register_init_ctx();
    qemu_set_current_aio_context(qemu_get_aio_context());
    xemu_main_loop_lock();
    xemu_input_init();
    xemu_main_loop_unlock();
    retro_set_status(RETRO_MACHINE_READY);

    bool vm_running = false;
    int64_t next_frame_us = 0;
    while (true) {
        pthread_mutex_lock(&retro_machine.lock);
        while (!retro_machine.request && !retro_machine.stop &&
               retro_machine.status == RETRO_MACHINE_READY) {
            if (!vm_running) {
                pthread_cond_wait(&retro_machine.wake, &retro_machine.lock);
                continue;
            }
            /* Frontends pause by ceasing retro_run calls. Keep emulation
             * running across normal callbacks, but stop after 100 ms idle. */
            struct timespec idle_deadline;
            clock_gettime(CLOCK_REALTIME, &idle_deadline);
            idle_deadline.tv_nsec += 100000000;
            if (idle_deadline.tv_nsec >= 1000000000) {
                idle_deadline.tv_sec++;
                idle_deadline.tv_nsec -= 1000000000;
            }
            int result = pthread_cond_timedwait(
                &retro_machine.wake, &retro_machine.lock, &idle_deadline);
            if (result == ETIMEDOUT && !retro_machine.request) {
                pthread_mutex_unlock(&retro_machine.lock);
                xemu_main_loop_lock();
                vm_stop(RUN_STATE_PAUSED);
                xemu_main_loop_unlock();
                vm_running = false;
                next_frame_us = 0;
                pthread_mutex_lock(&retro_machine.lock);
            }
        }
        bool stop =
            retro_machine.stop || retro_machine.status == RETRO_MACHINE_FAILED;
        bool reset = retro_machine.reset;
        retro_machine.reset = false;
        retro_machine.request = false;
        pthread_mutex_unlock(&retro_machine.lock);
        if (stop || qatomic_read(&qemu_exiting)) {
            break;
        }

        /* Service the private window on its owning thread, including Win32
         * messages. Controller input comes exclusively from the frontend. */
        SDL_PumpEvents();
        SDL_FlushEvents(SDL_EVENT_FIRST, SDL_EVENT_LAST);

        xemu_main_loop_lock();
        for (unsigned port = 0; port < 4; port++) {
            ControllerState *state = bound_controllers[port];
            state->buttons = retro_machine.pads[port].buttons;
            memcpy(state->axis, retro_machine.pads[port].axis,
                   sizeof(state->axis));
        }
        if (reset) {
            qemu_system_reset_request(SHUTDOWN_CAUSE_HOST_QMP_SYSTEM_RESET);
        }
        if (!vm_running) {
            vm_start();
            vm_running = true;
        }
        xemu_main_loop_unlock();

        /* Carry a deadline across frames so capture and frontend work count
         * toward the 60 Hz period instead of adding to a full-frame sleep. */
        int64_t now_us = g_get_monotonic_time();
        if (!next_frame_us || now_us > next_frame_us + 50000) {
            next_frame_us = now_us + 16667;
        }
        if (next_frame_us > now_us) {
            g_usleep(next_frame_us - now_us);
        }
        next_frame_us += 16667;
        if (!qatomic_read(&qemu_exiting)) {
            retro_capture_frame(&scon_list[0]);
            xemu_main_loop_lock();
            for (unsigned port = 0; port < 4; port++) {
                retro_machine.rumble[port][0] =
                    bound_controllers[port]->rumble_l;
                retro_machine.rumble[port][1] =
                    bound_controllers[port]->rumble_r;
            }
            xemu_main_loop_unlock();
        }
        pthread_mutex_lock(&retro_machine.lock);
        retro_machine.completed++;
        pthread_cond_broadcast(&retro_machine.wake);
        pthread_mutex_unlock(&retro_machine.lock);
    }

    if (!qatomic_read(&qemu_exiting)) {
        xemu_main_loop_lock();
        shutdown_action = SHUTDOWN_ACTION_POWEROFF;
        qemu_system_shutdown_request(SHUTDOWN_CAUSE_HOST_UI);
        xemu_main_loop_unlock();
    }
    qemu_sem_post(&display_shutdown_sem);
    qemu_thread_join(&machine_thread);
    display_finalize();
    rcu_unregister_thread();
    retro_rcu_registered = false;
    retro_set_status(RETRO_MACHINE_FINISHED);
    return NULL;
}

void retro_set_environment(retro_environment_t callback)
{
    bool no_game = true;
    retro_environment = callback;
    if (callback) {
        callback(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &no_game);
    }
}
void retro_set_video_refresh(retro_video_refresh_t cb)
{
    retro_video = cb;
}
void retro_set_audio_sample(retro_audio_sample_t cb)
{
    retro_sample = cb;
}
void retro_set_audio_sample_batch(retro_audio_sample_batch_t cb)
{
    retro_batch = cb;
}
void retro_set_input_poll(retro_input_poll_t cb)
{
    retro_poll = cb;
}
void retro_set_input_state(retro_input_state_t cb)
{
    retro_input = cb;
}
unsigned retro_api_version(void)
{
    return RETRO_API_VERSION;
}

void retro_init(void)
{
    struct retro_log_callback logging = { 0 };
    retro_log = NULL;
    memset(&retro_rumble, 0, sizeof(retro_rumble));
    if (retro_environment) {
        if (retro_environment(RETRO_ENVIRONMENT_GET_LOG_INTERFACE, &logging)) {
            retro_log = logging.log;
        }
        retro_environment(RETRO_ENVIRONMENT_GET_RUMBLE_INTERFACE,
                          &retro_rumble);
    }
}

void retro_get_system_info(struct retro_system_info *info)
{
    *info = (struct retro_system_info){
        .library_name = "xemu (experimental native)",
        .library_version = XEMU_LIBRETRO_VERSION,
        .valid_extensions = "iso",
        .need_fullpath = true,
        .block_extract = true,
    };
}

void retro_get_system_av_info(struct retro_system_av_info *info)
{
    *info = (struct retro_system_av_info){
        .geometry = { 640, 480, 1920, 1080, 4.0f / 3.0f },
        .timing = { 60.0, 48000.0 },
    };
}

static bool retro_check_file(const char *path, off_t size)
{
#ifdef _WIN32
    struct _stat64 st;
    int result = _stat64(path, &st);
#else
    struct stat st;
    int result = stat(path, &st);
#endif
    if (result || !S_ISREG(st.st_mode) || (size && st.st_size != size) ||
        (!size && !st.st_size)) {
        char error[1024];
        snprintf(error, sizeof(error), "Missing or invalid xemu asset: %s",
                 path);
        retro_notify(error);
        return false;
    }
    return true;
}

static void retro_free_paths(void)
{
    g_clear_pointer(&retro_machine.bootrom, g_free);
    g_clear_pointer(&retro_machine.bios, g_free);
    g_clear_pointer(&retro_machine.hdd, g_free);
    g_clear_pointer(&retro_machine.eeprom, g_free);
    g_clear_pointer(&retro_machine.disc, g_free);
    g_clear_pointer(&retro_machine.settings, g_free);
}

bool retro_load_game(const struct retro_game_info *game)
{
    const char *system = NULL, *save = NULL;
    enum retro_pixel_format format = RETRO_PIXEL_FORMAT_XRGB8888;
    if (retro_status() != RETRO_MACHINE_FRESH) {
        retro_notify("This prototype permits one Xbox machine per process. "
                     "Restart RetroArch.");
        return false;
    }
    if (!retro_environment ||
        !retro_environment(RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY, &system) ||
        !system ||
        !retro_environment(RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY, &save) ||
        !save) {
        retro_notify(
            "Set RetroArch's system and save directories before loading xemu.");
        return false;
    }
    if (!retro_environment(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format)) {
        retro_notify(
            "The xemu prototype requires XRGB8888 software video support.");
        return false;
    }
    retro_machine.bootrom =
        g_build_filename(system, "xemu", "mcpx_1.0.bin", NULL);
    retro_machine.bios = g_build_filename(system, "xemu", "bios.bin", NULL);
    retro_machine.eeprom = g_build_filename(save, "xemu", "eeprom.bin", NULL);
    retro_machine.hdd = g_build_filename(save, "xemu", "xbox_hdd.qcow2", NULL);
    retro_machine.settings =
        g_build_filename(save, "xemu", "libretro.toml", NULL);
    retro_machine.disc = g_strdup(game && game->path ? game->path : "");
    bool valid = (!game || (game->path && retro_check_file(game->path, 0))) &&
                 retro_check_file(retro_machine.bootrom, 512) &&
                 retro_check_file(retro_machine.bios, 0) &&
                 (!g_file_test(retro_machine.eeprom, G_FILE_TEST_EXISTS) ||
                  retro_check_file(retro_machine.eeprom, 256)) &&
                 retro_check_file(retro_machine.hdd, 0);
    if (!valid) {
        retro_free_paths();
        return false;
    }
#ifdef _WIN32
    if (!retro_module_pinned) {
        retro_notify("Unable to pin the xemu DLL in memory.");
        retro_free_paths();
        return false;
    }
#endif
    xemu_retro_audio_clear(&retro_audio);
    retro_set_status(RETRO_MACHINE_STARTING);
    qemu_thread_create(&retro_machine.worker, "xemu-present", retro_worker,
                       NULL, QEMU_THREAD_JOINABLE);
    if (!retro_wait(true, 0, 30)) {
        pthread_mutex_lock(&retro_machine.lock);
        char error[1024];
        snprintf(error, sizeof(error), "%s", retro_machine.error);
        pthread_mutex_unlock(&retro_machine.lock);
        retro_notify(error);
        return false;
    }
    retro_loaded = true;
    return true;
}

void retro_run(void)
{
    if (!retro_loaded) {
        return;
    }
    if (retro_poll) {
        retro_poll();
    }
    pthread_mutex_lock(&retro_machine.lock);
    unsigned previous = retro_machine.completed;
    for (unsigned port = 0; port < 4; port++) {
        xemu_retro_map_pad(retro_connected[port] ? retro_input : NULL, port,
                           &retro_machine.pads[port]);
    }
    retro_machine.request = true;
    pthread_cond_broadcast(&retro_machine.wake);
    pthread_mutex_unlock(&retro_machine.lock);
    if (!retro_wait(false, previous, 10)) {
        retro_notify("xemu stopped or timed out; restart RetroArch. See the "
                     "log for details.");
        retro_loaded = false;
        if (retro_environment) {
            retro_environment(RETRO_ENVIRONMENT_SHUTDOWN, NULL);
        }
        return;
    }
    if (retro_video) {
        retro_video(retro_machine.pixels, retro_machine.width,
                    retro_machine.height,
                    retro_machine.width * sizeof(uint32_t));
    }
    int16_t samples[800 * 2];
    size_t frames = xemu_retro_audio_peek(&retro_audio, samples, 800);
    size_t accepted = 0;
    if (retro_batch) {
        accepted = retro_batch(samples, frames);
    } else if (retro_sample) {
        for (size_t i = 0; i < frames; i++) {
            retro_sample(samples[2 * i], samples[2 * i + 1]);
        }
        accepted = frames;
    }
    xemu_retro_audio_consume(&retro_audio, MIN(accepted, frames));
    if (retro_rumble.set_rumble_state) {
        for (unsigned port = 0; port < 4; port++) {
            retro_rumble.set_rumble_state(
                port, RETRO_RUMBLE_STRONG,
                retro_connected[port] ? retro_machine.rumble[port][0] : 0);
            retro_rumble.set_rumble_state(
                port, RETRO_RUMBLE_WEAK,
                retro_connected[port] ? retro_machine.rumble[port][1] : 0);
        }
    }
}

void retro_unload_game(void)
{
    retro_loaded = false;
    if (retro_rumble.set_rumble_state) {
        for (unsigned port = 0; port < 4; port++) {
            retro_rumble.set_rumble_state(port, RETRO_RUMBLE_STRONG, 0);
            retro_rumble.set_rumble_state(port, RETRO_RUMBLE_WEAK, 0);
        }
    }
    if (retro_status() == RETRO_MACHINE_READY) {
        pthread_mutex_lock(&retro_machine.lock);
        retro_machine.stop = true;
        pthread_cond_broadcast(&retro_machine.wake);
        unsigned previous = retro_machine.completed;
        pthread_mutex_unlock(&retro_machine.lock);
        retro_wait(false, previous, 10);
        if (retro_status() == RETRO_MACHINE_FINISHED) {
            qemu_thread_join(&retro_machine.worker);
        }
    }
    xemu_retro_audio_clear(&retro_audio);
}

void retro_deinit(void)
{
    retro_unload_game();
    retro_log = NULL;
}
void retro_reset(void)
{
    pthread_mutex_lock(&retro_machine.lock);
    retro_machine.reset = true;
    pthread_mutex_unlock(&retro_machine.lock);
}
void retro_set_controller_port_device(unsigned port, unsigned device)
{
    if (port < 4) {
        retro_connected[port] =
            (device & RETRO_DEVICE_MASK) == RETRO_DEVICE_JOYPAD;
    }
}
unsigned retro_get_region(void)
{
    return RETRO_REGION_NTSC;
}
size_t retro_serialize_size(void)
{
    return 0;
}
bool retro_serialize(void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
bool retro_unserialize(const void *data, size_t size)
{
    (void)data;
    (void)size;
    return false;
}
bool retro_load_game_special(unsigned type, const struct retro_game_info *game,
                             size_t count)
{
    (void)type;
    (void)game;
    (void)count;
    return false;
}
void retro_cheat_reset(void)
{
}
void retro_cheat_set(unsigned index, bool enabled, const char *code)
{
    (void)index;
    (void)enabled;
    (void)code;
}
void *retro_get_memory_data(unsigned id)
{
    (void)id;
    return NULL;
}
size_t retro_get_memory_size(unsigned id)
{
    (void)id;
    return 0;
}
