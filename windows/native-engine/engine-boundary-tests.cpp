// Synthetic boundary tests: no model loading, inference or user data.
#define main wml_engine_main
#include "../../build/tools/yue-server.cpp"
#undef main
#include <iostream>

static int checks = 0;
static void check(bool ok, const char *message) {
    ++checks;
    if (!ok) throw std::runtime_error(message);
}
static bool wait_for(const std::function<bool()> &predicate, int ms = 3000) {
    const auto limit = std::chrono::steady_clock::now() + std::chrono::milliseconds(ms);
    while (std::chrono::steady_clock::now() < limit) {
        if (predicate()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return predicate();
}
static void http_boundary() {
    _putenv_s("WINDOWS_MUSIC_LAB_LOCAL_ONLY", "1");
    _putenv_s("LAB_PORT", "41871");
    httplib::Server server;
    const int port = server.bind_to_any_port("127.0.0.1");
    check(port > 0, "mock HTTP bind failed");
    server.set_pre_routing_handler([port](const httplib::Request &req, httplib::Response &res) {
        return server_request_guard(req, res, port, true); // public override cannot bypass local flag
    });
    std::atomic<int> mutations{0};
    server.Post(R"(/.*)", [&mutations](const httplib::Request &, httplib::Response &res) { ++mutations; res.set_content("ok", "text/plain"); });
    server.Get("/health", [](const httplib::Request &, httplib::Response &res) { res.set_content("ok", "text/plain"); });
    std::thread serving([&] { server.listen_after_bind(); });
    try {
        check(wait_for([&] { return server.is_running(); }), "mock HTTP server did not start");
        httplib::Client client("127.0.0.1", port);
        client.set_connection_timeout(2, 0);
        const auto own = "http://localhost:" + std::to_string(port);
        auto ok = client.Post("/synth", {{"Host", "localhost:" + std::to_string(port)}, {"Origin", own}}, "{}", "application/json");
        check(ok && ok->status == 200, "own UI origin blocked");
        ok = client.Post("/settings", {{"Origin", "http://127.0.0.1:41871"}}, "{}", "application/json");
        check(ok && ok->status == 200, "own lab origin blocked");
        const int permitted = mutations.load();
        for (const std::string path : {"/synth", "/transcribe", "/job", "/settings", "/unload", "/library/delete", "/lab/writer", "/api/jobs"}) {
            auto bad = client.Post(path, {{"Origin", "https://attacker.example"}}, "{}", "application/json");
            check(bad && bad->status == 403, "foreign origin reached mutating route");
        }
        for (const httplib::Headers headers : {
                httplib::Headers{{"Host", "attacker.example:" + std::to_string(port)}},
                httplib::Headers{{"Host", "localhost:41871"}},
                httplib::Headers{{"Origin", "null"}},
                httplib::Headers{{"Origin", own + "/extra"}},
                httplib::Headers{{"Referer", "http://localhost:41871@attacker.example/page"}},
                httplib::Headers{{"Sec-Fetch-Site", "cross-site"}}}) {
            auto bad = client.Post("/synth", headers, "{}", "application/json");
            check(bad && bad->status == 403, "Host/origin/fetch attack permitted");
        }
        check(mutations.load() == permitted, "blocked requests mutated state");
        auto read = client.Get("/health", {{"Origin", "https://attacker.example"}});
        check(read && read->status == 403, "foreign origin read API");
        read = client.Get("/health");
        check(read && read->status == 200, "loopback CLI read blocked");
        httplib::Request remote;
        remote.remote_addr = "192.168.0.2"; remote.headers.emplace("Host", "localhost:" + std::to_string(port));
        httplib::Response response;
        check(server_request_guard(remote, response, port, true) == httplib::Server::HandlerResponse::Handled && response.status == 403,
              "private network/public override bypassed local guard");
        _putenv_s("WINDOWS_MUSIC_LAB_LOCAL_ONLY", "0");
        response.status = 200;
        check(server_request_guard(remote, response, port, false) == httplib::Server::HandlerResponse::Unhandled,
              "legacy non-local mode changed");
    } catch (...) { server.stop(); serving.join(); throw; }
    server.stop(); serving.join();
}
static void queue_handoff() {
    const std::string name = "Local\\WindowsMusicLab-EngineTest-" + std::to_string(GetCurrentProcessId());
    _putenv_s("RUACH_GPU_MUTEX", name.c_str());
    std::shared_ptr<Job> first = job_create(), second = job_create();
    std::atomic<int> rendered{0};
    std::thread worker(worker_main);
    try {
        {
            wml::GpuLease python_owner;
            check(python_owner.try_acquire(), "fixture owner cannot acquire lease");
            work_push([&] { ++rendered; first->status.store(JobStatus::DONE); }, first);
            work_push([&] { ++rendered; second->started.store(true); second->status.store(JobStatus::DONE); }, second);
            check(wait_for([&] { return first->waiting_gpu.load(); }), "job did not wait for foreign lease");
            check(!first->started.load() && rendered.load() == 0, "queued job started before GPU lease");
            { std::lock_guard<std::mutex> lock(mtx_active); check(!g_active_job && g_waiting_job == first, "waiting job reported active"); }
            bool control = false;
            check(work_run_soon([&] { control = true; }, 2000) && control, "unload/control could not bypass waiting GPU job");
            first->cancel.store(true);
            check(wait_for([&] { return first->status.load() == JobStatus::CANCELLED; }), "waiting cancel failed");
            check(rendered.load() == 0, "cancelled GPU job ran");
            check(wait_for([&] { return second->waiting_gpu.load(); }), "FIFO second GPU job lost");
        }
        check(wait_for([&] { return second->status.load() == JobStatus::DONE; }), "GPU job did not resume after owner release");
        check(rendered.load() == 1, "FIFO/cancellation executed wrong job");
        auto throwing = job_create();
        work_push([throwing] { active_job_set(throwing); throw std::runtime_error("synthetic render failure"); }, throwing);
        check(wait_for([&] { return throwing->status.load() == JobStatus::FAILED; }), "render exception not surfaced");
        { wml::GpuLease after_error; check(after_error.try_acquire(1000), "render exception leaked GPU lease"); }
        { std::lock_guard<std::mutex> lock(mtx_active); check(!g_active_job, "render exception left active state"); }
        _putenv_s("RUACH_GPU_MUTEX", "Global\\ForbiddenTest");
        auto failure = job_create();
        work_push([failure] { failure->status.store(JobStatus::DONE); }, failure);
        check(wait_for([&] { return failure->status.load() == JobStatus::FAILED; }), "lease initialization failure was not surfaced");
        check(!failure->error.empty() && !failure->waiting_gpu.load(), "failed lease left stale waiting state");
        check(work_run_soon([] {}, 2000), "lease failure killed worker/control loop");
    } catch (...) {
        { std::lock_guard<std::mutex> lock(mtx_work); g_work_stop = true; }
        cv_work.notify_all(); worker.join(); throw;
    }
    { std::lock_guard<std::mutex> lock(mtx_work); g_work_stop = true; }
    cv_work.notify_all(); worker.join();
    _putenv_s("RUACH_GPU_MUTEX", name.c_str());
    // An exited process abandoned the lease. Its successor must recover it.
    wml::GpuLease successor;
    wchar_t exe[MAX_PATH]; GetModuleFileNameW(nullptr, exe, MAX_PATH);
    std::wstring command = L"\"" + std::wstring(exe) + L"\" --abandon";
    STARTUPINFOW startup{}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process{};
    check(CreateProcessW(nullptr, &command[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &startup, &process) != FALSE,
          "cannot create abandoned-owner fixture");
    const DWORD waited = WaitForSingleObject(process.hProcess, 3000);
    CloseHandle(process.hThread); CloseHandle(process.hProcess);
    check(waited == WAIT_OBJECT_0, "abandoned-owner fixture did not exit");
    check(successor.try_acquire(1000), "abandoned GPU lease not recoverable");
}
int main(int argc, char **argv) {
    if (argc > 1 && std::string(argv[1]) == "--abandon") {
        wml::GpuLease lease;
        if (!lease.try_acquire(1000)) return 2;
        ExitProcess(0); // intentionally skip destructor, exercising WAIT_ABANDONED
    }
    try {
        http_boundary(); queue_handoff();
        std::cout << "PASS " << checks << " engine boundary/queue/mutex checks; no inference\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "FAIL: " << error.what() << "\n";
        return 1;
    }
}
