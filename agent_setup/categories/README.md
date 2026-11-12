# Categories

One settings file per ASICS category. A city is assessed in each category: first choose the
city, then the category. There are two:

- **ULG** (Urban Local Government): its own set of questions. Each ULG question is answered
  once per city.
- **Parastatal**: each applicable question is answered separately for every parastatal in the
  city. The parastatals differ between cities; the question set and question codes are the same.

UPD, SC and DPG are **sections** inside a category's question bank. They are not categories.

Every category runs the same steps:

1. **Find sources**: the units to assess, their official websites, the Citation Sheet.
2. **Answer questions**: from the reviewed Citation Sheet only.
3. **Score**: from each Step 2 answer and its citation.

What differs is set here: the question bank, what is assessed (`unit`: `parastatal` or `ulg`),
which agent does each job in each step, the shared rules, where its city folders go, and its
scoring workbook (`scoring_code` names its files and sheets). See the main README, "Adding a
new ASICS category".
