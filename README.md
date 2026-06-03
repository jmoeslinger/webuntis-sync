# WebUntis Sync — Backend

Stuendlicher Sync deines WebUntis-Stundenplans nach `stundenplan.json`,
gehostet auf GitHub Pages. Wird von der
[Stundenplan-App](../webuntis-app/) gelesen.

## Was das Tool macht

- Loggt sich bei WebUntis ein, holt 4 Wochen Stundenplan
- Wendet deine Personalisierung aus `config.yaml` an (Fach-Farben, Filter,
  Vertretungs-Markierungen, Klausuren-Erkennung)
- Schreibt `stundenplan.json` (App-Format) ins Repo
- **Optional:** schreibt zusaetzlich `stundenplan.ics` fuer Google/Apple/Outlook,
  wenn du den Stundenplan extern teilen willst

## Architektur

```
GitHub Actions (stuendlich, Cronjob)
    |
    v
webuntis_sync.py
    | liest config.yaml + Login aus GitHub Secrets
    | holt 4 Wochen Stundenplan via webuntis-API
    | wendet Personalisierungen an
    v
stundenplan.json -> committet ins Repo
    |
    v
GitHub Pages -> https://<dein-user>.github.io/<repo>/stundenplan.json
    |
    v
Stundenplan-App (Android + Windows) holt sich die JSON
```

Falls du in der `config.yaml` zusaetzlich `outputs.ics.enabled: true` setzt,
wird parallel eine `stundenplan.ics`-Datei generiert (siehe Anhang A in
SETUP.md).

## Erstes Setup

Siehe [`SETUP.md`](SETUP.md) — Schritt-fuer-Schritt-Anleitung, ca. 15-20 Minuten.

Danach: [`webuntis-app/SETUP_APP.md`](../webuntis-app/SETUP_APP.md) fuer die App.

## Personalisierung anpassen

1. `config.yaml` im Repo bearbeiten (entweder lokal oder direkt auf github.com)
2. Aenderungen committen
3. Beim naechsten Sync (max. 1 Stunde) sind sie aktiv
4. Die App uebernimmt die neuen Werte beim naechsten Refresh

## Lokal testen

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
# config.yaml bearbeiten (server, school, Faecher)

# Login als Umgebungsvariablen setzen (Windows PowerShell)
$env:WEBUNTIS_USER = "dein-user"
$env:WEBUNTIS_PASSWORD = "dein-passwort"

python webuntis_sync.py
# -> erzeugt stundenplan.json im aktuellen Ordner
# -> erzeugt stundenplan.ics nur wenn outputs.ics.enabled = true
```

## Troubleshooting

| Problem | Loesung |
|---|---|
| `Could not find school` | `webuntis.school` in config.yaml exakt wie auf der WebUntis-Login-Seite |
| `Bad credentials` | GitHub Secrets pruefen (Settings -> Secrets -> Actions) |
| App zeigt veraltete Daten | App-Refresh-Button oder Repo: "Run workflow" haendisch ausloesen |
| Stunden fehlen in JSON | `filter:` Section in config.yaml pruefen; ggf. `weeks_ahead` erhoehen |
| Brauche doch ICS fuer Google | In `config.yaml` `outputs.ics.enabled: true` setzen, committen |
| ICS soll wieder weg | In `config.yaml` `outputs.ics.enabled: false` — die Datei wird beim naechsten Lauf geloescht |
