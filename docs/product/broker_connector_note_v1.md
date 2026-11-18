# The first read-only broker connector: what the APIs expose, and what to build next

TICKET-901. Status: **started, not delivered**. This is the written note the ticket names as its deliverable when the connector itself cannot be built this week.

Written 13 November 2026 from the brokers' public API documentation (links at the end). Nothing here was tested against a live account. Every claim below is about what the documentation says, and a live check comes before any code that depends on it.

## Why the connector is not built yet

The ticket depends on two others that are still open:

- **Consent for a recurring pull** is still to do. The ticket says plainly: do not pull a trader's trades under a consent that never mentioned pulling. The consent text in force covers an uploaded file for a diagnosis, not a stored credential or a repeated fetch.
- **The Groww tradebook adapter** is still to do. The ticket wanted it first, so that Groww's field names, quantity convention and charges would be learnt from a file before risking them through an API.

A connector built ahead of the consent could not be switched on, and a connector built ahead of the adapter would be learning the broker's data and its API at the same time. So this note does the part that is cheap now and expensive to get wrong later: what each API can actually give us.

## The finding that changes the plan: Groww's API cannot fetch a trade book

Groww is the broker the epic picked for the second adapter, so it was the natural first connector. Its trading API does not do what §7.8 needs.

| What §7.8 needs | Groww Trade API (documented) |
|---|---|
| Past trades over a date range | **Not offered.** `get_order_list` returns orders *placed during the day*; nothing takes a date range. `get_trade_list_for_order` needs an order id we would only have from that day's list. |
| A credential that cannot trade | **Not offered.** No read-only key, scope or permission is documented. The same token that reads orders places, modifies and cancels them. |
| Charges per trade | Not in the trade list fields. |
| Cost to the trader | Needs an active paid Trading API subscription. |

A connector that can only see today's orders would have to poll every trading day without missing one, from the day he connects. It could never read the months before he connected. That is the scheduled background pull the ticket puts out of scope. It also brings back the bias §7.8 exists to remove: any day the pull fails is a missing day, and nothing guarantees missing days are random.

**Conclusion: Groww cannot be the first connector.** Its CSV adapter stays worth building on its own.

## Dhan's API does expose a trade book

Dhan is the broker Scope already reads by file.

| What §7.8 needs | DhanHQ API v2 (documented) |
|---|---|
| Past trades over a date range | **Offered.** `GET /v2/trades/{from-date}/{to-date}/{page}` returns trade history for a date range, paginated from page 0. How far back it reaches is not documented, so that has to be measured. |
| Fields | Order and exchange trade ids, side, segment, product, symbol, security id, quantity, price, order and exchange timestamps; for F&O expiry, option type and strike. |
| Charges per trade | **Offered**: brokerage, STT, SEBI fee, exchange transaction charge, stamp duty and service tax, each separately. The uploaded CSV often has no charges column, so the API would carry more than the file does. |
| Ledger | `GET /v2/ledger?from-date&to-date`, a separate statement of money in and out. Not needed for trips. |
| Cost to the trader | Trading APIs are free to Dhan users. Only the market Data APIs are paid, and the trade book does not need them. |

### The auth flow

Dhan documents three ways to get an access token:

1. **Token pasted from Dhan Web**: valid 24 hours. It can be renewed while it is still alive, but not once it has expired.
2. **API key and secret (individual)**: three steps. Generate Consent with key and secret gives a `consentAppId`. The trader logs in at Dhan in a browser and does 2FA, and is redirected back with a `tokenId`. Consume Consent with the `tokenId` gives the access token. Key and secret last 12 months.
3. **Partner**: the same three steps with a `partner_id` and `partner_secret`. The login can run inside our own page or a mobile webview. This is the flow a product would use, and it needs a partner agreement with Dhan.

The access token's lifetime under flows 2 and 3 is returned as `expiryTime`, not documented as a fixed figure. Treat it as about a day until measured.

### Read-only: what we can and cannot prove

Gate 2 asks for read-only *proven, not assumed*. With Dhan, **no read-only token exists in the documentation**: any valid token is accepted by every endpoint.

What does exist is the exchange rule Dhan enforces. Order placement, modification and cancellation are accepted only from a static IP the account holder registered, at most two per account, unique to that account and locked for 7 days once set. Reading trades and orders needs no registered IP. So a token held on Scope's servers can place an order only if the trader registered Scope's server address as his own trading IP.

That is a real control, but it is a property of the trader's account, not of the token. We cannot claim more than this:

> The credential Scope holds can read your trades. It cannot place, change or cancel an order unless you register Scope's server address as your trading IP with Dhan, which nothing in Scope asks you to do.

The proof the ticket asks for would be a test against a sandbox or a consenting live account. It sends an order, a modify and a cancel with the held token from Scope's server and records each rejection. That test needs an account and cannot be written from documentation.

## The token lifecycle, as it would work

| Question (gate 4) | Proposal |
|---|---|
| Where it is stored | One row per trader in its own table, encrypted at rest with the Fernet file key Scope already uses for uploaded files (`SCOPE_FILE_KEY`). Never logged. Never in a cookie. |
| How it refreshes | It mostly can't. Dhan renews a live web token by 24 hours, but an expired one needs the trader to log in again. A connector that only pulls when the trader opens Scope sidesteps this: he logs in at Dhan, we fetch, and the token can be discarded after the pull. Storing nothing is the strongest answer to gate 6. |
| What he sees when it has expired | "Your Dhan connection has ended. Reconnect to fetch your latest trades." His report from earlier pulls stays exactly as it was. Never a broken page or a 500. |

## How each gate would be met

1. **End to end:** connect, then fetch `/v2/trades` for the trader's chosen range, page by page. Write the rows in the shape of the Dhan CSV the adapter already reads, and pass them through the existing import pipeline, so there is one parser and no second path into trips.
2. **Read-only:** the claim above, plus the order/modify/cancel rejection test against a consenting account. Write in the PR exactly what was sent and what came back.
3. **Fetched equals uploaded:** for one month, upload the CSV and fetch the same month by API. Compare trips and every figure. Any difference is a finding and stops the ticket. The likeliest differences are charges (the API has them, the file often does not) and timestamps (order time against exchange time).
4. **Lifecycle:** as in the table above.
5. **Disconnect in one action:** delete the token row. Imports already made stay, because they are ordinary imports.
6. **Deletion:** the token row joins what `/delete` removes, so "two rows survive and nothing else" stays true. Because the table holds a `trader_id`, `test_every_table_holding_a_traders_rows_is_reached_by_deletion` fails until deletion names it.
7. **`supply_bias`:** a month that came by upload while a connection existed is flagged for any pooled read and left unflagged in his own figures. A month fetched by connection is not flagged.

## What I would do next, in order

1. **Get the consent text for a recurring pull written.** It has to name a stored credential, a repeated fetch and the right to disconnect. Nothing below can be switched on without it.
2. **Measure the two things the docs leave open**, on a consenting Dhan account, by hand, with no code merged: how far back `/v2/trades` reaches, and how long a key-flow token lives. If history is short, the "connect once and read his past" design fails, and the note needs a new section before any code.
3. **Run the order/modify/cancel rejection test** on that account, and write down what came back.
4. **Ask Dhan about partner access.** The individual key flow makes each trader create his own API key, which is too much to ask of him. The partner flow is the one that fits a product.
5. **Then build gate 1 and gate 3 together.** A fetched month that is not compared against an uploaded month in the same PR proves nothing.
6. **Leave Groww's connector until Groww offers trade history.** Check their changelog when the Groww CSV adapter lands.

## Sources

- Groww Trade API, Python SDK: introduction, auth and rate limits. https://groww.in/trade-api/docs/python-sdk
- Groww Trade API, orders. https://groww.in/trade-api/docs/python-sdk/orders
- DhanHQ API v2, statements (trade history, ledger). https://dhanhq.co/docs/v2/statements/
- DhanHQ API v2, authentication (tokens, consent flow, static IP). https://dhanhq.co/docs/v2/authentication/

All four pages were read on 13 November 2026. APIs change: check them again before building.
