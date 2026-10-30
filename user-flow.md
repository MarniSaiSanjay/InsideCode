# One Complete Example: Finding the Logout Code

This uses real Flask tutorial source. IDs below are illustrative.

## 1. What is inside the uploaded ZIP?

The user uploads the Flask repository. One file is:

**`examples/tutorial/flaskr/auth.py`, lines 112-116:**

```python
@bp.route("/logout")
def logout():
    """Clear the current session, including the stored user id."""
    session.clear()
    return redirect(url_for("index"))
```

We will follow **this same function** through every step below.

## 2. What does parsing do?

Our Python backend reads that file. Python's `ast` parser identifies:

```text
This is a function.
Its name is logout.
It starts at line 112 (its decorator) and ends at line 116.
```

**Parsing finds structure and positions. It does not execute the function or ask
AI what the function means.**

## 3. What does indexing do?

Our code saves a searchable record in local SQLite:

| Field | Saved value |
|---|---|
| Record ID | C1 |
| File | examples/tutorial/flaskr/auth.py |
| Function | logout |
| Start/end lines | 112 / 116 |
| Code | Exact function text shown in step 1 |

SQLite's full-text index lets words point back to matching records:

```text
"logout"  -> C1
"session" -> C1
"clear"   -> C1
```

These are real words in the function, not an AI-generated description. SQLite
builds the lookup automatically from the text we give it.

**Think of indexing as saving both the code and a fast way to find it by words.**
We do this once after upload, not for every question.

## 4. The user asks a question

**User:** "Where is logout implemented?"

```text
Our search extracts the useful word: logout
The local index finds:              logout -> C1
Our backend loads C1:               file, function, code, and lines
```

In a repository with more matches, symbol and keyword ranking choose the most
relevant records. This simple question already matches the function name; no AI
is needed to find it.

## 5. What does the user see?

An evidence card:

```text
File:     examples/tutorial/flaskr/auth.py
Function: logout
Lines:    112-116
Why:      Exact function-name match
Code:     The actual five lines shown in step 1
```

The card displays the source code, not just its name. Clicking it opens the
saved file with those lines highlighted.

## 6. Where does AI come in?

With the user's consent, send AI:

```text
Question: Where is logout implemented?
Evidence E1: The actual function code from C1.
```

Expected explanation, **not a recorded model response**:

> Start with `logout` in `examples/tutorial/flaskr/auth.py`. It clears the session
> and redirects to the `index` endpoint. [E1]

Our backend checks that `E1` references the supplied source and creates its
clickable path/line link. AI does not invent the location. Valid references alone
do not guarantee every claim is correct; claims must reflect the shown code.

If AI fails, the code result from step 5 still works. If no useful code is found,
say so instead of guessing. Optional AI search-term expansion is a separate
enhancement for harder wording; it is not needed to understand this example.

**In one line: source code -> parse its structure -> index its words -> find a
match -> show the real code -> explain that code with AI.**

### Real source

Checked at commit `49943b5a94413a530761350f04e896f76e8d620e`.
Short excerpt: Copyright 2010 Pallets, BSD-3-Clause.

```text
https://github.com/pallets/flask/blob/49943b5a94413a530761350f04e896f76e8d620e/examples/tutorial/flaskr/auth.py
https://github.com/pallets/flask/blob/49943b5a94413a530761350f04e896f76e8d620e/LICENSE.txt
```
