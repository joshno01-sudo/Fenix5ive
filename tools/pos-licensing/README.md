# POS Licensing — one paid seat, one running copy

License keys, an activation server, and a remote kill switch for the Fenix
point-of-sale software. Plain Python 3.10+, standard library only — the same
zero-dependency rule as the other tools in this repo.

**The two documents that go with this code:**

- [`LICENSING_GUIDE.md`](LICENSING_GUIDE.md) — the legal side: what goes in a
  software license agreement, how to make it enforceable, and how the
  contract and this code back each other up.
- [`EULA_TEMPLATE.md`](EULA_TEMPLATE.md) — a fill-in-the-blanks single-location
  license agreement to take to an attorney.

## How it works

```
┌─────────────┐  activate / heartbeat   ┌────────────────┐
│   the POS    │ ──────────────────────▶ │ license server │  you run this
│ (customer's  │ ◀────────────────────── │  + SQLite DB   │  (any small VPS)
│  machine)    │   signed token (72 h)   └────────────────┘
└─────────────┘                                  ▲
   verifies tokens offline with the       pos-license CLI
   embedded public key                    issue / revoke / release
```

1. **You issue a key** (`pos-license issue`) and give it to the customer:
   `FNX5-69XG9-DSM8W-91H2T-3NTJH`. The key itself grants nothing — it's a
   handle the server resolves to a customer record and a seat count.
2. **The POS activates.** After the customer accepts the EULA (a real
   checkbox — acceptance and EULA version are recorded server-side as your
   evidence of assent), the app sends the key plus a hashed machine
   fingerprint. If a seat is free, the server binds it to that machine and
   returns an Ed25519-signed token good for 72 hours.
3. **One seat means one machine.** A second machine activating with the same
   key gets `409 seat_limit` and a message saying which machine holds the
   seat. That's the whole "shared key at a second location" scenario, dead
   on arrival.
4. **The app re-verifies quietly.** On startup and a few times a day it
   exchanges the token for a fresh one. If the internet is down the cached
   token keeps the shop trading for the rest of its 72-hour life (`GRACE`),
   then the app locks (`EXPIRED`) until a check gets through. Tokens are
   verified locally with the embedded public key — forging one requires the
   private key, which never leaves your server.
5. **You can pull a license at any time.** `pos-license revoke` flips one row
   in the database; the app locks at its next heartbeat — within about a day
   for an online machine, and no later than the end of the 72-hour token for
   one that's been unplugged from the network. `reinstate` undoes it,
   `release` frees the seat for a legitimate machine swap.

Honest scope note: like every licensing system ever shipped, the client-side
check can be defeated by someone determined enough with a debugger. The goal
is that *casual* copying fails immediately and visibly, you get a working
kill switch, and the license agreement is the backstop for the determined
case — see the guide.

## Vendor setup (once)

```bash
cd tools/pos-licensing
pip install .

pos-license init                 # keypair + database in ~/.fenix-license-server
pos-license serve --port 8722    # run it behind nginx/Caddy for TLS
```

`init` prints the **public key** — paste that hex string into the POS build.
The `signing.key` file is the crown jewels: anyone holding it can mint valid
tokens, so back it up and keep it off customer machines.

Run the server anywhere that's reachable over HTTPS — a $5 VPS is plenty,
traffic is a handful of tiny requests per customer per day. Put a reverse
proxy in front for TLS; the server itself speaks plain HTTP on localhost.

## Day-to-day

```bash
pos-license issue --customer "Cottage Hills Vinyl" --email owner@example.com
pos-license list                          # every license, seats, last seen
pos-license show FNX5-69XG9-...           # one license in detail
pos-license revoke 69XG9 --reason "second location unpaid"
pos-license reinstate 69XG9               # they paid — turn it back on
pos-license release 69XG9                 # free the seat (dead PC, upgrade)
```

Selling a second location is just `issue`-ing a second key — or one key with
`--seats 2` if you'd rather they manage one key across two tills.

## Integrating into the POS

```python
from pos_licensing.client import LicenseClient, ActivationError

lic = LicenseClient(
    server_url="https://license.yourdomain.com",
    public_key_hex="9a96ad1b…",        # from `pos-license init`
    state_dir=APP_DATA_DIR,
    eula_version="1.0",                 # bump when the EULA text changes
)

# Activation screen — only after the user ticks "I agree":
try:
    lic.activate(entered_key, eula_accepted=agree_checkbox.checked)
except ActivationError as exc:
    show_error(str(exc))                # "all seats in use (active on: TILL-1)"

# Startup + a timer a few times a day:
status = lic.check()
if not status.usable:
    lock_the_app(status.message)
```

What "lock" means is your product decision. A POS holds the customer's own
business data, so the friendly-but-firm pattern is: block new sales, keep
existing data readable/exportable, show the reason and your phone number.
Locking their data hostage makes enemies (and, depending on the situation,
legal trouble); locking your *software's function* is exactly what the
agreement provides for.

`check()` returns one of: `ACTIVE`, `GRACE` (offline, still fine), 
`NOT_ACTIVATED`, `EXPIRED` (offline too long — locked), `REVOKED` (you
pulled it — locked, with your reason as the message). `status.usable` is
the one-word answer.

There's also `lic.deactivate()` — put it behind a "move my license to
another computer" button so customers can do clean machine swaps without
calling you.

## Tests

```bash
pip install -e .[dev]
python -m pytest
```

Twelve tests cover the crypto roundtrip, key checksums, and the full
lifecycle end-to-end against a real server: single-seat enforcement, EULA
recording, revoke/reinstate, vendor seat release, offline grace and expiry,
and copied-state / tampered-token rejection.
