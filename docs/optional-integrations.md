# Optional integrations

The core runs with nothing but Claude Code, `gh` and Python. These four integrations come from running this setup on real products. Each one is off, or does nothing, until you switch it on.

| Integration | What it gives you | Default |
|---|---|---|
| [Second opinions from other model families](#1-second-opinions-from-other-model-families-sa-003) | Gemini, GPT and DeepSeek review every design and diff next to Claude | Off until you set the API keys |
| [Claude in Chrome for the CEO](#2-claude-in-chrome-for-the-ceo) | The CEO can look at web pages in your browser | Listed in the CEO's tools; works only when you start it with `--chrome` |
| [Neon (Postgres) connector, with a SQL guard](#3-neon-postgres-connector-with-a-sql-guard) | Engineering agents read your production database and make backup branches, with dangerous SQL blocked and every statement logged | Not installed |
| [Vercel CLI guard](#4-vercel-cli-guard) | Agents can't deploy from the CLI; products deploy only through Git | Not installed |

## 1. Second opinions from other model families (SA-003)

Both reviewers (`design-reviewer`, `code-reviewer`) run `scripts/second_opinion.py`, which sends the material under review to other model families. Models tend to favour their own output, so a second family catches what Claude misses. A blocker or major from a second opinion counts unless the Claude reviewer refutes it with `file:line` evidence.

1. Create API keys and export them in your shell profile (`~/.zshrc`), never in this repo:
   - `GEMINI_API_KEY` from Google AI Studio, with billing enabled there (the free tier's quota for the larger models is tiny);
   - `OPENAI_API_KEY`;
   - `DEEPSEEK_API_KEY` (optional: it takes Gemini's slot when Gemini is off or out of quota).
2. Check it: `python3 scripts/second_opinion.py --kind code --brief check --file README.md`.
3. Confirm [SA-003](../knowledge/board/standing-authorizations.md) with your Board: the providers may train on what is sent. The script screens credential values out of every packet anyway.

The default models are in the `choose_*` functions in the script. It confirms each model is on the key's model list and never guesses ids. Every call is logged to `workspaces/second-opinions/calls.jsonl` (gitignored) with its token counts, so spend can be counted, and every answer is saved to `workspaces/second-opinions/answers/<call id>.txt`, so a review stopped after its paid calls can reuse them. Without keys, reviews run single-family and say so.

## 2. Claude in Chrome for the CEO

The CEO's tool list includes `mcp__claude-in-chrome__*`, so with the [Claude in Chrome](https://claude.com/chrome) extension installed the CEO can open and read pages in your browser, for example to check what a competitor's sign-up page shows.

- Start the CEO with `claude --agent ceo --chrome`.
- The browser is yours, with your signed-in accounts. `CLAUDE.md` forbids sending anything outside the company without the Board, but nothing in the tool list enforces "look only". Tell the CEO in the directive what it may do in the browser.
- To remove it, delete `mcp__claude-in-chrome__*` from the `tools:` line in `.claude/agents/executive/ceo.md`.

## 3. Neon (Postgres) connector, with a SQL guard

With the claude.ai Neon connector, engineering agents can inspect your database, make a backup branch before a migration, and run checked SQL. The setup below gives each role only what it needs, denies the destructive tools to every session, and runs a hook that blocks dangerous SQL and logs every statement.

1. **Connect** the Neon connector in Claude, and check that it shows in `claude mcp list`.
2. **Give the roles their tools.** Append to the `tools:` line of:
   - `.claude/agents/engineering/cto.md`: all 22 tools in the allow list below;
   - `.claude/agents/engineering/staff-engineer.md`: the same, except `mcp__claude_ai_Neon__run_sql_transaction`;
   - `.claude/agents/engineering/senior-engineer.md`: the first 10 (read-only) tools.
3. **Add the permission rules** to `.claude/settings.json`: the allow list to `permissions.allow`, the deny list to `permissions.deny`.

   <details><summary>Allow list (22 tools)</summary>

   ```json
   "mcp__claude_ai_Neon__list_projects", "mcp__claude_ai_Neon__describe_project", "mcp__claude_ai_Neon__list_branches",
   "mcp__claude_ai_Neon__get_branch", "mcp__claude_ai_Neon__get_default_branch", "mcp__claude_ai_Neon__describe_branch",
   "mcp__claude_ai_Neon__list_postgres_databases", "mcp__claude_ai_Neon__get_database_tables",
   "mcp__claude_ai_Neon__describe_table_schema", "mcp__claude_ai_Neon__compare_database_schema",
   "mcp__claude_ai_Neon__list_organizations", "mcp__claude_ai_Neon__list_postgres_roles", "mcp__claude_ai_Neon__list_snapshots",
   "mcp__claude_ai_Neon__get_snapshot_schedule", "mcp__claude_ai_Neon__list_operations", "mcp__claude_ai_Neon__get_operation",
   "mcp__claude_ai_Neon__inspect_database", "mcp__claude_ai_Neon__list_docs_resources", "mcp__claude_ai_Neon__get_doc_resource",
   "mcp__claude_ai_Neon__create_branch", "mcp__claude_ai_Neon__run_sql", "mcp__claude_ai_Neon__run_sql_transaction"
   ```
   </details>

   <details><summary>Deny list (61 tools: deleting, resetting, credentials, auth, functions, storage)</summary>

   ```json
   "mcp__claude_ai_Neon__delete_project", "mcp__claude_ai_Neon__create_project", "mcp__claude_ai_Neon__update_project",
   "mcp__claude_ai_Neon__recover_project", "mcp__claude_ai_Neon__delete_branch", "mcp__claude_ai_Neon__reset_from_parent",
   "mcp__claude_ai_Neon__update_branch", "mcp__claude_ai_Neon__set_default_branch", "mcp__claude_ai_Neon__restore_snapshot",
   "mcp__claude_ai_Neon__finalize_branch_restore", "mcp__claude_ai_Neon__delete_snapshot", "mcp__claude_ai_Neon__update_snapshot",
   "mcp__claude_ai_Neon__set_snapshot_schedule", "mcp__claude_ai_Neon__get_connection_string",
   "mcp__claude_ai_Neon__reset_postgres_role_password", "mcp__claude_ai_Neon__create_credential",
   "mcp__claude_ai_Neon__rotate_credential", "mcp__claude_ai_Neon__revoke_credential", "mcp__claude_ai_Neon__create_postgres_role",
   "mcp__claude_ai_Neon__delete_postgres_role", "mcp__claude_ai_Neon__create_postgres_database",
   "mcp__claude_ai_Neon__update_postgres_database", "mcp__claude_ai_Neon__delete_postgres_database",
   "mcp__claude_ai_Neon__prepare_database_migration", "mcp__claude_ai_Neon__complete_database_migration",
   "mcp__claude_ai_Neon__prepare_query_tuning", "mcp__claude_ai_Neon__complete_query_tuning",
   "mcp__claude_ai_Neon__create_postgres_endpoint", "mcp__claude_ai_Neon__update_postgres_endpoint",
   "mcp__claude_ai_Neon__delete_postgres_endpoint", "mcp__claude_ai_Neon__start_postgres_endpoint",
   "mcp__claude_ai_Neon__suspend_postgres_endpoint", "mcp__claude_ai_Neon__restart_postgres_endpoint",
   "mcp__claude_ai_Neon__provision_neon_auth", "mcp__claude_ai_Neon__disable_auth", "mcp__claude_ai_Neon__update_auth_config",
   "mcp__claude_ai_Neon__add_auth_oauth_provider", "mcp__claude_ai_Neon__update_auth_oauth_provider",
   "mcp__claude_ai_Neon__delete_auth_oauth_provider", "mcp__claude_ai_Neon__add_auth_trusted_domain",
   "mcp__claude_ai_Neon__delete_auth_trusted_domain", "mcp__claude_ai_Neon__create_auth_user",
   "mcp__claude_ai_Neon__delete_auth_user", "mcp__claude_ai_Neon__update_auth_user_role",
   "mcp__claude_ai_Neon__provision_neon_data_api", "mcp__claude_ai_Neon__update_data_api", "mcp__claude_ai_Neon__delete_data_api",
   "mcp__claude_ai_Neon__deploy_function", "mcp__claude_ai_Neon__update_function", "mcp__claude_ai_Neon__delete_function",
   "mcp__claude_ai_Neon__create_trigger", "mcp__claude_ai_Neon__update_trigger", "mcp__claude_ai_Neon__delete_trigger",
   "mcp__claude_ai_Neon__register_functions_custom_domain", "mcp__claude_ai_Neon__delete_functions_custom_domain",
   "mcp__claude_ai_Neon__create_storage_bucket", "mcp__claude_ai_Neon__delete_storage_bucket",
   "mcp__claude_ai_Neon__delete_storage_object", "mcp__claude_ai_Neon__delete_storage_objects_by_prefix",
   "mcp__claude_ai_Neon__presign_storage_object", "mcp__claude_ai_Neon__send_feedback"
   ```
   </details>

   Deny rules apply to every session in the repo, including your own maintenance sessions.
4. **Switch on the SQL guard:** add this to `hooks.PreToolUse` in `.claude/settings.json`:

   ```json
   {
     "matcher": "mcp__claude_ai_Neon__run_sql|mcp__claude_ai_Neon__run_sql_transaction",
     "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/scripts/hooks/guard_neon_sql.py", "args": [], "timeout": 10}]
   }
   ```

   It blocks `DROP`, `TRUNCATE`, role and password changes, `DELETE` or `UPDATE` without `WHERE`, and any statement naming a table in `PROTECTED_TABLES`. Edit that list at the top of the script for your schema; the default is Better Auth's `account`, `session` and `verification` tables. Every statement, blocked or not, is logged to `workspaces/neon-sql-audit.log` (gitignored); if the log can't be written, the call is blocked. It guards against mistakes; it can't parse Postgres, so it isn't a sandbox.
5. **Write the guardrails into an ADR** for the product (`knowledge/engineering/adr/`), and point to it from the runbook. The engineering prompts already say: a backup before any migration or bulk write; never delete or reset a database, project or branch; read personal-data tables only when the task needs it; never print a connection string; schema changes only through the repo's migrations.

## 4. Vercel CLI guard

`scripts/hooks/guard_vercel_cli.py` stops agents from deploying with the Vercel CLI: `vercel deploy`, `vercel` with no command or with a path, `--prod`, `redeploy`, `link` (which writes a token to `.env.local`) and `promote`. It sees through chains, subshells, `sh -c`, variable assignments and `npx`/`bunx`-style launchers. Plain `claude` sessions aren't limited, so you can still deploy by hand. Reads (`ls`, `inspect`, `env ls`, `api` GETs) and builds stay allowed.

1. Add this to `hooks.PreToolUse` in `.claude/settings.json`:

   ```json
   {
     "matcher": "Bash",
     "hooks": [{"type": "command", "command": "${CLAUDE_PROJECT_DIR}/scripts/hooks/guard_vercel_cli.py", "args": [], "timeout": 10}]
   }
   ```

2. Configure it at the top of the script (all empty by default):
   - `PROMOTE_SCOPES`: teams whose runbook rolls back with Instant Rollback and then `vercel promote`. Without one, `promote` is always refused.
   - `GIT_ONLY_SCOPES` and `GIT_ONLY_DIRS`: products whose production and aliases change only through Git. For them, agents also can't run `rollback` (except `rollback status`), alias writes or `rolling-release`. A call targets such a product with its `--scope`, or with no scope from its folder under `workspaces/`.
3. Run the tests: `python3 -m unittest discover -s scripts/tests`.
