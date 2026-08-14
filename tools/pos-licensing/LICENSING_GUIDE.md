# Licensing your POS software: the legal side

This is a practical orientation for a small software vendor, not legal
advice — before you sell the first license, have an attorney (ideally one
who does software/IP work; Illinois bar referral: isba.org) review your
agreement. Expect a few hundred to a couple thousand dollars for a review
of a template like the one in this folder. It's the cheapest insurance
you'll ever buy on this product.

## 1. What you're actually selling

You are **not selling the software** — you're selling a *license*: a
limited, revocable permission to use it. You keep ownership of the code
(copyright attaches automatically the moment you write it). This framing is
the legal foundation for everything else: because use is permitted only on
your terms, using it outside those terms (a second location, a shared key)
isn't just a billing dispute — it's use without permission, which is
copyright infringement plus breach of contract.

The document that does this is a **software license agreement** (called an
EULA when it's presented to the end user at install time). For a POS sold
to businesses, one document can serve as both.

## 2. The clauses that matter, and why

`EULA_TEMPLATE.md` in this folder implements all of these; here's what each
one is doing for you:

- **License grant** — the heart of the deal. Non-exclusive, non-transferable,
  and scoped: *one location, one activated terminal per paid seat*. Scope is
  what makes "they installed it at their second store" a violation instead
  of an argument.
- **Restrictions** — no copying (beyond backup), no sharing the license key,
  no sublicensing/renting, no reverse engineering or circumventing the
  license mechanism. The anti-circumvention clause pairs with federal law
  (DMCA §1201 makes circumventing a technical protection measure its own
  violation, separate from infringement).
- **Activation and verification consent** — the clause most homegrown
  agreements miss, and the one this codebase depends on. The customer
  agrees that the software activates against your server, periodically
  re-verifies, sends a hashed machine identifier for that purpose, and
  **that you may remotely deactivate the license** on breach or non-payment.
  Without this disclosed and agreed to, a remote kill switch can expose *you*
  to claims (interference with their business, computer-tampering theories).
  With it, you're exercising a contract right the customer signed up to.
- **Fees and additional seats** — each location/terminal needs its own paid
  license; using one key beyond its seat count is a material breach.
- **Term and termination** — you may terminate (and deactivate) on breach,
  with a short cure period for non-payment. Say explicitly what survives:
  their data is theirs and remains exportable; your software stops working.
- **Data ownership** — sales records belong to the customer. This costs you
  nothing and defuses the ugliest possible headline about your kill switch.
- **Warranty disclaimer & limitation of liability** — the software is
  provided "as is" and your total liability is capped (typically at fees
  paid in the last 12 months). A POS outage during a rush will generate a
  "you cost me thousands" claim someday; this clause is why it doesn't
  become a lawsuit that outweighs the license fee a hundredfold.
- **Governing law / venue** — your home state (Illinois), your county's
  courts, so a dispute happens on your turf.

## 3. Making it binding

A contract needs assent. For software, courts have consistently enforced
**clickwrap**: the terms are presented and the user must take an affirmative
step (tick "I agree") before the software activates. Browsewrap ("by using
this software you agree…") is much shakier. So:

1. Show the EULA at activation with a checkbox that is **unticked by
   default**; the Activate button stays disabled until it's ticked.
2. **Record the acceptance.** The license server in this folder refuses
   activation without `eula_accepted: true` and stores the EULA version,
   timestamp, license key and machine with the activation record — that
   database row is your evidence of who agreed to what, when.
3. When you change the EULA, bump the version string in the app so
   re-acceptance is captured on the next activation.
4. **Belt and suspenders for B2B:** also get a signature (paper or
   DocuSign) on a one-page order form at the time of sale — "N licenses at
   location X, priced Y, governed by the attached license agreement." A
   signed order plus recorded clickwrap is about as solid as it gets.

## 4. Strengthening your position (cheap, worth doing)

- **Register the copyright** (copyright.gov, ~$65). Registration before
  infringement (or within 3 months of first publication) unlocks statutory
  damages ($750–$30,000 per work, up to $150k if willful) and attorney's
  fees — which usually means a demand letter gets taken seriously and you
  never see a courtroom. Unregistered, you can only chase actual damages, so
  register early, and re-register on major versions.
- **Trademark** your product name (optional, later): stops a bad actor from
  reselling a cracked copy under your name.
- **Keep the private signing key private.** Legally it changes nothing, but
  practically it's what makes "they just copied the install folder to the
  second till" fail — see the README for the mechanics.

## 5. When you find a violation

The scenario you asked about — a legitimate customer running your software
at a second location they never paid for:

1. **Confirm it from your own records.** The license server's activation log
   (machines, hostnames, last-seen times) is your evidence; a seat-limit
   rejection from a machine you've never seen is usually how you'll find out.
2. **Start friendly.** Most of the time it's genuinely an oversight, and a
   "looks like the second store needs its own license — here's the invoice"
   email converts a violation into revenue and keeps the relationship. This
   resolves the overwhelming majority of cases.
3. **Escalate in writing.** If they blow it off: a letter citing the
   specific clauses breached (license grant, seat limits), a deadline, and
   the consequence — termination and deactivation per the agreement they
   accepted. An attorney's letterhead at this stage is a few hundred
   dollars and remarkably effective.
4. **Then, and only then, pull the license** (`pos-license revoke`, reason
   string included — it's shown on their locked screen). Because the
   agreement discloses remote deactivation and their data stays exportable,
   you're on solid ground. Deactivating *without* the paper trail above is
   how vendors end up as defendants, so resist the urge to lead with the
   kill switch.
5. **True piracy** (cracked copies, someone reselling your software):
   that's your attorney and a DMCA/infringement claim, where the copyright
   registration from §4 pays for itself.

## 6. The one-page checklist

- [ ] EULA reviewed by an attorney, version-stamped ("1.0")
- [ ] Clickwrap at activation: unticked box, disabled button, acceptance
      recorded server-side (the code here does this)
- [ ] Signed order form for each B2B sale
- [ ] Copyright registered before first sale
- [ ] Signing key backed up offline; server behind TLS
- [ ] Per-location pricing on the order form matches the license grant
- [ ] Violation playbook: confirm → invoice → letter → revoke, in that order
