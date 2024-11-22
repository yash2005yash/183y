from telethon import events, TelegramClient
import os
import asyncio


api_id = 23892949
api_hash = '44d07c2f92d37fe3c08e918ca11c2985'
guessSolver = TelegramClient('temp', api_id, api_hash)
chatid = -1002050945918#change
from telethon.tl.types import PhotoStrippedSize
@guessSolver.on(events.NewMessage(from_users=6573664248, pattern=".bin",outgoing=True))
async def guesser(event):
    await guessSolver.send_message(entity=chatid,message='/guess')
    for i in range(1,3000):
        await asyncio.sleep(30)
        await guessSolver.send_message(entity=chatid,message='/guess')
@guessSolver.on(events.NewMessage(from_users=572621020, pattern="Who's that pokemon?",chats=(int(chatid)),incoming=True))
async def guesser(event):
    for size in event.message.photo.sizes:
        if isinstance(size, PhotoStrippedSize):
            size = str(size)
            for file in (os.listdir("cache/")):
                with open(f"cache/{file}", 'r') as f:
                    file_content = f.read()
                if file_content == size:
                     chat = await event.get_chat()
                     fiel = file.split(".txt")[0]
                     await guessSolver.send_message(chat,fiel)
                     await asyncio.sleep(10)
                     await guessSolver.send_message(chat,"/guess")
                     break
            with open("cache.txt", 'w') as file:
                file.write(size)
            file.close()
                         
@guessSolver.on(events.NewMessage(from_users=572621020, pattern="The pokemon was ",chats=int(chatid)))
async def guesser(event):
    massage = ((event.message.text).split("The pokemon was ")[1]).split(".")[0]
    with open(f"cache/{massage}.txt", 'w') as file:
        with open("cache.txt",'r') as inf:
            cont = inf.read()
            file.write(cont)
        inf.close()
    file.close()
    os.remove("cache.txt")
    chat = await event.get_chat()
    await guessSolver.send_message(chat, "/guess")

@guessSolver.on(events.NewMessage(from_users=1235684181, pattern=".giveMe",incoming=True))
async def guesser(event):
    x = await guessSolver.send_message("@HeXamonbot",'/myinventory')
    async with guessSolver.conversation('@Hexamonbot') as conv:
      response = await conv.get_response(x.id)
      bal = response.text.split(": ")[1].split("**\n")[0]
    if bal != '0':
     await asyncio.sleep(2)
     await event.reply(("/give "+str(bal)))
              
guessSolver.start()
guessSolver.run_until_disconnected()