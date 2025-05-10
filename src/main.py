import os
import discord
from discord.ext import commands
import asyncio
import json
import config
from discord.ext import tasks
from datetime import datetime, time

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.messages = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

client = discord.Client(intents=intents)

user_settings = {}


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ ログインしました: {bot.user}")


@client.event
async def on_message(message):
    # 自身が送信したメッセージには反応しない
    if message.author == client.user:
        return

    if client.user in message.mentions:
        # data.jsonを読み込む
        try:
            await get_user_settings(user_settings)
        except FileNotFoundError:
            print("⚠️ ユーザー設定ファイルが見つかりません。")

        # チャンネルでセットアップ案内を送信し、DMでセットアップ開始
        try:
            # DMで 活動調査 を実行
            dm_channel = await member.create_dm()
            await dm_channel.send(
                "👋 活動調査を行います。オンステ情報を入力してください。"
            )
            await activity_investigation(member, dm_channel)
        except Exception as e:
            print(f"⚠️ 初期設定送信中にエラー: {e}")


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
                return (
                    u == user
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in ["✅", "❎"]
                )

            reaction, _ = await bot.wait_for("reaction_add", check=check)
            data["stage"][key] = str(reaction.emoji) == "✅"

    # 修正付き確認フェーズ
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
                    f"**{data['stage'][key]}**: {'乗る' if data['stage'][key] else '乗らない'}"
                    for i, key in enumerate(["first", "second", "german", "takata"])
                )
                + "\n\n❗️ 修正したい項目の絵文字を押してください\n✅ 問題なければ確認完了です",
                color=discord.Color.orange(),
            )

            msg = await channel.send(embed=confirm_embed)
            for emoji in emoji_map:
                await msg.add_reaction(emoji)

            def check(reaction, u):
                return (
                    u == user
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in emoji_map
                )

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
                return (
                    u == user
                    and reaction.message.id == msg.id
                    and str(reaction.emoji) in ["✅", "❎"]
                )

            reaction, _ = await bot.wait_for("reaction_add", check=stage_check)
            data["stage"][selected] = str(reaction.emoji) == "✅"

        # 実行フェーズ

        # ギルドID → ロール付与処理（元コードをそのまま続けて使用）
        guild_id = read_guild_id_from_file()
        if guild_id is None:
            await channel.send(
                "⚠️ サーバーIDが正しく読み込めませんでした。管理者にお問い合わせください。"
            )
            return

        guild = bot.get_guild(guild_id)
        if guild is None:
            await channel.send(
                "⚠️ サーバーが見つかりませんでした。Botが参加しているか確認してください。"
            )
            return

        role = discord.utils.get(guild.roles, name=config.CONFIRMATION_ROLE_NAME)
        if role is None:
            await channel.send(
                "⚠️ ロールが見つかりませんでした。管理者にお問い合わせください。"
            )
            return

        member = guild.get_member(user.id)

        await activity_investigation()
        await confirm_activity_investigation()

        embed_done = discord.Embed(
            title="✅ オンステ情報の入力が完了しました！",
            description=(
                f"**副指揮**: {'乗る' if data['stage']['first'] else '乗らない'}\n"
                f"**正指揮**: {'乗る' if data['stage']['second'] else '乗らない'}\n"
                f"**ドイツリート**: {'乗る' if data['stage']['german'] else '乗らない'}"
                f"**髙田曲**: {'乗る' if data['stage']['takata'] else '乗らない'}"
            ),
            color=discord.Color.green(),
        )

        await channel.send(embed=embed_done)

        # 副指揮ロールの付与
        if data["stage"]["first"]:
            first_role = discord.utils.get(guild.roles, name="副指揮")
            if first_role:
                await member.add_roles(first_role)
                await channel.send("🎶 `副指揮` ロールを付与しました！")
            else:
                await channel.send("⚠️ `副指揮` ロールが見つかりませんでした")

        # 正指揮ロールの付与
        if data["stage"]["second"]:
            second_role = discord.utils.get(guild.roles, name="正指揮")
            if second_role:
                await member.add_roles(second_role)
                await channel.send("🎶 `正指揮` ロールを付与しました！")
            else:
                await channel.send("⚠️ `正指揮` ロールが見つかりませんでした")

        # 3ステロールの付与
        if data["stage"]["german"]:
            german_role = discord.utils.get(guild.roles, name="ドイツリート")
            if german_role:
                await member.add_roles(german_role)
                await channel.send("🎶 `ドイツリート` ロールを付与しました！")
            else:
                await channel.send("⚠️ `ドイツリート` ロールが見つかりませんでした")

        # 4ステロールの付与
        if data["stage"]["takata"]:
            takata_role = discord.utils.get(guild.roles, name="髙田曲")
            if takata_role:
                await member.add_roles(takata_role)
                await channel.send("🎶 `髙田曲` ロールを付与しました！")
            else:
                await channel.send("⚠️ `髙田曲` ロールが見つかりませんでした")

        # 保存と完了メッセージ
        user_settings[user.id] = data
        save_user_settings(user_settings)


def get_user_settings(data, filename="./src/user_settings.json"):
    with open(filename, "r", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def save_user_settings(data, filename="./src/user_settings.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def read_guild_id_from_file(filename="src/guild_id.txt"):
    try:
        with open(filename, "r") as f:
            guild_id = f.read().strip()
            return int(guild_id)  # ファイルから読み込んだIDを整数として返す
    except FileNotFoundError:
        print(f"❌ {filename} が見つかりませんでした")
        return None
    except ValueError:
        print("❌ guild_id.txt に無効なIDが含まれています")
        return None


def read_term_of_execution_from_file(filename="src/term_of_execution.txt"):
    try:
        with open(filename, "r") as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


@bot.tree.command(
    name="set_server-id", description="guild_id.txt にサーバーIDを記録します"
)
async def set_server_id(interaction: discord.Interaction):
    await interaction.response.send_message(
        "サーバーIDをこのチャンネルで送信してください。"
    )

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for(
            "message", check=check, timeout=60.0
        )  # 60秒のタイムアウト
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "⚠️ 時間切れです。もう一度 `/set_server-id` を実行してください。"
        )
        return

    file_path = os.path.join(os.path.dirname(__file__), "guild_id.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"{msg.content}\n")

    await interaction.followup.send("✅ サーバーIDを `guild_id.txt` に書き込みました。")


@bot.tree.command(
    name="set_term-of-execution",
    description="term_of_execution.txt に執行代を記録します",
)
async def set_term_of_execution(interaction: discord.Interaction):
    await interaction.response.send_message(
        "執行代の期を数字のみでこのチャンネルで送ってください。"
    )

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for(
            "message", check=check, timeout=60.0
        )  # 60秒のタイムアウト
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "⚠️ 時間切れです。もう一度 `/set_term-of-execution` を実行してください。"
        )
        return

    if not msg.content.isdigit():
        await interaction.followup.send(
            "⚠️ 入力は数字のみでお願いします。もう一度 `/set_term-of-execution` を実行してください。"
        )
        return

    file_path = os.path.join(os.path.dirname(__file__), "term_of_execution.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"{msg.content}\n")

    await interaction.followup.send(
        "✅ 執行代を `term_of_execution.txt` に書き込みました。"
    )


@tasks.loop(time=time(hour=19, minute=0))  # 毎日19時に実行
async def check_birthdays():
    today = datetime.now()
    today_month = today.month
    today_day = today.day

    try:
        with open(user_settings.json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("ユーザー設定読み込みエラー:", e)
        return

    birthday_users = []
    for user_id, info in data.items():
        if (
            info.get("birth_month") == today_month
            and info.get("birth_day") == today_day
        ):
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
            await channel.send(
                f"🎂 本日誕生日のメンバー:\n{user_lines}\nお祝いの準備をしましょう！"
            )


bot.run(config.DISCORD_TOKEN)
