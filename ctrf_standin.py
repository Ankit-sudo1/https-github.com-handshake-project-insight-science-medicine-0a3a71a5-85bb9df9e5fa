"""Stand-in for pytest-json-ctrf, used only by authoring/harness_checks.sh.

The verifier image installs the real pytest-json-ctrf==0.5.2 (tests/Dockerfile). The authoring sandbox this task
was built in cannot reach PyPI, so the harness runs the real pinned pytest 9.1.1 with this plugin in place of
that one: it accepts --ctrf PATH and writes a CTRF report from pytest's own results, so tests/test.sh runs
unmodified. It takes no part in selecting, running or judging the tests, and it is not in the verifier image.
"""
import json
import time


def pytest_addoption(parser):
    parser.addoption("--ctrf", action="store", default=None, help="write a CTRF report to this path")


def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--ctrf")
    if not path:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    tests = []
    for status in ("passed", "failed", "error", "skipped"):
        for rep in reporter.stats.get(status, []):
            if hasattr(rep, "nodeid") and getattr(rep, "when", "call") in ("call", "setup"):
                tests.append({"name": rep.nodeid,
                              "status": "failed" if status == "error" else status,
                              "duration": int(1000 * getattr(rep, "duration", 0.0))})
    now = int(time.time() * 1000)
    summary = {"tests": len(tests),
               "passed": sum(t["status"] == "passed" for t in tests),
               "failed": sum(t["status"] == "failed" for t in tests),
               "skipped": sum(t["status"] == "skipped" for t in tests),
               "pending": 0, "other": 0, "start": now, "stop": now}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"results": {"tool": {"name": "pytest (ctrf stand-in)"},
                               "summary": summary, "tests": tests}}, f, indent=1)
