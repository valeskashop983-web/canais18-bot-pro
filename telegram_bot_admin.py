import asyncio
import logging
import re
import html
import os
from telethon import TelegramClient, events, Button, types, functions
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

# --- MOTOR DE SINCRONIZAÇÃO EM TEMPO REAL ---

@bot.on(events.ChatAction)
async def chat_action_handler(event):
    """Detecta quando o bot é adicionado ou removido de chats/canais."""
    try:
        chat = await event.get_chat()
        chat_id = str(event.chat_id)
        title = getattr(chat, 'title', 'Sem Título')
        
        # Bot foi adicionado ou permissões alteradas
        if event.user_added or event.new_pin or (event.action_message and hasattr(event.action_message.action, 'users')):
            # Verificar se o bot é admin
            me = await bot.get_me()
            permissions = await bot.get_permissions(chat, me)
            
            if permissions.is_admin:
                logger.info(f"✅ Bot ativado como admin em: {title} ({chat_id})")
                
                # Tentar obter link de convite
                invite_link = None
                try:
                    full_chat = await bot(functions.channels.GetFullChannelRequest(channel=chat))
                    invite_link = getattr(full_chat.full_chat, 'exported_invite', None)
                    if invite_link: invite_link = invite_link.link
                except: pass

                # Upsert no Supabase
                data = {
                    "chat_id": chat_id,
                    "title": title,
                    "is_active": True,
                    "invite_link": invite_link
                }
                supabase.table("bot_groups").upsert(data, on_conflict="chat_id").execute()
                
                # Mensagem de boas-vindas no grupo (opcional)
                try:
                    await bot.send_message(event.chat_id, "✅ **Bot Canais18 Ativado!**\n\nEste grupo agora faz parte da nossa rede de divulgação. Mantenha o bot como admin para garantir sua permanência no site.\n\n_Você pode apagar esta mensagem agora._")
                except: pass

        # Bot foi removido
        elif event.user_kicked or event.user_left:
            me = await bot.get_me()
            if event.user_id == me.id:
                logger.info(f"❌ Bot removido de: {title} ({chat_id})")
                supabase.table("bot_groups").update({"is_active": False}).eq("chat_id", chat_id).execute()

    except Exception as e:
        logger.error(f"Erro no chat_action_handler: {e}")

# --- MOTOR DE REPLICAÇÃO NATIVO ---

async def get_safe_message_and_entities(state):
    if state.get('no_caption'): return "", []
    msg_id = state.get('custom_caption_msg_id') or state.get('msg_id')
    if not msg_id: return "", []
    try:
        msg = await bot.get_messages(state['chat_id'], ids=msg_id)
        return (msg.message or "", msg.entities or []) if msg else ("", [])
    except: return "", []

async def send_broadcast_message(target_id, state, buttons=None):
    try:
        orig_msg = await bot.get_messages(state['chat_id'], ids=state['msg_id'])
        text, entities = await get_safe_message_and_entities(state)
        final_buttons = []
        if buttons: final_buttons.extend(buttons)
        if state.get('reactions'):
            final_buttons.append([Button.inline(r, data=f"react_{r}") for r in state['reactions']])

        return await bot.send_message(
            target_id, text,
            file=orig_msg.media if orig_msg and orig_msg.media else None,
            buttons=final_buttons if final_buttons else None,
            formatting_entities=entities,
            silent=not state['settings']['notify'],
            link_preview=state['settings']['preview']
        )
    except Exception as e:
        logger.error(f"Erro no broadcast para {target_id}: {e}")
        raise e

# --- UI / UX ---

async def show_stats(event):
    """Estatísticas REAIS consultando o Telegram em tempo real."""
    await event.respond("⏳ **Calculando audiência em tempo real...**")
    try:
        res = supabase.table("bot_groups").select("chat_id").eq("is_active", True).execute()
        active_groups = res.data or []
        total_members = 0
        working_channels = 0

        for g in active_groups:
            try:
                chat = await bot.get_entity(int(g['chat_id']))
                full_chat = await bot(functions.channels.GetFullChannelRequest(channel=chat))
                count = full_chat.full_chat.participants_count
                total_members += count
                working_channels += 1
            except:
                # Se falhar, o bot pode ter sido removido sem o webhook disparar
                supabase.table("bot_groups").update({"is_active": False}).eq("chat_id", g['chat_id']).execute()

        text = (
            "📊 **Estatísticas Reais • Canais18**\n\n"
            f"📡 **Canais Ativos Agora:** `{working_channels}`\n"
            f"👥 **Audiência Real (Membros):** `{total_members:,}`\n"
            f"⚡ **Média por Canal:** `{int(total_members/working_channels) if working_channels > 0 else 0}`\n\n"
            "✅ **Sincronização:** `Database + Telegram API`\n"
            "💎 **Status Premium:** `Ativo`"
        )
    except Exception as e:
        logger.error(f"Erro nas estatísticas: {e}")
        text = "📊 **Estatísticas**\n\n⚠️ Erro ao processar dados em tempo real."

    buttons = [[Button.inline("🔄 Atualizar Agora", b"refresh_stats"), Button.inline("🏠 Menu", b"cancel")]]
    await event.respond(text, buttons=buttons)

# --- FLUXO DE POSTAGEM (CH STYLE) ---

async def show_settings_step(event, user_id):
    state = user_states[user_id]
    s = state['settings']
    text = "📨 **Criar Postagem • Configurações**"
    buttons = [
        [Button.inline("➡️ Próximo (Conteúdo)", b"nav_content")],
        [Button.inline("🔔 Notificar", b"info"), Button.inline("✅ ON" if s['notify'] else "❌ OFF", b"tog_notif")],
        [Button.inline("🏷️ Preview", b"info"), Button.inline("✅ ON" if s['preview'] else "❌ OFF", b"tog_preview")],
        [Button.inline("📌 Fixar", b"info"), Button.inline("✅ ON" if s['pin'] else "❌ OFF", b"tog_pin")],
        [Button.inline("🏠 Cancelar", b"cancel")]
    ]
    await (event.edit(text, buttons=buttons) if hasattr(event, 'data') else event.respond(text, buttons=buttons))

async def show_content_input(event, user_id):
    await event.edit("**Envie o conteúdo (Mídia ou Texto)**", buttons=[[Button.inline("⬅️ Voltar", b"nav_settings")]])

async def show_caption_input(event, user_id):
    await event.respond("**Envie a legenda**", buttons=[[Button.inline("🚫 Sem Legenda", b"set_no_caption")]])

async def show_reactions_input(event, user_id):
    await event.respond("**Envie as reações (ex: 🔥 ❤️)**", buttons=[[Button.inline("🚫 Pular", b"nav_buttons")]])

async def show_buttons_input(event, user_id):
    await event.respond("**Envie os botões (Texto - Link)**", buttons=[[Button.inline("🚫 Pular", b"nav_final")]])

async def show_final_menu(event, user_id):
    state = user_states[user_id]
    await event.respond("👁️ **PREVIEW:**")
    await send_broadcast_message(event.chat_id, state, buttons=parse_inline_buttons(state['buttons_raw']))
    buttons = [[Button.inline("👤 DISPARAR AGORA ➡️", b"send_now")], [Button.inline("🏠 Cancelar", b"cancel")]]
    await event.respond("Pronto para enviar?", buttons=buttons)

# --- HANDLERS ---

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("👋 **Canais18 Bot Pro**", buttons=MAIN_MENU_REPLY)

@bot.on(events.NewMessage(func=lambda e: e.text == "📨 Criar Postagem"))
async def create_post(event):
    user_id = event.sender_id
    user_states[user_id] = {'step': 'SETTINGS', 'chat_id': event.chat_id, 'settings': {'notify': True, 'preview': True, 'pin': False}, 'msg_id': None, 'custom_caption_msg_id': None, 'no_caption': False, 'buttons_raw': "", 'reactions': []}
    await show_settings_step(event, user_id)

@bot.on(events.NewMessage(func=lambda e: e.text == "📊 Estatísticas"))
async def stats_handler(event): await show_stats(event)

@bot.on(events.NewMessage(func=lambda e: e.text == "❓ Ajuda"))
async def help_handler(event):
    await event.respond("❓ **Ajuda Rápida**\n\n1. Envie mídia/texto\n2. Configure botões: `Nome - Link`\n3. Use `&&` para botões lado a lado.")

@bot.on(events.NewMessage)
async def flow_handler(event):
    if not event.is_private or event.text in ["📨 Criar Postagem", "📊 Estatísticas", "❓ Ajuda", "⚙️ Configurações"]: return
    user_id = event.sender_id
    state = user_states.get(user_id)
    if not state: return
    if state['step'] == 'AWAIT_CONTENT':
        state['msg_id'] = event.id
        state['step'] = 'AWAIT_CAPTION' if event.media else 'AWAIT_REACTIONS'
        await (show_caption_input(event, user_id) if event.media else show_reactions_input(event, user_id))
    elif state['step'] == 'AWAIT_CAPTION':
        state['custom_caption_msg_id'] = event.id
        state['step'] = 'AWAIT_REACTIONS'; await show_reactions_input(event, user_id)
    elif state['step'] == 'AWAIT_REACTIONS':
        state['reactions'] = re.split(r'\s+', event.text.strip())[:10]
        state['step'] = 'AWAIT_BUTTONS'; await show_buttons_input(event, user_id)
    elif state['step'] == 'AWAIT_BUTTONS':
        state['buttons_raw'] = event.text
        state['step'] = 'FINAL_MENU'; await show_final_menu(event, user_id)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    data = event.data
    state = user_states.get(user_id)
    if data == b"refresh_stats": await event.delete(); await show_stats(event); return
    if not state:
        if data == b"cancel": await event.respond("Menu:", buttons=MAIN_MENU_REPLY)
        return
    if data == b"nav_content": state['step'] = 'AWAIT_CONTENT'; await show_content_input(event, user_id)
    elif data == b"set_no_caption": state['no_caption'] = True; state['step'] = 'AWAIT_REACTIONS'; await show_reactions_input(event, user_id)
    elif data == b"nav_buttons": state['step'] = 'AWAIT_BUTTONS'; await show_buttons_input(event, user_id)
    elif data == b"nav_final": state['step'] = 'FINAL_MENU'; await show_final_menu(event, user_id)
    elif data == b"cancel": user_states.pop(user_id, None); await event.respond("Cancelado.", buttons=MAIN_MENU_REPLY)
    elif data == b"tog_notif": state['settings']['notify'] = not state['settings']['notify']; await show_settings_step(event, user_id)
    elif data == b"tog_preview": state['settings']['preview'] = not state['settings']['preview']; await show_settings_step(event, user_id)
    elif data == b"tog_pin": state['settings']['pin'] = not state['settings']['pin']; await show_settings_step(event, user_id)
    elif data == b"send_now":
        await event.edit("🚀 **Disparando...**")
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
                await asyncio.sleep(0.3)
            except: pass
        await event.respond(f"✅ Sucesso: {success} grupos.", buttons=MAIN_MENU_REPLY)
        user_states.pop(user_id, None)

def parse_inline_buttons(text):
    if not text: return None
    rows = []
    for line in text.split('\n'):
        row = []
        for p in line.split('&&'):
            match = re.search(r'(.+?)(?:\s*->\s*|\s*--\s*|\s*-\s*)(https?://\S+)', p)
            if match: row.append(Button.url(match.group(1).strip(), match.group(2).strip()))
        if row: rows.append(row)
    return rows if rows else None

async def main():
    await bot.start(bot_token=BOT_TOKEN)
    print("🚀 Canais18 Bot Pro: Real-Time Sync & Stats Active!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
