# Setup-Anleitung — Backend (WebUntis Sync)

Diese Anleitung richtet das **Backend** ein: ein GitHub-Repo, das stuendlich
deinen WebUntis-Stundenplan abholt und als `stundenplan.json` ablegt. Die
[Stundenplan-App](../webuntis-app/SETUP_APP.md) liest diese Datei.

**Gesamtdauer: ca. 15-20 Minuten.**

> **Brauche ich Google Kalender?** Nein, wenn du die App nutzt. Die App liest
> direkt die JSON. Den optionalen ICS-Export fuer Google/Apple/Outlook kannst
> du in [Anhang A](#anhang-a--ics-export-fuer-google-apple-outlook) anschalten,
> falls du den Stundenplan mal mit jemandem teilen willst.

---

## Schritt 1 — GitHub-Account & Repo erstellen

1. Falls noch nicht vorhanden: Account auf https://github.com/signup erstellen.
2. Neues Repo erstellen: https://github.com/new
   - **Repository name:** `webuntis-sync` (oder wie du willst)
   - **Visibility: Public** auswaehlen
     > Warum public? Damit GitHub Pages funktioniert. Die JSON-URL ist nicht
     > erratbar (zufaelliger langer Pfad), und sensible Daten liegen in den
     > Secrets — nicht im Code.
   - **Add a README file** ankreuzen
   - "Create repository" klicken

---

## Schritt 2 — Dateien ins Repo laden

**Variante A — wenn du Git/CLI gewohnt bist:**

```bash
cd C:\Users\smart\claude\projects\webuntis-sync
git init
git remote add origin https://github.com/DEIN-USER/webuntis-sync.git
git checkout -b main
git add .
git commit -m "initial setup"
git push -u origin main --force
```

**Variante B — ueber die GitHub-Website (kein Git noetig):**

1. Auf deiner Repo-Seite oben "Add file" -> "Upload files" klicken.
2. Alle Dateien aus `C:\Users\smart\claude\projects\webuntis-sync\` per
   Drag & Drop reinziehen, **inklusive** des Ordners `.github`.
   > Hinweis: Wenn du die `.github/workflows/sync.yml` einzeln hochlaedst, leg
   > sie ueber "Add file" -> "Create new file" mit dem Pfad
   > `.github/workflows/sync.yml` an.
3. Unten "Commit changes" klicken.

4. **config.yaml erstellen:** Das Tool braucht eine `config.yaml` (nicht nur
   `config.example.yaml`). Auf der GitHub-Repo-Seite:
   - `config.example.yaml` oeffnen -> oben rechts Stift-Symbol (Edit) klicken
   - Inhalt komplett kopieren
   - Zurueck zur Repo-Hauptseite -> "Add file" -> "Create new file"
   - Dateiname: `config.yaml`
   - Inhalt einfuegen
   - **Werte anpassen:** `webuntis.server`, `webuntis.school`, und deine Faecher
   - "Commit new file"

---

## Schritt 3 — WebUntis-Login als Secrets eintragen

Damit dein Passwort nicht im Code steht, kommt es verschluesselt in
GitHub Secrets. So:

1. Im Repo: **Settings** (oben rechts) -> linke Sidebar: **Secrets and variables**
   -> **Actions**.
2. "New repository secret" klicken.
3. Erstes Secret:
   - **Name:** `WEBUNTIS_USER`
   - **Secret:** dein WebUntis-Benutzername (genauso wie beim Login)
   - "Add secret"
4. Zweites Secret:
   - **Name:** `WEBUNTIS_PASSWORD`
   - **Secret:** dein WebUntis-Passwort
   - "Add secret"

Beide werden nach dem Speichern verschluesselt und sind nirgends mehr lesbar —
auch nicht fuer dich.

---

## Schritt 4 — GitHub Actions & GitHub Pages aktivieren

### 4a) Actions starten

1. Im Repo: **Actions**-Tab oben.
2. Falls noetig: "I understand my workflows, go ahead and enable them" klicken.
3. Links den Workflow **"WebUntis Sync"** waehlen.
4. Rechts "Run workflow" -> "Run workflow" klicken (manueller Test-Lauf).
5. Nach ca. 30-60 Sekunden sollte der Lauf gruen sein und im Repo eine neue
   Datei `stundenplan.json` aufgetaucht sein.

   > Wenn rot: Auf den Lauf klicken, dann auf den fehlgeschlagenen Step
   > ("Sync WebUntis") fuer die Fehlermeldung.

### 4b) GitHub Pages anschalten

1. Im Repo: **Settings** -> linke Sidebar **Pages**.
2. Unter "Build and deployment":
   - **Source:** "Deploy from a branch"
   - **Branch:** `main`, Ordner `/ (root)`
   - "Save"
3. Warte ~1 Minute. Oben erscheint dann eine URL der Form:
   `https://DEIN-USER.github.io/webuntis-sync/`
4. Deine JSON-URL ist:
   `https://DEIN-USER.github.io/webuntis-sync/stundenplan.json`
5. Testweise im Browser oeffnen — du solltest JSON mit Feldern wie
   `"schema_version"`, `"lessons"` etc. sehen. Wenn ja: perfekt.

---

## Schritt 5 — App einrichten

Backend laeuft. Jetzt zur App:

-> **[`webuntis-app/SETUP_APP.md`](../webuntis-app/SETUP_APP.md)** durchgehen.

Beim ersten Start der App traegst du dort einfach die JSON-URL aus Schritt 4b ein.

---

## Aenderungen an der Personalisierung

Wenn du z.B. eine andere Farbe fuer Mathe willst:

1. Im Repo `config.yaml` oeffnen -> Stift-Symbol (Edit).
2. Farbcode aendern.
3. "Commit changes".
4. Beim naechsten stuendlichen Lauf (oder manuell ueber "Run workflow") wird
   die Aenderung in die `stundenplan.json` uebernommen.
5. Die App holt die neuen Daten beim naechsten Refresh.

> Pro Geraet kannst du Farben in den App-Einstellungen ueberschreiben, ohne
> die `config.yaml` anzufassen. Die Override gilt nur fuer dieses Geraet.

---

## Sicherheits-Hinweise

- Dein Repo ist **public**, aber:
  - Keine Login-Daten im Code — die sind in Secrets.
  - Die JSON-URL ist nicht zufaellig genug um wirklich geheim zu sein. Wenn
    dir das Sorgen macht, sieh dir die Variante "Strikt — Cloudflare Worker"
    an (frag mich, dann baue ich die Variante).
- Wenn du dein Repo lieber privat haettest: GitHub Pages funktioniert mit
  Free-Account nur bei public repos. Alternative: GitHub Pro (privat moeglich)
  oder Cloudflare Worker / Vercel.

---

## Anhang A — ICS-Export fuer Google, Apple, Outlook

> **Nur lesen, wenn du den Stundenplan mit jemandem teilen willst, der die App
> nicht installieren kann/will** (z.B. Eltern, die nur Google Kalender nutzen).
> Fuer den eigenen Gebrauch reicht die App.

### A1) ICS-Output aktivieren

In `config.yaml` die `outputs`-Sektion anpassen:

```yaml
outputs:
  json:
    enabled: true
  ics:
    enabled: true    # <-- auf true setzen
```

Committen. Beim naechsten Sync-Lauf erscheint zusaetzlich `stundenplan.ics`
im Repo, erreichbar unter:
`https://DEIN-USER.github.io/webuntis-sync/stundenplan.ics`

### A2) In Google Kalender abonnieren

1. https://calendar.google.com oeffnen.
2. Links unten bei **"Weitere Kalender"** das **+** klicken.
3. **"Per URL"** auswaehlen.
4. Deine ICS-URL einfuegen:
   `https://DEIN-USER.github.io/webuntis-sync/stundenplan.ics`
5. "Kalender hinzufuegen" klicken.

**Wichtig:** Google Kalender holt ICS-Abos nicht in Echtzeit, sondern nur alle
paar Stunden (meist 4-12h, manchmal bis zu 24h). Vertretungen kommen also
nicht sofort an — daran kann man als Endnutzer leider nichts aendern.

### A3) Andere Kalender-Apps

- **Apple Kalender:** Datei -> Neues Kalender-Abo -> URL einfuegen
- **Outlook (Web):** Kalender hinzufuegen -> Aus dem Web abonnieren -> URL
- **Thunderbird:** Neuer Kalender -> Im Netzwerk -> iCalendar (ICS) -> URL

---

## Fragen / Probleme

Wenn etwas nicht funktioniert, sag mir:
- Welcher Schritt
- Welche Fehlermeldung (Screenshot oder kopierter Text)
- Ggf. Inhalt der `Actions`-Log-Ausgabe

Dann fixen wir das.
