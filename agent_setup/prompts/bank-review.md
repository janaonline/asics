TASK: bank_review

Review the ASICS question bank rows below for problems that would make answers unreliable:
- a scoring scale in the methodology that exceeds the question's maximum score;
- an Assessment Level that does not match the question (e.g. "in practice" marked Law/Policy);
- MQ maximum scores that do not match the sum of their sub-questions;
- unclear applicability, missing methodology, or duplicate questions.
Only report concrete problems; cite the question ID.

JSON keys:
  "issues": array of objects with "question_id", "severity" ("warning" | "error"), "message"
