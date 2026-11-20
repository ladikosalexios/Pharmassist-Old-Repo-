# PharmAssist Electron Agent — Demo & Test Scenarios

All scenarios below are wired to the Electron overlay agent (`agent/`). You can trigger them via:
- **Global hotkeys** (`⌘/Ctrl + Alt + 1…8`, works without Accessibility permission)
- **Physical barcode scanner** or **fast-typing** the `RX2024-xxx` code + `Enter`
- **Printable barcodes** in `agent/barcodes.html` (`npm run barcodes`)

---

## Hotkey Scenarios (`⌘/Ctrl + Alt + 1…8`)

| Hotkey | Rx ID | Patient (Age) | Medication & Regimen | Expected Safety Verdict & Key Flags |
| :--- | :--- | :--- | :--- | :--- |
| `⌘/Ctrl + Alt + 1` | `RX2024-005` | Maria Stavrou (64) | **Warfarin** 5 mg · Once daily · 90 days | **`BLOCK`** (Amiodarone DDI) + **`REVIEW`** (Aspirin DDI, SPC INR monitoring) |
| `⌘/Ctrl + Alt + 2` | `RX2024-001` | Sarah Johnson (32) | **Amoxicillin** 500 mg · 3×/day · 7 days | **`OK`** (All 5 checks clear) |
| `⌘/Ctrl + Alt + 3` | `RX2024-002` | James Martinez (71) | **Warfarin** 7.5 mg · Once daily · Long-term | **`REVIEW`** (Duplicate therapy check) |
| `⌘/Ctrl + Alt + 4` | `RX2024-003` | Maria Garcia (58) | **Lisinopril** 10 mg · Once daily · Long-term | **`OK`** (All 5 checks clear) |
| `⌘/Ctrl + Alt + 5` | `RX2024-006` | Nikos Papadopoulos (78) | **Metformin** 850 mg · Twice daily · Long-term | **`BLOCK`** (Contraindication — renal impairment / eGFR) |
| `⌘/Ctrl + Alt + 6` | `RX2024-011` | Kostas Georgiou (68) | **Warfarin** 5 mg · Once daily · 90 days (1 box × 30) | **`REVIEW`** (Insufficient boxes: 30 supplied < 90 needed) + **`OK`** (5 mg/day ≤ 9 mg SPC) |
| `⌘/Ctrl + Alt + 7` | `RX2024-012` | Eleni Markou (61) | **Warfarin** 1 mg · Once daily · 30 days (1 box × 30) | **`REVIEW`** (Dose below SPC min: 1 mg/day < 3 mg SPC) + **`OK`** (30 units covers 30 days) |
| `⌘/Ctrl + Alt + 8` | `RX2024-013` | Petros Nikolopoulos (72) | **Warfarin** 10 mg · Twice daily · 30 days (2 boxes × 30) | **`BLOCK`** (Dose exceeds SPC max: 20 mg/day > 9 mg SPC) + **`OK`** (60 units covers 30 days) |

> **Note:** Slots `6–8` (`RX2024-011`, `RX2024-012`, `RX2024-013`) are evaluated live by `safety_engine.py` against the ingested Warfarin HPRA SPC PDF in PostgreSQL (`spc_documents`), rather than static mock alerts. Run `python -m scripts.import_spc_dir` in `backend/` first so the ingested PDFs are present (otherwise `MOCK_SPC` is used as fallback).

---

## Additional Scenarios in `barcodes.html` (Scanner / Type + Enter)

| Rx ID | Patient (Age) | Medication & Regimen | Expected Safety Verdict |
| :--- | :--- | :--- | :--- |
| `RX2024-007` | Eleni Demetriou (45) | **Atorvastatin** 40 mg · Once daily · Long-term | **`OK`** (All 5 checks clear) |
| `RX2024-008` | Andreas Vasilakis (29) | **Clopidogrel** 75 mg · Once daily · 12 months | **`REVIEW`** (Duplicate therapy + DDI) |
| `RX2024-009` | Sofia Ioannidou (8) | **Amoxicillin** 250 mg / 5 mL · 3×/day · 10 days | **`REVIEW`** (Paediatric dose validation — weight check) |

---

## Live ΗΔΥΚΑ Example & Utility Hotkeys

- `⌘/Ctrl + Alt + 0` — Fires `2605203035241` (*OLENXA DISP.TAB* — real testeps sample prescription; resolves only when `PHARMAPI_MOCK=false`).
- `⌘/Ctrl + Alt + Enter` — Open the current card's full review in the web app (`http://localhost:5173`).
- `⌘/Ctrl + Shift + H` — Hide / show the overlay.
- `⌘/Ctrl + Shift + C` — Dismiss the current card.
- `⌘/Ctrl + Shift + Q` — Quit the Electron agent.
