"""
Lock-out insurance (27 Oct 2026, pilot readiness F3 c). When nobody can sign in as an admin, someone
signed in to Render runs, in the service's Shell tab:

    python backend/recover_admin.py you@example.com

It makes that login an enabled admin (creating it if missing), clears its two-step sign-in, signs it
out everywhere and prints a single-use link to choose a password. Nothing is sent by email. The run is
recorded in the activity log as "recovery command". It replaces the admin token as the way back in.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(argv):
    if len(argv) != 2:
        print("Usage: python backend/recover_admin.py you@example.com")
        return 2
    import db
    import users
    db.init_users_db()
    url, err = users.recover_admin(argv[1])
    if err:
        print("Not done: " + err)
        return 1
    print("Done. Open this link in a browser to choose a password (it works once):")
    print(url)
    print("Then set up two-step sign-in. This run is in Users > Activity.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
