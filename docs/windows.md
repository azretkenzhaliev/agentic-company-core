# Windows

Section 1 is for the founder. The rest is for the platform engineer. **Nobody has run the company on native Windows**, so nothing here says that something works there.

Each claim has its source:
- **code**: read in the code, at the file and line named. If a line has moved, search the file for the name.
- **docs**: from Claude Code's docs, with the link. Another maker's docs (Python, Microsoft, Git) are named and linked too.
- **unchecked**: nobody read it anywhere, or it's our inference.

## 1. For the founder

**Use WSL 2.** It runs Ubuntu inside Windows; the [README](../README.md) ("Windows (WSL 2)") has the steps. The company's scripts and safety checks are written for macOS and Linux (code: `docs/guards.md`, "Where they run"), and Claude Code is installed inside the WSL terminal ([docs: setup](https://code.claude.com/docs/en/setup)). We haven't run it in WSL 2 either (unchecked).

**Keep the company's folder on Ubuntu's own disk** (your home folder there), not under `/mnt/c`: that is slower ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/filesystems)), and Linux file permissions aren't kept there by default ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)).

**What works less well in WSL 2:**
- **Answers given in Notion don't reach the CEO: don't set the Board desk up there.** Its Notion side doesn't work in WSL 2 at all, not by a schedule and not by hand: its key is read only from the Mac's Keychain, and every command that talks to Notion needs it (code: `keychain_token` in `scripts/board_desk/adapter_notion.py`; `macos` in `scripts/board_desk.py`). So nothing is sent to Notion, and an answer or note you write there, from a phone too, never reaches the CEO. Instead:
  - **Talk to the CEO in the terminal.** While the desk is off or its Notion side isn't set up, it quotes each question there and you answer there (code: `ceo.md`, "The desk").
  - **Email to you still works** if you give an address and connect Gmail in Claude: nothing in the sending, nor in the check for emails that are due, needs a Mac (code: `scripts/hooks/board_email.py`; `email_due` in `scripts/capacity_scan.py`; unchecked by running). The CEO only sends; a reply isn't read (code: its `tools:` line).
  - **The hourly progress pages** can be written by cron with the desk switched on, and read as files ([board-desk.md](board-desk.md), "Elsewhere (Linux)"; unchecked by running).
  - **Marketing's calendar is another path:** it is read through Claude's own Notion connector, with no key of ours. When a session queries the calendar for a week, a hook copies your decisions on posts into the approvals pages, and nothing in the hook needs a Mac (code: `scripts/notion_approvals_sync.py`); the poll that queries it by itself is macOS only (code: `scripts/marketing_schedule_job.sh`). It carries decisions on posts, not answers to the CEO. Whether it works in WSL 2: unchecked.
- **Too much work at once.** The disk and load limits hold there as on a Mac; the memory limit is macOS only, and the check says "memory not checked (not macOS)" (code: `mac_room` in `scripts/capacity_scan.py`; `load_hold` in `scripts/hooks/guard_agent_spawn.py`). WSL gets half of the PC's memory unless you change it ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)). On a small PC, tell the CEO to run fewer agents at once.
- **Off, because they are macOS only** (code): battery emails; marketing's scheduled poll and nightly copy; every marketing tool whose key sits in the Mac's Keychain (AI images and video, voice-over, transcripts, the language check, uploads, stock footage).
- **No browser.** Claude in Chrome isn't supported in WSL ([docs: chrome](https://code.claude.com/docs/en/chrome)), so the CEO can't look at web pages in your browser, and marketing's trend-researcher can't read pages.
- **Nothing runs while WSL sleeps.** An idle Ubuntu is shut down ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)), and a service of its own doesn't keep it up ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/systemd)), so timed jobs run only while it is. Leave an Ubuntu window open while the company works (unchecked).
- **Windows is reachable from inside.** A command in Ubuntu can start a Windows program (`powershell.exe`) and open your whole Windows disk (`/mnt/c`). The safety checks don't know those programs: section 2.12 says which ones stop them anyway, and how to turn it off.

**Native Windows (without WSL): don't, until the work list in section 3 is done.**
1. The safety checks can't start there as they are written, and each one that can't start blocks the action it guards, so the agents can read and talk but not write a file, run a command or start each other; a Claude Code older than 2.1.295 lets those actions through unchecked instead (code and docs: 2.2).
2. Commands can pass through PowerShell, which no safety check reads (code and docs: 2.1).
3. Several checks don't understand Windows paths, so some would let through what they must stop even once they start (code: 2.3).

**To have it made ready,** paste this to the CEO:

```
Make the company run on native Windows, by docs/windows.md.
```

Have this work done from WSL 2 or a Mac: on native Windows the checks stop the platform engineer itself.

## 2. Known to break on native Windows

How bad: **hole** = lets through what it must stop. **stop** = refuses or doesn't start; safe, but nobody can work. **broken** = a script or step fails. "Guard" means a hook of [guards.md](guards.md); the line numbers are in `scripts/hooks/` unless a path is given. The settings are `.claude/settings.json`.

### 2.1 PowerShell is a second shell, and nothing covers it

- **Without Git for Windows** there is no Bash tool, and PowerShell is the shell tool ([docs: tools](https://code.claude.com/docs/en/tools-reference), [setup](https://code.claude.com/docs/en/setup)). Every guard of commands in the settings has the matcher `Bash` (code), so none fires, and no `Bash(...)` rule applies. **Hole:** nothing guards commands.
- **With Git for Windows** PowerShell is on by default for claude.ai and Console accounts, beside Bash, and is the first choice ([docs: tools](https://code.claude.com/docs/en/tools-reference)). The same page says that a deny rule on any Bash command, a scoped one included, turns PowerShell off for the session, without a warning, unless `CLAUDE_CODE_USE_POWERSHELL_TOOL` is `1` or a scoped `PowerShell(...)` rule exists.
- **Which case is ours:** the settings have `Bash(...)` deny rules (`git push --force` and its forms, `gh pr merge --admin` and `--auto`, `gemini`), no `PowerShell(...)` rule, and don't set the variable (code). So with Git for Windows PowerShell should be off, by the docs. Nobody has seen it, and it hangs on those deny rules staying.
- **Never set the variable to `1`,** and add no `PowerShell(...)` rule, not even a deny rule, before every guard reads PowerShell (item 8): each turns the tool on.
- No agent's `tools:` line names PowerShell (code: `.claude/agents/`). Whether an agent whose list names `Bash` is given PowerShell where Bash is missing: unchecked.
- Turning it off yourself: `CLAUDE_CODE_USE_POWERSHELL_TOOL=0` ([docs: env-vars](https://code.claude.com/docs/en/env-vars)). Without Git Bash that leaves no shell tool at all (unchecked), which is safe.

### 2.2 No hook can start

| What | What happens | How bad |
|---|---|---|
| Every hook in the settings is in exec form: `"command": "${CLAUDE_PROJECT_DIR}/scripts/hooks/<name>.py", "args": []` (code) | On Windows exec form needs a real executable such as a `.exe` ([docs: hooks](https://code.claude.com/docs/en/hooks)); a `.py` with a shebang isn't one (unchecked: the page doesn't name `.py`) | – |
| The guards have `"onFailure": "block"` (code) | A hook that can't start counts as a failure, and the call is blocked, from Claude Code 2.1.295 ([docs: hooks](https://code.claude.com/docs/en/hooks)): every Write, Edit, MultiEdit, NotebookEdit, Bash, Agent, Task, SendMessage, TaskStop and `mcp__` call | stop |
| The same on an older Claude Code | It doesn't know the key, so the call goes ahead (`docs/guards.md`, "How they behave") | **hole** |
| `approve_git_reads.py`, `approve_worktree_merge.py`, `approve_pr_ready.py` and `scripts/notion_approvals_sync.py` have no `onFailure` (code) | They don't approve or sync; the normal permission rules decide | stop |
| The Stop hook in `.claude/agents/executive/ceo.md` (front matter) is in shell form, a quoted `.py` path (code) | Git Bash runs it by its shebang, so it needs a `python3` there; PowerShell prints a command that is only a quoted string instead of running it ([docs: hooks](https://code.claude.com/docs/en/hooks)). `onFailure` has no effect on Stop and SubagentStop (same page), so a Stop check that can't start fails open: the CEO isn't reminded of idle work. It guards nothing | broken |
| Python's name. Scripts, rules, skills and agent files all say `python3` (code) | No one name is sure: python.org recommends `python`, has `py`, and `python3` as a copy ([Python](https://docs.python.org/3/using/windows.html)); the Store's Python has no `py` ([Microsoft](https://learn.microsoft.com/en-us/windows/python/faqs)). Windows' own Store shortcut answers with an error code when it is given arguments (same page); with `onFailure: block` that blocks | stop |
| Exit code 2 | Blocks the call, by the [docs](https://code.claude.com/docs/en/hooks). Reported by a user, unconfirmed: on Windows 11 it [didn't](https://github.com/anthropics/claude-code/issues/80039) | unchecked |
| A hook on the Store shortcut without `onFailure` | Reported by a user, unconfirmed: the call [went ahead](https://github.com/anthropics/claude-code/issues/57946) | unchecked |

### 2.3 The guards, once they start

Hook input arrives with backslashes in `file_path`, even under Git Bash; permission rules on paths match the form `//c/...`; and the docs don't say in which style `CLAUDE_PROJECT_DIR` comes ([docs: hooks](https://code.claude.com/docs/en/hooks), [permissions](https://code.claude.com/docs/en/permissions); reported by users, unconfirmed: [several styles](https://github.com/anthropics/claude-code/issues/94256)). Eight hooks read it (code; search `scripts/hooks/` for the name). If it came as `/c/...`, native Python would read it as `C:\c\...`, and checks that compare with the repo's root would miss (unchecked).

Everything in this table is from the code; none of it was run.

| Guard | What happens on native Windows | How bad |
|---|---|---|
| `guard_kb_write.py` | `parts_under` (190-195) compares with `folder + "/"`, so a Windows path is never "under" a folder. Lets any role write the Board's approvals pages (281), the Board's answers (284), the desk's state (287) and the founder's raw inbox (290) | **hole** |
| | The same makes it refuse every write of the ux-expert (275) and of the marketing roles (198-232) | stop |
| | A command that names `company.json` with a backslash in quotes (`'x\company.json'`) isn't seen: the backslash is dropped (156) and the name no longer stands alone (127); only "/" splits a path (164) | **hole** |
| | It reads commands only when the tool is `Bash` (241) | **hole** with PowerShell |
| | The worktree check, the secrets check and the analyst's folder use Python's own path type (71-118), which reads Windows paths | unchecked |
| `board_desk_bash.py` | Splits paths on "/" only (690-698) and knows only "/" as absolute (857-863): a quoted backslash path to the Board's answers, a `C:/...` or `/c/...` path to a folder that holds them, and a command whose folder is inside them (`C:\...`, 1651) aren't seen | **hole** |
| | `git -C /c/repo stash -u`, `clean` or `reset --hard`: `checkout_holds` (706-716) finds no `.git` there and lets it go. `git -C C:/repo ...` from inside a product's worktree is joined to that folder, so it isn't seen either | **hole** |
| | `python3 'scripts\board_desk.py' <any command>`: `desk_command` (1202-1217) splits the path on "/" only, so it isn't seen as a run of the desk. Today the desk's `fcntl` import stops the run itself | **hole** once the desk imports |
| | Its exceptions (a reset in a linked worktree, the row helper, the second-opinion brief) don't match Windows paths | stop |
| `cq_write.py` | `signal.SIGALRM` (1759) doesn't exist on Windows; the error is outside its `try`, so `guard_marketing_tools.py` (343-350) refuses every Bash call of a subagent | stop |
| | Behind that stop: folder comparisons with "/" (311, 1094-1100) miss every Windows path, so moving or removing a folder that holds a question file isn't seen | **hole** once the stop is fixed |
| | `checked_in` (1403-1411) compares with "/" too, so a script file in `workspaces/` counts as the checkout's own code, which isn't read for what it writes (1508). Nor is a script named `/c/...`, which is no file to native Python, or one run by a quoted backslash path (1498-1509) | **hole** once the stop is fixed |
| `guard_neon_sql.py` | `signal.SIGALRM` (381), outside its `try`: the hook crashes with exit 1, which blocks only through `onFailure`. On an older Claude Code the SQL goes through | stop, or **hole** |
| `guard_agent_spawn.py` | `os.getloadavg` (103) doesn't exist on Windows and only `OSError` is caught: every spawn of a role that runs tests is refused, one with a `PRODUCTION FIX:` line too. The org chart part is fine | stop |
| `guard_full_suite.py` | Off until it is set up. Then: the load is read only for a run in the landing slot outside the landing lock (567); there the same missing function reaches its "a bug here must never stop engineering" line, and the run is let go | **hole** (load only, no data) |
| | `cd /c/<product> && <suite>` (`moved_to`, 389) isn't under the product, so the run isn't checked; the root is split on "/.claude/worktrees/" (141), which a Windows path doesn't hold, so in a worktree the product's folder is wrong | **hole** (load only, no data) |
| `guard_critic_bash.py` | `os.path.relpath` (76) gives backslashes, so neither allowed script is recognised: the critic and the content-reviewer can't run their checks. They are told to pass text with `--file /dev/stdin` (`.claude/agents/executive/critic.md`), which native Python may not have (unchecked) | stop |
| | Reads only `Bash` (127), so PowerShell isn't limited for the read-only roles | **hole** with PowerShell |
| | Its readers take any path (80-105): `cat //host/share/file` reads a local path on a Mac, and may open a network one on Windows | **hole** (network access) |
| `guard_merge_queue.py`, `guard_vercel_cli.py` | Know programs by exact name: `gh` (636), `vercel` and `vc` (309). `gh.exe`, `vercel.cmd` and `vercel.exe` aren't seen | **hole** |
| `marketing_bash.py` | Compares paths with the system's own separator, so they work (117-139). What `cd`, `mkdir`, `mv`, `rm`, `cp` and a node script's `--out` are given is refused when it starts with a drive letter (`C:`, 185); a read and a script's own path aren't checked for one. `/c/...` resolves elsewhere and is refused where a folder is checked. Only `python3`, `python` and `node` are known. Written for zsh, not Git Bash | stop |
| | Its reads take any path, so `//host/share` as in `guard_critic_bash.py` | **hole** (network access) |
| `guard_marketing_tools.py` | Sending mail and scheduling a post import `fcntl` (through `board_email.py` 24 and `publish/post.py` 13) and are refused. It reads the channel list without naming an encoding (303) | stop |
| | Every limit on commands (320, 331, 343, 367, 374) is on `Bash` only | **hole** with PowerShell |
| | Its own approval (`approves` 483, `_bash_stays_home` 441; only where the founder lists `no_prompts`) looks in a long flag's name for "/" and "~" only, not a backslash | **hole** (small) |
| `background_bash.py`, `bounded_wait.py` | Text checks; `Bash` only | **hole** with PowerShell |
| `guard_agent_control.py`, `neon_branch.py`, `fastdl.py`, `trend_reader.py`, `approve_pr_ready.py` | No path or program name found that Windows changes | unchecked |
| `approve_worktree_merge.py` | Its pattern holds the root as Python writes it (90-95), so `git -C C:\<root>/workspaces/<p>/.worktrees/<id> push origin <branch>` (and the merge) matches and the real worktree is checked (103-105, 125-133). Git Bash then drops the unquoted backslashes, so the command that runs without a prompt names another folder, which nobody checked (Git Bash's part: unchecked) | **hole** |
| `approve_git_reads.py` | Never approves a command with a backslash, but approves `git -C //host/share status`: a local path on a Mac, on Windows perhaps another computer's repo, whose own settings git then reads (unchecked) | **hole** |

**Program names.** Besides the three above: `board_desk_bash.py` (176, 684), `cq_write.py` (169, 187) and `guard_full_suite.py` (116, 273) know shells and interpreters by exact name, and so do `guard_vercel_cli.py` (83-90: shells, and launchers such as `npx`) and `guard_merge_queue.py` (53-54: shells, and `curl`). `bash.exe`, `python.exe`, `py`, `node.exe`, `npx.cmd`, `curl.exe`, `powershell` and `cmd` are just unknown programs to them. The deny rules too: `git.exe push --force` doesn't match `Bash(git push *--force*)`. **Hole.**

**Other names for one file** (8.3 short names, a trailing dot or space, `::$DATA`, `\\?\`, a network name such as `\\host\share`, `//host/share` or `//localhost/c$/...`, junctions, a `subst` drive): no guard handles them (code); what Windows does with each: unchecked. A short name in a hook's path was reported by a user, unconfirmed ([here](https://github.com/anthropics/claude-code/issues/94256)).

**Permission rules** with a drive letter or a quoted path: reported by users, unconfirmed, as [not matching](https://github.com/anthropics/claude-code/issues/76490). Our rules hold no absolute path (code: `scripts/tests/test_settings.py`).

### 2.4 Read, Grep and Glob

On Windows Grep and Glob are tools of their own; on macOS, Linux and WSL a search is a Bash call ([docs: tools](https://code.claude.com/docs/en/tools-reference)). No guard of ours is on Read, Grep or Glob (code), so a search that on a Mac meets a role's Bash guard meets none here. Roles that list Grep and Glob: platform-engineer, ux-expert, content-reviewer, performance-analyst (code); of these only the content-reviewer's Bash is a list of allowed commands (`guard_critic_bash.py`). Grep opens nothing that the same role's Read doesn't (code: neither has a guard). The `Read(...)` deny rules the founder may add ([guards.md](guards.md)): whether they hold Grep is unchecked.

### 2.5 Worktrees and the sandbox

- A subagent's isolation in its worktree is weaker for PowerShell: only the working folder is checked ([docs: worktrees](https://code.claude.com/docs/en/worktrees)).
- Native Windows has no sandbox; WSL 2 has ([docs: setup](https://code.claude.com/docs/en/setup)). The company doesn't turn one on (code: the settings).

### 2.6 Python that Windows doesn't have

`fcntl` exists only on Unix ([Python](https://docs.python.org/3/library/fcntl.html)); so do `os.getloadavg` and `os.getuid` ([Python](https://docs.python.org/3/library/os.html)). The lines are from the code.

| Needs | Where | What happens |
|---|---|---|
| `fcntl` (file locks) | `scripts/board_desk/answers_seal.py` 48, and through it `scripts/capacity_scan.py` 254 | **The capacity scan doesn't start**, so `--mac` never prints `room: yes` and every agent that must wait for it waits for ever; the heartbeat ends silently. Broken |
| | `scripts/board_desk.py` 146, `scripts/kb_sweep.py` 39, `scripts/battery_alert.py` 51, `scripts/hooks/board_email.py` 24 | Broken; mail is refused |
| | `tools/marketing/`: `spend.py` 27, `publish/post.py` 13, `reels/save.py` 42, `reels/watch.py` 65 | Broken: no paid call, no scheduling, no downloads |
| `os.getloadavg` | `scripts/token_report.py` 242 | Broken. `capacity_scan.py` takes it as "load unknown", which is `room: no` |
| `signal.SIGALRM`, `setitimer` | `cq_write.py` 1759, `guard_neon_sql.py` 381, `tools/marketing/reels/watch.py` 468-474 | 2.3; broken |
| `os.getuid` | `battery_alert.py` 440, 448; `board_desk.py` 2667, 2687; `marketing_intelligence_backup.py` 175, 183 | Only in macOS steps |
| `O_NOFOLLOW`, `O_NONBLOCK` | `tools/marketing/reels/save.py` 460-473, `watch.py` 513 | Broken |
| File modes (`0o600`, `0o700`) | `scripts/guard_replay.py` 132-139, `answers_seal.py` 220, `reels/save.py` 460, `watch.py` 513 | Windows keeps only the read-only mark ([Python](https://docs.python.org/3/library/os.html)): a file meant to be private isn't |

### 2.7 Programs and folders that only macOS has

All from the code. On Linux and WSL 2 these are off or say so; on native Windows the same, where the file starts at all (2.6).

- `launchctl` and plists: `battery_alert.py` 71-76, 441-450; `board_desk.py` 209-215, 2675-2689; `capacity_scan.py` 1373 (`capacity_heartbeat.py` asks through it); `marketing_intelligence_backup.py` 51-53, 175-185; `marketing_schedule_job.sh` (bash; stops unless `uname` is Darwin, 24).
- `security` (the Keychain): `board_desk/adapter_notion.py` 251; `scripts/language_check.py` 114; `tools/marketing/`: `gen/gemini.py` 70, `voice/scribe.py` 73, `publish/stage_item.py` 60, `footage/fetch.py` 77. Each stops without it.
- `pmset` (`battery_alert.py` 140), `sysctl` and `memory_pressure` (`capacity_scan.py`, `mac_memory`), `osascript` (`tools/marketing/measure/ocr.py` 29; Tesseract is the other engine), `sips` (`reels/save.py` 91).
- `/usr/bin/python3` in the jobs: `battery_alert.py` 74, `board_desk.py` 214, `marketing_intelligence_backup.py` 53.
- Virtual environments at `bin/python`: `footage/fetch.py` 53, `reels/save.py` 58, `measure/run.py` 86, `tools/marketing/README.md`. On Windows it is `Scripts\python.exe` (unchecked).
- `~/Library/...`: `capacity_scan.py` 386, `tools/ux/README.md` 12. The seal's folder falls to `~/.local/state` (`answers_seal.py` 60-63).

### 2.8 Text, files and Git

| What | What happens | How bad |
|---|---|---|
| Encoding | Before Python 3.15, `open()` without `encoding=` uses the PC's own code page ([Python](https://docs.python.org/3/using/windows.html)). The hooks read their input from `sys.stdin`, and these read files, with none named (code): `capacity_scan.py` 563, 649, 710, 797, 807, 1090, 1656, 1743, 1775; `board_desk.py` 557, 973-996, 1383; `answers_seal.py` 168; `adapter_notion.py` 558; `kb_lint.py` 186; `capacity_heartbeat.py` 88; `guard_marketing_tools.py` 234, 303. Names and pages in any other alphabet are misread, or stop the script; printing them can stop it too (unchecked) | broken; a misread path in a guard: unchecked |
| Replacing a file that another program holds open | `os.replace` in `kb_sweep.py` 116, `board_desk.py` 983-1000, `answers_seal.py` 204, `battery_alert.py` 370 and marketing's tools (code) may fail with "access denied" (unchecked; reported by users of other projects) | broken |
| Line endings | There is no `.gitattributes` (code). Git for Windows may check files out with CRLF, by its settings ([git-config](https://git-scm.com/docs/git-config), [gitattributes](https://git-scm.com/docs/gitattributes)): a `#!/usr/bin/env python3` or `#!/bin/bash` line then ends in a stray character under Git Bash, and checks that split on a newline alone see it (unchecked) | broken |
| The executable bit | Hooks are mode 755 (code), and `scripts/tests/test_settings.py` checks it; Git follows it only where the disk keeps it ([git-config](https://git-scm.com/docs/git-config)) | broken test |
| Symlinks | The repo holds none (code). Tests make them; Windows needs a right or Developer Mode for that ([Python](https://docs.python.org/3/library/os.html)), and Git for Windows turns them off by default ([Git for Windows](https://gitforwindows.org/symbolic-links)) | broken tests |
| Long paths | Off by default in Git for Windows ([Git for Windows](https://gitforwindows.org/git-cannot-create-a-file-or-directory-with-a-long-path.html)); worktrees under `.claude/worktrees/` lengthen each path | broken |
| File names | None in the repo differ only in case or hold a character Windows bars (code). Question files, archives and weeks' pages are named from ids and dates; their names weren't all checked | unchecked |
| Time zones | `company.json`'s `timezone` needs the IANA database (`company_config.py`); Windows has none of its own for Python, so `tzdata` must be installed (unchecked) | broken |

### 2.9 Shell text in agents, skills and runbooks

Commands there are written for bash or zsh: `grep`, `sed`, `find`, `date -u`, `until` loops, heredocs, `/tmp`, `> /dev/null`, `&&` (code). The one rule that covers them all: **Git Bash is the only shell**, so no text needs a PowerShell form. What Git Bash doesn't give (unchecked which of them it brings):

- `python3`: in about 60 files (agent files, skills, `docs/`, `knowledge/`, `tools/marketing/`, the README, `CLAUDE.md`; `git grep -lF "python3 "` lists them). One name for all of them is item 3.
- `lsof`: `.claude/agents/executive/ceo.md` 93-94; `.claude/agents/engineering/cto.md` 189, 191, 198, `staff-engineer.md` 56, 137; `knowledge/engineering/cores/staff-engineer.md` 21; `knowledge/engineering/standards/board-steps.md` 78. It answers "does a process still run in this worktree"; that check needs a Windows form before two agents share a worktree.
- `launchctl`: `ceo.md` 113 (the Board desk). `shasum`: `.claude/skills/system-check/SKILL.md` 10. `timeout`, `kill`: the engineering agents and cores. `/dev/stdin`: `critic.md` 34.
- macOS's own command forms (`date -v`, `sed -i ''`): `marketing_schedule_job.sh` only (code).

### 2.10 The tests

CI runs `scripts/tests/` and `tools/marketing/tests/` on Ubuntu only (code: `.github/workflows/kb-lint.yml`, `marketing-tools.yml`). On Windows these fail or must be skipped, from the code: every test that makes a symlink (search both folders for `symlink`); `fcntl` (`test_board_email.py` 3, `test_reels_save.py` 5, `test_reels_watch.py` 4); `os.getloadavg` patched without `create=True` (`test_capacity_scan.py`, `test_guard_agent_spawn.py`, `test_guard_full_suite.py`, `test_slot_l.py`, `test_token_report.py`); `SIGKILL` (`test_reels_watch.py`); `/bin/bash` (`test_marketing_schedule_gate.py` 209); `python3` by name (`session.test.mjs`, `taste.test.mjs`, `trial.test.mjs`); the shebang, the executable bit and `"args": []` (`test_settings.py`). A test that asserts a POSIX path isn't listed: most guard tests do.

### 2.11 Agents that need a browser

Claude in Chrome is supported on native Windows and not in WSL ([docs: chrome](https://code.claude.com/docs/en/chrome)). It is the CEO's (`mcp__claude-in-chrome__*`) and the trend-researcher's whole tool (code). Neither was tried on Windows.

### 2.12 WSL 2: the way out to Windows

From WSL a command can start Windows programs, and Windows' PATH is added, by default ([Microsoft](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)). Do our guards see `powershell.exe` and `cmd.exe`? From the code:

- No guard and no rule names `powershell.exe`, `cmd.exe`, `git.exe`, `gh.exe` or `/mnt/c`. `cq_write.py` (170) knows `pwsh`, without `.exe`.
- Roles whose Bash is a list of allowed programs are refused them: the critic and the content-reviewer (`guard_critic_bash.py`) and the marketing roles (`marketing_bash.py`).
- Any command that names the Board's answers or the desk's state with "/" is refused unless it only reads, whatever the program (`board_desk_bash.py`). With backslashes, or by the `\\wsl.localhost\` name, it isn't seen.
- For every other agent (the CEO, the CTO, Staff, Seniors, the platform engineer) `powershell.exe -Command "..."` is an unknown program, and `git.exe push --force` passes the deny rules. What's left is Claude Code's own permission check, which asks for a command with no allow rule.

To turn it off: in Ubuntu's `/etc/wsl.conf`, `[interop]` with `enabled=false`, then `wsl --shutdown` in Windows. It also stops opening the Windows browser from Ubuntu, so sign in by pasting the code ([docs: troubleshooting](https://code.claude.com/docs/en/troubleshoot-install)). Not tried (unchecked). Claude Code's docs warn against turning off `appendWindowsPath` (same page).

Two more, both unchecked: the load, the number of CPUs and the free disk the checks read are the Ubuntu machine's, not the PC's, so a full Windows drive isn't seen.

## 3. The platform engineer's work list

In this order, and **items 3 and 5 land only with or after items 4 and 6**: today a hook that can't start and a check that crashes are what stop the holes of 2.3, so until then 3 and 5 are tried in the disposable clone only. Items 4 and 6 may land first, alone. "Guardrail" = it goes through the CEO's gate (`ceo.md`, "System changes"); a change that loosens one goes to the Board first. `.claude/settings.json` and `company.json` are written only by the main session on the founder's own message: hand the CEO the exact text. Work from WSL 2 or a Mac; prove each item on a real Windows machine (section 4). Nothing on Mac and Linux may change: both must stay green.

### Safety

| # | Files | What to change | How to prove it | Guardrail |
|---|---|---|---|---|
| 1 | None: a disposable clone on the Windows machine, with one test hook and no other settings | Before any other work: a hook that exits 2 for the harmless command `echo guard-test`, matcher `Bash\|PowerShell`, in the form of item 3 | The refusal is **seen** in Bash and in PowerShell (with no Bash deny rule in that clone PowerShell is on by itself, by the docs). If either goes through, stop: no guard can hold there, and nothing below helps | No |
| 2 | `.claude/settings.json` (`env`), `scripts/tests/test_settings.py` (`ENV`), the README | Git for Windows required; `CLAUDE_CODE_USE_POWERSHELL_TOOL` set to `0`, in the settings and in the Windows user's environment (whether the settings' `env` is read in time: unchecked). Keep every `Bash(...)` deny rule. Say the least Claude Code version, 2.1.295, at setup and check it | `claude` on Windows lists no PowerShell tool; a probe that asks for a PowerShell command gets none | Yes, tighter |
| 3 | `.claude/settings.json`, `ceo.md` (front matter), `test_settings.py` | With or after items 4 and 6, never before them. Every hook as interpreter plus script: `"command": "python3", "args": ["${CLAUDE_PROJECT_DIR}/scripts/hooks/<name>.py"]`, `onFailure` as now. One name on every system: `python3`, made a real program on Windows (an installer that brings it; the Store shortcuts off) and checked at setup with `python3 --version`. If no one name can hold, the settings need a per-machine file: ask the CEO | `test_settings.py` checks the new form; a probe per guard (section 4); on a machine where `python3` is the Store shortcut, every guarded call is refused | Yes |
| 4 | `guard_kb_write.py`, `board_desk_bash.py`, `cq_write.py`, `guard_critic_bash.py`, `guard_full_suite.py`, `marketing_bash.py`, `approve_worktree_merge.py`, `approve_git_reads.py`, `guard_marketing_tools.py` (with its own approval) and every reader of `CLAUDE_PROJECT_DIR` | One shared module that turns a path from a tool input, a command word, the cwd or the environment into one form: backslashes, `C:\`, `C:/`, `/c/`, `\\?\`, network names (`\\host\share`, `//host/share`, `//localhost/c$/`), case, short names. A path it can't read is refused where the guard stops things, and not approved where it approves; nor is a command whose words Git Bash would change (an unquoted backslash), and a network name is neither read nor approved. `os.path.realpath` before each comparison | For each path hole of 2.3 a test that fails today and refuses (or isn't approved) after; the same tests with POSIX paths unchanged. `guard_replay.py` over real commands on a Mac: no new false refusal | Yes |
| 5 | `cq_write.py`, `guard_neon_sql.py`, `guard_agent_spawn.py`, `guard_full_suite.py` | With or after items 4 and 6, never before them: the crash is what stops the path and program-name holes behind it (2.3). A time limit without `SIGALRM` (a thread or a child process), inside the `try`; a missing `getloadavg` is an unknown load: the spawn guard holds, and `PRODUCTION FIX:` passes as on a Mac; `guard_full_suite.py` doesn't let a run go for it | Tests with the functions removed (`del os.getloadavg`), as `test_capacity_scan.py` does | Yes |
| 6 | Guards that know programs by name (2.3); the deny rules | Drop `.exe`, `.cmd`, `.bat` and case from a program's name before comparing; add `py`, `python`, `powershell`, `pwsh`, `cmd`; a deny rule for each `.exe` form of git, gh and gemini. It helps on WSL 2 too: do this one, alone, even if native Windows never comes | Tests per name; a probe of `git.exe push --force` in a clone with no remote | Yes, tighter |
| 7 | The settings, `guard_critic_bash.py`, `marketing_bash.py` | Decide, with the CEO, whether the roles whose Bash reading is limited also need a limit on Read, Grep and Glob, or whether that limit was only Bash's | A test per role | Yes, tighter |
| 8 | Every guard of commands; the settings' matchers and deny rules | Only if PowerShell is ever wanted: each guard parses PowerShell (`Remove-Item` and its aliases, `;`, `\|`, backquotes, `&`, `-EncodedCommand`), the matchers become `Bash\|PowerShell`, each deny rule gets a `PowerShell(...)` twin. The twins turn the tool on, so they land last, after the guards. Until then item 2 stays. The worktree isolation is weaker there (2.5) | Each guard's whole test list again in PowerShell; a probe per guard | Yes; turning the tool on goes to the Board |

### What stops the first run

| # | Files | What to change | How to prove it | Guardrail |
|---|---|---|---|---|
| 9 | `.gitattributes` (new) | `* text=auto eol=lf`, binary types marked | A clone on Windows has no CRLF in `*.py`, `*.sh`, `*.md`, `*.json` | No |
| 10 | `answers_seal.py`, `board_desk.py`, `kb_sweep.py`, `board_email.py`, `battery_alert.py`, `spend.py`, `post.py`, `save.py`, `watch.py` | After items 4 to 6: until then the failing import is what stops a run of the desk that its guard doesn't see (2.3). One small lock module (`fcntl`, else Windows' own `msvcrt`); import it where the lock is taken. Where a lock can't be had, stop, as now | Two processes in a test: the second waits | `board_email.py`, `spend.py`, `publish/`: yes |
| 11 | `capacity_scan.py` | Once it imports: the load. Windows gives none, so `room: no` for ever. Read the CPU's use another way, or a limit on running agents, and say in the line which. The same reading in `guard_agent_spawn.py` | The two agree in `test_guard_agent_spawn.py`, as on a Mac | `guard_agent_spawn.py`: yes; a higher limit loosens |
| 12 | Every `open`, `read_text`, `write_text` and text subprocess without an encoding (2.8); hooks' `stdin` and `stdout` | `encoding="utf-8"`; for hooks `sys.stdin.reconfigure(encoding="utf-8")`. `PYTHONUTF8=1` in the settings' `env` besides | A test with a page and a path in another alphabet, run with `PYTHONUTF8=0` and a non-UTF-8 locale | Hooks and settings: yes |
| 13 | Agent files, skills, runbooks, cores (2.9) | One line in `CLAUDE.md`: Git Bash is the only shell. A Windows form of "does a process run in this worktree" (`lsof`). `/dev/stdin`: a `--file -` in `second_opinion.py`, and the same in `guard_critic_bash.py` and `critic.md` | The critic's and a reviewer's whole run on Windows | `CLAUDE.md`, `second_opinion.py`, the hook: yes |
| 14 | `os.replace` calls (2.8) | Retry for a short time on `PermissionError`, then fail as now | A test with the target held open | No |
| 15 | The tests (2.10) | Skip with a reason what Windows can't do (symlinks, modes); replace `python3` with the running interpreter; patch `os.getloadavg` with `create=True`; add `windows-latest` to `kb-lint.yml` and `marketing-tools.yml` | CI green on both | No |
| 16 | README, `docs/guide.md`, `docs/guards.md` | `tzdata`, long paths (`core.longpaths`, Windows' own switch), the least versions; only after section 4 passed | The founder's steps, followed once from nothing | No |

### Scheduled jobs

| # | Files | What to change | How to prove it | Guardrail |
|---|---|---|---|---|
| 17 | `board_desk.py` (install, uninstall), `marketing_schedule_job.sh`, `marketing_intelligence_backup.py`, `battery_alert.py` | Task Scheduler in launchd's place, or say they are off. `marketing_schedule_job.sh` in Python | Installed, seen to run twice, removed | `marketing_schedule_job.sh`: yes |
| 18 | `adapter_notion.py`, `language_check.py`, `gen/`, `voice/`, `publish/stage_item.py`, `footage/fetch.py`; `board_desk_bash.py` (it holds reads of the Keychain) | A second place for the keys (Windows' Credential Manager), read by the one script that uses each; the guard holds that program as it holds `security` | Tests; a probe that an agent's own read is refused | Yes; a new place for secrets goes to the Board |
| 23 | `adapter_notion.py` (`keychain_token`), `board_desk.py` (`macos`, `install`, `uninstall`), `capacity_scan.py` (`desk_job_loaded`), `board_desk_bash.py`, `docs/board-desk.md`, `ceo.md` ("The desk") | The desk's Notion side on WSL 2 and Ubuntu. It needs no native Windows and no item above, so it can be done first. A Linux place for the desk's key in the Keychain's stead, read by `adapter_notion.py` alone, with `board_desk_bash.py` and the other guards holding that program as they hold `security`; a plain file won't do by itself, since no guard is on Read (2.4). cron or a systemd timer: `read` every 2 minutes, `run` hourly; they run only while Ubuntu does. `desk_job_loaded` asks launchd alone, so a reader that stopped shows no `DESK STALE` until it knows the timer. The attribution test again before any answer counts. Then take the first point out of section 1's list | An answer typed in Notion on a phone reaches `board_desk.py wait` with the Ubuntu window open, **seen**; a probe that an agent's own read of the key is refused; the desk's tests green on a Mac and on Linux | Yes; a new place for secrets goes to the Board |

### Comfort

| # | Files | What to change | How to prove it | Guardrail |
|---|---|---|---|---|
| 19 | `tools/marketing/`, `tools/ux/` | `Scripts\python.exe`, Tesseract's and ffmpeg's paths, an image converter in place of `sips`; `npm` on Windows | Their own tests on Windows | `footage/fetch.py`, `gen/`, `voice/`, `publish/`: yes |
| 20 | `trend_reader.py`, the CEO's Chrome | Try Claude in Chrome on Windows | One read of one page | No |
| 21 | `token_report.py` | A load line only where the system gives one | A test | No |
| 22 | macOS upkeep (battery emails), the memory limit | A Windows form, or say they are off | A test | No |

## 4. How to check it afterwards

On a real Windows machine, by a person, the refusals **seen** and written down. Nothing is called working before that.

1. Item 1 again, in the company's own folder: one guard visibly blocks one harmless test command, in Bash and, if the tool is there, in PowerShell. The docs say exit code 2 blocks; one user's report says it didn't.
2. `claude --version` is 2.1.295 or later. `python3 --version` answers in Git Bash and is what the hooks start.
3. `python3 -m unittest discover -s scripts/tests` and, with marketing on, `python3 -m unittest discover -s tools/marketing/tests` and `npm test --offline --ignore-scripts`: green, each skip with its reason.
4. One probe per guard, in a disposable clone, by the platform engineer's probe rule (`.claude/agents/executive/platform-engineer.md`; read `permission_denials`, never the model's own words). For each: one call it must stop, one it must let through, each with `\`, `C:/`, `/c/` and network (`//localhost/c$/`) paths. Each approving hook too: a merge, a push and a git read in those forms must not be approved unless the folder that runs is the one checked. The calls to stop: a write to the Board's answers, to the approvals pages, to `company.json` from a subagent, to another agent's worktree; a secret in a page; a spawn outside the org chart; a message to a stranger agent; a removed question-file folder; a run of the desk by a backslash path; a read of a network path by the critic; `git push --force` and `git.exe push --force`; a Vercel deploy; a `gh` command that leaves the merge queue; a mail to any other address; a `DROP TABLE`.
5. Break one guard on purpose (rename its file): the call it guards is refused.
6. The Stop hook fires once, with idle work in a test directive.
7. `python3 scripts/capacity_scan.py --mac` prints a line, and `guard_agent_spawn.py` agrees with it.
8. A second machine with Python from the Store, and one with Python from python.org.

## 5. What nobody has checked

- Anything at all by running it on native Windows; the company in WSL 2.
- The Board desk in WSL 2: nobody has tried it, neither its hourly run by cron nor its Notion side.
- Whether our Bash deny rules turn PowerShell off, and what they do without Git for Windows.
- Whether an agent whose `tools:` names Bash is given PowerShell when Bash is missing.
- Whether a `.py` in exec form can't start (inferred from the docs' rule), and whether a hook that can't start really blocks on Windows.
- In which style `CLAUDE_PROJECT_DIR`, `cwd` and a command's own paths reach a hook; the encoding of the input.
- Whether path rules ignore case and drive-letter case.
- Whether an agent's own worktree on Windows stays its own: the check reads as right and wasn't run.
- The name tricks of Windows' file system against each guard (2.3).
- Which programs Git Bash brings, and whether it gives native Python a `/dev/stdin`.
- `os.replace` with an open file; CRLF in a shebang.
- The npm packages, Remotion, Playwright, ffmpeg, yt-dlp, Tesseract and instaloader on Windows.
- Docker Desktop, test databases and the full-suite slots, natively or in WSL.
- `[interop] enabled=false` in WSL with Claude Code's sign-in, notifications and IDE.
- The clock after sleep in WSL; whether an open window keeps it awake.
- Cloud sessions opened from a Windows PC.
