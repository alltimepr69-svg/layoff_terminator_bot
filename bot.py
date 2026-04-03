import os
import io
import random
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ChatMemberHandler, ContextTypes, filters
from telegram.constants import ChatMemberStatus
from PIL import Image, ImageDraw, ImageFont, ImageFilter

load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN")


def add_terminated_stamp(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size
    if w > MAX_DIMENSION or h > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        w, h = img.size

    max_stamp_w = int(w * 0.70)
    padding_x = int(w * 0.06)
    padding_y = int(h * 0.04)

    font_size = int(h * 0.18)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        font = ImageFont.truetype(font_path, font_size)
    except (IOError, OSError):
        font = ImageFont.load_default()

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), "TERMINATED", font=font)
    text_w = bbox[2] - bbox[0]

    while text_w + padding_x * 2 > max_stamp_w:
        font_size -= 2
        try:
            font = ImageFont.truetype(font_path, font_size)
        except (IOError, OSError):
            font = ImageFont.load_default()
        bbox = dummy_draw.textbbox((0, 0), "TERMINATED", font=font)
        text_w = bbox[2] - bbox[0]

    text_h = bbox[3] - bbox[1]
    stamp_w = text_w + padding_x * 2
    stamp_h = text_h + padding_y * 2

    canvas = Image.new("RGBA", (stamp_w, stamp_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    RED = (210, 15, 15)
    brd = max(5, int(stamp_h * 0.08))

    draw.rectangle([0, 0, stamp_w - 1, stamp_h - 1], outline=RED, width=brd)
    inset = int(brd * 1.5)
    draw.rectangle(
        [inset, inset, stamp_w - 1 - inset, stamp_h - 1 - inset],
        outline=RED,
        width=max(2, brd // 2),
    )

    text_x = (stamp_w - text_w) // 2
    text_y = (stamp_h - text_h) // 2
    draw.text((text_x, text_y), "TERMINATED", font=font, fill=RED)

    pixels = canvas.load()
    random.seed(42)
    for _ in range(int(stamp_w * stamp_h * 0.18)):
        px = random.randint(0, stamp_w - 1)
        py = random.randint(0, stamp_h - 1)
        if pixels[px, py][3] != 0:
            pixels[px, py] = (pixels[px, py][0], pixels[px, py][1], pixels[px, py][2], 0)

    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=1.2))

    r, g, b, a2 = canvas.split()
    a2 = a2.point(lambda p: int(p * 0.62))
    canvas = Image.merge("RGBA", (r, g, b, a2))

    canvas = canvas.rotate(18, expand=True)

    paste_x = (w - canvas.width) // 2
    paste_y = (h - canvas.height) // 2
    img.paste(canvas, (paste_x, paste_y), canvas)

    img = img.convert("RGB")
    output = io.BytesIO()
    img.save(output, format="JPEG", quality=95)
    output.seek(0)
    return output.read()


WELCOME_TEXT = """🔴 *TERMINATED BOT is here.*

I stamp your photos with an official-looking *TERMINATED* seal.

*How to trigger:*

Two ways to use `/terminate`:
1. Send a photo with `/terminate` as the caption
2. Reply to any existing photo with `/terminate`

*Commands:*
/start — Show this message
/help — How to use the bot
/terminate — Stamp a photo (use as caption or reply to a photo)

Just drop an image and watch it get terminated. 💀"""


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")


async def handle_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    was_member = result.old_chat_member.status in (
        ChatMemberStatus.LEFT, ChatMemberStatus.BANNED
    )
    is_member = result.new_chat_member.status in (
        ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR
    )
    if was_member and is_member:
        await context.bot.send_message(
            chat_id=result.chat.id,
            text=WELCOME_TEXT,
            parse_mode="Markdown",
        )


MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_DIMENSION = 8000  # pixels


async def _stamp_and_reply(update, context, file_id, file_size):
    if file_size and file_size > MAX_FILE_SIZE:
        await update.message.reply_text("❌ Image too large (max 10 MB).")
        return
    await update.message.reply_text("⏳ Stamping...")
    file = await context.bot.get_file(file_id)
    file_bytes = await file.download_as_bytearray()
    stamped = add_terminated_stamp(bytes(file_bytes))
    await update.message.reply_photo(photo=io.BytesIO(stamped), caption="🔴 TERMINATED")


async def handle_terminate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply = update.message.reply_to_message
    if reply and reply.photo:
        photo = reply.photo[-1]
        await _stamp_and_reply(update, context, photo.file_id, photo.file_size)
    elif reply and reply.document and reply.document.mime_type and reply.document.mime_type.startswith("image/"):
        doc = reply.document
        await _stamp_and_reply(update, context, doc.file_id, doc.file_size)
    else:
        return


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (update.message.caption or "").strip()
    if not caption.startswith("/terminate"):
        return
    photo = update.message.photo[-1]
    await _stamp_and_reply(update, context, photo.file_id, photo.file_size)


async def handle_document_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (update.message.caption or "").strip()
    if not caption.startswith("/terminate"):
        return
    doc = update.message.document
    await _stamp_and_reply(update, context, doc.file_id, doc.file_size)


if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("terminate", handle_terminate_command))
    app.add_handler(ChatMemberHandler(handle_bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, handle_document_image))
    app.run_polling(allowed_updates=Update.ALL_TYPES)
