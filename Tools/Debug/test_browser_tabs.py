#!/usr/bin/env python3
"""Browser tab labels (skills/cowork/tools/browser_tabs.cjs), against a real throwaway Chrome.

    python Tools/Debug/test_browser_tabs.py

ADR Memory/tasks/20261115-090000-browser-tab-labels. Starts its own headless Chrome on a free port in
9350-9359 with a temp profile - ⛔ never 9333-9337, which other sessions use. A missing Node or Chrome is
a FAILURE (as test_watch_folder.py), never a quiet skip.
Cases: label tags mine and idles the rest; another role's tab is never taken; Game's in-page code and
ours on one page converge and the page still answers; keep restores a tag after a full navigation; a
second keeper exits; the keeper exits when the browser goes away.
"""

import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _debugpaths import fresh_scratch, repo_path, scratch_dir  # noqa: E402

TOOL = repo_path("skills", "cowork", "tools", "browser_tabs.cjs")
CHROMES = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
           "/usr/bin/google-chrome", "/usr/bin/chromium"]
# Game's in-page code with a DIFFERENT tag - must converge with ours, not fight (ADR B2).
GAME = ("(() => { const strip = (t) => t.replace(/^\\[\\d+-\\d+ [^\\]]*\\] /, ''); window.__tabTagText = '[1-9 GAME] ';"
        " const fix = () => { const want = window.__tabTagText + strip(document.title); if (document.title !== want)"
        " document.title = want; }; fix(); if (!window.__tabTag) { window.__tabTag = new MutationObserver(fix);"
        " window.__tabTag.observe(document.querySelector('title') || document.head, { childList: true, subtree: true,"
        " characterData: true }); } return 1; })()")
HELPER = r"""
const [port, id, method, arg] = process.argv.slice(2);
(async () => {
  const t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find((x) => x.id === id);
  const ws = new WebSocket(t.webSocketDebuggerUrl);
  await new Promise((ok) => ws.onopen = ok);
  const params = method === 'nav' ? { url: arg } : { expression: arg, returnByValue: true };
  ws.send(JSON.stringify({ id: 1, method: method === 'nav' ? 'Page.navigate' : 'Runtime.evaluate', params }));
  const m = await Promise.race([new Promise((ok) => ws.onmessage = (e) => ok(JSON.parse(e.data))),
                                new Promise((ok) => setTimeout(() => ok(null), 3000))]);
  console.log(m ? JSON.stringify(m.result && m.result.result ? m.result.result.value : 'ok') : 'TIMEOUT');
  process.exit(0);
})();
"""


def free_port():
    for p in range(9350, 9360):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    raise AssertionError("no free port in 9350-9359")


def get(port, path, method="GET"):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), method=method)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    fresh_scratch()
    node = shutil.which("node")
    assert node, "node is not installed - browser_tabs.cjs needs Node with built-in WebSocket"
    chrome = next((c for c in CHROMES if os.path.exists(c)), None)
    assert chrome, "Google Chrome not found in %s" % CHROMES
    with scratch_dir("browser") as d:
        for name, title in (("one", "One"), ("two", "Two"), ("three", "Three")):
            with open(os.path.join(d, name + ".html"), "w", encoding="utf-8") as f:
                f.write("<title>%s</title>%s" % (title, name))
        helper = os.path.join(d, "helper.cjs")
        with open(helper, "w", encoding="utf-8") as f:
            f.write(HELPER)
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=d))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        web = "http://127.0.0.1:%d/" % httpd.server_address[1]
        port = free_port()
        chrome_p = subprocess.Popen([chrome, "--headless=new", "--remote-debugging-port=%d" % port,
                                     "--user-data-dir=" + os.path.join(d, "profile"), "--no-first-run",
                                     "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        keepers = []
        try:
            for _ in range(50):
                try:
                    get(port, "/json/version")
                    break
                except OSError:
                    time.sleep(0.2)
            ids = {n: get(port, "/json/new?" + web + n + ".html", "PUT")["id"] for n in ("one", "two", "three")}
            time.sleep(1.5)

            def titles():
                return {n: next(t["title"] for t in get(port, "/json/list") if t["id"] == i) for n, i in ids.items()}

            def tool(*args, timeout=30):
                return subprocess.run([node, TOOL] + [str(a) for a in args], capture_output=True, text=True,
                                      timeout=timeout)

            def page(name, method, arg):
                return subprocess.run([node, helper, str(port), ids[name], method, arg], capture_output=True,
                                      text=True, timeout=15).stdout.strip()

            # 1. another role tags "three" first; then T1 labels with a url-part: one = T1, two = idle,
            #    three stays X's (never taken).
            r = tool("label", port, "X", "three.html")
            assert r.returncode == 0, r.stderr
            r = tool("label", port, "T1", "one.html")
            assert r.returncode == 0, r.stderr
            time.sleep(0.3)
            t = titles()
            assert t["one"].endswith(" T1] One") and t["one"].startswith("[%d-" % port), t
            assert t["two"].endswith(" 閒置] Two"), t
            assert t["three"].endswith(" X] Three"), "another role's tab was taken: %r" % t
            # ... and without a url-part T1 still does not take X's tab, but takes the idle one.
            tool("label", port, "T1")
            time.sleep(0.3)
            t = titles()
            assert t["three"].endswith(" X] Three") and t["two"].endswith(" T1] Two"), t
            # 2. Game's observer with a different tag on the same page: converges, page still answers.
            assert page("one", "eval", GAME) == "1"
            time.sleep(0.5)
            alive = page("one", "eval", "document.title")
            assert alive != "TIMEOUT", "the page stopped answering with Game's and our observer together"
            assert alive.count("] ") == 1, "two tags on one title: %s" % alive
            # 3. keep restores a tag lost on a full navigation; a second keeper exits.
            k = subprocess.Popen([node, TOOL, "keep", str(port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True)
            keepers.append(k)
            time.sleep(2)
            before = titles()["two"]
            page("two", "nav", web + "one.html")
            time.sleep(3)
            after = titles()["two"]
            assert after.startswith(before.split("] ")[0] + "] ") and after.endswith("One"), (before, after)
            r = tool("keep", port, timeout=20)
            assert "another keeper" in r.stdout, "a second keeper did not leave: %r" % r.stdout
            assert k.poll() is None, "the first keeper exited"
            # 4. the browser goes away -> the keeper exits by itself.
            chrome_p.terminate()
            chrome_p.wait(timeout=10)
            k.wait(timeout=15)
            assert "exiting" in k.stdout.read(), "the keeper did not say why it exited"
        finally:
            for k in keepers:
                if k.poll() is None:
                    k.kill()
            if chrome_p.poll() is None:
                chrome_p.kill()
            httpd.shutdown()
        # the temp profile is rebuildable: not kept
        shutil.rmtree(os.path.join(d, "profile"), ignore_errors=True)
    print("browser tabs OK")


if __name__ == "__main__":
    main()
