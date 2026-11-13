import argparse
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SECRETS_DIR = Path.home() / ".drive-sync"
#Q: Where is ~/.drive-sync on my Mac?
#A: /Users/prashhastii/.drive-sync/, next to build-projects/, outside the repo. Hidden because of the dot: Cmd+Shift+G in Finder, or ls -l ~/.drive-sync.

# Least privilege: A can only read; B only sees files this app creates
SCOPES = {
    "source": ["https://www.googleapis.com/auth/drive.readonly"],
    "dest": ["https://www.googleapis.com/auth/drive.file"],
    #Q: The scope doesn't say which account is Team A?
    #A: Right. A scope says what kind of access, not whose Drive. The account is whoever signs in at consent. That's why we print the email, and why the sync script will stop on a mismatch.
}


def get_token(account):
    #Q: What is this?
    #A: InstalledAppFlow (google-auth-oauthlib) runs OAuth login for desktop apps. from_client_secrets_file sets it up from client_secret.json, the app's ID badge. Second argument = scopes to ask for
    flow = InstalledAppFlow.from_client_secrets_file(
        str(SECRETS_DIR / "client_secret.json"),  # the app's ID badge
        SCOPES[account],
        #Q: Does SCOPES[account] mean source or dest?
        #A: Yes. account comes from --account. --account source looks up SCOPES["source"] and asks for drive.readonly.
        #Q: Are the two slips controlled in code or the console?
        #A: Code chooses what to ask for and which token does which job. Google issues and enforces the limits on every call. The console decides who may consent.
    )
    # select_account forces the account chooser, so you can't
    # accidentally approve as whatever account the browser has open
    return flow.run_local_server(port=0, prompt="select_account consent")


# Ask Google whose token this is, so I can catch a wrong-account click
def who_am_i(creds):
    drive = build("drive", "v3", credentials=creds)
    #Q: Where do I choose the account? Is it the Google API?
    #A: The library opens a tiny server on localhost and your browser at Google's sign-in page. You pick the account there. Google redirects back with a code; the library swaps it for tokens. See the diagram.
    #Q: Why a Desktop app, not Web?
    #A: No website, no visitors. You consent once on your laptop and the job reuses the refresh token.
    
    about = drive.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]



def save_token(creds, account):
    path = SECRETS_DIR / f"token_{account}.json" # file to save to: token_source.json or token_dest.json, picked by --account 
    # 0o600: only you can read or write this file
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json()) # save this run's token as JSON text into that file
    return path
    #Q: Why os.open instead of open()?
    #A: open() creates the file with default permissions, often readable by others, until you chmod it. os.open with 0o600 creates it locked from the first moment. O_TRUNC empties an old file first.
    with os.fdopen(fd, "w") as f:
        f.write(creds.to_json())
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", choices=["source", "dest"], required=True)
    account = parser.parse_args().account

    creds = get_token(account)
    print("Signed in as:", who_am_i(creds))
    print("Scopes:", creds.scopes)
    print("Token saved to:", save_token(creds, account))