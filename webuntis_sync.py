"""
WebUntis -> ICS Sync
====================
Loggt sich bei WebUntis ein, holt den Stundenplan fuer den konfigurierten
Zeitraum, wendet Personalisierungen aus config.yaml an und schreibt das
Ergebnis in stundenplan.ics.

Login-Daten kommen aus Umgebungsvariablen (WEBUNTIS_USER, WEBUNTIS_PASSWORD)
und liegen in GitHub Actions als Secrets.

Aufruf:
    python webuntis_sync.py
"""

from __future__ import annotations

import os
import sys
import json
import hashlib
import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import webuntis
from ics import Calendar, Event
from ics.alarm import DisplayAlarm


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.yaml"
OUTPUT_PATH = SCRIPT_DIR / "stundenplan.ics"
OUTPUT_JSON_PATH = SCRIPT_DIR / "stundenplan.json"

# Schema-Version des JSON-Outputs. Erhoehen, wenn breaking changes am Schema
# gemacht werden, damit die App reagieren kann.
JSON_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Config-Handling
# ---------------------------------------------------------------------------

@dataclass
class Config:
    raw: dict

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            sys.exit(
                f"[FEHLER] {path.name} fehlt. Kopiere config.example.yaml "
                f"nach config.yaml und passe sie an."
            )
        with path.open("r", encoding="utf-8") as fh:
            return cls(raw=yaml.safe_load(fh))

    def get(self, dotted: str, default=None):
        node: Any = self.raw
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node


# ---------------------------------------------------------------------------
# Helpers fuer Fach-Matching & Formatierung
# ---------------------------------------------------------------------------

def normalize(s: str | None) -> str:
    return (s or "").strip()


def match_subject(name: str, subjects_cfg: dict) -> tuple[str, dict]:
    """Findet den konfigurierten Fach-Eintrag fuer einen WebUntis-Fachnamen.

    Returnt (canonical_name, subject_config_dict).
    Faellt auf '_default' zurueck, wenn nichts matcht.
    """
    name_norm = normalize(name)
    for canonical, cfg in subjects_cfg.items():
        if canonical == "_default":
            continue
        if canonical.lower() == name_norm.lower():
            return canonical, cfg
        aliases = [a.lower() for a in cfg.get("aliases", [])]
        if name_norm.lower() in aliases:
            return canonical, cfg
    return name_norm, subjects_cfg.get("_default", {"color": "#95a5a6"})


def format_template(template: str, **values) -> str:
    """Wie str.format, aber fehlende Keys werden zu leeren Strings."""
    class _Safe(dict):
        def __missing__(self, k):
            return ""
    return template.format_map(_Safe(**values))


# ---------------------------------------------------------------------------
# WebUntis -> Domain-Objekt
# ---------------------------------------------------------------------------

@dataclass
class Lesson:
    """Eine Stunde, bereits in unsere Datenstruktur uebersetzt."""
    start: dt.datetime
    end: dt.datetime
    subject: str
    teachers: list[str]
    rooms: list[str]
    klassen: list[str]
    code: str          # "" / "cancelled" / "irregular"
    is_exam: bool
    sub_text: str      # Vertretungstext, falls vorhanden
    original_teachers: list[str]  # bei Vertretung: ursprueglicher Lehrer
    original_rooms: list[str]


def _names_from_attr(period, attr_name: str, raw_key: str) -> list[str]:
    """Liest period.<attr> (z.B. period.teachers). Wenn das einen
    Permission-Fehler wirft (haeufig bei Schueler-Accounts ohne Recht
    fuer getTeachers/getRooms/...), faellt es auf die rohen Period-Daten
    zurueck — dann gibt's IDs statt Namen, aber kein Crash."""
    try:
        items = getattr(period, attr_name)
        if not items:
            return []
        return [_extract_name(i) for i in items]
    except Exception:
        try:
            raw_list = period._data.get(raw_key, []) or []
        except Exception:
            return []
        return [_extract_raw_name(r) for r in raw_list]


def _extract_name(item) -> str:
    for a in ("name", "longname"):
        v = getattr(item, a, None)
        if v:
            return str(v)
    iid = getattr(item, "id", None)
    return f"#{iid}" if iid is not None else "?"


def _extract_raw_name(raw: dict) -> str:
    for k in ("name", "longname"):
        if raw.get(k):
            return str(raw[k])
    iid = raw.get("id")
    return f"#{iid}" if iid is not None else "?"


def _original_names(period, attr_name: str, raw_key: str,
                    orgid_key: str) -> list[str]:
    """Ursprueglicher Lehrer/Raum bei Vertretungen. Erst aus dem Lib-Objekt,
    bei Permission-Error aus _data[raw_key][i][orgid_key]."""
    try:
        items = getattr(period, attr_name)
        if not items:
            return []
        return [str(t.orgname) for t in items if getattr(t, "orgname", None)]
    except Exception:
        try:
            raw_list = period._data.get(raw_key, []) or []
        except Exception:
            return []
        return [f"#{r[orgid_key]}" for r in raw_list if r.get(orgid_key)]


def fetch_lessons(session: webuntis.Session, start: dt.date, end: dt.date) -> list[Lesson]:
    """Holt den Stundenplan vom WebUntis-Server und mappt ihn auf Lesson."""
    timetable = session.my_timetable(start=start, end=end)
    lessons: list[Lesson] = []
    for period in timetable:
        subjects_list = _names_from_attr(period, "subjects", "su")
        subject = ", ".join(subjects_list) if subjects_list else "?"
        teachers = _names_from_attr(period, "teachers", "te")
        rooms = _names_from_attr(period, "rooms", "ro")
        klassen = _names_from_attr(period, "klassen", "kl")

        # Originale (bei Vertretung): WebUntis liefert original_* nur wenn anders.
        original_teachers = _original_names(period, "teachers", "te", "orgid")
        original_rooms = _original_names(period, "rooms", "ro", "orgid")

        code = getattr(period, "code", "") or ""
        # In manchen WebUntis-Instanzen sind Klausuren ueber period.type erkennbar.
        is_exam = bool(getattr(period, "exam", None)) or \
                  (getattr(period, "type", "") == "exam")

        sub_text = getattr(period, "substText", "") or getattr(period, "lstext", "") or ""

        lessons.append(Lesson(
            start=period.start,
            end=period.end,
            subject=subject,
            teachers=teachers,
            rooms=rooms,
            klassen=klassen,
            code=code,
            is_exam=is_exam,
            sub_text=sub_text,
            original_teachers=original_teachers,
            original_rooms=original_rooms,
        ))
    return lessons


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def passes_filter(lesson: Lesson, cfg: Config) -> bool:
    filt = cfg.get("filter", {}) or {}
    excl_subj = {s.lower() for s in filt.get("exclude_subjects", [])}
    excl_tea = {t.lower() for t in filt.get("exclude_teachers", [])}
    excl_cls = {c.lower() for c in filt.get("exclude_classes", [])}
    excl_wd = set(filt.get("exclude_weekdays", []))

    if lesson.subject.lower() in excl_subj:
        return False
    if any(t.lower() in excl_tea for t in lesson.teachers):
        return False
    if any(c.lower() in excl_cls for c in lesson.klassen):
        return False
    if lesson.start.weekday() in excl_wd:
        return False
    return True


# ---------------------------------------------------------------------------
# Lesson -> ICS Event
# ---------------------------------------------------------------------------

def build_event(lesson: Lesson, cfg: Config) -> Event | None:
    """Baut ein ICS-Event aus einer Stunde. Returnt None wenn die Stunde
    laut Config rausgefiltert werden soll (z.B. entfallen + mode=remove)."""

    subjects_cfg = cfg.get("subjects", {}) or {}
    canonical, subj_cfg = match_subject(lesson.subject, subjects_cfg)
    color = subj_cfg.get("color", "#95a5a6")

    title_prefix = ""
    title_suffix_info: list[str] = []

    # --- Entfaelle ---
    if lesson.code == "cancelled":
        cancel_cfg = cfg.get("substitutions.cancelled", {}) or {}
        if cancel_cfg.get("mode", "mark") == "remove":
            return None
        title_prefix = cancel_cfg.get("title_prefix", "ENTFALL: ")
        color = cancel_cfg.get("color", color)

    # --- Vertretungen / Aenderungen ---
    elif lesson.code == "irregular":
        # Raumwechsel?
        if lesson.original_rooms:
            rc_cfg = cfg.get("substitutions.room_change", {}) or {}
            title_prefix = rc_cfg.get("title_prefix", "") + title_prefix
            if rc_cfg.get("show_original_room", True):
                title_suffix_info.append(
                    f"(statt {', '.join(lesson.original_rooms)})"
                )
        # Lehrervertretung?
        if lesson.original_teachers:
            sub_cfg = cfg.get("substitutions.substitute", {}) or {}
            title_prefix = sub_cfg.get("title_prefix", "") + title_prefix
            color = sub_cfg.get("color", color)
            if sub_cfg.get("show_original_teacher", True):
                title_suffix_info.append(
                    f"(statt {', '.join(lesson.original_teachers)})"
                )
        # Zusatzstunde?
        if not lesson.original_teachers and not lesson.original_rooms:
            add_cfg = cfg.get("substitutions.additional", {}) or {}
            title_prefix = add_cfg.get("title_prefix", "+ ")
            color = add_cfg.get("color", color)

    # --- Klausuren ---
    if lesson.is_exam:
        exam_cfg = cfg.get("exams", {}) or {}
        if exam_cfg.get("enabled", True):
            title_prefix = exam_cfg.get("title_prefix", "KLAUSUR: ") + title_prefix
            color = exam_cfg.get("color", color)

    # --- Titel / Beschreibung / Ort zusammenbauen ---
    values = dict(
        subject=canonical,
        teacher=", ".join(lesson.teachers),
        room=", ".join(lesson.rooms),
        **{"class": ", ".join(lesson.klassen)},
    )
    base_title = format_template(
        cfg.get("display.title_format", "{subject}"), **values
    )
    title = title_prefix + base_title
    if title_suffix_info:
        title += " " + " ".join(title_suffix_info)

    description = format_template(
        cfg.get("display.description_format", ""), **values
    )
    if lesson.sub_text:
        description = (description + "\n\nHinweis: " + lesson.sub_text).strip()

    location = format_template(
        cfg.get("display.location_format", ""), **values
    )

    event = Event()
    event.name = title
    event.begin = lesson.start
    event.end = lesson.end
    event.description = description
    event.location = location

    # Farbe (Microsoft-Property + ics Categories als Fallback)
    if color:
        event.categories = {canonical}
        # Hack: ics-Lib hat keine direkte color-API, also Extra-Property
        event.extra.append(_ics_color_line(color))

    # Klausur-Erinnerung
    if lesson.is_exam:
        reminder = cfg.get("exams.reminder_minutes", 0) or 0
        if reminder > 0:
            event.alarms.append(DisplayAlarm(
                trigger=dt.timedelta(minutes=-reminder)
            ))

    return event


def _ics_color_line(hex_color: str):
    """Erzeugt eine X-APPLE-CALENDAR-COLOR / COLOR Zeile fuer die ics-Lib."""
    from ics.grammar.parse import ContentLine
    return ContentLine(name="COLOR", value=hex_color)


# ---------------------------------------------------------------------------
# JSON-Export fuer die App
# ---------------------------------------------------------------------------

def _lesson_status(lesson: Lesson) -> str:
    """Klassifiziert eine Stunde in eine fuer die App nuetzliche Kategorie."""
    if lesson.code == "cancelled":
        return "cancelled"
    if lesson.code == "irregular":
        if lesson.original_teachers and lesson.original_rooms:
            return "substitute"  # Lehrer- + Raumwechsel = generelle Vertretung
        if lesson.original_teachers:
            return "substitute"
        if lesson.original_rooms:
            return "room_change"
        return "additional"
    return "regular"


def _stable_id(lesson: Lesson) -> str:
    """Stabile, deterministische ID fuer eine Stunde (fuer App-Caching)."""
    raw = f"{lesson.start.isoformat()}|{lesson.subject}|{','.join(lesson.teachers)}|{','.join(lesson.rooms)}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_json_payload(lessons: list[Lesson], cfg: Config) -> dict:
    """Baut das JSON-Payload, das die Flutter-App liest."""
    subjects_cfg = cfg.get("subjects", {}) or {}
    default_color = (subjects_cfg.get("_default") or {}).get("color", "#95a5a6")

    json_lessons = []
    for lesson in lessons:
        if not passes_filter(lesson, cfg):
            continue
        canonical, subj_cfg = match_subject(lesson.subject, subjects_cfg)
        status = _lesson_status(lesson)
        # Entfaelle: respektiere mode=remove auch im JSON
        if status == "cancelled":
            mode = (cfg.get("substitutions.cancelled") or {}).get("mode", "mark")
            if mode == "remove":
                continue

        json_lessons.append({
            "id": _stable_id(lesson),
            "start": lesson.start.isoformat(),
            "end": lesson.end.isoformat(),
            "subject_raw": lesson.subject,
            "subject_canonical": canonical,
            "subject_color": subj_cfg.get("color", default_color),
            "teachers": lesson.teachers,
            "rooms": lesson.rooms,
            "classes": lesson.klassen,
            "status": status,
            "is_exam": lesson.is_exam,
            "original_teachers": lesson.original_teachers,
            "original_rooms": lesson.original_rooms,
            "note": lesson.sub_text,
        })

    # Sortiert nach Startzeit fuer die App
    json_lessons.sort(key=lambda x: x["start"])

    # Fach-Config nochmal kompakt fuer die App (ohne _default-Sonderfall)
    subjects_export = {}
    for name, c in subjects_cfg.items():
        if name == "_default":
            continue
        subjects_export[name] = {
            "color": c.get("color", default_color),
            "aliases": c.get("aliases", []),
        }

    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "timezone": cfg.get("sync.timezone", "Europe/Vienna"),
        "school": {
            "name": cfg.get("webuntis.school"),
            "server": cfg.get("webuntis.server"),
        },
        "calendar": {
            "name": cfg.get("calendar.name", "Schule"),
            "description": cfg.get("calendar.description", ""),
        },
        "subjects": subjects_export,
        "default_color": default_color,
        "lessons": json_lessons,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    cfg = Config.load(CONFIG_PATH)

    user = os.environ.get("WEBUNTIS_USER")
    password = os.environ.get("WEBUNTIS_PASSWORD")
    if not user or not password:
        sys.exit("[FEHLER] WEBUNTIS_USER und WEBUNTIS_PASSWORD muessen gesetzt sein.")

    server = cfg.get("webuntis.server")
    school = cfg.get("webuntis.school")
    if not server or not school:
        sys.exit("[FEHLER] webuntis.server und webuntis.school in config.yaml setzen.")

    today = dt.date.today()
    start = today - dt.timedelta(weeks=cfg.get("sync.weeks_back", 1))
    end = today + dt.timedelta(weeks=cfg.get("sync.weeks_ahead", 4))

    print(f"[INFO] Sync {start} bis {end} von {server} / {school}")

    with webuntis.Session(
        server=server,
        school=school,
        username=user,
        password=password,
        useragent="webuntis-sync (personal calendar)",
    ).login() as session:
        lessons = fetch_lessons(session, start, end)

    print(f"[INFO] {len(lessons)} Stunden erhalten")

    # Welche Outputs sind aktiviert?
    ics_enabled = bool(cfg.get("outputs.ics.enabled", False))
    json_enabled = bool(cfg.get("outputs.json.enabled", True))

    if not ics_enabled and not json_enabled:
        sys.exit("[FEHLER] Weder JSON- noch ICS-Output aktiviert. "
                 "outputs.json.enabled oder outputs.ics.enabled auf true setzen.")

    # --- JSON-Export fuer die App ---------------------------------------
    if json_enabled:
        payload = build_json_payload(lessons, cfg)
        OUTPUT_JSON_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[OK] {OUTPUT_JSON_PATH.name} geschrieben "
              f"({len(payload['lessons'])} Stunden)")
    else:
        print("[INFO] JSON-Output deaktiviert (outputs.json.enabled = false)")

    # --- ICS-Export (optional, fuer Google/Apple/Outlook) ---------------
    if ics_enabled:
        calendar = Calendar()
        kept = 0
        for lesson in lessons:
            if not passes_filter(lesson, cfg):
                continue
            event = build_event(lesson, cfg)
            if event is None:
                continue
            calendar.events.add(event)
            kept += 1
        print(f"[INFO] {kept} Events fuer ICS nach Filter/Personalisierung")

        from ics.grammar.parse import ContentLine
        calendar.extra.append(ContentLine(
            name="X-WR-CALNAME",
            value=cfg.get("calendar.name", "Schule")
        ))
        calendar.extra.append(ContentLine(
            name="X-WR-CALDESC",
            value=cfg.get("calendar.description", "")
        ))
        calendar.extra.append(ContentLine(
            name="X-WR-TIMEZONE",
            value=cfg.get("sync.timezone", "Europe/Vienna")
        ))

        OUTPUT_PATH.write_text(calendar.serialize(), encoding="utf-8")
        print(f"[OK] {OUTPUT_PATH.name} geschrieben")
    else:
        # Alte ICS-Datei aufraeumen, falls Feature deaktiviert wurde.
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()
            print(f"[INFO] {OUTPUT_PATH.name} entfernt "
                  "(outputs.ics.enabled = false)")
        else:
            print("[INFO] ICS-Output deaktiviert (outputs.ics.enabled = false)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
