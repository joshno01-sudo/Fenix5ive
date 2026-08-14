"""Vendor admin CLI.

Runs on the same box as the license server, against the same database, so
every change (revoke, release, reinstate) is live on the next heartbeat.

    pos-license init                     one-time setup: keypair + database
    pos-license serve                    run the license server
    pos-license issue --customer "..."   create and print a new key
    pos-license list                     all licenses and where they're active
    pos-license show FNX5-...            one license in detail
    pos-license revoke KEYID --reason "" kill switch: app locks at next check
    pos-license reinstate KEYID          undo a revoke
    pos-license release KEYID            free the seat(s) so the customer can
                                         activate on a replacement machine
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import keys, server
from .store import Store

DEFAULT_DATA_DIR = "~/.fenix-license-server"


def _store(args) -> Store:
    root = Path(args.data_dir).expanduser()
    db = root / server.DB_FILE
    if not db.exists():
        sys.exit(f"no license database at {db} — run `pos-license init` first")
    return Store(db)


def _resolve_key_id(store: Store, ref: str) -> str:
    """Accept either a full license key or a bare key id."""
    if keys.is_valid_format(ref):
        return keys.key_id(ref)
    ref = ref.strip().upper()
    if store.get(ref) is None:
        sys.exit(f"no license matching {ref!r}")
    return ref


def _when(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def cmd_init(args) -> None:
    root = Path(args.data_dir).expanduser()
    try:
        server.init_data_dir(root)
    except FileExistsError as exc:
        sys.exit(str(exc))
    print(f"initialized {root}")
    print(f"  signing key : {root / server.SIGNING_KEY_FILE}  (keep this secret)")
    print(f"  database    : {root / server.DB_FILE}")
    print()
    print("embed this public key in the POS build:")
    print(f"  {server.load_public_key(root).hex()}")


def cmd_serve(args) -> None:
    server.serve(Path(args.data_dir).expanduser(), host=args.host,
                 port=args.port, token_ttl=args.grace_hours * 3600)


def cmd_issue(args) -> None:
    store = _store(args)
    lic = store.issue(customer=args.customer, email=args.email,
                      seats=args.seats, note=args.note)
    print(f"issued to {lic.customer} ({lic.seats} seat"
          f"{'s' if lic.seats != 1 else ''}):")
    print(f"  {lic.license_key}")


def cmd_list(args) -> None:
    store = _store(args)
    licenses = store.list_licenses()
    if not licenses:
        print("no licenses issued yet")
        return
    for lic in licenses:
        active = store.activations(lic.key_id)
        flag = "REVOKED" if lic.revoked else f"{len(active)}/{lic.seats} seats"
        print(f"{lic.key_id}  {flag:<12}  {lic.customer}")
        for act in active:
            print(f"          on {act.hostname or act.fingerprint[:12]}"
                  f"  (last seen {_when(act.last_seen)})")


def cmd_show(args) -> None:
    store = _store(args)
    lic = store.get(_resolve_key_id(store, args.key))
    if lic is None:
        sys.exit("license not found")
    print(f"key      : {lic.license_key}")
    print(f"customer : {lic.customer}" + (f" <{lic.email}>" if lic.email else ""))
    print(f"seats    : {lic.seats}")
    print(f"issued   : {_when(lic.created_at)}")
    if lic.note:
        print(f"note     : {lic.note}")
    if lic.revoked:
        print(f"status   : REVOKED — {lic.revoke_reason or 'no reason recorded'}")
    else:
        print("status   : active")
    for act in store.activations(lic.key_id):
        print(f"seat     : {act.hostname or '?'}  fp={act.fingerprint[:12]}…"
              f"  eula={act.eula_version or '?'}"
              f"  activated {_when(act.activated_at)},"
              f" last seen {_when(act.last_seen)}")


def cmd_revoke(args) -> None:
    store = _store(args)
    kid = _resolve_key_id(store, args.key)
    store.set_revoked(kid, True, args.reason)
    print(f"{kid} revoked — the app will lock at its next license check")
    print("(within the offline grace period at the latest)")


def cmd_reinstate(args) -> None:
    store = _store(args)
    kid = _resolve_key_id(store, args.key)
    store.set_revoked(kid, False)
    print(f"{kid} reinstated")


def cmd_release(args) -> None:
    store = _store(args)
    kid = _resolve_key_id(store, args.key)
    n = store.deactivate_all(kid)
    print(f"released {n} seat{'s' if n != 1 else ''} on {kid}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="pos-license",
        description="Issue, serve and revoke Fenix POS licenses.")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR,
                        help=f"server data directory (default {DEFAULT_DATA_DIR})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the keypair and database")

    p = sub.add_parser("serve", help="run the license server")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=server.DEFAULT_PORT)
    p.add_argument("--grace-hours", type=int, default=72,
                   help="how long the POS keeps running offline (default 72)")

    p = sub.add_parser("issue", help="create a new license key")
    p.add_argument("--customer", required=True)
    p.add_argument("--email", default="")
    p.add_argument("--seats", type=int, default=1,
                   help="how many machines may activate at once (default 1)")
    p.add_argument("--note", default="")

    sub.add_parser("list", help="list all licenses")

    p = sub.add_parser("show", help="show one license in detail")
    p.add_argument("key", help="license key or key id")

    p = sub.add_parser("revoke", help="deactivate a license remotely")
    p.add_argument("key", help="license key or key id")
    p.add_argument("--reason", default="",
                   help="shown to the customer on the locked screen")

    p = sub.add_parser("reinstate", help="undo a revoke")
    p.add_argument("key", help="license key or key id")

    p = sub.add_parser("release", help="free a license's seat(s)")
    p.add_argument("key", help="license key or key id")

    args = parser.parse_args(argv)
    {
        "init": cmd_init,
        "serve": cmd_serve,
        "issue": cmd_issue,
        "list": cmd_list,
        "show": cmd_show,
        "revoke": cmd_revoke,
        "reinstate": cmd_reinstate,
        "release": cmd_release,
    }[args.command](args)


if __name__ == "__main__":
    main()
