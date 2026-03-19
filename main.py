import os
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import anthropic

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_STRING = os.environ["TELEGRAM_SESSION_STRING"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
SOURCE_CHANNELS = [ch.strip() for ch in os.environ["SOURCE_CHANNELS"].split(",")]
DEST_CHANNEL = os.environ["DEST_CHANNEL"]

claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def translate(text: str) -> str:
    message = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": (
                    "Traduci in italiano questo annuncio immobiliare di Dubai. "
                    "Mantieni esattamente la stessa formattazione, emoji, simboli e struttura. "
                    "Traduci solo il testo, non aggiungere nulla.\n\n"
                    f"{text}"
                ),
            }
        ],
    )
    return message.content[0].text


BACKFILL_COUNT = 10  # messaggi da recuperare per canale all'avvio


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
                text = msg.text or getattr(msg, 'caption', None)
                if not text or len(text.strip()) < 20:
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
        text = msg.text or getattr(msg, 'caption', None)

        if not text or len(text.strip()) < 20:
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
