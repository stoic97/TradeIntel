# Why an outside FIFO count differs from Scope's (TICKET-788)

A trader or reviewer pairing the same tradebook independently will usually get a different trade count from Scope. This page lists every source of that difference. Figures for a real file stay out of this repo (README rule 1).

Scope states one count: **trades, as the record reads them**. Every screen uses it, including the upload receipt. A trade is one position.

| Difference | Reason | Money moved | Outcome |
|---|---|---|---|
| **One trip per lot, or per closing fill** | An outside FIFO often emits one round trip each time a closing fill meets an opening lot. Scope emits one per closing fill, however many lots it closes (`reconstruct.py`). A fill that closes three lots is one decision and one row in the broker's file. | None. Both units pair the same units of the same fills. | Kept. Recorded here. |
| **Trades opened with a SELL** | Sold options were refused at schema level, so their money left every total. | Yes, by their net. | Fixed in TICKET-810. |
| **Intraday pairing across days** | Plain FIFO let a lot from an earlier day take an intraday close, shifting later pairs onto other days. | Totals, none. Day figures, yes. | Fixed in TICKET-789. |
| **Spread legs** | A long leg and a short leg opened together are one position, so two rows are one trade (Annex H draft 2). | None. A position's money is the sum of its legs. | Fixed in TICKET-810. The receipt follows in TICKET-788. |
| **Holdings** | A trade held past the day stays in the count and the total. The report splits same-day from held on the pages that read same-day trades only. | None. The two parts sum to the total. | Fixed in TICKET-791. |

To compare with an outside FIFO, count per closing fill rather than per lot, then count linked legs once. The total must then match to the paisa. Trade Value is the broker's own figure, so a total worked from quoted price times quantity can differ by a few rupees.
