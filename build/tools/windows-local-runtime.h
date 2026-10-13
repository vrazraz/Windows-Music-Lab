// Windows Music Lab: local request boundary and process-scoped GPU lease.
// Included after httplib so winsock2 precedes windows.h on Windows.
#pragma once
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <stdexcept>
#include <string>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace wml {
inline bool local_only() {
    const char *value = std::getenv("WINDOWS_MUSIC_LAB_LOCAL_ONLY");
    return value && std::string(value) == "1";
}
inline bool loopback(const std::string &address) {
    return address == "127.0.0.1" || address == "::1" || address == "::ffff:127.0.0.1";
}
inline std::string lower(std::string value) {
    for (char &c : value) c = (char) std::tolower((unsigned char)c);
    return value;
}
inline bool authority(const std::string &value, int port) {
    if (port < 1 || port > 65535) return false;
    const std::string s = lower(value), suffix = ":" + std::to_string(port);
    return s == "localhost" + suffix || s == "127.0.0.1" + suffix || s == "[::1]" + suffix;
}
inline bool local_url(const std::string &value, int engine_port, int lab_port, bool referer) {
    if (value.empty()) return true; // CLI clients have no browser origin.
    if (value.rfind("http://", 0) != 0) return false;
    const auto end = value.find_first_of("/?#", 7);
    const auto host = value.substr(7, end == std::string::npos ? end : end - 7);
    if (!authority(host, engine_port) && !authority(host, lab_port)) return false;
    return referer || end == std::string::npos;
}
inline bool request_allowed(const std::string &remote, const std::string &host,
                            const std::string &origin, const std::string &referer,
                            const std::string &fetch_site, int engine_port, int lab_port) {
    return loopback(remote) && authority(host, engine_port) &&
           local_url(origin, engine_port, lab_port, false) &&
           local_url(referer, engine_port, lab_port, true) &&
           lower(fetch_site) != "cross-site";
}
class GpuLease {
#ifdef _WIN32
    HANDLE handle_ = nullptr;
#endif
    bool owned_ = false;
public:
    GpuLease() {
#ifdef _WIN32
        const char *name = std::getenv("RUACH_GPU_MUTEX");
        if (name && *name) {
            // Only this login session. No Global namespace or privilege changes.
            const std::string value(name);
            if (value.rfind("Local\\", 0) != 0 || value.size() > 240)
                throw std::runtime_error("RUACH_GPU_MUTEX must name a Local session mutex");
            handle_ = CreateMutexA(nullptr, FALSE, name);
            if (!handle_) throw std::runtime_error("Cannot create shared GPU mutex: " + std::to_string(GetLastError()));
        }
#endif
    }
    GpuLease(const GpuLease &) = delete;
    GpuLease &operator=(const GpuLease &) = delete;
    ~GpuLease() {
#ifdef _WIN32
        if (owned_) ReleaseMutex(handle_);
        if (handle_) CloseHandle(handle_);
#endif
    }
    bool try_acquire(unsigned timeout_ms = 100) {
#ifdef _WIN32
        if (!handle_ || owned_) return true;
        const DWORD result = WaitForSingleObject(handle_, timeout_ms);
        if (result == WAIT_OBJECT_0 || result == WAIT_ABANDONED) {
            owned_ = true; // A crashed owner is recoverable; always release it.
            return true;
        }
        if (result == WAIT_TIMEOUT) return false;
        throw std::runtime_error("Cannot acquire shared GPU mutex: " + std::to_string(GetLastError()));
#else
        (void) timeout_ms;
        return true;
#endif
    }
};
} // namespace wml
