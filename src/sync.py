"""sync.py: copy new or changed files from Drive A (source) to Drive B (dest).
 
Piece 1: load settings, connect to both accounts, and refuse to run
if either token belongs to the wrong account.
 
Q: How is authorize.py used with sync.py?
A: They never call each other. They're connected only through the token
   files in ~/.drive-sync:
     authorize.py (run by hand, once per account) WRITES token_*.json
     sync.py      (runs every time)                READS  token_*.json
   authorize.py = getting the keys cut. sync.py = using the keys every day.
   Go back to authorize.py only if a token stops working (7-day Testing-mode
   limit, revoked access, or switching account B).
"""

import os
import sys
import re
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SECRETS_DIR = Path.home() / ".drive-sync"


# Read settings from environment variables; stop if any are missing
def load_config():
    config = {
        "source_folder_id": os.environ.get("SOURCE_FOLDER_ID", ""),
        "expected_source": os.environ.get("EXPECTED_SOURCE_EMAIL", ""),
        "expected_dest": os.environ.get("EXPECTED_DEST_EMAIL", ""),
    }
    missing = [name for name, value in config.items() if not value]
    if missing:
        sys.exit(f"Missing settings: {missing}")
    return config


# Load a saved token from ~/.drive-sync and make a Drive API client with it
def connect(account):
    token_file = SECRETS_DIR / f"token_{account}.json"
    creds = Credentials.from_authorized_user_file(str(token_file))
    return build("drive", "v3", credentials=creds)


# Ask Google whose token this client is using
def who_am_i(drive):
    about = drive.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]
# A Drive ID is only letters, digits, - and _. Anything else is rejected
# before it can reach a Drive query.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


# List the files directly inside the source folder (subfolders are not included)
def list_source_files(drive, folder_id):
    if not ID_PATTERN.match(folder_id):
        sys.exit("STOP: SOURCE_FOLDER_ID doesn't look like a Drive folder ID")

    files = []
    page_token = None
    while True:
        response = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false", 
            #Token A can read the entire Drive, because drive.readonly can’t be limited to a folder. So the query’s '<folder>' in parents is where my code limits itself to one folder: least privilege enforced in code, on top of the scope.
            fields="nextPageToken, files(id, name, mimeType, size, md5Checksum, modifiedTime)",
            pageToken=page_token,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


if __name__ == "__main__":
    config = load_config()
    source = connect("source")
    dest = connect("dest")

    # Mismatch guard: refuse to run if a token belongs to the wrong account
    source_email = who_am_i(source)
    dest_email = who_am_i(dest)
    if source_email.lower() != config["expected_source"].lower():
        sys.exit(f"STOP: source token is for {source_email}, expected {config['expected_source']}")
    if dest_email.lower() != config["expected_dest"].lower():
        sys.exit(f"STOP: dest token is for {dest_email}, expected {config['expected_dest']}")

    print("Tokens OK:", source_email, "->", dest_email)

    files = list_source_files(source, config["source_folder_id"])
    print(f"Found {len(files)} files in the source folder:")
    for f in files:
        print(" -", f["name"], "|", f["mimeType"], "|", f.get("size"), "bytes")