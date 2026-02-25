import argparse

from werkzeug.security import generate_password_hash

from journal_utils import add_entry, create_user, get_user_by_email, load_entries
from sentiment import classify_sentiment


def _ensure_cli_user_id() -> int:
    email = "cli@mindmirror.app"
    user = get_user_by_email(email)
    if user:
        return user["id"]
    ok, _, user_id = create_user("CLI User", email, generate_password_hash("cli-local-user"))
    if ok and user_id:
        return user_id
    # Fallback if account already created by race condition
    user = get_user_by_email(email)
    return user["id"]


def cmd_add(text: str) -> None:
    sentiment = classify_sentiment(text)
    entry = add_entry(text, sentiment, _ensure_cli_user_id())
    print(f"Saved entry #{entry['id']} | {entry['sentiment']['label']}")


def cmd_list() -> None:
    entries = load_entries(_ensure_cli_user_id())
    if not entries:
        print("No entries yet.")
        return
    for entry in entries:
        print(
            f"[{entry['created_at']}] {entry['sentiment']['label']} "
            f"(polarity={entry['sentiment']['polarity']}): {entry['text']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Mind Mirror CLI")
    sub = parser.add_subparsers(dest="command")

    add_parser = sub.add_parser("add", help="Add journal entry")
    add_parser.add_argument("text", type=str, help="Entry text")
    sub.add_parser("list", help="List entries")

    args = parser.parse_args()
    if args.command == "add":
        cmd_add(args.text)
    elif args.command == "list":
        cmd_list()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
