# benethos-hub

Open-source projects in AI, agents and software architecture. The tools here connect AI clients to real systems such as mailboxes, accounting software and market data. They are built for production use, with clear permissions and predictable behaviour.

## Projects

### <img src="https://raw.githubusercontent.com/benethos-hub/mailbox/main/assets/brand/icon.svg" alt="" height="28" align="absmiddle"> [mailbox](https://github.com/benethos-hub/mailbox)

Self-hosted REST API and web UI for all your mailboxes, whether IMAP, JMAP, POP3, Gmail, Microsoft 365 or Outlook.com. Scripts, AI assistants and small AI agents work with your mail through this one service, each within the accounts, rights, folders and send limits its token grants. Change feed, signed webhooks and an audit included. Five packages:

- [mailbox-service](https://github.com/benethos-hub/mailbox/tree/main/packages/mailbox-service#readme): the REST API and web UI that hold the connections to all accounts.
- [mailbox-agents](https://github.com/benethos-hub/mailbox/tree/main/packages/mailbox-agents#readme): small agents that work on a mailbox continuously, one narrow question and one reversible action each.
- [mailbox-mcp](https://github.com/benethos-hub/mailbox/tree/main/packages/mailbox-mcp#readme): the MCP server that opens your mailboxes to Claude and other AI assistants.
- [mailbox-client](https://github.com/benethos-hub/mailbox/tree/main/packages/mailbox-client#readme): the Python client of the REST API, async and sync.
- [mailbox-common](https://github.com/benethos-hub/mailbox/tree/main/packages/mailbox-common#readme): what the service, the MCP server and the agents share.

### <img src="https://raw.githubusercontent.com/benethos-hub/lexware-office-mcp/main/assets/brand/icon.svg" alt="" height="28" align="absmiddle"> [lexware-office-mcp](https://github.com/benethos-hub/lexware-office-mcp)

Unofficial MCP server for the Lexware Office accounting API. Gives AI clients access to contacts, vouchers and invoices. No tool is active until you enable it.

### <img src="https://raw.githubusercontent.com/benethos-hub/yahoo-finance-mcp/main/assets/brand/icon.svg" alt="" height="28" align="absmiddle"> [yahoo-finance-mcp](https://github.com/benethos-hub/yahoo-finance-mcp)

Unofficial MCP server for Yahoo Finance data via yfinance. Read-only, with prices, key figures, analyst estimates and stock screening.

### <img src="https://raw.githubusercontent.com/benethos-hub/agent-skills/main/assets/brand/icon.svg" alt="" height="28" align="absmiddle"> [agent-skills](https://github.com/benethos-hub/agent-skills)

Skills for AI agents, written to the open Agent Skills standard and ordered by category. Where a skill needs live data, it works together with an MCP server such as the ones above.

## Contributing

Issues and pull requests are welcome. For larger changes, please open an issue first so we can agree on the approach.

---

[![Maintainer](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/maintainer.svg)](https://github.com/BeneODev)
[![Sponsor](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/sponsor.svg)](https://github.com/sponsors/BeneODev)
[![PayPal](https://raw.githubusercontent.com/benethos-hub/.github/main/profile/badges/paypal.svg)](https://paypal.me/BeneODev)
