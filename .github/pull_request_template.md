<!-- Title: <type>(<area>): TICKET-NNN <what changed, in plain words>. Only this PR's own ticket key, here and in its commits. -->

## TICKET-NNN: <what changed>

<!-- Stacked on #n?  Say so on the first line. -->

### Gate (copied from the ticket)

- [ ] 1.
- [ ] 2.
- [ ] 3.

### RED, then GREEN

<!-- The RED test commit's failing lines, then the passing run. -->

```
RED:
GREEN (make test, last line):
```

### Screenshots

<!-- Drag images in here. Never commit them or push them to a branch. Synthetic or demo accounts only. -->

### Checklist

- [ ] Branch and title carry the ticket id; only this ticket's key appears in the title and commits
- [ ] RED test commit first, fix second
- [ ] `main` merged in; `make test` last line pasted above
- [ ] Hand-calculated fixture for any figure that changed
- [ ] Touches definitions, consent, never-use words or an engine read? Then "pending research seat"
- [ ] **No trader data** in code, tests, fixtures, commits, screenshots or this description (README rule 1)
- [ ] Reviewer (not the author):
- [ ] After merge: PR on the ticket; deploy or data fix noted; Done only when the gate is true on the product

<!-- The full practice: CONTRIBUTING.md, and the Project document it links. -->
