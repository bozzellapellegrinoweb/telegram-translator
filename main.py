import os
import asyncio
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl, MessageEntityMention
import anthropic

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SOURCE_CHANNELS = [ch.strip() for ch in os.environ["SOURCE_CHANNELS"].split(",")]
DEST_CHANNEL = os.environ["DEST_CHANNEL"]

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def extract_clean_text(msg) -> str:
    """Rimuove entità Telegram (link t.me, menzioni) dal testo del messaggio."""
    text = msg.text or getattr(msg, 'caption', None) or ''
    entities = msg.entities or []

    # Trova span da rimuovere (link t.me e menzioni @)
    spans = []
    for e in entities:
        if isinstance(e, MessageEntityTextUrl) and ('t.me' in e.url or 'telegram' in e.url):
            spans.append((e.offset, e.offset + e.length))
        elif isinstance(e, MessageEntityMention):
            spans.append((e.offset, e.offset + e.length))
        elif isinstance(e, MessageEntityUrl):
            url_text = text[e.offset:e.offset + e.length]
            if 't.me' in url_text or 'telegram.me' in url_text:
                spans.append((e.offset, e.offset + e.length))

    # Rimuovi da destra a sinistra per non spostare gli offset
    spans.sort(reverse=True)
    chars = list(text)
    for start, end in spans:
        chars[start:end] = []

    # Rimuovi anche URL t.me rimasti come testo semplice
    clean = ''.join(chars)
    clean = re.sub(r'https?://t\.me/\S+', '', clean)
    clean = re.sub(r't\.me/\S+', '', clean)
    return clean.strip()


def is_listing(text: str) -> bool:
    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        messages=[
            {
                "role": "user",
                "content": (
                    "Rispondi solo YES o NO. "
                    "Il seguente testo è un annuncio immobiliare (vendita o affitto di proprietà)? "
                    "Rispondi NO se è: una richiesta di acquisto/affitto, un messaggio di chat, un saluto, una domanda generica, spam.\n\n"
                    f"{text}"
                ),
            }
        ],
    )
    return message.content[0].text.strip().upper().startswith("YES")


def translate(text: str) -> str:
    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Traduci in italiano questo annuncio immobiliare di Dubai. "
                    "Rispondi SOLO con il testo tradotto, senza commenti, spiegazioni o prefazioni. "
                    "Mantieni esattamente la stessa formattazione, emoji, simboli e struttura. "
                    "IMPORTANTE: "
                    "1) Sostituisci qualsiasi contatto (numeri di telefono, WhatsApp, username Telegram, email) con: Telegram @Gionine06 | WhatsApp +971 58 636 8860. "
                    "2) Rimuovi qualsiasi riferimento alla fonte originale: link t.me/..., nomi di canali/agenzie, watermark. "
                    "3) Rimuovi qualsiasi menzione di commissioni, percentuali di agenzia (es. 2%, 3% commission, agency fee).\n\n"
                    f"{text}"
                ),
            }
        ],
    )
    return message.content[0].text


BACKFILL_COUNT = 0  # backfill disabilitato — solo nuovi messaggi


async def main():
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    await client.connect()

    print(f"Connesso. In ascolto su: {SOURCE_CHANNELS}")
    print(f"Pubblico su: @{DEST_CHANNEL}")

    # Recupera ultimi messaggi da ogni canale
    for channel in SOURCE_CHANNELS:
        print(f"\nRecupero ultimi {BACKFILL_COUNT} messaggi da {channel}...")
        try:
            count = 0
            async for msg in client.iter_messages(channel, limit=BACKFILL_COUNT):
                text = extract_clean_text(msg)
                if not text or len(text.strip()) < 20:
                    continue
                if not is_listing(text):
                    print(f"  [skip] Non è un annuncio")
                    continue
                try:
                    translated = translate(text)
                    if msg.media:
                        await client.send_file(DEST_CHANNEL, msg.media, caption=translated)
                    else:
                        await client.send_message(DEST_CHANNEL, translated)
                    count += 1
                    print(f"  [{count}] Pubblicato")
                except Exception as e:
                    print(f"  Errore: {e}")
            print(f"  Recupero completato: {count} messaggi pubblicati")
        except Exception as e:
            print(f"  Errore canale {channel}: {e}")

    print("\nIn ascolto per nuovi messaggi...")

    @client.on(events.NewMessage(chats=SOURCE_CHANNELS))
    async def handler(event):
        msg = event.message
        text = extract_clean_text(msg)

        if not text or len(text.strip()) < 20:
            return

        if not is_listing(text):
            print(f"Skippato: non è un annuncio")
            return

        print(f"\n--- Nuovo annuncio da {event.chat.username} ---")
        print(text[:100] + "..." if len(text) > 100 else text)

        try:
            translated = translate(text)
            print(f"Tradotto: {translated[:80]}...")

            if msg.media:
                await client.send_file(
                    DEST_CHANNEL,
                    msg.media,
                    caption=translated,
                )
            else:
                await client.send_message(DEST_CHANNEL, translated)

            print("Pubblicato!")
        except Exception as e:
            print(f"Errore: {e}")

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
