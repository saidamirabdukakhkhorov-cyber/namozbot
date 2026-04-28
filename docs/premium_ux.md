# Premium Telegram Bot UX Upgrade

This version separates global navigation and screen actions:

- Reply Keyboard is used only for the main global menu.
- Inline Keyboard is used only for the current screen actions.
- Callback screens prefer `edit_text` to avoid message spam.
- Main menu / dashboard clears active wizard state.
- Back, Cancel and Main menu are consistent across flows.

## Main screens

- `/start` onboarding: language -> intro -> privacy -> city -> reminders -> dashboard.
- Dashboard: compact summary for today's prayers and qazo counts.
- Today's prayers: one screen with prayer list, then a focused detail/action screen.
- Qazo list: current month/manual qazos by default; calculator qazos are separate.
- Qazo period filter: today, yesterday, this/last week, this/last month, this/last year and custom period.
- Calculator qazos: separate calculator-generated qazo summary and history.
- Qazo calculator: wizard with progress: period type -> start -> end -> prayers -> preview -> confirmation.
- Qazo completion: source -> prayer -> count -> success + undo.
- Statistics: one editable screen with period filters.
- Settings: compact profile/reminder summary with focused actions.

## UX safety

- Large qazo calculator apply action requires confirmation.
- Manual counts are validated against active qazo count.
- Future dates are rejected for qazo creation/calculation.
- Duplicate qazo rows are shown as a friendly state.
- Empty states are calm and non-judgmental.

## Translation structure

All premium UX copy is stored in `app/locales/{uz,ru,en}.json`. Handlers use translation keys through `t()` instead of hardcoding screen copy.
