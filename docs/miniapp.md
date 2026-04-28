# Telegram Mini App — O'rnatish

## Nima bu?

Bot ichida ochiluvchi to'liq ilova. Foydalanuvchi "Ilovani ochish" tugmasini bosadi → 
namoz vaqtlari, qazo tracker va sozlamalar ko'rsatiladi.

## Qanday ishlaydi

1. `webapp/index.html` → Mini App interfeysi
2. `app/webapp.py` → Mini App uchun API backend
3. `app/main.py` → Bot va Mini App server birgalikda ishga tushadi

## O'rnatish

### 1. WEBAPP_URL ni sozlash

Mini App HTTPS domenga joylashtirilishi kerak (Telegram talabi).

```env
WEBAPP_URL=https://your-domain.com
WEBAPP_PORT=8080
```

Railway'da deploy qilsangiz:
- Railway avtomatik HTTPS beradi
- `WEBAPP_URL=https://your-app-name.railway.app` deb qo'ying

### 2. Bot menu tugmasi

`WEBAPP_URL` kiritilgandan so'ng bot restart bo'lganda avtomatik qo'shiladi.
Yoki qo'lda: `@BotFather → /setmenubutton` 

### 3. Portni ochish (Railway)

Railway'da PORT environment variable bo'ladi, shuning uchun:
```env
WEBAPP_PORT=$PORT
```

## API endpointlar

| Endpoint | Method | Vazifa |
|----------|--------|--------|
| `/webapp` | GET | Mini App HTML |
| `/webapp/api/data` | POST | Foydalanuvchi ma'lumotlarini olish |
| `/webapp/api/action` | POST | Amallarni bajarish (til, shahar, qazo, va h.k.) |

## Mini App imkoniyatlari

- Bugungi namoz vaqtlari + holatlar
- Qazo namozlarni ko'rish va ado qilish
- Oylik statistika
- Til va shahar o'zgartirish
- Namoz eslatmalarini yoqish/o'chirish
