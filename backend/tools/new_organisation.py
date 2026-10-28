"""
A new organisation's deployment, prepared on a laptop (28 Oct 2026, pilot readiness phase 3, F3 a).

    python backend/tools/new_organisation.py acme "Acme Rail" you@wayscope.co.uk

writes two files into C:/Users/.../Wayscope/pilots/acme/ (a folder OUTSIDE the git checkout; refused inside one):

  acme-render-environment.txt   the settings to paste into Render's "Add from .env", with a FRESH GATE_SECRET and
                                MAP_PASSWORD made here (never copied from the demo)
  acme-steps.txt                the numbered click path with this organisation's names filled in: Render database
                                and web service in Frankfurt, the settings, the Cloudflare record, the custom domain,
                                the first admin, the organisation file, the checks, and the end of the pilot

It sends nothing anywhere and changes nothing on Render or Cloudflare: creating the service and the database is a
person's click. The environment file holds two secrets: delete it once pasted (keep the map password in a
password manager; it is what the organisation's outside viewers type).
"""
import argparse
import os
import re
import secrets
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DOMAIN = "wayscope.co.uk"
REGION = "Frankfurt (EU Central)"
RELEASE_BRANCH = "pilot-release"
PYTHON_VERSION = "3.12.7"
WEB_PLAN = "Standard (1 CPU, 2 GB)"
DB_PLAN = "Basic-256mb, 15 GB storage"
BUILD = "pip install -r backend/requirements.txt"
START = "cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT"
ORG_RE = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# the map password is read aloud and typed by council officers: no 0 / o / 1 / l / i
MAP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
# settings an organisation's deployment must NOT have (deployment.problems() says the same at start-up)
NEVER = ("ADMIN_TOKEN", "PLANNER_CODE", "ADMIN_CODE", "IPT1_CODE … IPT6_CODE", "DEMO_LEADS", "ALLOW_DEMO_CODES",
         "MAP_GATE")


def map_password(rng=secrets):
    return "-".join("".join(rng.choice(MAP_ALPHABET) for _ in range(4)) for _ in range(4))


def gate_secret(rng=secrets):
    return rng.token_hex(24)


def mapbox_public_token(repo=REPO):
    """The pk. token map/config.js carries (public by design; the same one every deployment uses)."""
    try:
        with open(os.path.join(repo, "map", "config.js"), encoding="utf-8") as f:
            m = re.search(r'MAPBOX_TOKEN:\s*"(pk\.[^"]+)"', f.read())
        return m.group(1) if m else ""
    except OSError:
        return ""


def inside_git(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def names(org):
    return {"org": org, "web": f"wayscope-{org}", "db": f"wayscope-{org}-db", "host": f"{org}.{DOMAIN}",
            "url": f"https://{org}.{DOMAIN}"}


def environment(org, admin_email, admin_name, gate=None, map_pw=None, mapbox=None):
    """The lines for Render's "Add from .env". Secrets the demo already holds (HERE, email) are NOT here: the steps
    say to copy them from the demo's own Environment page, so they never pass through a file or a chat."""
    n = names(org)
    lines = [
        f"PYTHON_VERSION={PYTHON_VERSION}",
        f"TENANT_ID={org}",
        f"APP_URL={n['url']}",
        f"FIRST_ADMIN_EMAIL={admin_email}",
    ]
    if admin_name:
        lines.append(f"FIRST_ADMIN_NAME={admin_name}")
    lines += [f"GATE_SECRET={gate or gate_secret()}", f"MAP_PASSWORD={map_pw or map_password()}"]
    tok = mapbox if mapbox is not None else mapbox_public_token()
    if tok:
        lines.append(f"MAPBOX_TOKEN={tok}")
    return "\n".join(lines) + "\n"


def steps(org, display, admin_email, branch=RELEASE_BRANCH):
    n = names(org)
    never = ", ".join(NEVER)
    branch_note = (' (not main: a pilot gets a change only when you say "release to pilots")'
                   if branch == RELEASE_BRANCH else " (a REHEARSAL: not the release branch)")
    return f"""WAYSCOPE: A NEW ORGANISATION'S DEPLOYMENT: {display} ({org})
Made by backend/tools/new_organisation.py. Do the steps in order. Claude can check each one; creating things on
Render and Cloudflare is your click. Render bills web services and databases by the second.

A. THE DATABASE (Render)
 1. dashboard.render.com, workspace "My Workspace" -> New -> Postgres.
 2. Name: {n['db']}. Region: {REGION}. Plan: {DB_PLAN}. Leave the rest. Create Database.
 3. When it says Available: Info -> Connections -> copy the INTERNAL Database URL (it starts postgresql://).
    It works only from a service in the same region, which is why both are in Frankfurt.

B. THE WEB SERVICE (Render)
 4. New -> Web Service -> Git Provider -> jgd230490-RBE/Modus.
 5. Name: {n['web']}. Language: Python 3. Branch: {branch}{branch_note}.
    Region: {REGION} (the same as the database). Root Directory: leave empty.
 6. Build Command:  {BUILD}
    Start Command:  {START}
 7. Instance Type: {WEB_PLAN}.
 8. Environment Variables -> Add from .env -> paste everything in {org}-render-environment.txt.
    Then add these, copying each value from modus-web -> Environment (the eye shows it):
      HERE_API_KEY, SMTP_USER, SMTP_PASSWORD, DEMO_FROM, DEMO_REPLY_TO (if set)
    And one with the URL from step 3:  DATABASE_URL
    NEVER add: {never}.
 9. Advanced -> Health Check Path: /api/health. Auto-Deploy: On Commit. Deploy Web Service.
10. Under the service's name Render shows its address, e.g. https://{n['web']}.onrender.com (Render may add a few
    letters if the name is taken). Note it: step 13 needs the part after https://.

C. THE ADDRESS ({n['host']})
11. Render -> {n['web']} -> Settings -> Custom Domains -> Add Custom Domain -> {n['host']} -> Save.
12. dash.cloudflare.com -> {DOMAIN} -> DNS -> Records -> Add record:
      Type CNAME · Name {org} · Target <the address from step 10, without https://> · Proxy status: DNS only (grey)
    Save. Touch no other record (the Google email records must stay as they are).
13. Back on Render -> Custom Domains -> Verify. Wait until it says Certificate Issued (minutes, sometimes an hour).

D. FIRST SIGN-IN
14. Render -> {n['web']} -> Logs. Look for the lines that start "deployment:" and "first admin:".
    "deployment ✓ nothing that must be fixed" is what you want; a line with ✗ says what to change.
    "first admin: invite sent to {admin_email}" -> open that email. If it says the email is not set up, the link is
    in the log line itself: open it (it works once, for 72 hours).
15. Choose a password, set up two-step sign-in, save the 10 recovery codes.

E. THE ORGANISATION'S DATA
16. Config -> Everything -> Organisation file -> Replace from file -> the organisation's package.
17. Then, as for the demo:
      Routes -> Create route panel -> tick the organisation's vehicles -> Route all -> wait for it to finish.
      Look-ahead -> "Road closures (National Highways)" -> check now.
      Lorry limits have no button: ask Claude to run the import and the re-check from your Chrome while you are
      signed in (a new deployment starts with none).
      Config -> Map and bulletin -> Community considerations -> Fetch now; Collision history -> Fetch now.
      The carbon target, once the organisation has agreed one: Carbon planner -> Set as the scheme's carbon target.
18. Users -> invite the organisation's people (each sets up their own two-step sign-in).

F. CHECKS BEFORE HANDING OVER (Claude can run both)
19. On the laptop, in Modus:   python backend/tools/check_pilot.py {n['url']}
    Every line pass (a "note" is information).
20. Render -> {n['web']} -> Shell:   python backend/check_deployment.py
    Its last line says "nothing that must be fixed".
21. Config -> Everything -> Organisation file -> Download. Keep it with the pilot's papers (it is the client's data).
22. Delete {org}-render-environment.txt. Keep the map password in your password manager; give it to the people
    the organisation chooses (council officers, residents' groups), never in the same email as the address.

G. THE END OF THE PILOT
23. Organisation file -> Download, and give it to the client if the agreement says so.
24. Render -> {n['db']} -> Settings -> Delete Database. Render -> {n['web']} -> Settings -> Delete Web Service.
25. Cloudflare -> {DOMAIN} -> DNS -> the {org} CNAME -> Delete.
26. Write the date in the pilot's note (notes\\pilots\\{org}.md).
"""


def main(argv):
    ap = argparse.ArgumentParser(description="Prepare a new organisation's deployment (two files, nothing sent).")
    ap.add_argument("org", help="short name: lower-case letters, digits, hyphens (e.g. acme). The subdomain and TENANT_ID")
    ap.add_argument("display", help='the organisation\'s name as people read it (e.g. "Acme Rail")')
    ap.add_argument("admin_email", help="the first admin's email (the invite goes there)")
    ap.add_argument("--admin-name", default="", help="the first admin's name (default: the part before the @)")
    ap.add_argument("--out", default="", help="folder for the two files (default: Wayscope\\pilots\\<org>)")
    ap.add_argument("--branch", default=RELEASE_BRANCH,
                    help="the branch Render follows (default pilot-release; another only to rehearse)")
    a = ap.parse_args(argv[1:])
    org = a.org.strip().lower()
    if not ORG_RE.match(org):
        print("The short name must be 3-30 characters: lower-case letters, digits and hyphens, starting with a letter.")
        return 2
    if not EMAIL_RE.match(a.admin_email.strip()):
        print("The admin email does not look like an email address.")
        return 2
    out = a.out or os.path.join(os.path.dirname(REPO), "pilots", org)
    if inside_git(out):
        print(f"Not written: {out} is inside a git checkout, and the environment file holds secrets.")
        return 2
    os.makedirs(out, exist_ok=True)
    env_path = os.path.join(out, f"{org}-render-environment.txt")
    if os.path.exists(env_path):
        print(f"Not written: {env_path} exists. Delete it first if you mean to make fresh secrets.")
        return 2
    with open(env_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(environment(org, a.admin_email.strip(), a.admin_name.strip()))
    steps_path = os.path.join(out, f"{org}-steps.txt")
    with open(steps_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(steps(org, a.display.strip(), a.admin_email.strip(), branch=a.branch.strip() or RELEASE_BRANCH))
    print("Written:")
    print("  " + env_path + "   (two fresh secrets: delete it once pasted into Render)")
    print("  " + steps_path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
