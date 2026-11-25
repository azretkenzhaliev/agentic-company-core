"""Tests for scripts/hooks/trend_reader.py: what the trend-researcher may do in the browser,
its agent file, and its fixed scripts run in node against a small fake page."""

import json
import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "hooks"))

import trend_reader as tr  # noqa: E402

AGENT = ROOT / ".claude" / "agents" / "marketing" / "trend-researcher.md"
CHROME = "mcp__claude-in-chrome__"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"


def shortcode(days_ago):
    """An 11-character shortcode whose id says it was posted days_ago."""
    n = (int(time.time() * 1000) - days_ago * 86400000 - 1314220021721) << 23
    code = ""
    for _ in range(11):
        code = ALPHABET[n % 64] + code
        n //= 64
    return code


def top_level_await(line):
    """The javascript tool takes `await` at the top of a line; the tests' eval doesn't."""
    return f"(async()=>{{return {line}}})()"


READER = {"browser": "reader-browser", "accounts": ["reader.one", "reader_two"]}


def filled(script):
    """The script as the role runs it: READER where the agent file puts it, filled with the reader accounts."""
    return script.replace("READER", tr.signed_in(READER["accounts"]))


REELS_JS, REEL_JS, SHEET_JS = filled(tr.REELS_JS), filled(tr.REEL_JS), filled(tr.SHEET_JS)
INSTALL = filled(tr.INSTALL)


def run(tool, tool_input, reader=READER):
    return tr.reader_reason(CHROME + tool, tool_input, reader)


class Tools(unittest.TestCase):
    def test_the_page_tools_pass(self):
        for tool in sorted(tr.PAGE_TOOLS):
            with self.subTest(tool=tool):
                self.assertIsNone(run(tool, {}))

    def test_everything_else_in_chrome_is_refused(self):
        for tool in ["form_input", "file_upload", "upload_image", "shortcuts_execute", "shortcuts_list", "find",
                     "tabs_create_mcp", "gif_creator", "read_network_requests", "read_console_messages",
                     "resize_window", "switch_browser", "tabs_close_mcp", "read_page", "a_tool_chrome_adds_later"]:
            with self.subTest(tool=tool):
                self.assertIn("can't use", run(tool, {}))

    def test_nothing_runs_without_a_reader_profile(self):
        for reader in [{}, {"browser": "reader-browser"}, {"browser": "", "accounts": ["reader.one"]},
                       {"browser": "reader-browser", "accounts": []}, {"browser": "reader-browser", "accounts": "reader.one"},
                       {"browser": "reader-browser", "accounts": ["x'],body"]}, {"browser": 7, "accounts": ["reader.one"]}]:
            for tool, tool_input in [("get_page_text", {}), ("select_browser", {"deviceId": reader.get("browser")}),
                                     ("javascript_tool", {"action": "javascript_exec", "text": tr.RUN_REELS}),
                                     ("browser_batch", {"actions": [{"name": "get_page_text", "input": {}}]})]:
                with self.subTest(reader=reader, tool=tool):
                    self.assertIn("needs a reader profile", run(tool, tool_input, reader))

    def test_only_the_reader_profile_can_be_selected(self):
        self.assertIsNone(run("select_browser", {"deviceId": READER["browser"]}))
        for tool_input in [{"deviceId": "some-other-browser"}, {}, {"deviceId": READER["browser"], "name": "x"},
                           {"deviceId": [READER["browser"]]}, {"deviceId": None}]:
            with self.subTest(tool_input=tool_input):
                self.assertIn("reader profile", run("select_browser", tool_input))
                self.assertIn("reader profile", run("browser_batch", {"actions": [{"name": "select_browser", "input": tool_input}]}))

    def test_a_lookalike_server_is_refused(self):
        for tool in ["mcp__claude-in-chrome-2__navigate", "mcp__chrome__navigate", "mcp__Claude-In-Chrome__navigate"]:
            with self.subTest(tool=tool):
                self.assertIn("Chrome tools", tr.reader_reason(tool, {"url": "https://www.instagram.com/"}, READER))


class Urls(unittest.TestCase):
    def test_the_pages_the_role_reads_pass(self):
        for url in ["https://www.instagram.com/some.one_1/reels/", "https://www.instagram.com/another.account/reels/",
                    "https://www.instagram.com/reel/AbCdEfGhI01/", "https://www.youtube.com/@someone/shorts",
                    "https://t.me/s/channel"]:
            with self.subTest(url=url):
                self.assertIsNone(tr.url_reason(url))

    def test_every_other_url_is_refused(self):
        for url in ["http://www.instagram.com/", "https://example.com/", "https://instagram.com.example.com/",
                    "https://notinstagram.com/", "https://www.instagram.com.", "https://l.instagram.com/?u=x",
                    "https://accounts.google.com/", "https://studio.youtube.com/", "https://x.t.me/s/channel",
                    "https://user@www.instagram.com/", "https://www.instagram.com@example.com/",
                    "https://www.instagram.com:8443/", "https://www.instagram.com:bad/", "https://example.com\\@t.me/s/x",
                    "www.instagram.com/someone/", "back", "forward", "javascript:alert(1)", "", None, 7, ["x"],
                    "https://www.instagram.com/\\accounts/edit/", "https://www.instagram.com/%61ccounts/edit/",
                    "https://www.instagram.com/some one/", "https://www.instagram.com/\u0441omeone/",
                    "https://www.instagram.com/", "https://www.instagram.com/someone/", "https://www.instagram.com/someone/reels",
                    "https://instagram.com/someone/reels/", "https://instagram.com/reel/AbCdEfGhI01/",
                    "https://www.instagram.com/p/AbCdEfGhI01/", "https://m.youtube.com/@someone/shorts",
                    "https://www.youtube.com/watch?v=abc", "https://www.youtube.com/shorts/abc"]:
            with self.subTest(url=url):
                self.assertIn("Blocked", tr.url_reason(url))

    def test_dot_segments_are_refused(self):
        """A browser removes these before it fetches, so they'd reach whatever follows them."""
        for url in ["https://www.instagram.com/./direct/inbox/", "https://www.instagram.com/./accounts/logout/",
                    "https://www.instagram.com/../reels/", "https://www.instagram.com/./reels/",
                    "https://www.instagram.com/.someone/reels/", "https://www.instagram.com/someone./reels/",
                    "https://www.instagram.com/reel/../direct/inbox/", "https://t.me/s/../joinchat/abc",
                    "https://t.me/s/../iv?url=x", "https://www.youtube.com/./redirect?q=https://example.com/?k=abc"]:
            with self.subTest(url=url):
                self.assertIn("Blocked", tr.url_reason(url))

    def test_the_signed_in_sessions_private_pages_are_refused(self):
        for url in ["https://www.youtube.com/feed/history", "https://www.youtube.com/feed/subscriptions",
                    "https://www.youtube.com/playlist?list=LL", "https://www.instagram.com/someone/saved/",
                    "https://www.instagram.com/your_activity/interactions/likes/", "https://www.instagram.com/emails/settings/"]:
            with self.subTest(url=url):
                self.assertIn("Blocked", tr.url_reason(url))

    def test_a_good_page_takes_no_query_or_fragment(self):
        for url in ["https://t.me/s/channel?before=100", "https://www.instagram.com/someone/reels/?x=1",
                    "https://www.instagram.com/reel/AbCdEfGhI01/?igsh=abc", "https://www.instagram.com/someone/reels/#x",
                    "https://www.youtube.com/@someone/shorts?view=0", "https://t.me/s/channel#1"]:
            with self.subTest(url=url):
                self.assertIn("Blocked", tr.url_reason(url))

    def test_instagrams_own_paths_are_not_handles(self):
        for name in sorted(tr.NOT_HANDLES) + ["ACCOUNTS"]:
            with self.subTest(name=name):
                self.assertIn("Blocked", tr.url_reason(f"https://www.instagram.com/{name}/reels/"))

    def test_sign_in_message_upload_and_redirect_pages_are_refused(self):
        for path in ["accounts/login/", "accounts/edit/", "ACCOUNTS/edit/", "/accounts/edit/", "direct/inbox/",
                     "challenge/x/", "create/select/", "oauth/authorize", "api/v1/users/web_profile_info/?username=x",
                     "graphql/query", "redirect?q=https://example.com", "signin", "upload", "account", "logout"]:
            for host in ["www.instagram.com", "www.youtube.com"]:
                with self.subTest(host=host, path=path):
                    self.assertIn("Blocked", tr.url_reason(f"https://{host}/{path}"))

    def test_telegram_is_only_the_public_preview(self):
        for path in ["channel", "+invite", "joinchat/abc", "iv?url=https://example.com", "share/url?url=x",
                     "addstickers/x", "s", "s/"]:
            with self.subTest(path=path):
                self.assertIn("Blocked", tr.url_reason(f"https://t.me/{path}"))


class Computer(unittest.TestCase):
    def test_a_screenshot_passes(self):
        self.assertIsNone(run("computer", {"action": "screenshot", "tabId": 1, "scale": 1}))

    def test_typing_keys_clicks_and_the_rest_are_refused(self):
        for action in ["type", "key", "paste", "left_click", "double_click", "triple_click", "right_click",
                       "left_click_drag", "hover", "scroll", "scroll_to", "zoom", "wait", None, ["screenshot"]]:
            with self.subTest(action=action):
                self.assertIn("no typing", run("computer", {"action": action, "tabId": 1, "text": "x"}))


class Javascript(unittest.TestCase):
    def test_the_fixed_scripts_pass(self):
        for script in sorted(tr.allowed_js(READER["accounts"])):
            with self.subTest(script=script[:40]):
                self.assertIsNone(run("javascript_tool", {"action": "javascript_exec", "tabId": 1, "text": script}))
                self.assertIsNone(run("javascript_tool", {"action": "javascript_exec", "text": f"\n{script}\n"}))

    def test_nothing_else_runs(self):
        for text in ["document.cookie", "fetch('/api/v1/users/web_profile_info/')", "1+1", "", None, 7,
                     tr.RUN_REELS + ";fetch('https://example.com')", "eval(localStorage.__readerReels)",
                     "await eval(localStorage.__readerReels)", REELS_JS, tr.INSTALL, INSTALL.replace("'installed'", "fetch('/x')")]:
            with self.subTest(text=str(text)[:40]):
                self.assertIn("fixed scripts", run("javascript_tool", {"action": "javascript_exec", "text": text}))

    def test_only_javascript_exec_and_only_its_keys(self):
        self.assertIn("fixed scripts", run("javascript_tool", {"action": "other", "text": tr.RUN_REELS}))
        self.assertIn("fixed scripts", run("javascript_tool", {"text": tr.RUN_REELS}))
        self.assertIn("fixed scripts", run("javascript_tool", {"action": "javascript_exec", "text": tr.RUN_REELS,
                                                               "code": "document.cookie"}))


    def test_no_stored_script_sends_clicks_or_leaves_the_page(self):
        for script in [REELS_JS, REEL_JS, SHEET_JS, tr.CLEAR]:
            for word in ["fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "new Image", ".click(", ".submit(", "window.open",
                         "location.href", "location.assign", "location.replace", "location="]:
                with self.subTest(script=script[:40], word=word):
                    self.assertNotIn(word, script)


class Batch(unittest.TestCase):
    STEP = {"name": "navigate", "input": {"tabId": 1, "url": "https://www.instagram.com/someone/reels/"}}
    JS = {"name": "javascript_tool", "input": {"action": "javascript_exec", "tabId": 1, "text": tr.RUN_REELS}}

    def test_a_reading_batch_passes(self):
        self.assertIsNone(run("browser_batch", {"actions": [self.STEP, self.JS] * 10}))
        self.assertIsNone(run("browser_batch", {"actions": json.dumps([self.STEP, self.JS])}))

    def test_one_bad_step_refuses_the_batch(self):
        for step in [{"name": "navigate", "input": {"url": "https://example.com/"}},
                     {"name": "javascript_tool", "input": {"action": "javascript_exec", "text": "document.cookie"}},
                     {"name": "computer", "input": {"action": "type", "text": "x"}},
                     {"name": "form_input", "input": {}}, {"name": "browser_batch", "input": {"actions": []}},
                     {"name": CHROME + "navigate", "input": self.STEP["input"]}]:
            with self.subTest(step=step):
                self.assertIn("Blocked", run("browser_batch", {"actions": [self.STEP, step]}))

    def test_a_malformed_batch_is_refused(self):
        for actions in [None, "", "not json", {}, [], ["navigate"], [{"name": "navigate"}], [{"input": {}}],
                        [{"name": "navigate", "input": "x"}], [{"name": ["navigate"], "input": {}}],
                        [{**self.STEP, "tool": "form_input"}]]:
            with self.subTest(actions=actions):
                self.assertIn("Blocked", run("browser_batch", {"actions": actions}))


class AgentFile(unittest.TestCase):
    TEXT = AGENT.read_text(encoding="utf-8")

    def field(self, name):
        return re.search(rf"^{name}: (.+)$", self.TEXT, re.M).group(1).strip()

    def test_each_script_is_in_the_agent_file_word_for_word(self):
        for script in [tr.INSTALL, tr.RUN_REELS, tr.RUN_REEL, tr.RUN_SHEET, tr.CLEAR]:
            with self.subTest(script=script[:40]):
                self.assertIn(script, self.TEXT)

    def test_it_says_where_the_browser_and_the_accounts_come_from(self):
        for words in ["company.json", "`reader`", "`READER`", 'a[href="/<account>/"]']:
            with self.subTest(words=words):
                self.assertIn(words, self.TEXT)

    def test_its_frontmatter(self):
        self.assertEqual(self.field("name"), "trend-researcher")
        self.assertEqual(self.field("model"), "sonnet")
        self.assertEqual(self.field("effort"), "xhigh")
        self.assertEqual(self.field("autoCompactWindow"), "375000")  # test_marketing_context.py says why

    def test_the_csv_keeps_its_columns_and_ends_in_the_two_collab_columns(self):
        self.assertIn("recent_or_old,language,format,collab,collab_with\n", self.TEXT)

    def test_it_says_what_a_collab_no_means_in_the_rule_and_in_the_weeks_file(self):
        self.assertIn("a partner the page doesn't name stays unseen", self.TEXT)
        self.assertIn("so a partner can be unseen", self.TEXT)

    def test_a_language_from_the_cover_is_marked(self):
        self.assertIn("`de (cover)`", self.TEXT)

    def test_the_covers_are_read_at_full_size(self):
        self.assertIn('{"action":"screenshot","tabId":1,"scale":1}', self.TEXT)
        self.assertNotIn('"scale":0.6', self.TEXT)

    def test_its_tools_are_what_the_hook_lets_through(self):
        tools = {tool.strip() for tool in self.field("tools").split(",")}
        chrome = {CHROME + name for name in tr.BATCH_TOOLS | {"browser_batch"}}
        fastdl = {tool for tool in tools if "fastdl" in tool.lower()}  # held in test_guard_marketing_tools.py's FastDL
        self.assertEqual(tools - fastdl, {"Read", "Write", "Edit", "ToolSearch"} | chrome)
        for name in ["form_input", "file_upload", "upload_image", "shortcuts_execute"]:
            self.assertNotIn(CHROME + name, tools)


@unittest.skipUnless(shutil.which("node"), "needs node")
class Scripts(unittest.TestCase):
    PAGE = r"""
const meta={'og:image':'https://cdn.example/c.jpg','og:description':'1,000 likes, 80 comments - someone on January 15, 2026: "words". '};
globalThis.location={pathname:'/someone/reels/',hostname:'www.instagram.com'};
globalThis.localStorage={removeItem(k){delete this[k]}};
globalThis.setTimeout=f=>f();
globalThis.innerWidth=1440;globalThis.innerHeight=800;
let sheet=null;
const el=()=>({style:{},dataset:{},kids:[],append(...k){this.kids.push(...k)},appendChild(k){this.kids.push(k)},remove(){sheet=null}});
const link=(handle,text,fixed)=>({href:'/'+handle+'/',textContent:text,position:'static',
  parentElement:{position:'static',parentElement:{position:fixed?'fixed':'static',parentElement:null}}});
globalThis.getComputedStyle=e=>({position:e.position});
globalThis.document={
  password:false,
  links:[link('reader.one','Profile',true)],
  querySelector(s){
    if(s.startsWith('input'))return this.password?{}:null;
    const m=meta[s.match(/"(.+)"/)[1]];return m?{content:m}:null;
  },
  querySelectorAll(s){
    if(s.includes('/reel/'))return TILES.map(([c,t])=>({getAttribute:()=>'/someone/reel/'+c+'/',innerText:t}));
    return this.links.filter(l=>s.split(',').includes('a[href="'+l.href+'"]'));
  },
  getElementById:()=>sheet,
  createElement:el,
  body:{innerText:'1,024 posts\n12.5K followers\n3 following',appendChild(s){sheet=s}},
};
"""

    def run_page(self, tiles, script, install, run_script):
        code = (f"const TILES={json.dumps(tiles)};{self.PAGE}\n"
                f"const INSTALL={json.dumps(install)};const SCRIPT={json.dumps(script)};const RUN={json.dumps(run_script)};\n"
                "(async()=>{const a=(0,eval)(INSTALL);const stored=localStorage[RUN];"
                "console.log(JSON.stringify({a,stored,out:await (0,eval)(stored),same:stored===SCRIPT}))})()")
        done = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_the_reels_script_keeps_outliers_and_takes_the_median_of_the_newest_nine(self):
        newest = [[shortcode(day), "10K"] for day in range(1, 9)]
        hit = [shortcode(9), "50K"]
        pinned = [shortcode(800), "5M"]
        tiles = [pinned, newest[0], *newest, hit, [shortcode(700), "15,000"], [shortcode(650), ""]]
        result = self.run_page(tiles, REELS_JS, INSTALL, "__readerReels")
        self.assertEqual(result["a"], "installed")
        self.assertTrue(result["same"])
        self.assertEqual(result["out"], f"someone|12.5K|10000|11|{pinned[0]} 5000000 800 500.0;{hit[0]} 50000 9 5.0")

    def test_the_reels_script_on_an_empty_page(self):
        self.assertEqual(self.run_page([], REELS_JS, INSTALL, "__readerReels")["out"], "someone|12.5K|0|0|")

    def test_the_reel_script_keeps_the_cover(self):
        result = self.run_page([], REEL_JS, INSTALL, "__readerReel")
        self.assertTrue(result["same"])
        self.assertEqual(result["out"], "reels||words")
        self.assertEqual(self.run_in_order("location.pathname='/reel/DeAbCd01234/'", REEL_JS, "localStorage.__readerCovers"),
                         ["DeAbCd01234||words", '[["DeAbCd01234","https://cdn.example/c.jpg"]]'])

    def test_the_sheet_runs(self):
        result = self.run_page([], SHEET_JS, INSTALL, "__readerSheet")
        self.assertTrue(result["same"])
        self.assertEqual(result["out"], "end")

    def run_in_order(self, setup, *scripts):
        """Run the scripts one after another on a page setup changed; each one's result, in order."""
        code = (f"const TILES=[];{self.PAGE}\n{setup};\n"
                f"(async()=>{{for(const s of {json.dumps(scripts)})console.log(await (0,eval)(s))}})()")
        done = subprocess.run(["node", "-e", code], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout.splitlines()

    CODE = "DeAbCd01234"

    def reel_line(self, description, accounts=("someone",)):
        """What the reel script returns on a reel page with this og:description, the reel kept under accounts."""
        read = json.dumps({self.CODE: list(accounts)})
        return self.run_in_order(f"meta['og:description']={json.dumps(description)};location.pathname='/reel/{self.CODE}/';"
                                 f"localStorage.__readerRead={json.dumps(read)}", REEL_JS)[0]

    def caption(self, text):
        """The caption field for a page that gives this caption."""
        return self.reel_line(f'20K likes, 100 comments - someone on January 5, 2026: "{text}". ').split("|", 2)[2]

    def test_a_caption_comes_from_the_real_description(self):
        for likes in ["20K likes, 100 comments", "2,500 likes, 9 comments", "2M likes, 5,000 comments"]:
            with self.subTest(likes=likes):
                self.assertEqual(self.reel_line(f'{likes} - some.one_1 on January 5, 2026: "Neues Vidéo". ', ["some.one_1"]),
                                 f"{self.CODE}|some.one_1 no|Neues Vidéo")

    def test_a_caption_of_lines_quotes_and_emoji_stays_one_line(self):
        self.assertEqual(self.caption("First line\n\nsecond \"line\" 🚀"), 'First line second "line" 🚀')

    def test_the_byline_is_the_first_one_not_one_inside_the_caption(self):
        line = self.reel_line('5 likes, 1 comment - someone on May 1, 2026: "see - other_one on May 2, 2026: \"x\"". ')
        self.assertEqual(line, f'{self.CODE}|someone no|see - other_one on May 2, 2026: "x"')

    def test_the_cap_is_on_the_caption_alone(self):
        self.assertEqual(self.caption("é" * 200), "é" * 200)
        self.assertEqual(self.caption("é" * 300), "é" * 230)
        self.assertEqual(self.caption("é" * 229 + "🚀ü"), "é" * 229 + "🚀")

    def test_mentions_are_masked_and_a_pipe_cant_break_the_table(self):
        self.assertEqual(self.caption("@some.bank_1 new video a|b"), "@... new video a/b")

    def test_contacts_are_masked_and_dates_and_prices_stay(self):
        self.assertEqual(self.caption("mail: some.one+1@mail.example"), "mail: @...")
        for phone in ["+1 555 123 4567", "0555 12 34 56", "0 (555) 12-34-56", "0555123456"]:
            with self.subTest(phone=phone):
                self.assertEqual(self.caption(f"call {phone} today"), "call ... today")
        self.assertEqual(self.caption("on 2026-01-05 for 10 000 000 euros"), "on 2026-01-05 for 10 000 000 euros")

    def test_no_caption_says_none(self):
        for description in ["1,000 likes, 80 comments - someone on January 14, 2026",
                            "2M likes, 5,000 comments - someone on January 6, 2026", ""]:
            with self.subTest(description=description):
                self.assertTrue(self.reel_line(description).endswith("|none"))

    def test_a_collab_stays_under_the_account_read(self):
        """A tile under the account read, a reel page that names another account."""
        code = shortcode(14)
        lines = self.run_in_order(f"TILES.push(['{code}','50k']);location.pathname='/someone/reels/';"
                                  "meta['og:description']='1,000 likes, 80 comments - other_one on January 14, 2026'",
                                  REELS_JS, f"location.pathname='/reel/{code}/';'moved'", REEL_JS)
        self.assertEqual(lines, [f"someone|12.5K|50000|1|{code} 50000 14 1.0", "moved", f"{code}|someone yes other_one|none"])

    def test_the_reel_page_can_land_on_the_reels_path(self):
        code = shortcode(14)
        lines = self.run_in_order(f"TILES.push(['{code}','50k'])", REELS_JS,
                                  f"location.pathname='/reels/{code}/';'moved'", REEL_JS)
        self.assertEqual(lines[2], f"{code}|someone no|words")

    def test_an_owner_read_alone_says_no(self):
        self.assertEqual(self.reel_line("1,000 likes, 80 comments - someone on January 14, 2026"),
                         f"{self.CODE}|someone no|none")

    def test_an_owner_with_two_others_gets_one_of_them_and_they_get_the_owner(self):
        self.assertEqual(self.reel_line("5 likes, 1 comment - someone on May 1, 2026", ["someone", "one", "two"]),
                         f"{self.CODE}|someone yes one;one yes someone;two yes someone|none")

    def test_a_reel_kept_under_two_accounts_gets_an_answer_for_each(self):
        code = shortcode(14)
        lines = self.run_in_order(f"TILES.push(['{code}','50k']);"
                                  "meta['og:description']='1,000 likes, 80 comments - other_one on January 14, 2026'",
                                  REELS_JS, "location.pathname='/other_one/reels/';'moved'", REELS_JS,
                                  f"location.pathname='/reel/{code}/';'moved'", REEL_JS)
        self.assertEqual(lines[-1], f"{code}|someone yes other_one;other_one yes someone|none")

    def test_a_handle_in_other_capitals_is_the_same_account(self):
        self.assertEqual(self.reel_line('5 likes, 1 comment - some.one on May 1, 2026: "x". ', ["Some.One"]),
                         f"{self.CODE}|Some.One no|x")

    def test_a_description_of_another_shape_doesnt_guess(self):
        self.assertEqual(self.reel_line("Instagram"), f"{self.CODE}|someone ?|none")

    SHEET_STATE = ("JSON.stringify({css:sheet.style.cssText,cells:sheet.kids.map(c=>({img:c.kids[0].style.cssText,"
                   "src:c.kids[0].src,n:c.kids[1].textContent}))})")

    def sheet_screens(self, covers, screens, width=1440, height=800):
        """Run the sheet screens times; each run's returned line and what it laid out."""
        kept = json.dumps([[f"code{n}", f"https://cdn.example/{n}.jpg"] for n in range(1, covers + 1)])
        lines = self.run_in_order(f"innerWidth={width};innerHeight={height};localStorage.__readerCovers={json.dumps(kept)}",
                                  *[SHEET_JS, self.SHEET_STATE] * screens)
        return [(lines[n], json.loads(lines[n + 1])) for n in range(0, len(lines), 2)]

    def test_each_cover_is_whole_at_9_16_and_on_the_screen(self):
        """Two rows and the columns must fit: nothing can scroll into view."""
        for width, height in [(1440, 800), (1280, 720)]:
            with self.subTest(width=width, height=height):
                _, layout = self.sheet_screens(20, 1, width, height)[0]
                columns, cell = map(int, re.search(r"repeat\((\d+),(\d+)px\)", layout["css"]).groups())
                rows = int(re.search(r"grid-auto-rows:(\d+)px", layout["css"]).group(1))
                self.assertAlmostEqual(cell / rows, 9 / 16, delta=0.01)
                self.assertLessEqual(columns * (cell + 4) + 4, width)
                self.assertLessEqual(2 * (rows + 4) + 4, height)
                self.assertEqual(len(layout["cells"]), 2 * columns)
                for shown in layout["cells"]:
                    self.assertIn("object-fit:contain", shown["img"])
                    self.assertIn("width:100%;height:100%", shown["img"])

    def test_a_cover_is_wide_enough_to_read(self):
        """A cropped cover about 178 pixels wide in a screenshot could still be read."""
        _, layout = self.sheet_screens(1, 1)[0]
        self.assertGreater(int(re.search(r"repeat\(\d+,(\d+)px\)", layout["css"]).group(1)), 178)

    def test_every_cover_gets_its_turn_across_the_screens(self):
        (first, one), (second, two), (third, _) = self.sheet_screens(20, 3)
        self.assertEqual(first, " ".join(f"{n} code{n}" for n in range(1, 13)) + " more")
        self.assertEqual(second, " ".join(f"{n} code{n}" for n in range(13, 21)) + " end")
        self.assertEqual([shown["n"] for shown in one["cells"] + two["cells"]], list(range(1, 21)))
        self.assertEqual(two["cells"][-1]["src"], "https://cdn.example/20.jpg")
        self.assertTrue(third.startswith("1 code1 "), "a run after the end starts again")

    def test_a_short_list_is_one_screen(self):
        self.assertEqual(self.sheet_screens(1, 1)[0][0], "1 code1 end")
        self.assertEqual(self.sheet_screens(12, 1)[0][0].split()[-1], "end")

    def test_clear_removes_the_sheet_and_what_the_run_kept(self):
        self.assertEqual(self.run_in_order("localStorage.__readerCovers='[]';localStorage.__readerRead='{}'", SHEET_JS, tr.CLEAR,
                                           "Object.keys(localStorage).filter(k=>k.startsWith('__reader')).length+' '+sheet"),
                         ["end", "cleared", "0 null"])

    def test_a_sign_in_verification_or_block_page_stops_the_read(self):
        for setup in ["document.password=true", "location.pathname='/accounts/login/'", "location.pathname='/challenge/x/'",
                      "location.pathname='/auth_platform/x/'", "document.body.innerText='Try Again Later'",
                      "document.body.innerText='We restrict certain activity'", "document.body.innerText='Action Blocked'",
                      'document.body.innerText="Confirm it\'s you"', "document.body.innerText='Confirm you\u2019re human'",
                      "document.body.innerText='Log in to continue'", "document.body.innerText='We suspended your account'"]:
            for script in [REELS_JS, REEL_JS, SHEET_JS]:
                with self.subTest(setup=setup, script=script[:60]):
                    self.assertEqual(self.run_in_order(setup, script), ["STOP login or block page"])

    def test_off_instagram_stops_the_read(self):
        for script in [REELS_JS, REEL_JS, SHEET_JS]:
            with self.subTest(script=script[:60]):
                self.assertEqual(self.run_in_order("location.hostname='t.me'", script), ["STOP off instagram"])

    def test_a_page_with_no_stored_script_stops_the_read(self):
        for line in [tr.RUN_REELS, tr.RUN_REEL, tr.RUN_SHEET]:
            with self.subTest(line=line):
                self.assertEqual(self.run_in_order("location.hostname='t.me'", top_level_await(line)),
                                 ["STOP no script on this page"])

    def test_the_run_lines_run_what_install_stored(self):
        self.assertEqual(self.run_in_order("", INSTALL, top_level_await(tr.RUN_REELS)),
                         ["installed", "someone|12.5K|0|0|"])

    def test_every_script_reads_only_for_a_reader_account(self):
        self.assertEqual(self.run_in_order("document.links=[link('reader_two','Profile',true)]", REELS_JS),
                         ["someone|12.5K|0|0|"])
        for links in ["[]", "[link('demo','Profile',true)]",
                      "[link('demo','Profile',true),link('reader.one','reader.one',false)]",
                      "[link('demo','Profile',true),link('reader.one','Profile',false)]",
                      "[link('demo','Profile',true),link('reader.one','reader.one',true)]"]:
            for script in [REELS_JS, REEL_JS, SHEET_JS]:
                with self.subTest(links=links, script=script[:60]):
                    self.assertEqual(self.run_in_order(f"document.links={links}", script),
                                     ["STOP not a reader account"])

    def test_a_stop_holds_for_the_rest_of_the_batch_until_install(self):
        self.assertEqual(self.run_in_order("document.password=true", REELS_JS, "document.password=false",
                                           REELS_JS, REEL_JS, INSTALL, REELS_JS),
                         ["STOP login or block page", "false", "STOP earlier in this run", "STOP earlier in this run",
                          "installed", "someone|12.5K|0|0|"])


if __name__ == "__main__":
    unittest.main()
