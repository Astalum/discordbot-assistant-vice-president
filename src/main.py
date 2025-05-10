import os
import discord
from discord.ext import commands, tasks
import asyncio
import json
import config
from datetime import datetime, time

# ファイルパスを定数化
USER_SETTINGS_FILE = "./src/user_settings.json"
GUILD_ID_FILE = "./src/guild_id.txt"

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.messages = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
user_settings = {}


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ ログインしました: {bot.user}")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user in message.mentions:
        try:
            data = get_user_settings()
        except FileNotFoundError:
            print("⚠️ ユーザー設定ファイルが見つかりません。")
            return
        try:
            await broadcast_dm()

        except Exception as e:
            print(f"⚠️ 初期設定送信中にエラー: {e}")


async def broadcast_dm(interaction: discord.Interaction):
    await interaction.response.send_message("📨 DMの送信を開始します...")

    try:
        data = get_user_settings()
    except Exception as e:
        await interaction.followup.send(f"⚠️ ユーザー設定の読み込みに失敗しました: {e}")
        return

    guild_id = read_guild_id_from_file()
    if guild_id is None:
        await interaction.followup.send("⚠️ サーバーIDが読み込めませんでした")
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        await interaction.followup.send("⚠️ サーバーが見つかりませんでした")
        return

    success_count = 0
    fail_count = 0

    for user_id_str, info in data.items():
        try:
            user_id = int(user_id_str)
            member = guild.get_member(user_id)

            if member is None:
                print(f"⚠️ メンバーが見つかりません: {user_id}")
                fail_count += 1
                continue

            dm = await member.create_dm()
            await dm.send(f"👋 {info.get('name_kanji', '不明')}さん、こんにちは！以下のメッセージにリアクションをして活動調査に回答してください")
            tmp = {}  # stage項目を初期化
            await activity_investigation(int(user_id_str), dm, tmp)
            await confirm_activity_investigation(int(user_id_str), dm, tmp)
            success_count += 1

        except Exception as e:
            print(f"❌ DM送信失敗 ({user_id_str}): {e}")
            fail_count += 1

    await interaction.followup.send(f"✅ DM送信完了！成功: {success_count}人 / 失敗: {fail_count}人")


async def activity_investigation(user, channel, data):
    stages = {
        "first": "副指揮ステージ",
        "second": "正指揮ステージ",
        "german": "ドイツリートステージ",
        "takata": "髙田曲ステージ",
    }

    for key, label in stages.items():
        embed = discord.Embed(
            title=f"あなたは{label}にオンステしますか？",
            description="✅：はい\n❎：いいえ\n\n該当するリアクションをクリックしてください",
            color=discord.Color.blue(),
        )
        msg = await channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❎")

        def check(reaction, u):
            return u == user and reaction.message.id == msg.id and str(reaction.emoji) in ["✅", "❎"]

        reaction, _ = await bot.wait_for("reaction_add", check=check)
        data["stage"][key] = str(reaction.emoji) == "✅"


async def confirm_activity_investigation(user, channel, data):
    emoji_map = {
        "1️⃣": "first",
        "2️⃣": "second",
        "3️⃣": "german",
        "4️⃣": "takata",
        "✅": "confirm",
    }

    labels = {
        "first": "副指揮",
        "second": "正指揮",
        "german": "ドイツリート",
        "takata": "髙田曲",
    }

    while True:
        confirm_embed = discord.Embed(
            title="📝 入力内容を確認してください",
            description="\n".join(
                f"**{labels[key]}**: {'乗る' if data['stage'][key] else '乗らない'}"
                for key in ["first", "second", "german", "takata"]
            )
            + "\n\n❗️ 修正したい項目の絵文字を押してください\n✅ 問題なければ確認完了です",
            color=discord.Color.orange(),
        )

        msg = await channel.send(embed=confirm_embed)
        for emoji in emoji_map:
            await msg.add_reaction(emoji)

        def check(reaction, u):
            return u == user and reaction.message.id == msg.id and str(reaction.emoji) in emoji_map

        reaction, _ = await bot.wait_for("reaction_add", check=check)
        selected = emoji_map[str(reaction.emoji)]
        await msg.delete()

        if selected == "confirm":
            break

        label = labels[selected]
        embed = discord.Embed(
            title=f"✏️ {label}に乗るかどうかを再選択してください：",
            description="✅：はい\n❎：いいえ\n\n該当するリアクションをクリックしてください",
            color=discord.Color.blue(),
        )
        msg = await channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❎")

        def stage_check(reaction, u):
            return u == user and reaction.message.id == msg.id and str(reaction.emoji) in ["✅", "❎"]

        reaction, _ = await bot.wait_for("reaction_add", check=stage_check)
        data["stage"][selected] = str(reaction.emoji) == "✅"


async def finalize_roles_and_save(user, data, channel):
    guild_id = read_guild_id_from_file()
    if guild_id is None:
        await channel.send("⚠️ サーバーIDが正しく読み込めませんでした。管理者にお問い合わせください。")
        return

    guild = bot.get_guild(guild_id)
    if guild is None:
        await channel.send("⚠️ サーバーが見つかりませんでした。Botが参加しているか確認してください。")
        return

    member = guild.get_member(user.id)

    embed_done = discord.Embed(
        title="✅ オンステ情報の入力が完了しました！",
        description=(
            f"**副指揮**: {'乗る' if data['stage']['first'] else '乗らない'}\n"
            f"**正指揮**: {'乗る' if data['stage']['second'] else '乗らない'}\n"
            f"**ドイツリート**: {'乗る' if data['stage']['german'] else '乗らない'}\n"
            f"**髙田曲**: {'乗る' if data['stage']['takata'] else '乗らない'}"
        ),
        color=discord.Color.green(),
    )
    await channel.send(embed=embed_done)

    # ロールの付与
    for key, role_name in {
        "first": "副指揮",
        "second": "正指揮",
        "german": "ドイツリート",
        "takata": "髙田曲",
    }.items():
        if data["stage"].get(key):
            role = discord.utils.get(guild.roles, name=role_name)
            if role:
                await member.add_roles(role)
                await channel.send(f"🎶 `{role_name}` ロールを付与しました！")
            else:
                await channel.send(f"⚠️ `{role_name}` ロールが見つかりませんでした")

    user_settings[user.id] = data
    save_user_settings(user_settings)


def get_user_settings(filename=USER_SETTINGS_FILE):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def save_user_settings(data, filename=USER_SETTINGS_FILE):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def read_guild_id_from_file(filename=GUILD_ID_FILE):
    try:
        with open(filename, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        print("❌ サーバーIDの読み込みに失敗しました")
        return None


@bot.tree.command(name="set_server-id", description="guild_id.txt にサーバーIDを記録します")
async def set_server_id(interaction: discord.Interaction):
    await interaction.response.send_message("サーバーIDをこのチャンネルで送信してください。")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=60.0)
    except asyncio.TimeoutError:
        await interaction.followup.send("⚠️ 時間切れです。もう一度 `/set_server-id` を実行してください。")
        return

    with open(GUILD_ID_FILE, "w", encoding="utf-8") as f:
        f.write(f"{msg.content}\n")

    await interaction.followup.send("✅ サーバーIDを `guild_id.txt` に書き込みました。")


@tasks.loop(time=time(hour=18, minute=30))  # 毎日18:30に実行
async def check_birthdays():
    today = datetime.now()
    today_month = today.month
    today_day = today.day

    try:
        with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("ユーザー設定読み込みエラー:", e)
        return

    birthday_users = []
    for user_id, info in data.items():
        if info.get("birth_month") == today_month and info.get("birth_day") == today_day:
            name = info.get("name_kanji", "不明")
            part = info.get("part", "不明")
            term = info.get("term", "不明")
            birthday_users.append(f"{name}（{term}期・{part}）")

    if not birthday_users:
        return

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name="副団長用")
        if channel:
            user_lines = "\n".join(f"🎉 {user}" for user in birthday_users)
            await channel.send(f"🎂 本日誕生日のメンバー:\n{user_lines}\nお祝いの準備をしましょう！")


bot.run(config.DISCORD_TOKEN)
