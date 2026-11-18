# UAT smoke — the fixed pass every train gets

*Fifteen minutes, on staging, after `deploy/refresh-staging.sh` and before the train's own
tickets. Run it twice: once on a phone, once on a laptop. Every line is a sentence that is
true or false. One false line is a Fail: write it up as a raw note (the tester's page in
the feedback-loop repo, `onboarding/tester.md`, step 5) and record the device result on the
train page.*

**Files.** Use the team's own Dhan export and its charges file, never a trader's. If none is
to hand, `data/fixtures/dhan_tradebook_sample.csv` (made up, real format) does for the
tradebook. Everything uploaded here is deleted in line 12, so staging does not grow with
tests.

**Ids.** A fresh login id per device per train, e.g. `uat1114p` (phone) and `uat1114l`
(laptop). Never an id on the admin list; you can't sign up with one.

Open **https://staging.scope.plusev.in**. The browser asks for the staging password first
(founder's password manager). Then:

| # | Do | True when you see |
|---|---|---|
| 1 | Sign up: `/signup`, the fresh id, any password, **Create account** | The page headed **Before you upload** ("Your data") |
| 2 | Consent: read to the end, **Agree and continue** | **Upload your tradebook**, with "Works with: Dhan and Groww (more coming)" |
| 3 | **Try it with a demo file** | A report opens with **Open your report**, and no error page |
| 4 | Home, then **Open your report**, then each chapter in turn | Four chapters open, headed **Where your results came from**, **Your patterns**, **Your behaviour**, **What we read**; every figure has words beside it |
| 5 | Journal | **Your Journals** opens, and one journal opens from it |
| 6 | **What we read** (chapter 4) | It lists what was read from the file: rows read and rows set aside |
| 7 | Account: `/account` | **Your account**, with **Your uploads** listing the demo |
| 8 | **Upload new trades**, choose the Dhan export, answer when you downloaded it | The review page **What we read**, with **Rows we could read** and **Trades rebuilt** above zero |
| 9 | **Add charges**, choose the charges file | The charges page accepts it, and home shows a result after charges |
| 10 | `/account`, **Read this file again** on the upload | It reads again without asking for a file. Where code changed, the page says "This is the same file, read with newer code" |
| 11 | `/admin` signed in as an admin id (yours, in a second browser or a private window) | The admin page, with **Running deploy:** showing the version `refresh-staging.sh` printed |
| 11b | `/admin` signed in as the fresh id | **Not found**: "There is nothing at this address." (404, not a "forbidden" page) |
| 12 | `/account`, **Delete everything**, tick "I have read this and I want everything deleted.", **Delete everything** | **Deleted**, saying your file, trades, Journals and account are gone. Signing in again with the fresh id fails |
| 13 | Sign out in the admin browser | The signed-out front page; `/account` there no longer shows your account |

**Pass** = all thirteen true on both devices. Write it on the train page:
`Phone (model, browser): Pass` and `Laptop (OS, browser): Pass`, with your name.

The phone pass is not the laptop pass made smaller: tap every button with a thumb, and
look for anything cut off at the right edge. That is where Scope has broken before.
