import asyncio
import logging
import re
import html
import os
from telethon import TelegramClient, events, Button, types
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURAÇÕES ---
API_ID = int(os.getenv('TG_API_ID', '24375561'))
API_HASH = os.getenv('TG_API_HASH', 'ae3883654709849d47c3553be7aaada4')
BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '8512413789:AAECik5KNiYytYv2rPQVlPg8PoKxO-UlnaU')

SUPABASE_URL = os.getenv('SUPABASE_URL', "https://lymjjozpdsdoloahsyey.supabase.co")
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5bWpqb3pwZHNkb2xvYWhzeWV5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MDk4ODEwNCwiZXhwIjoyMDg2NTY0MTA0fQ.RfJ7MHacsQZrIL_yG84lVcl2qDNF6xeriHomO1eRG0g")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = TelegramClient('canais18_bot_session', API_ID, API_HASH)
user_states = {}

MAIN_MENU_REPLY = [
    [Button.text("📨 Criar Postagem", resize=True), Button.text("📊 Estatísticas")],
    [Button.text("⚙️ Configurações"), Button.text("❓ Ajuda")]
]

# --- MOTOR DE REPLICAÇÃO NATIVO (PREMIUM) ---

async def get_safe_message_and_entities(state):
    if state.get('no_caption'):
        return "", []
    msg_id = state.get('custom_caption_msg_id') or state.get('msg_id')
    if not msg_id:
        return "", []
    try:
        msg = await bot.get_messages(state['chat_id'], ids=msg_id)
        if not msg:
            return "", []
        return msg.message or "", msg.entities or []
    except Exception as e:
        logger.error(f"Erro ao recuperar mensagem original: {e}")
        return "", []

async def send_broadcast_message(target_id, state, buttons=None):
    try:
        orig_msg = await bot.get_messages(state['chat_id'], ids=state['msg_id'])
        text, entities = await get_safe_message_and_entities(state)
        return await bot.send_message(
            target_id,
            text,
            file=orig_msg.media if orig_msg else None,
            buttons=buttons,
            formatting_entities=entities,
            silent=not state['settings']['notify'],
            link_preview=state['settings']['preview']
        )
    except Exception as e:
        logger.error(f"Erro fatal no envio do broadcast: {e}")
        raise e

def clean_button_text(text):
    if not text: return ""
    return re.sub(r'(\*\*|__|`|~~)', '', text).strip()

def parse_inline_buttons(text):
    """Parser avançado: Texto - Link. Use && para botões na mesma linha."""
    if not text: return None
    final_rows = []
    lines = text.split('\n')
    for line in lines:
        row = []
        parts = line.split('&&')
        for p in parts:
            match = re.search(r'(.+?)(?:\s*->\s*|\s*--\s*|\s*-\s*)(https?://\S+)', p)
            if match:
                label = clean_button_text(match.group(1))
                url = match.group(2).strip()
                row.append(Button.url(label, url))
        if row: final_rows.append(row)
    return final_rows if final_rows else None

# --- MÓDULOS DE INTERFACE ---

async def show_stats(event):
    try:
        res_active = supabase.table("bot_groups").select("*", count="exact").eq("is_active", True).execute()
        active_count = res_active.count or len(res_active.data or [])
        res_pending = supabase.table("bot_groups").select("*", count="exact").eq("is_active", False).execute()
        pending_count = res_pending.count or len(res_pending.data or [])
        estimated_audience = active_count * 500

        text = (
            "📊 **Estatísticas Profissionais • Canais18**\n\n"
            f"🌐 **Canais Conectados:** `{active_count}`\n"
            f"⏳ **Aguardando Admin:** `{pending_count}`\n"
            f"👥 **Alcance Estimado:** `~{estimated_audience:,} users`\n\n"
            "✅ **Motor UTF-16 Premium:** `Ativo`\n"
            "📌 **Auto-Fixação:** `Disponível`"
        )
    except Exception as e:
        text = f"📊 **Estatísticas**\n\n⚠️ Erro: {e}"

    buttons = [[Button.inline("🔄 Atualizar", b"refresh_stats"), Button.inline("🏠 Menu", b"cancel")]]
    await event.respond(text, buttons=buttons)

async def show_help(event):
    text = (
        "❓ **Guia ChannelHelp Style • Canais18**\n\n"
        "✨ **Criação de Postagens:**\n"
        "1. Clique em '📨 Criar Postagem'.\n"
        "2. Envie a mídia ou texto (Emojis Premium são aceitos).\n"
        "3. Configure os botões:\n"
        "   `Site - https://canais18.com` (1 botão)\n"
        "   `Bot - t.me/bot && Site - canais18.com` (2 botões lado a lado)\n\n"
        "📌 **Destaque:**\n"
        "Ative a opção 'Fixar postagem' no menu final para destacar sua mensagem em todos os grupos."
    )
    buttons = [[Button.inline("🏠 Menu", b"cancel")]]
    await event.respond(text, buttons=buttons)

async def show_settings(event, user_id):
    state = user_states[user_id]
    s = state['settings']
    text = (
        "📨 **Editor de Postagem • Configurações**\n\n"
        "Ajuste os parâmetros antes de enviar o conteúdo."
    )
    buttons = [
        [Button.inline("➡️ Próximo Passo", b"nav_content")],
        [Button.inline("🔔 Notificar", b"info"), Button.inline("✅ ON" if s['notify'] else "❌ OFF", b"tog_notif")],
        [Button.inline("🏷️ Preview Link", b"info"), Button.inline("✅ ON" if s['preview'] else "❌ OFF", b"tog_preview")],
        [Button.inline("📌 Fixar Post", b"info"), Button.inline("✅ ON" if s['pin'] else "❌ OFF", b"tog_pin")],
        [Button.inline("🏠 Menu", b"cancel")]
    ]
    await (event.edit(text, buttons=buttons) if hasattr(event, 'data') else event.respond(text, buttons=buttons))

async def show_content_input(event, user_id):
    text = "**Etapa 1: Envie o conteúdo principal**\n\n(Foto, Vídeo, GIF ou Texto puro com Emojis Premium)"
    buttons = [[Button.inline("⬅️ Voltar", b"nav_settings"), Button.inline("🏠 Menu", b"cancel")]]
    await event.edit(text, buttons=buttons)

async def show_caption_input(event, user_id):
    text = "**Etapa 2: Envie a legenda da mídia**\n\n(Ou clique abaixo para enviar sem legenda)"
    buttons = [[Button.inline("🚫 Sem legenda", b"set_no_caption")], [Button.inline("🏠 Menu", b"cancel")]]
    await event.respond(text, buttons=buttons)

async def show_buttons_input(event, user_id):
    text = (
        "**Etapa 3: Configurar Botões Inline**\n\n"
        "Formato: `Texto - Link`\n"
        "Exemplo:\n`🌐 Site - https://google.com && 🤖 Bot - https://t.me/bot`"
    )
    buttons = [[Button.inline("🚫 Sem botões", b"nav_final")], [Button.inline("🏠 Menu", b"cancel")]]
    await event.respond(text, buttons=buttons)

async def show_final_menu(event, user_id):
    state = user_states[user_id]
    await event.respond("👁️ **PRÉ-VISUALIZAÇÃO DA POSTAGEM:**")
    try:
        await send_broadcast_message(event.chat_id, state, buttons=parse_inline_buttons(state['buttons_raw']))
    except Exception as e:
        await event.respond(f"⚠️ **Erro no Preview:** {e}")

    buttons = [
        [Button.inline("👤 Enviar Agora ➡️", b"send_now")],
        [Button.inline("📅 Agendar (Em breve)", b"info")],
        [Button.inline("🏠 Menu", b"cancel")]
    ]
    await event.respond("Tudo pronto para o broadcast?", buttons=buttons)

# --- HANDLERS ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("👋 **Canais18 Bot Pro**\n_Central de Broadcast & Gestão_", buttons=MAIN_MENU_REPLY)

@bot.on(events.NewMessage(func=lambda e: e.text == "📨 Criar Postagem"))
async def create_post(event):
    user_id = event.sender_id
    user_states[user_id] = {
        'step': 'SETTINGS', 'chat_id': event.chat_id,
        'settings': {'notify': True, 'preview': True, 'protected': False, 'pin': False},
        'msg_id': None, 'custom_caption_msg_id': None, 'no_caption': False, 'buttons_raw': ""
    }
    await show_settings(event, user_id)

@bot.on(events.NewMessage(func=lambda e: e.text == "📊 Estatísticas"))
async def stats_handler(event):
    await show_stats(event)

@bot.on(events.NewMessage(func=lambda e: e.text == "❓ Ajuda"))
async def help_handler(event):
    await show_help(event)

@bot.on(events.NewMessage(func=lambda e: e.text == "⚙️ Configurações"))
async def settings_handler(event):
    await event.respond("⚙️ **Configurações Globais**\n\n• Motor: UTF-16 Nativo\n• Status: Operacional\n• Versão: 2.0 (CH Style)")

@bot.on(events.NewMessage)
async def message_handler(event):
    if not event.is_private or event.text in ["📨 Criar Postagem", "📊 Estatísticas", "❓ Ajuda", "⚙️ Configurações"]: return
    user_id = event.sender_id
    state = user_states.get(user_id)
    if not state: return

    if state['step'] == 'AWAIT_CONTENT':
        state['msg_id'] = event.id
        state['step'] = 'AWAIT_CAPTION' if event.media else 'AWAIT_BUTTONS'
        await (show_caption_input(event, user_id) if event.media else show_buttons_input(event, user_id))
    elif state['step'] == 'AWAIT_CAPTION':
        state['custom_caption_msg_id'] = event.id
        state['step'] = 'AWAIT_BUTTONS'
        await show_buttons_input(event, user_id)
    elif state['step'] == 'AWAIT_BUTTONS':
        state['buttons_raw'] = event.text
        state['step'] = 'FINAL_MENU'
        await show_final_menu(event, user_id)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    state = user_states.get(user_id)

    if data == b"refresh_stats":
        await event.delete()
        await show_stats(event)
        return

    if not state:
        if data == b"cancel": await event.respond("Menu:", buttons=MAIN_MENU_REPLY)
        return

    if data == b"nav_content": state['step'] = 'AWAIT_CONTENT'; await show_content_input(event, user_id)
    elif data == b"set_no_caption": state['no_caption'] = True; state['step'] = 'AWAIT_BUTTONS'; await show_buttons_input(event, user_id)
    elif data == b"nav_final": state['step'] = 'FINAL_MENU'; await show_final_menu(event, user_id)
    elif data == b"cancel": user_states.pop(user_id, None); await event.respond("Cancelado.", buttons=MAIN_MENU_REPLY)
    elif data == b"tog_pin": state['settings']['pin'] = not state['settings']['pin']; await show_settings(event, user_id)
    elif data == b"tog_notif": state['settings']['notify'] = not state['settings']['notify']; await show_settings(event, user_id)
    elif data == b"tog_preview": state['settings']['preview'] = not state['settings']['preview']; await show_settings(event, user_id)
    
    elif data == b"send_now":
        await event.edit("🚀 **Disparando broadcast...**")
        res = supabase.table("bot_groups").select("chat_id").eq("is_active", True).execute()
        success = 0
        btns = parse_inline_buttons(state['buttons_raw'])
        for g in (res.data or []):
            try:
                sent = await send_broadcast_message(int(g['chat_id']), state, buttons=btns)
                if state['settings']['pin']:
                    try: await bot.pin_message(int(g['chat_id']), sent.id)
                    except: pass
                success += 1
                await asyncio.sleep(0.3) # Broadcast mais rápido
            except Exception as e:
                logger.error(f"Erro em {g['chat_id']}: {e}")
        await event.respond(f"✅ Sucesso: {success} grupos alcançados.", buttons=MAIN_MENU_REPLY)
        user_states.pop(user_id, None)

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("🚀 Canais18 Bot Pro operacional (CH Style)!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
