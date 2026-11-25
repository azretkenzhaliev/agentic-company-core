#!/usr/bin/env python3
"""Who may call the Board's FastDL connector, and with what. guard_marketing_tools.py calls fastdl_reason.

FastDL (https://api-wh.fastdl.app/instagram/mcp) is an unofficial outside service that reads public Instagram. The
Board may connect it to its Claude account (docs/marketing.md, "Optional connectors"); without it nothing here runs.
The tools are an allowlist, so a tool FastDL adds
later, another role, a session without a role and any other connector with "fastdl" in its name stay refused,
whatever company.json says:
- ROLES: the content tools each role may call. The trend-researcher has no download: it downloads nothing (the
  swipe-teardown skill's Hard rules). Not the analyst, which reads mail and Telegram:
  repeated calls could carry text out with no prompt;
- PEOPLE: four tools that list people, which nobody may call under any connector's name: the department keeps public
  accounts and counts only (knowledge/marketing/README.md, "Rules"; swipe-teardown, "No personal data");
- the arguments: nothing that looks like a login, no URL or host off instagram.com (www. and m. too), no email address
  or phone-like number, and little text: FastDL should see only which public accounts and posts we look up.
A call that passes still meets Claude Code's own permission check, unless company.json's "no_prompts" names "fastdl".
"""

import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_secrets import find_secrets  # noqa: E402

FASTDL = "mcp__claude_ai_FastDL__"
CONTENT = {"download_instagram_video", "get_instagram_post", "get_instagram_profile", "get_instagram_story",
           "list_instagram_posts", "list_instagram_stories", "list_instagram_highlights", "search_instagram_accounts"}
PEOPLE = {"list_instagram_followers", "list_instagram_following", "list_instagram_post_likers",
          "list_instagram_comments"}
ROLES = {"cmo": CONTENT, "trend-researcher": CONTENT - {"download_instagram_video"},
         "reel-analyst": {"download_instagram_video", "get_instagram_post", "get_instagram_profile",
                          "list_instagram_posts"}}

# A login by the argument's name, read without case or punctuation (apiKey, api_key, X-API-Key).
LOGIN_KEY = re.compile(r"passw|passcode|passphrase|pwd|cookie|session|token|apikey|accesskey|privatekey|secret|credential"
                       r"|creds|csrf|jwt|authorization|login|bearer|authent|oauth|userpass|igpass|otpcode")
LOGIN_WORDS = {"pass", "auth", "otp", "sid"}  # the whole name, or one of its words (user_pass, basicAuth): "bypass" is no login
LOGIN_PART = re.compile(r"sess|auth(?!or)|cred(?!it)")  # in one word: "author" and "credits" are no login
NAME_KEYS = {"name", "key", "field", "header", "param", "parameter", "label", "id", "k", "n"}  # {"name": "password",
VALUE_KEYS = {"value", "content", "val", "data", "text", "body", "v"}  # "value": ...}
PAGE_TOKEN = re.compile(r"(next|prev|previous)?(page|pagination|continuation)token|(next|prev|previous)token")  # a list's next page
# A login by its shape: a name and value in one string, a bearer value, a JWT, a Meta token, an Instagram sessionid.
LOGIN_SHAPE = re.compile(
    r"(?:passw|passcode|passphrase|pwd|cookie|session|token|api[_-]?key|secret|credential|authorization|ds_user_id)"
    r"[\w-]{0,40}[\"']?\s{0,5}[=:]"
    r"|\bbearer\s+[\w.~+/-]{16,}|\beyJ[\w-]{8,}\.[\w-]{8,}|\b(?-i:IGQV|EAA)[A-Za-z0-9]{20,}"
    r"|\b\d{5,}(?:%3A|:)[\w-]{6,}(?:%3A|:)\d", re.I)
LOGIN = "Blocked: FastDL is never given a login, and this call holds what looks like one (password, cookie, session, token, API key)."

HOST = re.compile(r"(?:(?:www|m)\.)?instagram\.com", re.I | re.A)  # re.A: without it, i also matches two other letters
SCHEME = re.compile(r"(?<![a-z0-9+.-])[a-z][a-z0-9+.-]*:(?=[/\\])|https?:", re.I)  # where a URL with a scheme starts
WEB = re.compile(r"https?://([^/?#]*)", re.I | re.A)  # its host and all before a path: a login, a port, a space, a backslash
PORT = re.compile(r"(?:[^:]*\.[^:]*|localhost):\d*", re.I)
URL_KEY = re.compile(r"url|uri|link|href", re.I)
HOST_KEY = re.compile(r"hook|callback|host|prox|endpoint|domain|server|site|redirect|origin(?!al)|referr?er|gateway|upstream"
                      r"|notif|dns|destination|remote|relay|forward", re.I)  # under one, nothing but instagram.com

# How much text a call holds (picked numbers, no data).
QUERY_MAX, URL_MAX, CURSOR_MAX, TEXT_MAX, ITEMS_MAX, DEPTH_MAX, CALL_MAX = 100, 500, 1000, 200, 20, 5, 1700
TOO_MUCH = (f"Blocked: FastDL is given little text: a search query or handle up to {QUERY_MAX} characters, an Instagram "
            f"URL up to {URL_MAX}, for a list_ or search_ tool one page cursor (up to {CURSOR_MAX} letters, digits and "
            f"- _ = + / : . %, or a number of up to 20), anything else up to {TEXT_MAX}, at most {ITEMS_MAX} items in a "
            f"list, {DEPTH_MAX} levels and {CALL_MAX} characters in all.")
SHORT_KEY = re.compile(r"quer|search|keyword|term|phrase|tag|user|handle|account|profile|owner|author|creator|name"
                       r"|(?:^|\.)q$", re.I)
CURSOR_KEY = re.compile(r"(?:next|prev|previous|end|start|page|pagination)?cursor|(?:next|prev|previous)?(?:max|min)id|after|before")
CURSOR = re.compile(r"[A-Za-z0-9_=+/:.%-]*")
INSTAGRAM_URL = re.compile(r"(?:https?://)?(?:(?:www|m)\.)?instagram\.com(?:[/?#][!-~]*)?", re.I | re.A)
EMAIL = re.compile(r"[\w.%+-]@")  # a handle's @ stands at the start or after a space
DIGITS = re.compile(r"\d(?:[\W_]{0,3}\d)*")
CONTACT = "Blocked: FastDL is given no email address and no phone-like number (7 digits or more; a post's own id has 16 to 20)."


def _off_instagram(text: str, key: str) -> bool:
    """Whether text holds a URL whose host isn't exactly Instagram's: with a scheme, as //host, as host.tld/path or as
    host.tld:port. A browser drops tabs and line breaks inside a URL and a list may be split on them, so the text is
    read both ways. A handle may look like a host (a.b), so a bare one counts only under a URL's or a host's own key."""
    for form in (text, re.sub(r"[\t\r\n]", "", text)):
        for found in SCHEME.finditer(form):
            web = WEB.match(form, found.start())
            if not (web and HOST.fullmatch(web[1])):
                return True
        for piece in re.split(r"[\s,;|<>\"'()]+", form):
            if SCHEME.match(piece):  # read above
                continue
            head, path = re.match(r"([^/\\?#]*)([/\\?#]?)", piece).groups()
            if re.match(r"[/\\]{2}", piece) or PORT.fullmatch(head):
                return True
            if HOST.fullmatch(head) and path != "\\":
                continue
            if (path and set(".:@") & set(head)) or (URL_KEY.search(key) and re.search(r"[./\\:]", piece)):
                return True
            if piece and HOST_KEY.search(key):
                return True
    return False


def _is_cursor(key: str) -> bool:
    plain = re.sub(r"[^a-z0-9]", "", key.rsplit(".", 1)[-1].lower())
    return bool(CURSOR_KEY.fullmatch(plain) or PAGE_TOKEN.fullmatch(plain))


def _cursors(value: object, key: str = "") -> list:
    """Every page cursor in a call. Not in a JSON string, which is text of TEXT_MAX at most and read as such."""
    if isinstance(value, dict):
        return [found for name, inner in value.items() for found in _cursors(inner, name)]
    if isinstance(value, list):
        return [found for inner in value for found in _cursors(inner, key)]
    return [value] if value is not None and _is_cursor(key) else []


def _too_long(text: str, key: str) -> bool:
    if _is_cursor(key):
        return len(text) > CURSOR_MAX or not CURSOR.fullmatch(text)
    short = SHORT_KEY.search(key)
    if INSTAGRAM_URL.fullmatch(text) and (URL_KEY.search(key) or not short):
        return len(text) > URL_MAX
    return len(text) > (QUERY_MAX if short else TEXT_MAX)


def _contact(text: str) -> bool:
    """Whether text holds an email address or a phone-like number: 7 digits or more with up to three other characters
    between two of them. A URL's parts are read one by one; a story's or highlight's id is 16 to 20 digits in a row."""
    text = "".join(char for char in text if unicodedata.category(char) != "Cf")  # no invisible separators
    pieces = re.split(r"[/?&=#]", text) if INSTAGRAM_URL.fullmatch(text) else [text]
    runs = [run for piece in pieces for run in DIGITS.findall(piece)]
    return bool(EMAIL.search(text)) or any(
        len(re.sub(r"\D", "", run)) >= 7 and not re.fullmatch(r"\d{16,20}", run) for run in runs)


def _text_reason(text: str, key: str) -> "str | None":
    """The text is read as it is, with its %-escapes decoded (three deep), and each with look-alikes of . : / folded."""
    if _too_long(text, key):
        return TOO_MUCH
    forms = [text]
    for _ in range(3):
        forms.append(unquote(forms[-1]))
    folded = [unicodedata.normalize("NFKC", form).replace("。", ".") for form in forms]
    for form in dict.fromkeys(forms + folded):
        if LOGIN_SHAPE.search(form) or find_secrets(form):
            return LOGIN
        if _off_instagram(form, key):
            return "Blocked: FastDL is given no URL but one on instagram.com (www. and m. too)."
    if not _is_cursor(key) and any(_contact(form) for form in forms + folded):
        return CONTACT
    return None


def _login_name(name: str) -> bool:
    plain = re.sub(r"[^a-z0-9]", "", name.lower())
    words = [word.lower() for word in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", name)]
    return (plain in LOGIN_WORDS or bool(LOGIN_KEY.search(plain) and not PAGE_TOKEN.fullmatch(plain))
            or any(word in LOGIN_WORDS or LOGIN_PART.search(word) for word in words))


def argument_reason(value: object, key: str = "", depth: int = 0) -> "str | None":
    """Why a call with this argument is refused, or None. A key is read as text too, and a JSON string both as text
    (a repeated key) and as what it holds (an escape). key is the argument's path, dotted."""
    if isinstance(value, str):
        reason = _text_reason(value, key)
        if reason or value.lstrip()[:1] not in ("{", "["):
            return reason
        try:
            return argument_reason(json.loads(value), key, depth)
        except json.JSONDecodeError:
            return None
    if isinstance(value, (dict, list)) and (depth >= DEPTH_MAX or len(value) > ITEMS_MAX):
        return TOO_MUCH
    if isinstance(value, dict):
        labels = [str(inner) for name, inner in value.items() if name.lower() in NAME_KEYS]
        if any(name.lower() in VALUE_KEYS for name in value) and any(map(_login_name, labels)):
            return LOGIN
        for name, inner in value.items():
            if _login_name(name):
                return LOGIN
            path = ".".join(filter(None, [key, *(labels if name.lower() in VALUE_KEYS else ()), name]))
            reason = _text_reason(name, "") or argument_reason(inner, path, depth + 1)
            if reason:
                return reason
    elif isinstance(value, list):
        if any(isinstance(inner, str) and re.fullmatch(r"[\w .-]{1,40}", inner) and _login_name(inner) for inner in value[:-1]):
            return LOGIN  # ["password", ...]
        for inner in value:
            reason = argument_reason(inner, key, depth + 1)
            if reason:
                return reason
    elif not _is_cursor(key) and _contact(str(value)):  # a number
        return CONTACT
    return None


def people_reason(tool_name: str) -> "str | None":
    """Why a tool that lists people is refused, under any connector's name and spelling, or None."""
    plain = re.sub(r"[^a-z]", "", tool_name.lower())
    for tool in sorted(PEOPLE):
        if tool.replace("_", "") in plain:
            return (f"Blocked: {tool} lists people. The department keeps public accounts and counts only, so no agent uses "
                    "FastDL's followers, following, likers or comments.")
    return None


def fastdl_reason(agent: str, tool_name: str, tool_input: object) -> "str | None":
    """Why this FastDL call is refused, or None."""
    tool = tool_name.rsplit("__", 1)[1]
    reason = people_reason(tool_name)
    if reason:
        return reason
    if agent not in ROLES:
        return (f"Blocked: FastDL is for the {', '.join(sorted(ROLES))}, not "
                f"{'the ' + agent if agent else 'a session without a role'}.")
    if tool_name != FASTDL + tool or tool not in ROLES[agent]:
        return (f"Blocked: the {agent} uses only these tools of the FastDL connector ({FASTDL}): "
                f"{', '.join(sorted(ROLES[agent]))}. Not {tool_name}.")
    cursors = _cursors(tool_input)
    if (len(json.dumps(tool_input, ensure_ascii=False)) > CALL_MAX or len(cursors) > 1
            or (cursors and not tool.startswith(("list_", "search_")))
            or any(not isinstance(cursor, str) and len(str(cursor)) > 20 for cursor in cursors)):
        return TOO_MUCH
    return argument_reason(tool_input, "search" if tool.startswith("search") else "")
