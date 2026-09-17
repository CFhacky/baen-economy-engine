# TypeScript tick (browser / Node)

Port of Merchant-15 / Administration-16 preview math. HMAC 3d6 matches
`operator_dice._die` in the Python engine (verified against a Python 3.11 fixture).

This folder is the algorithm. Bind it to a census JSON in the consuming app,
or call the Python HTTP API instead:

`POST /v1/preview` with `{ "kind": "food"|"registry"|"business", "seed": "..." }`.
