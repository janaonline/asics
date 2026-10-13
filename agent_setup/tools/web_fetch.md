---
name: web_fetch
kind: server
options: [max_uses, allowed_domains, blocked_domains, max_content_tokens]
defaults: {max_uses: 8}
---
Open a web page or PDF and read its text. Run by Anthropic. It can only open URLs that already
appeared in the conversation (e.g. in search results). Fetching a page is NOT proof a person
can open it; the code runs the human-accessibility test on every source afterwards.

Options: `max_uses`, `max_content_tokens` (cap on the text read from one page; keeps
cost down), and either `allowed_domains` or `blocked_domains`.
