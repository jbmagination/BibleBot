"""
    Copyright (c) 2018 Elliott Pardee <me [at] vypr [dot] xyz>
    This file is part of BibleBot.

    BibleBot is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    BibleBot is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with BibleBot.  If not, see <http://www.gnu.org/licenses/>.
"""

import asyncio
import configparser
import datetime
import os
import time

import discord

import central
from bible_modules import biblegateway, rev, bibleutils
from data.BGBookNames import start as bg_book_names
from handlers.commandlogic.settings import languages
from handlers.commandlogic.settings import versions
from handlers.commandlogic.settings import misc
from handlers.commands import CommandHandler
from handlers.verses import VerseHandler

dir_path = os.path.dirname(os.path.realpath(__file__))

config = configparser.ConfigParser()
config.read(dir_path + "/config.ini")

configVersion = configparser.ConfigParser()
configVersion.read(dir_path + "/config.example.ini")


class BibleBot(discord.AutoShardedClient):
    def __init__(self, *args, loop=None, **kwargs):
        super().__init__(*args, loop=loop, **kwargs)
        self.bg_task = self.loop.create_task(self.run_timed_votds())
        self.current_page = None
        self.total_pages = None

    async def on_ready(self):
        mod_time = os.path.getmtime(dir_path + "/data/BGBookNames/books.json")

        now = time.time()
        one_week_ago = now - 60 * 60 * 24 * 7  # seven days to seconds

        if mod_time < one_week_ago:
            bg_book_names.get_books()

        if int(config["BibleBot"]["shards"]) < 2:
            activity = discord.Game(central.version + " | Shard: 1 / 1")
            await self.change_presence(status=discord.Status.online, activity=activity)

            central.log_message("info", 1, "global", "global", "connected")

    async def on_shard_ready(self, shard_id):
        activity = discord.Game(central.version + " | Shard: " + str(shard_id + 1) + " / " +
                                str(config["BibleBot"]["shards"]))
        await self.change_presence(status=discord.Status.online, activity=activity, shard_id=shard_id)

        central.log_message("info", shard_id + 1, "global", "global", "connected")

    async def run_timed_votds(self):
        await self.wait_until_ready()

        while not self.is_closed():
            # noinspection PyBroadException
            try:
                # a nice list comprehension for getting all the servers with votd stuff set
                results = [x for x in central.guildDB.all() if "channel" in x and "time" in x]

                for item in results:
                    if "channel" in item and "time" in item:
                        channel = self.get_channel(int(item["channel"]))
                        votd_time = item["time"]

                        try:
                            version = versions.get_guild_version(channel.guild)
                            lang = languages.get_guild_language(channel.guild)
                        except AttributeError:
                            version = None
                            lang = "english_us"

                        lang = getattr(central.languages, lang)

                        if version is None:
                            version = "NRSV"

                        current_time = datetime.datetime.utcnow().strftime("%H:%M")

                        if votd_time == current_time:
                            await channel.send("Here is today's verse of the day:")
                            if version != "REV":
                                verse = bibleutils.get_votd()
                                result = biblegateway.get_result(verse, version, "enable", "enable")

                                content = "```Dust\n" + result["title"] + "\n\n" + result["text"] + "```"
                                response_string = "**" + result["passage"] + " - " + result["version"] + \
                                                  "**\n\n" + content

                                if len(response_string) < 2000:
                                    await channel.send(response_string)
                                elif len(response_string) > 2000:
                                    if len(response_string) < 3500:
                                        split_text = central.splitter(result["text"])

                                        content1 = "```Dust\n" + result["title"] + "\n\n" + split_text["first"] + "```"
                                        response_string1 = "**" + result["passage"] + " - " + \
                                                           result["version"] + "**\n\n" + content1

                                        content2 = "```Dust\n " + split_text["second"] + "```"

                                        await channel.send(response_string1)
                                        await channel.send(content2)
                                    else:
                                        await channel.send(lang["passagetoolong"])
                            else:
                                verse = bibleutils.get_votd()
                                result = rev.get_result(verse, "enable")

                                content = "```Dust\n" + result["title"] + "\n\n" + result["text"] + "```"
                                response_string = "**" + result["passage"] + " - " + result["version"] + \
                                                  "**\n\n" + content

                                if len(response_string) < 2000:
                                    await channel.send(response_string)
                                elif len(response_string) > 2000:
                                    if len(response_string) < 3500:
                                        split_text = central.splitter(result["text"])

                                        content1 = "```Dust\n" + result["title"] + "\n\n" + split_text["first"] + "```"
                                        response_string1 = "**" + result["passage"] + " - " + \
                                                           result["version"] + "**\n\n" + content1

                                        content2 = "```Dust\n " + split_text["second"] + "```"

                                        await channel.send(response_string1)
                                        await channel.send(content2)
                                    else:
                                        await channel.send(lang["passagetoolong"])
            except Exception:
                pass

            # central.log_message("info", shard, "votd_sched", "global", "Sending VOTDs...")
            await asyncio.sleep(60)

    async def on_message(self, raw):
        await self.wait_until_ready()

        sender = raw.author
        identifier = sender.name + "#" + sender.discriminator
        channel = raw.channel
        message = raw.content
        guild = None

        if config["BibleBot"]["devMode"] == "True":
            if str(sender.id) != config["BibleBot"]["owner"]:
                return

        if sender == self.user:
            return

        if central.is_optout(str(sender.id)):
            return

        language = languages.get_language(sender)

        if hasattr(channel, "guild"):
            guild = channel.guild

            if language is None:
                language = languages.get_guild_language(guild)

            if hasattr(channel.guild, "name"):
                source = channel.guild.name + "#" + channel.name
            else:
                source = "unknown (direct messages?)"

            if "Discord Bot" in channel.guild.name:
                if sender.id != config["BibleBot"]["owner"]:
                    return
        else:
            source = "unknown (direct messages?)"

        if guild is None:
            shard = 1
        else:
            shard = guild.shard_id + 1

        if language is None:
            language = "english_us"

        embed_or_reaction_not_allowed = False

        if guild is not None:
            try:
                perms = channel.permissions_for(guild.me)

                if perms is not None:
                    if not perms.send_messages or not perms.read_messages:
                        return

                    if not perms.embed_links:
                        embed_or_reaction_not_allowed = True

                    if not perms.add_reactions:
                        embed_or_reaction_not_allowed = True

                    if not perms.manage_messages or not perms.read_message_history:
                        embed_or_reaction_not_allowed = True
            except AttributeError:
                pass

        if message.startswith(config["BibleBot"]["commandPrefix"]):
            command = message[1:].split(" ")[0]
            args = message.split(" ")

            if not isinstance(args.pop(0), str):
                args = None

            raw_language = getattr(central.languages, language).raw_object

            cmd_handler = CommandHandler()

            res = cmd_handler.process_command(bot, command, language, sender, guild, channel, args)

            original_command = ""
            self.current_page = 1

            if res is None:
                return

            if res is not None:
                if "leave" in res:
                    if res["leave"] == "this":
                        if guild is not None:
                            await guild.leave()
                    else:
                        for item in bot.guilds:
                            if str(item.id) == res["leave"]:
                                await item.leave()
                                await channel.send("Left " + str(item.name))

                    central.log_message("info", shard, identifier, source, "+leave")
                    return

                if "isError" not in res:
                    if guild is not None:
                        is_banned, reason = central.is_banned(str(guild.id))

                        if is_banned:
                            await channel.send("This server has been banned from using BibleBot. Reason: `" +
                                               reason + "`.")
                            await channel.send("If this is invalid, the server owner may appeal by contacting " +
                                               "vypr#0001.")

                            central.log_message("err", shard, identifier, source, "Server is banned.")
                            return

                    is_banned, reason = central.is_banned(str(sender.id))
                    if is_banned:
                        await channel.send(sender.mention + " You have been banned from using BibleBot. " +
                                           "Reason: `" + reason + "`.")
                        await channel.send("You may appeal by contacting vypr#0001.")

                        central.log_message("err", shard, identifier, source, "User is banned.")
                        return

                    if embed_or_reaction_not_allowed:
                        await channel.send("I need 'Embed Links', 'Read Message History', "
                                           + "'Manage Messages', and 'Add Reactions' permissions!")
                        return

                    if "announcement" not in res:
                        if "twoMessages" in res:
                            await channel.send(res["firstMessage"])
                            await channel.send(res["secondMessage"])
                        elif "paged" in res:
                            self.total_pages = len(res["pages"])

                            msg = await channel.send(embed=res["pages"][0])

                            await msg.add_reaction("⬅")
                            await msg.add_reaction("➡")

                            def check(r, u):
                                if r.message.id == msg.id:
                                    if str(r.emoji) == "⬅":
                                        if u.id != bot.user.id:
                                            if self.current_page != 1:
                                                self.current_page -= 1
                                                return True
                                    elif str(r.emoji) == "➡":
                                        if u.id != bot.user.id:
                                            if self.current_page != self.total_pages:
                                                self.current_page += 1
                                                return True

                            continue_paging = True

                            try:
                                while continue_paging:
                                    reaction, user = await bot.wait_for('reaction_add', timeout=120.0, check=check)
                                    await reaction.message.edit(embed=res["pages"][self.current_page - 1])

                                    reaction, user = await bot.wait_for('reaction_remove', timeout=120.0, check=check)
                                    await reaction.message.edit(embed=res["pages"][self.current_page - 1])

                            except (asyncio.TimeoutError, IndexError):
                                await msg.clear_reactions()
                        else:
                            if "reference" not in res and "text" not in res:
                                # noinspection PyBroadException
                                try:
                                    await channel.send(embed=res["message"])
                                except Exception:
                                    pass
                            else:
                                if res["message"] is not None:
                                    await channel.send(res["message"])
                                else:
                                    await channel.send("Done.")

                        for original_command_name in raw_language["commands"].keys():
                            untranslated = ["setlanguage", "userid", "ban", "unban",
                                            "reason", "optout", "unoptout", "eval",
                                            "jepekula", "joseph", "tiger"]

                            if raw_language["commands"][original_command_name] == command:
                                original_command = original_command_name
                            elif command in untranslated:
                                original_command = command
                    else:
                        for original_command_name in raw_language["commands"].keys():
                            if raw_language["commands"][original_command_name] == command:
                                original_command = original_command_name

                        count = 1
                        total = len(bot.guilds)

                        for item in bot.guilds:
                            announce_tuple = misc.get_guild_announcements(item, False)

                            # noinspection PyBroadException
                            try:
                                if "Discord Bot" not in item.name:
                                    if announce_tuple is not None:
                                        chan, setting = announce_tuple
                                    else:
                                        chan = "preferred"
                                        setting = True

                                    preferred = ["misc", "bots", "meta", "hangout", "fellowship", "lounge",
                                                 "congregation", "general", "bot-spam", "staff"]

                                    if chan != "preferred" and setting:
                                        ch = self.get_channel(chan)
                                        perm = ch.permissions_for(item.me)

                                        if perm.read_messages and perm.send_messages:
                                            await channel.send(str(count) + "/" + str(total) + " - " + item.name +
                                                               " :white_check_mark:")

                                            if perm.embed_links:
                                                await ch.send(embed=res["message"])
                                            else:
                                                await ch.send(res["message"].fields[0].value)
                                        else:
                                            await channel.send(str(count) + "/" + str(total) + " - " + item.name +
                                                               " :regional_indicator_x:")
                                    elif chan == "preferred" and setting:
                                        sent = False

                                        for ch in item.text_channels:
                                            try:
                                                if not sent:
                                                    for name in preferred:
                                                        if ch.name == name:
                                                            perm = ch.permissions_for(item.me)

                                                            if perm.read_messages and perm.send_messages:
                                                                await channel.send(str(count) + "/" + str(total) +
                                                                                   " - " + item.name +
                                                                                   " :white_check_mark:")
                                                                if perm.embed_links:
                                                                    await ch.send(embed=res["message"])
                                                                else:
                                                                    await ch.send(res["message"].fields[0].value)
                                                            else:
                                                                await channel.send(str(count) + "/" + str(total) +
                                                                                   " - " + item.name +
                                                                                   " :regional_indicator_x:")

                                                            sent = True
                                            except (AttributeError, IndexError):
                                                sent = True
                                    else:
                                        await channel.send(str(count) + "/" + str(total) + " - " + item.name +
                                                           " :regional_indicator_x:")
                            except Exception:
                                pass

                            count += 1

                        await channel.send("Done.")

                    clean_args = str(args).replace(",", " ").replace("[", "").replace("]", "")
                    clean_args = clean_args.replace("\"", "").replace("'", "").replace("  ", " ")
                    clean_args = clean_args.replace("\n", "").strip()

                    if original_command == "puppet":
                        clean_args = ""
                    elif original_command == "eval":
                        clean_args = ""
                    elif original_command == "announce":
                        clean_args = ""

                    central.log_message(res["level"], shard, identifier, source,
                                        "+" + original_command + " " + clean_args)
                else:
                    # noinspection PyBroadException
                    try:
                        await channel.send(embed=res["return"])
                    except Exception:
                        pass
        else:
            verse_handler = VerseHandler()

            result = verse_handler.process_raw_message(raw, sender, language, guild)

            if result is not None:
                if "invalid" not in result and "spam" not in result:
                    for item in result:
                        try:
                            if "twoMessages" in item:
                                if guild is not None:
                                    is_banned, reason = central.is_banned(str(guild.id))
                                    if is_banned:
                                        await channel.send("This server has been banned from using BibleBot. " +
                                                           "Reason: `" + reason + "`.")
                                        await channel.send(
                                            "If this is invalid, the server owner may appeal by contacting " +
                                            "vypr#0001.")

                                        central.log_message("err", shard, identifier, source, "Server is banned.")
                                        return

                                is_banned, reason = central.is_banned(str(sender.id))
                                if is_banned:
                                    await channel.send(sender.mention + " You have been banned from using BibleBot. " +
                                                       "Reason: `" + reason + "`.")
                                    await channel.send("You may appeal by contacting vypr#0001.")

                                    central.log_message("err", shard, identifier, source, "User is banned.")
                                    return

                                if embed_or_reaction_not_allowed:
                                    await channel.send("I need 'Embed Links', 'Read Message History', "
                                                       + "'Manage Messages', and 'Add Reactions' permissions!")
                                    return
                                await channel.send(item["firstMessage"])
                                await channel.send(item["secondMessage"])
                            elif "message" in item:
                                if guild is not None:
                                    is_banned, reason = central.is_banned(str(guild.id))
                                    if is_banned:
                                        await channel.send("This server has been banned from using BibleBot. " +
                                                           "Reason: `" + reason + "`.")
                                        await channel.send(
                                            "If this is invalid, the server owner may appeal by contacting " +
                                            "vypr#0001.")

                                        central.log_message("err", shard, identifier, source, "Server is banned.")
                                        return

                                is_banned, reason = central.is_banned(str(sender.id))
                                if is_banned:
                                    await channel.send(sender.mention + " You have been banned from using BibleBot. " +
                                                           "Reason: `" + reason + "`.")
                                    await channel.send("You may appeal by contacting vypr#0001.")

                                    central.log_message("err", shard, identifier, source, "User is banned.")
                                    return

                                if embed_or_reaction_not_allowed:
                                    await channel.send("I need 'Embed Links', 'Read Message History', "
                                                       + "'Manage Messages', and 'Add Reactions' permissions!")
                                    return
                                await channel.send(item["message"])
                        except KeyError:
                            pass

                        if "reference" in item:
                            central.log_message(item["level"], shard, identifier, source, item["reference"])
                else:
                    if "spam" in result:
                        await channel.send(result["spam"])


if int(config["BibleBot"]["shards"]) > 1:
    bot = BibleBot(shard_count=int(config["BibleBot"]["shards"]))
else:
    bot = BibleBot()

central.log_message("info", 0, "global", "global", central.version + " by Elliott Pardee (vypr)")
bot.run(config["BibleBot"]["token"])
