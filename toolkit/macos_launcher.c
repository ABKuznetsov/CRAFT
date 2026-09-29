#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

int main(int argc, char **argv) {
    char executable[PATH_MAX];
    uint32_t size = sizeof(executable);
    if (_NSGetExecutablePath(executable, &size) != 0) {
        fprintf(stderr, "CRAFT: executable path is too long\n");
        return 1;
    }

    char resolved[PATH_MAX];
    if (realpath(executable, resolved) == NULL) {
        perror("CRAFT: realpath");
        return 1;
    }

    char macos_dir[PATH_MAX];
    strlcpy(macos_dir, resolved, sizeof(macos_dir));
    char *contents_dir = dirname(macos_dir);
    contents_dir = dirname(contents_dir);

    char script[PATH_MAX];
    if (snprintf(script, sizeof(script),
                 "%s/Resources/app/toolkit/launch_craft.command",
                 contents_dir) >= (int)sizeof(script)) {
        fprintf(stderr, "CRAFT: launcher path is too long\n");
        return 1;
    }

    char **child_argv = calloc((size_t)argc + 2, sizeof(char *));
    if (child_argv == NULL) {
        perror("CRAFT: calloc");
        return 1;
    }
    child_argv[0] = "/bin/zsh";
    child_argv[1] = script;
    for (int i = 1; i < argc; ++i) child_argv[i + 1] = argv[i];

    pid_t child = 0;
    int spawn_error = posix_spawn(&child, "/bin/zsh", NULL, NULL, child_argv, environ);
    free(child_argv);
    if (spawn_error != 0) {
        fprintf(stderr, "CRAFT: could not start launcher: %s\n",
                strerror(spawn_error));
        return 1;
    }

    int status = 0;
    if (waitpid(child, &status, 0) < 0) {
        perror("CRAFT: waitpid");
        return 1;
    }
    if (WIFEXITED(status)) return WEXITSTATUS(status);
    return 1;
}
