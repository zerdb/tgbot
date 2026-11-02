"""Mail.ru sending and local address book storage."""
from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

ADDRESS_BOOK_PATH = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "GigaAMVoiceAssistant" / "address_book.json"
_pending_email_subject: str | None = None

def load_address_book() -> dict[str, str]:
    try:
        data = json.loads(ADDRESS_BOOK_PATH.read_text(encoding="utf-8"))
        return {str(name): str(address) for name, address in data.items()}
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Не удалось прочитать адресную книгу: {exc}")
        return {}

def save_address_book(book: dict[str, str]):
    ADDRESS_BOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    ADDRESS_BOOK_PATH.write_text(
        json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8"
    )

def list_email_contacts():
    book = load_address_book()
    if not book:
        print("Адресная книга пуста. Скажите «добавить контакт» и заполните открывшуюся форму.")
        return
    print("Адресная книга:")
    for name, address in book.items():
        print(f"— {name}: {address}")

def begin_email(text: str):
    global _pending_email_subject
    subject = re.sub(
        r"^\s*отправ(?:ь|ить)\s+на\s+почту\s+(?:текст\s+)?",
        "", text, flags=re.IGNORECASE,
    ).strip().strip(" .,!?:;«»\"'")
    if not subject:
        print("Скажите тему письма после команды «отправь на почту текст ...».")
        return
    book = load_address_book()
    if not book:
        print("Адресная книга пуста. Сначала скажите «добавить контакт» и заполните форму.")
        return
    _pending_email_subject = subject
    print(f"Кому отправить письмо «{subject}»? Назовите получателя:")
    for name, address in book.items():
        print(f"— {name}: {address}")

def send_email_to_contact(name: str):
    global _pending_email_subject
    subject = _pending_email_subject
    if not subject:
        return False
    book = load_address_book()
    matched = next(
        ((saved_name, address) for saved_name, address in book.items()
         if saved_name.casefold() == name.casefold()),
        None,
    )
    if not matched:
        print(f"Получатель «{name}» не найден. Назовите имя точно как в адресной книге.")
        return True
    saved_name, address = matched
    login = os.getenv("GIGAAM_MAIL_LOGIN", "zerdb@mail.ru")
    password = os.getenv("GIGAAM_MAIL_PASSWORD")
    if not password:
        print("Не задан пароль приложения. Установите переменную GIGAAM_MAIL_PASSWORD и перезапустите помощника.")
        _pending_email_subject = None
        return True
    message = EmailMessage()
    message["From"] = login
    message["To"] = address
    message["Subject"] = subject
    message.set_content("")
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.mail.ru", 587, timeout=20) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(login, password)
            server.send_message(message)
        print(f"Письмо отправлено: {saved_name} <{address}>. Тема: {subject}")
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
