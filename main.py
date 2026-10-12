# AURELIAN — Android Telegram client
# Local session storage. Payloads/messages are sent only after explicit user action.
import asyncio, json, os, re, threading
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.graphics import Color, RoundedRectangle

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, PhoneCodeInvalidError, PhoneCodeExpiredError
from telethon.tl.types import Chat, Channel

BG = (0.035, 0.047, 0.075, 1)
PANEL = (0.075, 0.09, 0.13, 1)
PANEL2 = (0.10, 0.12, 0.17, 1)
ACCENT = (0.36, 0.48, 0.98, 1)
MINT = (0.24, 0.82, 0.68, 1)
TEXT = (0.91, 0.94, 0.99, 1)
MUTED = (0.58, 0.64, 0.74, 1)
WARN = (1.0, 0.66, 0.32, 1)
MAX_SELECTED_GROUPS = 20
MIN_DELAY_SECONDS = 10

class Card(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.padding = dp(12)
        self.spacing = dp(8)
        with self.canvas.before:
            Color(*PANEL)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
        self.bind(pos=self._sync, size=self._sync)
    def _sync(self, *_):
        self.bg.pos, self.bg.size = self.pos, self.size

class AurelianApp(App):
    def build(self):
        self.title = 'AURELIAN'
        Window.clearcolor = BG
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()
        self.clients = {}
        self.accounts = []
        self.active_alias = ''
        self.pending = None
        self.dialogs = []
        self.group_checks = []
        self.message_pool = []
        self.stats = {'sent': 0, 'failed': 0}
        self.send_future = None
        self.page = 'home'
        self.status_text = 'Hazır · Telegram hesabını bağlayarak başla.'
        self.config_file = Path(self.user_data_dir) / 'aurelian.json'
        self.session_dir = Path(self.user_data_dir) / 'sessions'
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.interval = 10
        self._load_data()
        self.shell = BoxLayout(orientation='vertical', padding=(dp(12),dp(10)), spacing=dp(8))
        with self.shell.canvas.before:
            Color(*BG); self.shell_bg = RoundedRectangle(pos=self.shell.pos, size=self.shell.size)
        self.shell.bind(pos=lambda *_: setattr(self.shell_bg,'pos',self.shell.pos), size=lambda *_: setattr(self.shell_bg,'size',self.shell.size))
        self._render()
        return self.shell

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _load_data(self):
        try:
            d=json.loads(self.config_file.read_text(encoding='utf-8'))
            self.accounts=d.get('accounts',[]); self.active_alias=d.get('active_alias','')
            self.message_pool=d.get('message_pool',[]); self.interval=max(MIN_DELAY_SECONDS,int(d.get('interval',10)))
            self.stats=d.get('stats',self.stats)
        except Exception: pass

    def _save_data(self):
        try:
            self.config_file.parent.mkdir(parents=True,exist_ok=True)
            self.config_file.write_text(json.dumps({'accounts':self.accounts,'active_alias':self.active_alias,
                'message_pool':self.message_pool,'interval':self.interval,'stats':self.stats},ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e: self._set_status('Ayarlar kaydedilemedi: '+str(e))

    def _submit(self, coro, done=None):
        f=asyncio.run_coroutine_threadsafe(coro,self.loop)
        def finish(fut):
            try:
                result=fut.result()
                if done: Clock.schedule_once(lambda _dt: done(result),0)
            except Exception as exc:
                self._set_status(self._friendly_error(exc))
        f.add_done_callback(finish)
        return f

    def _friendly_error(self, exc):
        if isinstance(exc,FloodWaitError): return f'Telegram bekleme istedi: {exc.seconds} sn. İşlem durduruldu.'
        return 'İşlem başarısız: '+str(exc)

    def _set_status(self, text):
        self.status_text=str(text)
        if hasattr(self,'status_label'):
            Clock.schedule_once(lambda _dt: setattr(self.status_label,'text',self.status_text),0)

    def _label(self, text, size=14, color=TEXT, height=None, bold=False):
        w=Label(text=text, font_size=f'{size}sp', color=color, bold=bold, halign='left', valign='middle',
                size_hint_y=None, height=dp(height or (max(26,size*1.8))))
        w.bind(size=lambda inst,val: setattr(inst,'text_size',(val[0],None)))
        return w

    def _button(self, text, callback, color=ACCENT, height=44):
        b=Button(text=text, size_hint_y=None, height=dp(height), background_normal='', background_down='',
                 background_color=color, color=TEXT, font_size='14sp', bold=True)
        b.bind(on_release=lambda *_: callback())
        return b

    def _input(self, hint, text='', password=False, multiline=False, height=44):
        w=TextInput(hint_text=hint,text=text,password=password,multiline=multiline,
            size_hint_y=None,height=dp(height),padding=(dp(12),dp(10)),font_size='14sp',
            foreground_color=TEXT, hint_text_color=MUTED, background_normal='',background_active='',
            background_color=PANEL2, cursor_color=MINT)
        return w

    def _card(self, parent, title=None, orientation='vertical'):
        c=Card(orientation=orientation,size_hint_y=None)
        if title: c.add_widget(self._label(title,16,TEXT,30,True))
        parent.add_widget(c)
        return c

    def _render(self):
        self.shell.clear_widgets()
        header=BoxLayout(orientation='vertical',size_hint_y=None,height=dp(70),spacing=dp(1))
        header.add_widget(self._label('A U R E L I A N',21,TEXT,34,True))
        header.add_widget(self._label('TELEGRAM WORKSPACE  ·  PREMIUM',10,MINT,20,True))
        self.shell.add_widget(header)
        nav=GridLayout(cols=3,size_hint_y=None,height=dp(86),spacing=dp(6))
        for label,page in [('⌂  Ana Sayfa','home'),('♙  Hesaplar','accounts'),('▦  Gruplar','groups'),('✉  Mesajlar','messages'),('◷  Ayarlar','settings'),('▤  İstatistik','stats')]:
            nav.add_widget(self._button(label,lambda p=page:self._go(p),ACCENT if page==self.page else PANEL2,40))
        self.shell.add_widget(nav)
        scroll=ScrollView(do_scroll_x=False,bar_width=dp(3))
        self.content=BoxLayout(orientation='vertical',spacing=dp(10),padding=(0,dp(3)),size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter('height'))
        scroll.add_widget(self.content); self.shell.add_widget(scroll)
        if self.page=='home': self._page_home()
        elif self.page=='accounts': self._page_accounts()
        elif self.page=='groups': self._page_groups()
        elif self.page=='messages': self._page_messages()
        elif self.page=='settings': self._page_settings()
        else: self._page_stats()
        status=Card(orientation='vertical',size_hint_y=None,height=dp(68),padding=dp(10))
        self.status_label=Label(text=self.status_text,color=MUTED,font_size='12sp',halign='left',valign='middle')
        self.status_label.bind(size=lambda i,v:setattr(i,'text_size',v)); status.add_widget(self.status_label)
        self.shell.add_widget(status)

    def _go(self,page): self.page=page; self._render()

    def _active_client(self): return self.clients.get(self.active_alias)

    def _page_home(self):
        acc=next((a for a in self.accounts if a.get('alias')==self.active_alias),None)
        c=self._card(self.content,'Kontrol Merkezi')
        c.add_widget(self._label('Merhaba, Aurelian.',21,TEXT,36,True))
        c.add_widget(self._label('Hesaplarını, gruplarını ve mesajlarını tek yerden yönet.',12,MUTED,40))
        c.add_widget(self._label('AKTİF HESAP',10,MUTED,20,True))
        c.add_widget(self._label(('●  '+self.active_alias) if acc else '●  Hesap bağlı değil',16,MINT if acc else WARN,30,True))
        grid=GridLayout(cols=2,size_hint_y=None,height=dp(78),spacing=dp(8))
        for title,value in [('Başarılı gönderim',str(self.stats.get('sent',0))),('Başarısız',str(self.stats.get('failed',0)))]:
            sub=Card(orientation='vertical',padding=dp(10),spacing=dp(2)); sub.add_widget(self._label(title,11,MUTED,22)); sub.add_widget(self._label(value,21,TEXT,30,True)); grid.add_widget(sub)
        self.content.add_widget(grid)
        actions=self._card(self.content,'Hızlı İşlemler')
        actions.add_widget(self._button('＋  Telegram hesabı ekle',lambda:self._go('accounts')))
        actions.add_widget(self._button('▦  Grupları yükle',self.load_groups,PANEL2))
        actions.add_widget(self._button('✉  Mesaj hazırla',lambda:self._go('messages'),PANEL2))
        note=self._card(self.content,'Güvenli kullanım')
        note.add_widget(self._label('Gönderim yalnızca sen başlattığında yapılır. Otomatik sonsuz döngü ve tespit atlatma davranışı yoktur. Telegram bekleme uyarısı gelirse işlem durur.',12,MUTED,75))

    def _page_accounts(self):
        c=self._card(self.content,'Kayıtlı Hesaplar')
        if not self.accounts: c.add_widget(self._label('Henüz hesap eklenmedi.',13,MUTED,30))
        for a in self.accounts:
            row=BoxLayout(size_hint_y=None,height=dp(44),spacing=dp(6))
            row.add_widget(self._label(('● ' if a['alias']==self.active_alias else '○ ')+a['alias'],13,MINT if a['alias']==self.active_alias else TEXT,36,True))
            row.add_widget(self._button('Aktif et',lambda alias=a['alias']:self.activate_account(alias),PANEL2,36))
            row.add_widget(self._button('Sil',lambda alias=a['alias']:self.remove_account(alias), (0.50,0.18,0.23,1),36))
            c.add_widget(row)
        c2=self._card(self.content,'Yeni Hesap Bağla')
        c2.add_widget(self._label('Telegram API bilgilerini resmi my.telegram.org panelinden al.',11,MUTED,32))
        self.alias_in=self._input('Hesap etiketi (örn. Kişisel)')
        self.api_id_in=self._input('API ID (sayısal)')
        self.api_hash_in=self._input('API Hash',password=True)
        self.phone_in=self._input('Telefon numarası (+90...)')
        for w in (self.alias_in,self.api_id_in,self.api_hash_in,self.phone_in): c2.add_widget(w)
        c2.add_widget(self._button('1 · Doğrulama kodu iste',self.request_code))
        self.code_in=self._input('Telegram doğrulama kodu')
        self.pass_in=self._input('İki adımlı doğrulama şifresi (gerekiyorsa)',password=True)
        c2.add_widget(self.code_in); c2.add_widget(self._button('2 · Giriş yap',self.sign_in))
        c2.add_widget(self.pass_in); c2.add_widget(self._button('2FA ile devam et',self.sign_in_password,PANEL2))
        c2.add_widget(self._label('Güvenlik: Oturum dosyaları uygulamanın özel alanında saklanır. Şifreni veya doğrulama kodunu kimseyle paylaşma.',11,MUTED,52))

    def _page_groups(self):
        c=self._card(self.content,'Grup Seçimi')
        c.add_widget(self._button('↻  Grupları yenile',self.load_groups))
        self.group_search=self._input('Grup adına göre ara')
        self.group_search.bind(text=lambda *_:self._render_group_rows())
        c.add_widget(self.group_search)
        bar=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(6))
        bar.add_widget(self._button('Tümünü seç',lambda:self._set_all_groups(True),PANEL2,34))
        bar.add_widget(self._button('Temizle',lambda:self._set_all_groups(False),PANEL2,34)); c.add_widget(bar)
        self.group_list=BoxLayout(orientation='vertical',size_hint_y=None,spacing=dp(2)); self.group_list.bind(minimum_height=self.group_list.setter('height'))
        c.add_widget(self.group_list); self._render_group_rows()
        c.add_widget(self._label(f'{len(self.dialogs)} grup yüklü · İşlem başına en fazla {MAX_SELECTED_GROUPS} grup',11,MUTED,28))

    def _render_group_rows(self):
        if not hasattr(self,'group_list'): return
        self.group_list.clear_widgets(); self.group_checks=[]
        query=getattr(self,'group_search',None).text.casefold().strip() if getattr(self,'group_search',None) else ''
        for name,entity in self.dialogs:
            if query and query not in name.casefold(): continue
            row=BoxLayout(size_hint_y=None,height=dp(38),spacing=dp(6))
            check=CheckBox(size_hint=(None,1),width=dp(36),color=MINT)
            row.add_widget(check); row.add_widget(self._label(name,12,TEXT,34))
            self.group_list.add_widget(row); self.group_checks.append((check,entity,name))

    def _page_messages(self):
        c=self._card(self.content,'Mesaj Havuzu')
        self.message_in=self._input('Mesajını yaz veya yapıştır…',multiline=True,height=110); c.add_widget(self.message_in)
        c.add_widget(self._button('＋  Mesajı havuza ekle',self.add_message))
        if not self.message_pool: c.add_widget(self._label('Kayıtlı mesaj yok.',12,MUTED,30))
        for idx,msg in enumerate(self.message_pool):
            row=BoxLayout(size_hint_y=None,height=dp(58),spacing=dp(6))
            row.add_widget(self._label(f'{idx+1}. {msg[:90]}',11,TEXT,52))
            row.add_widget(self._button('Sil',lambda i=idx:self.delete_message(i),(0.50,0.18,0.23,1),36)); c.add_widget(row)
        send=self._card(self.content,'Gönderim')
        send.add_widget(self._label('Bir mesaj seçip izinli gruplara tek seferlik gönderim yap.',12,MUTED,34))
        self.send_msg_in=self._input('Gönderilecek mesaj (havuzdan bağımsız)',multiline=True,height=92)
        send.add_widget(self.send_msg_in)
        send.add_widget(self._button('✓  Seçili gruplara bir kez gönder',self.send_once,MINT))
        send.add_widget(self._button('■  Gönderimi durdur',self.stop_send,(0.50,0.18,0.23,1)))
        send.add_widget(self._label('İzinli olduğun grupları seç. Otomatik tekrar yapılmaz.',11,MUTED,30))

    def _page_settings(self):
        c=self._card(self.content,'Gönderim Ayarları')
        c.add_widget(self._label('Gruplar arası bekleme süresi (saniye)',12,MUTED,26))
        self.interval_in=self._input('En az 10 saniye',str(self.interval))
        c.add_widget(self.interval_in); c.add_widget(self._button('Ayarları kaydet',self.save_settings))
        c2=self._card(self.content,'Uygulama')
        c2.add_widget(self._label('AURELIAN · Android Telegram Workspace',14,TEXT,30,True))
        c2.add_widget(self._label('Oturum verileri uygulama alanında tutulur. Uygulamayı kaldırmak yerel oturum dosyalarını silebilir.',11,MUTED,48))
        c2.add_widget(self._button('Oturumu kapat',self.disconnect_active,PANEL2))
        c2.add_widget(self._button('Yerel mesaj ve istatistik verilerini temizle',self.clear_local_data,(0.50,0.18,0.23,1)))

    def _page_stats(self):
        c=self._card(self.content,'İstatistikler')
        for k,v in [('Başarılı gönderim',self.stats.get('sent',0)),('Başarısız gönderim',self.stats.get('failed',0)),('Kayıtlı hesap',len(self.accounts)),('Yüklenen grup',len(self.dialogs)),('Mesaj havuzu',len(self.message_pool))]:
            row=BoxLayout(size_hint_y=None,height=dp(36)); row.add_widget(self._label(k,12,MUTED,32)); row.add_widget(self._label(str(v),15,TEXT,32,True)); c.add_widget(row)
        c.add_widget(self._button('İstatistikleri sıfırla',self.reset_stats,PANEL2))

    def request_code(self):
        try:
            alias=self.alias_in.text.strip() or self.phone_in.text.strip()
            api_id=int(self.api_id_in.text.strip()); api_hash=self.api_hash_in.text.strip(); phone=self.phone_in.text.strip()
            if not alias or not api_hash or not phone: raise ValueError('Etiket, API Hash ve telefon gerekli.')
            if any(a['alias']==alias for a in self.accounts): raise ValueError('Bu hesap etiketi zaten kullanılıyor.')
        except Exception as e: self._set_status(str(e)); return
        key=re.sub(r'[^A-Za-z0-9_-]','_',alias)[:40]
        self.pending={'alias':alias,'key':key,'api_id':api_id,'api_hash':api_hash,'phone':phone}
        self._set_status('Doğrulama kodu isteniyor…')
        self._submit(self._request_code_async(self.pending.copy()))

    async def _request_code_async(self,p):
        client=TelegramClient(str(self.session_dir/p['key']),p['api_id'],p['api_hash'],loop=self.loop)
        await client.connect(); await client.send_code_request(p['phone'])
        self.clients[p['alias']]=client
        self._set_status('Kod Telegram uygulamana/SMS kanalına gönderildi. Kodu gir.')

    def sign_in(self):
        if not self.pending or self.pending['alias'] not in self.clients: self._set_status('Önce doğrulama kodu iste.'); return
        code=self.code_in.text.strip()
        if not code: self._set_status('Doğrulama kodunu gir.'); return
        self._submit(self._sign_in_async(code))

    async def _sign_in_async(self,code):
        p=self.pending; client=self.clients[p['alias']]
        try: await client.sign_in(phone=p['phone'],code=code)
        except SessionPasswordNeededError:
            self._set_status('İki adımlı doğrulama açık. 2FA şifresini gir.'); return
        self._finish_login(p)

    def sign_in_password(self):
        if not self.pending or self.pending['alias'] not in self.clients: self._set_status('Önce doğrulama kodu iste.'); return
        pw=self.pass_in.text
        if not pw: self._set_status('2FA şifresini gir.'); return
        self._submit(self._sign_in_password_async(pw))

    async def _sign_in_password_async(self,pw):
        p=self.pending; await self.clients[p['alias']].sign_in(password=pw); self._finish_login(p)

    def _finish_login(self,p):
        # Login completes on the asyncio worker; marshal UI changes to Kivy's main thread.
        Clock.schedule_once(lambda _dt: self._finish_login_ui(p), 0)

    def _finish_login_ui(self,p):
        if not any(a['alias']==p['alias'] for a in self.accounts):
            self.accounts.append({'alias':p['alias'],'key':p['key'],'api_id':p['api_id'],'api_hash':p['api_hash'],'phone':p['phone']})
        self.active_alias=p['alias']; self._save_data(); self._set_status('Telegram hesabı bağlandı: '+p['alias']); self.page='accounts'; self._render()

    def activate_account(self,alias):
        self.active_alias=alias; self._save_data()
        if alias in self.clients: self._set_status('Aktif hesap: '+alias); self._render(); return
        acc=next((a for a in self.accounts if a['alias']==alias),None)
        if not acc: return
        self._set_status('Hesap bağlantısı kontrol ediliyor…')
        self._submit(self._activate_async(acc),lambda ok:self._after_activate(alias,ok))

    async def _activate_async(self,acc):
        client=TelegramClient(str(self.session_dir/acc['key']),int(acc['api_id']),acc['api_hash'],loop=self.loop)
        await client.connect()
        if not await client.is_user_authorized(): await client.disconnect(); raise RuntimeError('Bu oturum geçersiz. Hesabı yeniden bağla.')
        self.clients[acc['alias']]=client; return True

    def _after_activate(self,alias,ok): self.active_alias=alias; self._save_data(); self._set_status('Aktif hesap: '+alias); self._render()

    def remove_account(self,alias):
        async def remove():
            client=self.clients.pop(alias,None)
            if client:
                try: await client.disconnect()
                except Exception: pass
        self._submit(remove(),lambda _:self._finish_remove(alias))
    def _finish_remove(self,alias):
        acc=next((a for a in self.accounts if a['alias']==alias),None)
        self.accounts=[a for a in self.accounts if a['alias']!=alias]
        if self.active_alias==alias: self.active_alias=self.accounts[0]['alias'] if self.accounts else ''
        if acc:
            for filename in (acc['key']+'.session', acc['key']+'.session-journal'):
                p=self.session_dir/filename
                try:
                    if p.exists(): p.unlink()
                except Exception: pass
        self._save_data(); self._set_status('Hesap kaldırıldı.'); self._render()

    def load_groups(self):
        client=self._active_client()
        if not client: self._set_status('Önce hesap bağla ve Hesaplar ekranından aktif et.'); return
        self._set_status('Gruplar yükleniyor…'); self._submit(self._load_groups_async(client),self._groups_loaded)
    async def _load_groups_async(self,client):
        if not await client.is_user_authorized(): raise RuntimeError('Telegram oturumu geçerli değil.')
        result=[]
        async for d in client.iter_dialogs():
            e=d.entity
            if isinstance(e,Chat) or (isinstance(e,Channel) and getattr(e,'megagroup',False)): result.append((d.name,e))
        return sorted(result,key=lambda x:x[0].casefold())
    def _groups_loaded(self,dialogs):
        self.dialogs=dialogs; self._set_status(f'{len(dialogs)} grup yüklendi.'); self.page='groups'; self._render()
    def _set_all_groups(self,value):
        count=0
        for check,_,_ in self.group_checks:
            if value and count>=MAX_SELECTED_GROUPS: check.active=False; continue
            check.active=value
            if value: count+=1

    def add_message(self):
        msg=self.message_in.text.strip()
        if not msg: self._set_status('Önce mesaj yaz.'); return
        if msg not in self.message_pool: self.message_pool.append(msg)
        self._save_data(); self._set_status('Mesaj havuza eklendi.'); self._render()
    def delete_message(self,idx):
        if 0<=idx<len(self.message_pool): self.message_pool.pop(idx)
        self._save_data(); self._render()
    def save_settings(self):
        try: value=int(self.interval_in.text.strip())
        except Exception: self._set_status('Bekleme süresi tam sayı olmalı.'); return
        if value<MIN_DELAY_SECONDS: self._set_status(f'En düşük bekleme süresi {MIN_DELAY_SECONDS} saniye.'); return
        self.interval=value; self._save_data(); self._set_status('Ayarlar kaydedildi.'); self._render()

    def send_once(self):
        client=self._active_client()
        if not client: self._set_status('Önce Telegram hesabını bağla.'); return
        selected=[(e,n) for check,e,n in self.group_checks if check.active]
        if not selected: self._set_status('Gruplar ekranından en az bir grup seç.'); return
        if len(selected)>MAX_SELECTED_GROUPS: self._set_status(f'Bir işlemde en fazla {MAX_SELECTED_GROUPS} grup seçilebilir.'); return
        msg=self.send_msg_in.text.strip()
        if not msg and self.message_pool: msg=self.message_pool[0]
        if not msg: self._set_status('Gönderilecek mesajı yaz.'); return
        self._set_status(f'{len(selected)} seçili gruba gönderim başlıyor…')
        self.send_future=self._submit(self._send_once_async(client,selected,msg))
    async def _send_once_async(self,client,selected,msg):
        if not await client.is_user_authorized(): raise RuntimeError('Telegram oturumu geçerli değil.')
        ok=failed=0
        for i,(entity,name) in enumerate(selected):
            try:
                await client.send_message(entity,msg); ok+=1
                self.stats['sent']=self.stats.get('sent',0)+1; self._save_data()
            except FloodWaitError as e:
                self._set_status(f'Telegram {e.seconds} saniye bekleme istedi. Gönderim durduruldu.'); break
            except asyncio.CancelledError: raise
            except Exception as e:
                failed+=1; self.stats['failed']=self.stats.get('failed',0)+1; self._set_status(f'{name}: gönderilemedi.')
            if i<len(selected)-1: await asyncio.sleep(self.interval)
        self._save_data(); self._set_status(f'İşlem bitti · Başarılı: {ok} · Hatalı: {failed}. Otomatik tekrar yok.')
        return ok,failed
    def stop_send(self):
        if self.send_future and not self.send_future.done(): self.send_future.cancel(); self._set_status('Durdurma istendi.'); return
        self._set_status('Aktif gönderim yok.')
    def disconnect_active(self):
        alias=self.active_alias; client=self.clients.get(alias)
        if not client: self._set_status('Aktif oturum bağlı değil.'); return
        async def go(): await client.disconnect(); self.clients.pop(alias,None)
        self._submit(go(),lambda _:self._set_status('Aktif Telegram oturumu kapatıldı.'))
    def clear_local_data(self):
        self.message_pool=[]; self.stats={'sent':0,'failed':0}; self._save_data(); self._set_status('Mesaj havuzu ve istatistikler temizlendi.'); self._render()
    def reset_stats(self): self.stats={'sent':0,'failed':0}; self._save_data(); self._set_status('İstatistikler sıfırlandı.'); self._render()
    def on_stop(self):
        for c in list(self.clients.values()):
            try: asyncio.run_coroutine_threadsafe(c.disconnect(),self.loop)
            except Exception: pass
        try: self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception: pass

if __name__=='__main__': AurelianApp().run()
