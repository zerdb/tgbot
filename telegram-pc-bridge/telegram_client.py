import json
import socket
import threading
import urllib.parse
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from pc_controller import PCController

API_ROOT="https://api.telegram.org"

class TelegramBotClient:
    def __init__(self,token,on_message,on_status,allowed_user_id=None):
        self.token=token.strip(); self.on_message=on_message; self.on_status=on_status
        self.allowed_user_id=int(allowed_user_id) if str(allowed_user_id or "").strip() else None
        self.running=False; self.offset=0; self.thread=None; self.stop_event=threading.Event()
        self.controller=PCController(); self.audit_file=Path(__file__).with_name("audit.log"); self.download_dir=Path(__file__).with_name("downloads"); self.download_dir.mkdir(exist_ok=True)

    def api(self,method,params=None,timeout=20):
        data=urllib.parse.urlencode(params or {}).encode(); req=urllib.request.Request(f"{API_ROOT}/bot{self.token}/{method}",data=data)
        with urllib.request.urlopen(req,timeout=timeout) as r: payload=json.loads(r.read().decode())
        if not payload.get("ok"): raise RuntimeError(payload.get("description","Telegram API error"))
        return payload["result"]

    def keyboard(self):
        return {"inline_keyboard":[
            [{"text":"🖥 ПК","callback_data":"menu_pc"},{"text":"📸 Скриншот","callback_data":"cmd:/screenshot"}],
            [{"text":"📊 Мониторинг","callback_data":"menu_monitor"}],
            [{"text":"📁 Файлы","callback_data":"menu_files"},{"text":"🪟 Окна","callback_data":"menu_windows"}],
            [{"text":"📱 Приложения","callback_data":"menu_apps"},{"text":"🧰 Проекты","callback_data":"menu_projects"}],
            [{"text":"⚙️ Система","callback_data":"menu_system"},{"text":"📋 Журнал","callback_data":"menu_log"}]]}

    def subkeyboard(self,kind):
        m={
        "menu_pc":[[("🖥 Статус","cmd:/status"),("📸 Скриншот","cmd:/screenshot")],[("🔒 Блокировка","confirm:/lock"),("🖥 Свернуть всё","confirm:/minimize_all")],[("⬅️ Назад","menu:root")]],
        "menu_monitor":[[("📊 Процессы","cmd:/processes"),("💽 Диски","cmd:/drives")],[("🌐 Сеть","cmd:/network"),("⬅️ Назад","menu:root")]],
        "menu_files":[[("📂 Рабочий стол","files:desktop"),("📥 Загрузки","files:downloads")],[("📄 Документы","files:documents"),("⬆️ Файл → ПК","info:upload")],[("⬅️ Назад","menu:root")]],
        "menu_windows":[[("🪟 Список окон","cmd:/windows"),("🖥 Свернуть всё","confirm:/minimize_all")],[("⬅️ Назад","menu:root")]],
        "menu_apps":[[("📝 Блокнот","cmd:/run notepad"),("🧮 Калькулятор","cmd:/run calculator")],[("📁 Проводник","cmd:/run explorer"),("⛔ Стоп…","info:stop")],[("⬅️ Назад","menu:root")]],
        "menu_projects":[[("📦 Список","cmd:/projects")],[("▶️ Tetris","cmd:/project tkinter-tetris"),("▶️ Sorter","cmd:/project tkinter-file-sorter")],[("⬅️ Назад","menu:root")]],
        "menu_system":[[("📋 Clipboard","menu_clip"),("⌨️ Hotkeys","menu_hotkeys")],[("⚙️ Службы","cmd:/services"),("⬅️ Назад","menu:root")]],
        "menu_clip":[[("📋 Прочитать","cmd:/clip_get"),("✏️ Записать…","info:clipset")],[("⬅️ Назад","menu_system")]],
        "menu_hotkeys":[[("Ctrl+C","cmd:/hotkey ctrl_c"),("Ctrl+V","cmd:/hotkey ctrl_v")],[("Alt+Tab","cmd:/hotkey alt_tab"),("Ctrl+Shift+Esc","cmd:/hotkey ctrl_shift_esc")],[("Win+D","cmd:/hotkey win_d"),("⬅️ Назад","menu_system")]]
        }
        return {"inline_keyboard":[[{"text":a,"callback_data":b} for a,b in row] for row in m.get(kind,[[( "⬅️ Назад","menu:root")]])]}

    def send_message(self,chat_id,text,markup=None):
        self.api("sendMessage",{"chat_id":chat_id,"text":text,"reply_markup":json.dumps(markup or self.keyboard(),ensure_ascii=False)},timeout=15)

    def answer_callback(self,qid,text):
        try:self.api("answerCallbackQuery",{"callback_query_id":qid,"text":text},timeout=5)
        except Exception:pass

    def edit_menu(self,chat_id,msg_id,text,markup):
        self.api("editMessageText",{"chat_id":chat_id,"message_id":msg_id,"text":text,"reply_markup":json.dumps(markup,ensure_ascii=False)},timeout=10)

    def test(self): return self.api("getMe",timeout=10)

    def start(self):
        if self.running:return
        self.stop_event.clear(); self.running=True; self.thread=threading.Thread(target=self._poll,daemon=True); self.thread.start()

    def stop(self):
        self.running=False; self.stop_event.set(); self.on_status("offline","Прослушивание остановлено")

    def _poll(self):
        self.on_status("connecting","Подключение к Telegram...")
        try:
            me=self.test(); self.on_status("online",f"Бот @{me.get('username','')} подключён")
            if self.allowed_user_id:self.send_message(self.allowed_user_id,"🟢 PC Bridge v2 запущен.",self.keyboard())
        except Exception as e:self.running=False; self.on_status("error",f"Ошибка подключения: {e}"); return
        while self.running and not self.stop_event.is_set():
            try:
                updates=self.api("getUpdates",{"offset":self.offset,"timeout":0,"allowed_updates":json.dumps(["message","callback_query"])},timeout=3)
                for u in updates:
                    self.offset=u["update_id"]+1
                    if u.get("callback_query"): self._callback(u["callback_query"])
                    elif u.get("message"): self._message(u["message"])
                if not updates:self.stop_event.wait(.5)
            except (TimeoutError,socket.timeout): self.stop_event.wait(.2)
            except Exception as e:
                if self.running:self.on_status("error",f"Ошибка связи: {e}"); self.stop_event.wait(2)

    def _authorized(self,msg):
        return self.allowed_user_id is None or msg.get("from",{}).get("id")==self.allowed_user_id

    def _audit(self, user_id, action, result):
        try:
            line = f"{datetime.now().isoformat(timespec='seconds')} | user={user_id} | {action} | {result}\\n"
            self.audit_file.open("a", encoding="utf-8").write(line)
        except Exception:
            pass

    def _result(self,base,ok,text):
        self._audit(base.get("user_id"), base.get("action", "command"), "SUCCESS" if ok else "FAILED")
        self.on_message({**base,"type":"result","text":("SUCCESS: " if ok else "FAILED: ")+text})

    def _message(self,msg):
        if not self._authorized(msg): return
        chat=msg.get("chat",{}); base={"chat_id":chat.get("id"),"user_id":msg.get("from",{}).get("id"),"first_name":msg.get("from",{}).get("first_name",""),"action":""}
        if "text" in msg:
            text=msg["text"]
            base["action"]=text
            if text in ("/start","/help"):
                self.send_message(chat["id"],self.controller.help_text()); return
            if text.startswith("/"):
                ok,reply=self.controller.execute(text)
                if reply=="SCREENSHOT":
                    path,err=self.controller.screenshot()
                    if path:self.send_photo(chat["id"],path); self._result(base,True,"📸 Скриншот отправлен.")
                    else:self.send_message(chat["id"],err); self._result(base,False,err)
                elif reply.startswith("DOWNLOAD:"):
                    ok_path, path = self.controller.download_path(reply[9:])
                    if ok_path:
                        self.send_document(chat["id"], Path(path))
                        self._result(base, True, "📤 Файл отправлен.")
                    else:
                        self.send_message(chat["id"], path)
                        self._result(base, False, path)
                else:self.send_message(chat["id"],reply); self._result(base,ok,reply)
        elif "document" in msg:
            self._receive_upload(chat["id"],msg["document"])

    def _callback(self,q):
        if not self._authorized(q):return
        data=q.get("data",""); msg=q.get("message",{}); chat=msg.get("chat",{}); cid=chat.get("id")
        self.answer_callback(q["id"],"Ок")
        if data=="menu:root" or data=="menu_root": self.edit_menu(cid,msg["message_id"],"🎛 PC BRIDGE v2\nВыбери раздел:",self.keyboard()); return
        if data.startswith("menu_"):
            self.edit_menu(cid,msg["message_id"],"🎛 Раздел: "+data[5:],self.subkeyboard(data)); return
        if data=="info:stop": self.send_message(cid,"⛔ Для остановки доступны только allow-list: /stop notepad, /stop calculator, /stop explorer."); return
        if data=="info:clipset": self.send_message(cid,"✏️ Используй /clip_set <текст> — запись ограничена явной командой."); return
        if data=="info:upload": self.send_message(cid,"⬆️ Просто отправь мне файл как документ в Telegram. Он будет сохранён в Windows Downloads."); return
        if data.startswith("files:"):
            folder=data.split(":",1)[1]
            ok, listing=self.controller.list_files(folder)
            buttons=[]
            if ok:
                root=self.controller.allowed_folders.get(folder)
                if root:
                    try:
                        for p in sorted(root.iterdir(), key=lambda x:x.name.lower())[:40]:
                            if p.is_file():
                                rel=f"{folder}/{p.name}"
                                buttons.append([{"text":("📄 "+p.name)[:60],"callback_data":"file:"+urllib.parse.quote(rel,safe="")[:50]}])
                    except Exception:
                        pass
            buttons.append([{"text":"⬅️ Назад","callback_data":"menu_files"}])
            self.edit_menu(cid,msg["message_id"],listing+"\\n\\n👇 Нажми файл, чтобы отправить его в Telegram:",{"inline_keyboard":buttons})
            return
        if data.startswith("file:"):
            raw=urllib.parse.unquote(data[5:])
            ok_path,path=self.controller.download_path(raw)
            if ok_path:
                self.send_document(cid,Path(path))
                self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":"/download "+raw},True,"📤 Файл отправлен.")
            else:
                self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":"/download "+raw},False,path)
            return
        if data.startswith("confirm:"):
            action=data[8:]; self.send_message(cid,f"⚠️ Подтвердить действие?\n{action}",{"inline_keyboard":[[{"text":"⚠️ Подтвердить","callback_data":"yes:"+action},{"text":"❌ Отмена","callback_data":"cancel"}]]}); return
        if data=="cancel": self.answer_callback(q["id"],"Отменено"); return
        if data.startswith("yes:"):
            action=data[4:]; ok,reply=self.controller.execute(action); self.send_message(cid,reply,self.keyboard()); self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":action},ok,reply); return
        if data.startswith("cmd:"):
            cmd=data[4:]; ok,reply=self.controller.execute(cmd)
            if reply=="SCREENSHOT":
                path,err=self.controller.screenshot()
                if path:self.send_photo(cid,path); self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":"/screenshot"},True,"📸 Скриншот отправлен.")
                else:self.send_message(cid,err)
            elif reply.startswith("DOWNLOAD:"):
                ok_path, path = self.controller.download_path(reply[9:])
                if ok_path:
                    self.send_document(cid, Path(path))
                    self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":action},True,"📤 Файл отправлен.")
                else:
                    self.send_message(cid,path)
            else:self.send_message(cid,reply,self.keyboard()); self._result({"chat_id":cid,"user_id":q.get("from",{}).get("id"),"action":cmd},ok,reply)

    def send_photo(self,chat_id,path):
        with open(path,"rb") as f:
            self._multipart("sendPhoto",chat_id,"photo",Path(path).name,f.read())

    def send_document(self,chat_id,path):
        with open(path,"rb") as f:self._multipart("sendDocument",chat_id,"document",Path(path).name,f.read())

    def _multipart(self,method,chat_id,field,filename,content):
        boundary="----PCBridgeBoundary"
        body=b""
        body+=f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode()
        body+=f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()+content+f"\r\n--{boundary}--\r\n".encode()
        req=urllib.request.Request(f"{API_ROOT}/bot{self.token}/{method}",data=body,headers={"Content-Type":f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req,timeout=30) as r:
            if not json.loads(r.read().decode()).get("ok"): raise RuntimeError("Telegram upload failed")

    def _receive_upload(self,chat_id,doc):
        try:
            info=self.api("getFile",{"file_id":doc["file_id"]}); url=f"{API_ROOT}/file/bot{self.token}/{info['file_path']}"
            name=Path(doc.get("file_name","upload.bin")).name
            dest=self.controller.allowed_folders["downloads"] / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url,timeout=30) as r: dest.write_bytes(r.read())
            self.send_message(chat_id,f"✅ Файл сохранён на ПК в Downloads: {dest.name}",self.keyboard())
        except Exception as e:self.send_message(chat_id,f"❌ Upload: {e}")
