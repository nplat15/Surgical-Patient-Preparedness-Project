# Team review: how do we show the AI in our Nov 4 demo?

> Temporary file for the team to read before we talk it through. We'll delete it once we've decided.
> **Please read it before we meet** so we can decide by Monday night (Nov 2) and rehearse on Tuesday.

## The situation

- The class app works for everyone at once, and each student gets their own patient. But **we have no API key set up**, so students only get the rules-only check. If someone turns on "AI review", the app says "No API key found".
- The slides currently assume students run the AI themselves (activity step 3 and discussion question 1). Those need to change.
- The rubric gives 2 points for "uses the team's real AI prototype in appropriate context with examples," and our results slide still has blank AI scores because we haven't run the AI evaluation yet.

## Who pays for the AI

Not everyone has Claude, which is why we built the Streamlit app. **Students never need a Claude account in any option below.** Any AI use runs on April's account: in A, her claude.ai plan; in B, an API key she (or someone else) pays for. The API is billed separately from a claude.ai subscription. So the less AI we run live, the less it depends on one person.

## Options

**A. Students use rules only; the presenter shows the AI once using April's Claude account (no cost)**
- Students get a "be the AI" task: open the H&P tab and find anything the checklist missed (new symptoms, a blood thinner the patient didn't stop, and so on).
- Then the presenter runs the AI review on our showcase patient S082 on the projector, using the "Run Claude review" button in `demo/preop_demo.html` opened inside claude.ai.
- Downside: it depends on April's account in class, and that demo page still uses the old OR schedule rules.

**B. Same as A, but the presenter runs the AI in our Streamlit app with an Anthropic API key**
- Someone sets up an Anthropic API account with a small amount of credit and adds the key to the Streamlit Cloud secrets.
- One review is 3 API calls. With the same key we can also score the AI on the 20 test cases once (about 100 calls) and fill in the results slide.
- Downside: someone has to set up billing.

**C. No live AI; the demo is rules only, and we explain the AI with slides**
- Free and simple.
- Downside: weakest for the rubric, and the results slide stays empty.

**D. Every student runs the AI themselves**
- Needs a key and a budget for many calls at once, with a risk of slowdowns or rate limits during class.

**Suggested approach (open to change):** A or B, leaning B if someone can set up a key, because it also gives us AI scores for the results slide and the final report.

## Also needs owners

- Who presents which slides? The speaker notes have a `[Presenter: ____]` on each slide.
- Who keeps the team passcode and resets the demo right before class?
