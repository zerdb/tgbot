"""Mail sending and persistent local address book storage."""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from agent_core import APP_DATA

ADDRESS_BOOK_PATH = APP_DATA / "address_book.json"
_pending_email_subject: str | None = None


def load_address_book() -> dict[str, dict[str, str]]:
    """Load current records and transparently migrate legacy name-to-email entries."""
    try:
        data = json.loads(ADDRESS_BOOK_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Не удалось прочитать адресную книгу: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    result = {}
    migrated = False
    for raw_name, value in data.items():
        name = str(raw_name).strip()
        if not name:
            continue
        if isinstance(value, dict):
            result[name] = {
                "phone": str(value.get("phone", "")),
                "email": str(value.get("email", "")),
                "notes": str(value.get("notes", "")),
            }
        else:
            result[name] = {"phone": "", "email": str(value), "notes": ""}
            migrated = True
    if migrated:
        try:
            save_address_book(result)
        except OSError as exc:
            print(f"Не удалось обновить формат адресной книги: {exc}")
    return result


def save_address_book(book: dict):
    ADDRESS_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADDRESS_BOOK_PATH.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")


def list_email_contacts():
    book = load_address_book()
    contacts = [(name, item.get("email", "")) for name, item in book.items() if item.get("email")]
    if not contacts:
        print("В адресной книге пока нет контактов с электронной почтой.")
        return
    print("Адресная книга:")
    for name, address in contacts:
        print(f"— {name}: {address}")


def send_email(recipient: str, subject: str, body: str = "", attachments: list[str] | None = None):
    """Send an email with optional local-file attachments. Raises on failure."""
    from agent_core import load_settings
    login = os.getenv("ZERO_CONTROL_MAIL_LOGIN", os.getenv("GIGAAM_MAIL_LOGIN", load_settings()["mail_login"]))
    password = os.getenv("ZERO_CONTROL_MAIL_PASSWORD", os.getenv("GIGAAM_MAIL_PASSWORD", ""))
    if not password:
        raise RuntimeError(
            "Не задан пароль приложения. Установите переменную ZERO_CONTROL_MAIL_PASSWORD "
            "и перезапустите помощника."
        )
    if not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}", recipient.strip(), re.IGNORECASE):
        raise ValueError("Укажите корректный адрес электронной почты.")
    message = EmailMessage()
    message["From"] = login
    message["To"] = recipient.strip()
    message["Subject"] = subject.strip() or "Файлы"
    message.set_content(body or "")
    for file_name in attachments or []:
        path = Path(file_name)
        if not path.is_file():
            raise FileNotFoundError(f"Файл не найден: {path}")
        data = path.read_bytes()
        import mimetypes
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        message.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.mail.ru", 587, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(login, password)
        server.send_message(message)


def begin_email(text: str):
    global _pending_email_subject
    subject = re.sub(r"^\s*отправ(?:ь|ить)\s+на\s+почту\s+(?:текст\s+)?", "", text, flags=re.IGNORECASE).strip().strip(" .,!?:;«»")
    if not subject:
        print("Укажите тему письма после команды.")
        return
    _pending_email_subject = subject
    print(f"Тема письма: {subject}. В старом голосовом режиме отправка контакту больше не используется.")


def send_email_to_contact(name: str):
    global _pending_email_subject
    subject = _pending_email_subject
    if not subject:
        return False
    book = load_address_book()
    matched = next(((saved_name, item.get("email", "")) for saved_name, item in book.items()
                    if saved_name.casefold() == name.casefold() and item.get("email")), None)
    if not matched:
        print(f"Получатель «{name}» не найден или у него не указана почта.")
        return True
    try:
        send_email(matched[1], subject)
        print(f"Письмо отправлено: {matched[0]} <{matched[1]}>. Тема: {subject}")
    except Exception as exc:
        print(f"Не удалось отправить письмо: {exc}")
    finally:
        _pending_email_subject = None
    return True


def has_pending_email() -> bool:
    return _pending_email_subject is not None


def cancel_pending_email():
    global _pending_email_subject
    _pending_email_subject = None
