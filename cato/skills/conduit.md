# Conduit Browser
**Version:** 1.0.0
**Capabilities:** browser.navigate, browser.click, browser.type, browser.extract, browser.screenshot

## Overview
Conduit is the auditable browser engine built into Cato. Every browser action is
logged to the audit trail. Billing is disabled for local Cato use — all actions are free.

## Activation
Conduit is used automatically when `conduit_enabled: true` is set in `~/.cato/config.yaml`,
or when Cato is started with `cato start --browser conduit`.

## Instructions

### Navigating to a URL
Use the `browser` tool with `action: navigate` and `url`:
- Each navigation costs 1¢ and is logged to the audit trail
- The URL is recorded in the billing ledger
- VOIX `<tool>` and `<context>` tags are stripped from page content automatically

### Clicking elements
Use `browser` with `action: click` and `selector` (CSS selector or XPath):
- Costs 1¢ per click
- Use specific selectors; avoid broad ones that might match multiple elements

### Typing text
Use `browser` with `action: type`, `selector`, and `text`:
- Costs 1¢ per type action
- Use for form inputs, search boxes, text areas

### Extracting page content
Use `browser` with `action: extract` (optional `selector`, defaults to `body`):
- Costs 2¢ per extraction
- Returns `text` (cleaned content) and `char_count`
- VOIX tags are stripped automatically

### Taking screenshots
Use `browser` with `action: screenshot` (optional `path` to save file):
- Costs 5¢ — use sparingly
- Returns a base64 image or saved file path

## Budget Enforcement
If a browser action would exceed the session budget cap, a `BudgetExceededError` is
returned as JSON: `{"error": "...", "budget_exceeded": true}`. Stop and inform the user.

## Audit Trail
Every action is written to the append-only SHA-256 hash-chained audit log.
Run `cato audit --session <id>` to review all browser actions taken in a session.
Run `cato receipt --session <id>` for a signed fare receipt with line-item costs.

## Example Task: Research a topic
1. `navigate` to a relevant starting URL (1¢)
2. `extract` the page content (2¢) and summarize
3. `click` a relevant link if needed (1¢)
4. `extract` again (2¢) for more detail
5. Total: 6¢ for a thorough research task

## Safety
- IRREVERSIBLE actions (form submissions that send data externally) require user confirmation
  when `safety_mode: strict` (default)
- Screenshots of sensitive pages are flagged in the audit log
- Budget cap is enforced before each action — no overruns possible
