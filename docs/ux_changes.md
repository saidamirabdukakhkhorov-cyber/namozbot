# UX Changes in this build

## Navigation

- Main Reply Keyboard is now only global navigation.
- Inline buttons are now limited to current-screen actions.
- Dashboard callback and main screens clear active wizard state.
- Callback screens use `edit_text` first to reduce Telegram message spam.

## Onboarding

- `/start` now opens a guided onboarding:
  1. Language
  2. Intro
  3. Privacy
  4. City
  5. Reminder preference
  6. Dashboard

## Dashboard

- Added a compact dashboard with:
  - date
  - city
  - today's prayer statuses
  - current-month qazo count
  - calculator qazo count

## Today's prayers

- The first screen shows a clean list of all five prayers.
- Tapping a prayer opens a focused action screen:
  - O'qidim
  - Qazo bo'ldi
  - Keyinroq
- Snooze has 15 min, 30 min, 1 hour choices.

## Qazo

- Default qazo screen shows current-month/current-source qazos.
- Calculator-generated qazos are separated into their own section.
- Added period filter UI with today, yesterday, week, month, year and custom range.
- Qazo add flow is now date -> prayer -> confirmation.

## Qazo calculator

- Rebuilt as a wizard:
  1. Period type
  2. Start input
  3. End input
  4. Prayer selection
  5. Preview
  6. Confirmation before saving
- Month/year inputs are explained before the user types.
- Preview shows period, days, per-prayer breakdown and total.
- Bulk apply requires confirmation.

## Qazo completion

- Rebuilt as source -> prayer -> count.
- Count buttons only show valid options based on active count.
- Manual count validation prevents invalid or too-large numbers.
- Success screen includes undo, repeat, qazo list and main menu.

## Statistics

- Statistics now has one screen with inline period filters.
- Period callbacks edit the current message instead of sending repeated messages.

## Settings

- Settings screen now shows language, city, timezone and reminder summary.
- Language and city flows are separated from onboarding and do not break it.

## Localization

- UX copy was moved into `app/locales/uz.json`, `app/locales/ru.json`, `app/locales/en.json`.
- Handlers use `t()` translation keys instead of hardcoded long copy.


## Regression fix: Settings and Help buttons

- Global Reply Keyboard matching is now normalized, so Telegram clients that send emoji text with or without variation selectors still open the correct screen. This fixes cases like `⚙️ Sozlamalar` vs `⚙ Sozlamalar`.
- Help buttons no longer start functional flows. They open informational screens:
  - `help:calculator` explains how the qazo calculator works.
  - `help:completion` explains how qazo completion works.
- Help information screens include `Ortga` and `Asosiy menu` navigation.

## Prayer API provider update

- Replaced the Aladhan prayer-time provider with islomapi.uz.
- Daily times now use `GET https://islomapi.uz/api/daily?region=Toshkent&month=4&day=28`.
- Added a monthly provider helper for `GET https://islomapi.uz/api/monthly?region=Toshkent&month=4`.
- `PRAYER_API_BASE_URL` should now be `https://islomapi.uz`.
- Older Aladhan base URLs left in Railway are normalized to islomapi.uz to avoid breaking deploys.
