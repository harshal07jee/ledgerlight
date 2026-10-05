"""
Real Browser Session Auditor using Microsoft Edge (Chromium) and Chrome DevTools Protocol (CDP).
Single message dispatcher to reliably capture DOM and console errors across all 7 frontend pages.
"""
import asyncio
import json
import os
import subprocess
import time
import urllib.request
import websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
USER_DATA_DIR = os.path.abspath("./.edge_audit_profile")
PORT = 9222

PAGES_TO_AUDIT = [
    {
        "name": "Landing / Home Page",
        "url": "http://localhost:3000/"
    },
    {
        "name": "Onboarding Page",
        "url": "http://localhost:3000/onboarding"
    },
    {
        "name": "Question Bank Admin Page",
        "url": "http://localhost:3000/admin"
    },
    {
        "name": "Assessment Questionnaire Page",
        "url": "http://localhost:3000/assessment/test-browser-asmt-001"
    },
    {
        "name": "Data Room Documents Page",
        "url": "http://localhost:3000/assessment/test-browser-asmt-001/data-room"
    },
    {
        "name": "Extraction Verification Page",
        "url": "http://localhost:3000/assessment/test-browser-asmt-001/verify"
    },
    {
        "name": "Readiness Report & Roadmap Page",
        "url": "http://localhost:3000/assessment/test-browser-asmt-001/report"
    }
]


class CDPClient:
    def __init__(self, ws):
        self.ws = ws
        self.pending = {}
        self.counter = 1
        self.console_errors = []
        self.console_warnings = []
        self._reader_task = asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for raw in self.ws:
                data = json.loads(raw)
                if "id" in data:
                    fut = self.pending.pop(data["id"], None)
                    if fut and not fut.done():
                        fut.set_result(data.get("result", {}))
                elif "method" in data:
                    method = data["method"]
                    if method == "Runtime.consoleAPICalled":
                        p = data.get("params", {})
                        mtype = p.get("type")
                        args = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
                        if mtype == "error":
                            self.console_errors.append(args)
                        elif mtype == "warning":
                            self.console_warnings.append(args)
                    elif method == "Runtime.exceptionThrown":
                        exc = data.get("params", {}).get("exceptionDetails", {})
                        desc = exc.get("exception", {}).get("description") or exc.get("text", "")
                        self.console_errors.append(f"Uncaught Exception: {desc}")
        except Exception:
            pass

    async def send(self, method, params=None):
        msg_id = self.counter
        self.counter += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[msg_id] = fut
        await self.ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        return await fut

    def get_logs(self):
        return list(self.console_errors), list(self.console_warnings)

    def reset_logs(self):
        self.console_errors.clear()
        self.console_warnings.clear()

    async def close(self):
        self._reader_task.cancel()
        await self.ws.close()


async def audit():
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    cmd = [
        EDGE_PATH,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA_DIR}",
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Started Edge Chromium process (PID {proc.pid}) on port {PORT}")
    time.sleep(2)

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list") as resp:
            targets = json.loads(resp.read().decode())
        page_targets = [t for t in targets if t.get("type") == "page"]
        target_data = page_targets[0] if page_targets else targets[0]
        ws_url = target_data["webSocketDebuggerUrl"]
        print(f"Connected to CDP WebSocket: {ws_url}")

        audit_results = []

        raw_ws = await websockets.connect(ws_url, max_size=10_000_000)
        client = CDPClient(raw_ws)

        await client.send("Page.enable")
        await client.send("Runtime.enable")
        await client.send("Console.enable")

        # Initial navigation to set storage on domain
        await client.send("Page.navigate", {"url": "http://localhost:3000/"})
        await asyncio.sleep(2.0)

        init_script = """
        localStorage.setItem("ledgerlight_token", "0f69d4be6c84f3c477cb9a6061b2a1b042dfcb63d550ff1c65ea945425f8b5ea");
        localStorage.setItem("ledgerlight_user", JSON.stringify({
            id: "c1d36694-ff72-4da9-8397-054efa0f6ca9",
            email: "founder@company.com",
            full_name: "Jane Founder",
            is_admin: true
        }));
        document.cookie = "ledgerlight_session=0f69d4be6c84f3c477cb9a6061b2a1b042dfcb63d550ff1c65ea945425f8b5ea; path=/; SameSite=Strict";
        """
        await client.send("Runtime.evaluate", {"expression": init_script})

        for page_info in PAGES_TO_AUDIT:
            url = page_info["url"]
            name = page_info["name"]
            print(f"\n=======================================================")
            print(f"AUDITING: {name} ({url})")
            print(f"=======================================================")

            client.reset_logs()

            # Navigate
            await client.send("Page.navigate", {"url": url})
            await asyncio.sleep(3.0)  # Wait for React hydration & API calls

            # Extract DOM state
            dom_eval_script = """
            (() => {
                const title = document.title;
                const h1s = Array.from(document.querySelectorAll('h1')).map(h => h.innerText.trim()).filter(Boolean);
                const h2s = Array.from(document.querySelectorAll('h2')).map(h => h.innerText.trim()).filter(Boolean);
                const h3s = Array.from(document.querySelectorAll('h3')).map(h => h.innerText.trim()).filter(Boolean);
                
                const tables = Array.from(document.querySelectorAll('table')).map(t => ({
                    rows: t.querySelectorAll('tr').length,
                    headers: Array.from(t.querySelectorAll('th')).map(th => th.innerText.trim())
                }));

                const badges = Array.from(document.querySelectorAll('span, div')).filter(el => {
                    const t = el.innerText.trim();
                    return ['PASS', 'FAIL', 'PARTIAL', 'CRITICAL', 'AUTO_FILLED', 'NEEDS_CONFIRMATION', 'APPROVED', 'AI_PRE_REVIEWED', 'UNREVIEWED_SEED', 'DRAFT'].includes(t);
                }).map(el => el.innerText.trim());

                const buttons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(Boolean);
                
                const bodyText = document.body.innerText;
                const emptyStates = [];
                if (bodyText.includes("No documents uploaded yet")) emptyStates.push("No documents uploaded yet");
                if (bodyText.includes("No extractions found")) emptyStates.push("No extractions found");
                if (bodyText.includes("No applicable questions in this dimension")) emptyStates.push("No applicable questions in this dimension");
                if (bodyText.includes("No questions found")) emptyStates.push("No questions found");
                if (bodyText.includes("404") && bodyText.includes("This page could not be found")) emptyStates.push("404 Page Not Found");
                if (bodyText.includes("401") || bodyText.includes("Unauthorized")) emptyStates.push("401 Unauthorized Error");
                if (bodyText.includes("Failed to load diligence questionnaire")) emptyStates.push("Failed to load questionnaire");

                return {
                    title,
                    h1s,
                    h2s: h2s.slice(0, 5),
                    h3s: h3s.slice(0, 5),
                    tablesCount: tables.length,
                    tablesSummary: tables,
                    buttonsCount: buttons.length,
                    badgesCount: badges.length,
                    badgesFound: Array.from(new Set(badges)).slice(0, 10),
                    emptyStates,
                    bodyLength: bodyText.length,
                    contentSample: bodyText.slice(0, 400).replace(/\\s+/g, ' ')
                };
            })()
            """
            dom_eval_res = await client.send("Runtime.evaluate", {"expression": dom_eval_script, "returnByValue": True})
            dom_data = dom_eval_res.get("result", {}).get("value", {})

            # Roadmap tab audit on report page
            roadmap_tab_data = None
            if "/report" in url:
                click_tab_script = """
                (() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const rmBtn = buttons.find(b => b.innerText.includes('Remediation Roadmap Board'));
                    if (rmBtn) {
                        rmBtn.click();
                        return true;
                    }
                    return false;
                })()
                """
                await client.send("Runtime.evaluate", {"expression": click_tab_script, "returnByValue": True})
                await asyncio.sleep(2.0)
                
                rm_eval_script = """
                (() => {
                    const lanes = Array.from(document.querySelectorAll('h3, h4')).map(h => h.innerText.trim()).filter(t => t.includes('Day Horizon') || t.includes('Days'));
                    const taskCards = Array.from(document.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('pts recoverable')).length;
                    return {
                        lanesFound: lanes,
                        taskCardsCount: taskCards
                    };
                })()
                """
                rm_res = await client.send("Runtime.evaluate", {"expression": rm_eval_script, "returnByValue": True})
                roadmap_tab_data = rm_res.get("result", {}).get("value", {})

            errors, warnings = client.get_logs()

            result = {
                "name": name,
                "url": url,
                "title": dom_data.get("title", ""),
                "h1": dom_data.get("h1s", []),
                "h2": dom_data.get("h2s", []),
                "tablesCount": dom_data.get("tablesCount", 0),
                "tables": dom_data.get("tablesSummary", []),
                "badges": dom_data.get("badgesFound", []),
                "buttonsCount": dom_data.get("buttonsCount", 0),
                "emptyStates": dom_data.get("emptyStates", []),
                "consoleErrors": errors,
                "consoleWarnings": warnings,
                "roadmapTabAudit": roadmap_tab_data,
                "contentSample": dom_data.get("contentSample", "")
            }
            audit_results.append(result)

            print(f"Title: {result['title']}")
            print(f"H1: {result['h1']}")
            print(f"H2: {result['h2']}")
            print(f"Tables Count: {result['tablesCount']}")
            print(f"Badges: {result['badges']}")
            print(f"Empty States Detected: {result['emptyStates']}")
            print(f"Console Errors: {result['consoleErrors']}")
            if roadmap_tab_data:
                print(f"Roadmap Tab Lanes: {roadmap_tab_data.get('lanesFound')}, Tasks: {roadmap_tab_data.get('taskCardsCount')}")

        await client.close()

        with open("docs/frontend_browser_audit.json", "w") as f:
            json.dump(audit_results, f, indent=2)
        print("\n=> SAVED AUDIT REPORT TO docs/frontend_browser_audit.json")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        print("Edge Chromium process terminated.")

if __name__ == "__main__":
    asyncio.run(audit())
