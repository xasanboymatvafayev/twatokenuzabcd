# 🎰 Casino Platform - To'liq O'rnatish Qo'llanmasi

## 📁 Loyiha Strukturasi

```
casino/
├── backend/              # FastAPI backend
│   ├── main.py           # Asosiy API
│   ├── core/
│   │   ├── config.py     # Konfiguratsiya
│   │   ├── database.py   # DB ulanish
│   │   └── security.py   # JWT, parol
│   ├── models/
│   │   └── models.py     # DB modellari
│   ├── routers/
│   │   ├── auth.py       # Kirish/ro'yxatdan o'tish
│   │   ├── users.py      # Foydalanuvchi profili
│   │   ├── games.py      # Barcha o'yinlar (Aviator, Mines, Apple)
│   │   ├── payments.py   # To'lovlar
│   │   ├── admin.py      # Admin amallar
│   │   └── promocodes.py # Promokodlar
│   ├── services/
│   │   └── rng.py        # RNG algoritmlari
│   ├── requirements.txt
│   └── Dockerfile
├── bot/
│   ├── bot.py            # Telegram bot (aiogram 3)
│   └── Dockerfile
├── frontend/
│   └── templates/
│       └── index.html    # Web App (barcha 3 o'yin)
├── admin/
│   └── index.html        # Admin panel
├── docker-compose.yml
├── nginx.conf
└── .env.example
```

## 🚀 O'rnatish Bosqichlari

### 1. Talablar
- Ubuntu 20.04+ server
- Docker + Docker Compose
- Domen nomi (SSL uchun)
- Telegram Bot tokeni

### 2. Bot yaratish
1. @BotFather ga yozing
2. `/newbot` buyrug'ini yuboring
3. Bot token ni oling
4. Bot uchun `/setmenubutton` orqali Web App tugmasini sozlang

### 3. SSL sertifikat olish (Certbot bilan)
```bash
apt install certbot
certbot certonly --standalone -d your-domain.com
```

### 4. Loyihani sozlash
```bash
git clone ... casino
cd casino
cp .env.example .env
nano .env   # Barcha qiymatlarni to'ldiring
```

### 5. nginx.conf ni tahrirlash
```bash
nano nginx.conf
# your-domain.com ni o'z domeningizga almashtiring
```

### 6. Ishga tushirish
```bash
docker-compose up -d --build
```

### 7. Tekshirish
```bash
docker-compose ps          # Barcha servislar ishlamoqda?
docker-compose logs bot    # Bot loglari
docker-compose logs backend # API loglari
```

## 🔧 Admin Panel Foydalanish

1. Bot tokeniga `/start` yuboring → login/parol oling
2. https://your-domain.com/admin ga kiring
3. Olingan login/parolni kiriting

### Admin imkoniyatlari:
- 📊 **Dashboard** — statistika, foyda, top o'yinchilar
- 👥 **Users** — bloklash, muzlatish, o'yin ta'qiqi
- 💰 **Payments** — depozit/yechish so'rovlarini tasdiqlash
- 🎟 **Promos** — promokod yaratish va boshqarish
- 📢 **Ads** — banner, popup, bot xabarlari

## 🎮 O'yinlar

### ✈️ Aviator
- Server RNG asosida crash nuqtasi belgilanadi
- Multiplier real vaqtda oshadi
- Manual yoki avtomatik cashout
- House edge: 5%

### 💣 Mines
- 5×5 = 25 katakcha
- Mina soni: 1-24 (foydalanuvchi tanlaydi)
- Har ochishda koeffitsient oshadi
- Kombinatorial ehtimolik formulasi

### 🍎 Apple of Fortune
- 5 qavat × 3 tanlov
- Har qavatda 1 ta qizil olma
- Koeffitsient: (2/3)^qavat × 0.95 (house edge)
- Istalgan qavatda cashout

## 🔐 Xavfsizlik

- ✅ JWT tokenlar (7 kunlik)
- ✅ bcrypt parol hashlash
- ✅ RNG serverda ishlaydi (client aldolmaydi)
- ✅ Barcha balans operatsiyalari transaksion
- ✅ Rate limiting (nginx orqali)
- ✅ CORS himoya

## 💰 Balans Tizimi

```
Foydalanuvchi depozit so'raydi
    ↓
Bot adminlarga xabar yuboradi
    ↓
Admin Admin Panel'dan tasdiqlaydi
    ↓
Balans avtomatik qo'shiladi
    ↓
Foydalanuvchi o'ynaydi (real vaqt sinxron)
    ↓
Yechish so'rovida admin tasdiqlaydi
    ↓
Balans kamayadi + admin to'lovni amalga oshiradi
```

## 🛠 Texnik Ma'lumotlar

| Komponent | Texnologiya |
|-----------|------------|
| Backend API | FastAPI (Python) |
| Database | PostgreSQL (async) |
| ORM | SQLAlchemy 2.0 async |
| Bot | aiogram 3.x |
| Frontend | Vanilla HTML/CSS/JS |
| Auth | JWT + bcrypt |
| Deploy | Docker Compose + Nginx |

## ❗ Muhim Eslatmalar

1. `.env` faylini hech qachon git'ga qo'shmang
2. `SECRET_KEY` ni kamida 32 belgili qiling
3. Adminlar faqat `ADMIN_IDS` ro'yxatida bo'lgan Telegram ID'lar
4. SSL sertifikatsiz Telegram WebApp ishlamaydi
5. Har doim `docker-compose logs` bilan kuzatib boring

## 📱 Telegram Bot Buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Boshlash / Hisob ma'lumotlari |
| `/deposit 50000` | Depozit so'rovi yuborish |
| `/withdraw 100000 karta` | Yechish so'rovi |
| `/promo KOD` | Promokod aktivatsiya |
| `/admin` | Admin panel (faqat adminlar uchun) |
