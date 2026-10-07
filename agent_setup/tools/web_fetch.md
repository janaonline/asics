---
name: web_fetch
kind: server
options: [max_uses, allowed_domains, blocked_domains]
defaults: {max_uses: 8}
---
Open a web page or PDF and read its text. Run by Anthropic. It can only open URLs that already
appeared in the conversation (e.g. in search results). Fetching a page is NOT proof a person
can open it; the human-accessibility test is separate (see check_link).

Options: `max_uses`, and either `allowed_domains` or `blocked_domains`.
