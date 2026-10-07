---
name: check_link
kind: client
options: []
---
Run the human-accessibility test on one exact URL that a search or fetch returned in this
task: open it the way a person's browser would, and report whether it shows real, readable
content (not an error, login, captcha, metadata-only or data page). Returns the verdict, the
reasons and the start of the readable text.

Use it before listing a source, so you only propose links a person can open. Never pass a URL
you constructed or remembered; those are refused.
