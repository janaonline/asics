---
name: web_search
kind: server
options: [max_uses, allowed_domains, blocked_domains]
defaults: {max_uses: 8}
---
Search the web. Run by Anthropic. Every URL in the results counts as "returned by a tool", so
it may be used as a source (after it is checked).

Options in an agent's settings: `max_uses` (searches per call), and either `allowed_domains`
(only these sites and their subdomains, e.g. `[gov.in, nic.in]`; for the source finders
the code adds the agency's own official domain) or `blocked_domains` (never these sites). Not both.
