// Minimal Arduino shim so the pure-logic firmware modules (framebuf) can be
// compiled and stress-tested on a host with a thread sanitiser. It defines only
// what those modules use; it is not an emulator.
#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <cstdio>
using std::min;
using std::max;
#define log_e(...) do { printf("E: " __VA_ARGS__); printf("\n"); } while (0)
#define log_w(...) do { printf("W: " __VA_ARGS__); printf("\n"); } while (0)
#define log_i(...) do { printf("I: " __VA_ARGS__); printf("\n"); } while (0)
