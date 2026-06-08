# HMVO email — DRAFT (review and send yourself; not sent by the tool)

Reply on the **original HMVO thread**. Fill the bracketed placeholders, attach
the recording, then send. (English draft; a Greek version follows below if the
thread is in Greek.)

---

**To:** [HMVO contact name] <[hmvo contact email]>
**Cc:** [Vassilis] <[vassilis email]>
**Subject:** Re: [original thread subject] — HMVS input safeguards (Caps Lock + keyboard layout) recording

Dear [HMVO contact name],

As agreed for Gate 2, attached is a short screen recording (≈[N] s) of the
HMVS pack-code input safeguards, demonstrating points 5 and 6:

- **Caps Lock detection** — with Caps Lock on, the field shows an inline Greek
  warning and the submit action is disabled until it is turned off.
- **Keyboard-layout detection** — a non-Latin (e.g. Greek) character in the
  field, which indicates the OS is still on a non-English layout, raises a
  Greek warning and likewise disables submit until corrected.

Both warnings are shown in Greek; the recording uses mock data only — no
patient data appears.

The layout check uses character analysis of the scanned input. This is
consistent with Solidsoft's whitepaper **EMVS1344** ("Understanding Keyboard
Emulation", 7 Jun 2026), which confirms a layout mismatch manifests as
wrong / non-Latin characters in the scanned value (their Czech example,
`0 → é`) — precisely the corruption this detector catches.

This work was carried out under IT-supplier ticket **[TICKET-REF]**.

**One confirmation request (for Vassilis):** please confirm the
keyboard-layout heuristic — treating any non-Latin character in the HMVS field
as a wrong-layout signal — is acceptable as the detection approach.

Happy to provide anything further for the test book.

Kind regards,
[Your name]
[Role / pharmacy]

---

## Greek version (use if the thread is in Greek)

**Θέμα:** Απαντ.: [original thread subject] — Καταγραφή ασφαλιστικών δικλείδων εισαγωγής HMVS (Caps Lock + διάταξη πληκτρολογίου)

Αγαπητέ/ή [όνομα επαφής HMVO],

Όπως συμφωνήθηκε για το Gate 2, επισυνάπτεται σύντομη καταγραφή οθόνης (≈[N] δευτ.)
των ασφαλιστικών δικλείδων του πεδίου εισαγωγής κωδικού HMVS, που παρουσιάζει τα
σημεία 5 και 6:

- **Ανίχνευση Caps Lock** — με ενεργό Caps Lock, το πεδίο εμφανίζει προειδοποίηση
  στα ελληνικά και η υποβολή απενεργοποιείται έως ότου απενεργοποιηθεί.
- **Ανίχνευση διάταξης πληκτρολογίου** — ένας μη λατινικός (π.χ. ελληνικός)
  χαρακτήρας στο πεδίο, που υποδηλώνει ότι το λειτουργικό παραμένει σε μη αγγλική
  διάταξη, εμφανίζει προειδοποίηση και απενεργοποιεί την υποβολή έως ότου διορθωθεί.

Και οι δύο προειδοποιήσεις εμφανίζονται στα ελληνικά· η καταγραφή χρησιμοποιεί
μόνο εικονικά δεδομένα — δεν εμφανίζονται δεδομένα ασθενών.

Ο έλεγχος διάταξης βασίζεται σε ανάλυση χαρακτήρων της εισαγωγής. Αυτό συνάδει με
το whitepaper της Solidsoft **EMVS1344** ("Understanding Keyboard Emulation",
7 Ιουν 2026), που επιβεβαιώνει ότι μια αναντιστοιχία διάταξης εκδηλώνεται ως
λανθασμένοι / μη λατινικοί χαρακτήρες στην τιμή (παράδειγμα από τα τσεχικά,
`0 → é`) — ακριβώς η αλλοίωση που εντοπίζει αυτή η δικλείδα.

Η εργασία υλοποιήθηκε στο πλαίσιο του δελτίου του παρόχου IT **[TICKET-REF]**.

**Ένα αίτημα επιβεβαίωσης (προς Βασίλη):** παρακαλώ επιβεβαιώστε ότι η ευρετική
της διάταξης πληκτρολογίου — αντιμετώπιση οποιουδήποτε μη λατινικού χαρακτήρα στο
πεδίο HMVS ως ένδειξη λανθασμένης διάταξης — είναι αποδεκτή ως μέθοδος ανίχνευσης.

Με εκτίμηση,
[Όνομα]
[Ρόλος / Φαρμακείο]
