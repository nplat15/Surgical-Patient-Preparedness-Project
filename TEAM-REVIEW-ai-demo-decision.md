# Team review: should we also show the AI once in our Nov 4 demo?

> Temporary file for the team to read before we talk it through. We'll delete it once we've decided.
> **Please read it before we meet** so we can decide by Monday night (Nov 2) and rehearse on Tuesday.

## The plan as it stands

The demo stays the way it works now: rules-only, no AI calls, no cost.

- Each student signs in with their name and gets their own fictional patient. Nothing they change affects anyone else.
- They read the readiness card, switch between the pre-op nurse and anesthesiologist views, accept or decline next steps, and apply a suggested OR time.
- New "be the AI" step: students open the H&P tab and look for anything the checklist didn't flag (a new symptom, an allergy missing from the allergy list, a blood thinner the patient never stopped). That's exactly the gap our AI modules are built to catch, so it sets up why the AI matters without running it.
- The slides explain the AI design (Modules 2–4) and show the rules baseline catching 0 of the problems that only appear in the note.

The guidelines don't require the AI to run live. The rubric item is "uses the team's real AI prototype in appropriate context with examples," and the plan above covers it with the real app plus the slides.

## The open question

**Should the presenter also show the AI catching something once, on the projector?** It would make that rubric item stronger, but it's optional. Students never need a Claude account either way.

**Option 1: No, keep it rules-only.** Free and simple, and nothing can go wrong live. The results slide keeps blank AI scores (or we say "AI evaluation is our next step").

**Option 2: Yes, use April's Claude account.** After the activity, the presenter runs the AI review on showcase patient S082 using the "Run Claude review" button in `demo/preop_demo.html` opened inside claude.ai. That patient's chest pressure at rest is only in the H&P, so the rules miss it. Free, but it depends on April's account in class, and that page uses the older OR schedule rules (we'd only show the review part).

**Option 3: Yes, with an Anthropic API key.** Someone sets up a key with a small amount of credit and adds it to the Streamlit secrets, so the presenter runs the AI right in our app. One review is 3 calls. The same key could also score the AI on the 20 test cases once (about 100 calls) and fill in the results slide and the final report. The API is billed separately from a claude.ai subscription.

## Also to settle when we meet

- Who presents which slides? The speaker notes have a `[Presenter: ____]` on each slide.
- Who keeps the team passcode and resets the demo right before class?
