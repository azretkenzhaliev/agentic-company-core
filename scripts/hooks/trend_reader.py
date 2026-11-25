#!/usr/bin/env python3
"""What the trend-researcher may do in the browser. guard_marketing_tools.py calls reader_reason.

The role reads public Instagram, YouTube and Telegram pages and nothing else. Its settings are in company.json,
"integrations"."marketing"."reader": `browser`, the Chrome device id of a separate profile that is signed in only to
reader accounts, and `accounts`, those accounts' handles (docs/marketing.md, "The reader profile"). Without both, every
call is refused. Everything here is an allowlist, so a tool, an action or a page nobody named stays refused:
- PAGE_TOOLS read a page or the browser's own state;
- `select_browser` picks only the reader profile. Chrome's names ("Browser 1") swap, so the id is all
  that says which browser it is. A reinstalled extension gets a new id: the role is refused
  and reports, and the fix comes in company.json;
- `navigate` opens only the exact pages the agent file uses, with no query. A list of
  forbidden paths would never be complete: on a signed-in session /feed/history and
  /<handle>/saved/ are private too, and a browser removes dot segments before it fetches;
- `computer` only takes screenshots. No typing and no clicks, so nothing the role does can
  show on an account, and it can't follow a link off these pages;
- `javascript_tool` runs only allowed_js(accounts), compared whole, so no other script ever runs
  on the signed-in session. The scripts repeat word for word in
  .claude/agents/marketing/trend-researcher.md, with READER where the accounts go (signed_in), and a test holds the two
  together. If Instagram's page changes, the role reports and the fix comes here.
- `browser_batch` steps pass the same checks, one by one.

The RUN_ scripts `eval` what INSTALL stored, which is safe because only INSTALL writes those
keys: the role has no other script and no typing. On another site the key is absent, and the
RUN_ script returns a STOP line itself, or is that site's own code running in its own origin.

The hook can't see which page a tab is on or who is signed in, so the scripts check. GUARD
stops on a sign-in, verification or block page, and SIGNED_IN stops every stored script unless a
reader account is signed in. A batch runs on after a step's result, so a stop stays in storage
and every later script returns STOP without reading, until INSTALL starts a new run.
"""

import json
import re

CHROME = "mcp__claude-in-chrome__"
PAGE_TOOLS = {"tabs_context_mcp", "list_connected_browsers", "get_page_text"}
BATCH_TOOLS = PAGE_TOOLS | {"select_browser", "navigate", "computer", "javascript_tool"}
HANDLE = re.compile(r"(?!\.)[A-Za-z0-9._]{1,30}(?<!\.)")
REELS_TAB = re.compile(r"https://www\.instagram\.com/((?!\.)[A-Za-z0-9._]{1,30}(?<!\.))/reels/")
NOT_HANDLES = {"accounts", "api", "auth_platform", "challenge", "create", "direct", "emails", "explore", "graphql",
               "oauth", "p", "reel", "reels", "stories", "your_activity"}
PAGES = (re.compile(r"https://www\.instagram\.com/reel/[A-Za-z0-9_-]{11}/"),
         re.compile(r"https://www\.youtube\.com/@[A-Za-z0-9._-]{1,60}/shorts"),
         re.compile(r"https://t\.me/s/[A-Za-z0-9_]{1,64}"))

GUARD = r"""if(localStorage.__readerStop)return 'STOP earlier in this run';const S=m=>{localStorage.__readerStop='1';return 'STOP '+m};if(location.hostname!=='www.instagram.com')return S('off instagram');if(document.querySelector('input[name="password"]')||/^\/(accounts|challenge|auth_platform)\//.test(location.pathname)||/try again later|restrict certain|action blocked|confirm (it.s you|you.re human|that you.re)|suspicious login|suspended your account|temporarily (locked|blocked)|log in to (see|continue)/i.test(document.body.innerText))return S('login or block page');"""
# The sidebar's profile link names who is signed in. Measured on a Reels tab and a reel page: no <nav> or
# role=navigation; the link reads "Profile" inside a position:fixed block. A link elsewhere on the page (a bio, a
# caption) proves nothing, so it needs both.
SIGNED_IN = ("if(![...document.querySelectorAll('READER')].some(a=>{if(a.textContent.trim()!=='Profile')return false;"
             + "for(let e=a;e;e=e.parentElement)"
             + "if(getComputedStyle(e).position==='fixed')return true;return false}))return S('not a reader account');")


def signed_in(accounts) -> str:
    """What READER stands for in the scripts: the reader accounts' profile links, as a CSS selector."""
    return ",".join(f'a[href="/{handle}/"]' for handle in accounts)


# GUARD, then each reel's age from its shortcode and the median of the 9 newest. No backticks: INSTALL quotes them.
REELS_JS = r"""(async()=>{await new Promise(r=>setTimeout(r,3200));""" + GUARD + SIGNED_IN + r"""const p=s=>{s=s.replace(/,/g,'');const m=s.match(/([\d.]+)\s*([KkMm]?)/);return m?Math.round(+m[1]*({k:1e3,K:1e3,m:1e6,M:1e6}[m[2]]||1)):0};const A='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';const age=c=>{let n=0n;for(const h of c.slice(0,11))n=n*64n+BigInt(A.indexOf(h));return Math.floor((Date.now()-Number((n>>23n)+1314220021721n))/864e5)};const M=new Map();document.querySelectorAll('a[href*="/reel/"]').forEach(x=>{const c=x.getAttribute('href').split('/reel/')[1].split('/')[0];M.set(c,{c,v:p(x.innerText||''),a:age(c)})});const R=[...M.values()].filter(x=>x.v);const L=[...R].sort((x,y)=>x.a-y.a).slice(0,9).map(x=>x.v).sort((x,y)=>x-y);const med=L.length?L[Math.floor(L.length/2)]:0;const top=[...R].sort((x,y)=>y.v-x.v)[0];const K=R.filter(x=>x===top||(x.v/med>=2&&x.v>=20000));const fol=(document.body.innerText.match(/([\d.,]+[KM]?)\s+followers/i)||[])[1]||'';const H=location.pathname.split('/')[1];const T=JSON.parse(localStorage.__readerRead||'{}');K.forEach(x=>{T[x.c]=[...new Set([...(T[x.c]||[]),H])]});localStorage.__readerRead=JSON.stringify(T);return H+'|'+fol+'|'+med+'|'+R.length+'|'+K.map(x=>x.c+' '+x.v+' '+x.a+' '+(x.v/med).toFixed(1)).join(';')})()"""
# A reel page's og:description reads `20K likes, 100 comments - handle on January 5, 2026: "caption". `, or comes
# without the `: "..."` part. The handle is the reel's owner, not the account
# whose tab showed it: a tile's link names the account being read even when the reel's page names another. So
# REELS_JS keeps, in __readerRead, the accounts each kept reel was read under, and REEL_JS compares. On the owner's
# own row the description names only the owner: the partner shows if the reel was kept under the partner too,
# and otherwise that row says `no` with a partner unseen (the role says so in the week's file).
# REEL_JS masks @mentions, emails and phone numbers (9 digits or more, so dates and prices stay): the caption is
# the one text kept, and it shouldn't carry other people's handles or contacts.
REEL_JS = r"""(async()=>{await new Promise(r=>setTimeout(r,2600));""" + GUARD + SIGNED_IN + r"""const q=n=>(document.querySelector('meta[property="'+n+'"]')||{}).content||'';const C=JSON.parse(localStorage.__readerCovers||'[]');const c=location.pathname.split('/').filter(Boolean).pop();if(q('og:image')&&!C.some(x=>x[0]===c))C.push([c,q('og:image')]);localStorage.__readerCovers=JSON.stringify(C);const m=q('og:description').replace(/\s+/g,' ').trim().match(/ - ([\w.]+) on [A-Z][a-z]+ \d{1,2}, \d{4}(?:: "(.*?)"?)?\.?$/)||[];const h=(m[1]||'').toLowerCase();const L=JSON.parse(localStorage.__readerRead||'{}')[c]||[];const O=L.find(a=>a.toLowerCase()!==h);const W=L.map(a=>a+(!h?' ?':a.toLowerCase()!==h?' yes '+h:O?' yes '+O:' no')).join(';');const t=[...(m[2]||'').replace(/[\w.+-]*@[\w.]+/g,'@...').replace(/\+?\d(?:[ ()-]*\d){8,}/g,'...').replace(/\|/g,'/')].slice(0,230).join('').trim();return c+'|'+W+'|'+(t||'none')})()"""
# Covers at 9:16 in two rows that fill the screen, never cropped.
# Each run shows the next screen: the sheet itself holds where it got to, so nothing outlives the page.
SHEET_JS = r"""(async()=>{""" + GUARD + SIGNED_IN + r"""const C=JSON.parse(localStorage.__readerCovers||'[]');const o=document.getElementById('readersheet');let s=o?+o.dataset.next:0;if(o)o.remove();if(s>=C.length)s=0;const h=Math.floor((innerHeight-12)/2);const w=Math.floor(h*9/16);const k=Math.max(1,Math.floor((innerWidth-4)/(w+4)));const P=C.slice(s,s+2*k);const d=document.createElement('div');d.id='readersheet';d.dataset.next=s+2*k;d.style.cssText='position:fixed;inset:0;z-index:999999;background:#fff;display:grid;grid-template-columns:repeat('+k+','+w+'px);grid-auto-rows:'+h+'px;gap:4px;padding:4px;';P.forEach((x,i)=>{const c=document.createElement('div');c.style.cssText='position:relative;overflow:hidden;background:#222';const m=document.createElement('img');m.src=x[1];m.style.cssText='width:100%;height:100%;object-fit:contain';const b=document.createElement('b');b.textContent=s+i+1;b.style.cssText='position:absolute;left:4px;top:4px;background:#ff0;color:#000;padding:2px 8px;font-size:22px';c.append(m,b);d.appendChild(c)});document.body.appendChild(d);await new Promise(r=>setTimeout(r,2500));return P.map((x,i)=>(s+i+1)+' '+x[0]).concat(s+2*k<C.length?'more':'end').join(' ')})()"""
INSTALL = ("localStorage.__readerReels=String.raw`" + REELS_JS + "`;localStorage.__readerReel=String.raw`" + REEL_JS
           + "`;localStorage.__readerSheet=String.raw`" + SHEET_JS + "`;localStorage.removeItem('__readerStop');'installed'")
# A site INSTALL never ran on has no stored script, so these lines give that STOP themselves.
RUN = "await (localStorage.{0}?eval(localStorage.{0}):'STOP no script on this page')"
RUN_REELS = RUN.format("__readerReels")
RUN_REEL = RUN.format("__readerReel")
RUN_SHEET = RUN.format("__readerSheet")
CLEAR = "const o=document.getElementById('readersheet');if(o)o.remove();localStorage.removeItem('__readerCovers');localStorage.removeItem('__readerRead');'cleared'"


def allowed_js(accounts) -> set:
    """The scripts the role may run, for these reader accounts."""
    return {INSTALL.replace("READER", signed_in(accounts)), RUN_REELS, RUN_REEL, RUN_SHEET, CLEAR}


def url_reason(url: object) -> "str | None":
    """Why the role may not open url, or None."""
    if isinstance(url, str):
        tab = REELS_TAB.fullmatch(url)
        if (tab and tab[1].lower() not in NOT_HANDLES) or any(page.fullmatch(url) for page in PAGES):
            return None
    return ("Blocked: the trend-researcher opens only these public pages, as its agent file writes them: "
            "a Reels tab or a reel on www.instagram.com, a channel's shorts on www.youtube.com, a channel on t.me/s/.")


def step_reason(name: object, tool_input: object, reader: dict) -> "str | None":
    """Why one browser step is refused, or None. name is the tool's short name, reader company.json's settings."""
    if not isinstance(tool_input, dict):
        return "Blocked: a browser step's input must be an object."
    if name in PAGE_TOOLS:
        return None
    if name == "select_browser":
        return (None if tool_input == {"deviceId": reader["browser"]}
                else "Blocked: the trend-researcher works only in the reader profile (company.json).")
    if name == "navigate":
        return url_reason(tool_input.get("url"))
    if name == "computer":
        if tool_input.get("action") == "screenshot":
            return None
        return "Blocked: the trend-researcher reads, so `computer` only takes screenshots: no typing, no keys, no clicks."
    if name == "javascript_tool":
        text = tool_input.get("text")
        if (tool_input.get("action") == "javascript_exec" and set(tool_input) <= {"action", "tabId", "text"}
                and isinstance(text, str) and text.strip() in allowed_js(reader["accounts"])):
            return None
        return ("Blocked: the trend-researcher runs only its fixed scripts, word for word from its agent file. "
                "If a page needs another one, stop and report.")
    return f"Blocked: the trend-researcher can't use {name}."


def reader_reason(tool_name: str, tool_input: dict, reader: dict) -> "str | None":
    """Why the role may not make this Bash or MCP call, or None. reader: company.json's "reader" settings."""
    if not tool_name.startswith(CHROME):
        return f"Blocked: the trend-researcher has no {tool_name}. It uses only the Chrome tools in its agent file."
    accounts = reader.get("accounts")
    if not (isinstance(reader.get("browser"), str) and reader["browser"] and isinstance(accounts, list) and accounts
            and all(isinstance(handle, str) and HANDLE.fullmatch(handle) for handle in accounts)):
        return ("Blocked: the trend-researcher needs a reader profile: company.json, \"integrations\".\"marketing\".\"reader\", "
                "with its browser's device id and its accounts' handles (docs/marketing.md).")
    short = tool_name[len(CHROME):]
    if short != "browser_batch":
        return step_reason(short, tool_input, reader)
    actions = tool_input.get("actions")
    if isinstance(actions, str):
        try:
            actions = json.loads(actions)
        except ValueError:
            actions = None
    if not isinstance(actions, list) or not actions:
        return "Blocked: browser_batch needs a list of actions."
    for action in actions:
        if (not isinstance(action, dict) or set(action) != {"name", "input"} or not isinstance(action["name"], str)
                or action["name"] not in BATCH_TOOLS):
            return "Blocked: each browser_batch action is a name and an input, with a tool the role may use."
        reason = step_reason(action["name"], action["input"], reader)
        if reason:
            return reason
    return None
