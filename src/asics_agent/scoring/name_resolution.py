"""Names of cities and parastatals in people's files, and how they meet the city register.

A filled template can name a city or a parastatal the register does not know, or spell a known one
differently ("Bangalore", "Bengaluru - BWSSB" with a hyphen). This module is the one place that:

  * folds names so dashes, spaces and capitals never matter (norm_name, split_label);
  * finds the register's match for a name: exact, an "Other name" (alias), or a close match;
  * keeps the decisions a person made in the upload preview (map to an existing one, add as new,
    skip) and remembers them, so the same spelling is not asked about again;
  * places a row at merge time from those decisions (PlaceMap), never dropping one silently.

"Add as new" only means "keep it in the people's scoring": the register is not touched, and the page
says "Not in register - AI cannot score yet". Steps 1, 2 and 3 for the AI still need the register.
Stable ids: a city is its register slug, a parastatal its short code within the city (NAMING.md).
"""

import difflib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from asics_agent.cities import slugify
from asics_agent.parastatal_types import canonical_type, known_type, type_label

NOT_IN_REGISTER = "Not in register - AI cannot score yet"
CLOSE_CUTOFF = 0.7
ACTIONS = ("map", "new", "skip")
_SPACED = re.compile(r"\s+[-‐-―−]\s+|\s*[–—−]\s*")


def _text(value) -> str:
    return "" if value is None else " ".join(str(value).split())


def norm_name(text) -> str:
    """A name for comparing: lower case, letters and digits only ("Bengaluru - BWSSB" and
    "bengaluru–BWSSB" are the same)."""
    return re.sub(r"[^a-z0-9]", "", _text(text).casefold())


def split_label(label, cities=()) -> tuple[str, str]:
    """("city", "unit") of a row label such as "Bengaluru – BWSSB", whatever the dash, spaces or
    capitals. Splits at the last separator that has spaces around it (a hyphen) or is an en/em dash;
    an unspaced hyphen stays in the name ("Hubballi-Dharwad"). A label that is a known city
    name is the city alone ("Hubballi - Dharwad" with the register's name given in `cities`)."""
    text = _text(label)
    known = {norm_name(c) for c in cities}
    if norm_name(text) in known:
        return text, ""
    found = list(_SPACED.finditer(text))
    if not found:
        return text, ""
    last = found[-1]
    return text[: last.start()].strip(), text[last.end() :].strip()


def label_key(label, cities=()) -> tuple[str, str]:
    city, unit = split_label(label, cities)
    return norm_name(city), norm_name(unit)


# -- decisions -----------------------------------------------------------------------------------
@dataclass
class Decision:
    """What a person decided about one name in an uploaded file."""

    kind: str  # "city" | "parastatal"
    as_written: str  # the name in the file
    action: str  # "map" | "new" | "skip"
    city_as_written: str = ""  # for a parastatal: the city name beside it in the file
    city_slug: str = ""  # map: the register city; new: a slug for the new one
    parastatal_code: str = ""  # map: the register parastatal's short code; new: its code
    type: str = ""  # new parastatal: a parastatal type code
    state: str = ""  # new city: asked, never invented
    ulg: str = ""
    other_name_in_register: bool = False  # the name was also written into the register
    decided_by: str = ""
    decided_at: str = ""
    submission_id: str = ""  # the submission it was made on

    def key(self) -> tuple[str, str, str]:
        city = norm_name(self.city_as_written) if self.kind == "parastatal" else ""
        return self.kind, city, norm_name(self.as_written)

    def as_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(raw: dict) -> "Decision | None":
        names = Decision.__dataclass_fields__
        try:
            d = Decision(**{k: v for k, v in raw.items() if k in names})
        except TypeError:
            return None
        return d if d.action in ACTIONS and d.kind in ("city", "parastatal") else None


def stamp(decision: Decision, by: str, submission_id: str = "") -> Decision:
    decision.decided_by = decision.decided_by or by
    decision.decided_at = decision.decided_at or datetime.now(UTC).isoformat(timespec="seconds")
    decision.submission_id = decision.submission_id or submission_id
    return decision


def remembered_decisions(settings) -> dict[tuple, Decision]:
    """Every decision saved with earlier submissions of the category: the latest per name wins."""
    from asics_agent.scoring.submissions import list_submissions

    found: dict[tuple, Decision] = {}
    for sub in list_submissions(settings):  # oldest first
        for raw in sub.decisions:
            d = Decision.from_dict(raw)
            if d is not None:
                found[d.key()] = d
    return found


# -- matching against the register ---------------------------------------------------------------
@dataclass
class Match:
    kind: str  # "exact" | "alias" | "close" | "none"
    name: str = ""  # the register's name
    slug: str = ""  # a city's slug, or a parastatal's short code
    candidates: list[str] = field(default_factory=list)


def _close(name: str, options: dict[str, tuple[str, str]]) -> Match:
    """options: norm -> (display name, id). The nearest one by spelling, if close enough."""
    guess = difflib.get_close_matches(norm_name(name), list(options), n=3, cutoff=CLOSE_CUTOFF)
    if not guess:
        return Match("none")
    shown = list(dict.fromkeys(options[g][0] for g in guess))
    return Match("close", options[guess[0]][0], options[guess[0]][1], shown)


def match_city(register, name: str) -> Match:
    """The register city a name is: its name, one of its "Other names", or the nearest spelling."""
    key = norm_name(name)
    if not key:
        return Match("none")
    options: dict[str, tuple[str, str]] = {}
    for city in register.values():
        if norm_name(city.name) == key:
            return Match("exact", city.name, city.slug)
        options.setdefault(norm_name(city.name), (city.name, city.slug))
    for city in register.values():
        for alias in city.aliases:
            if norm_name(alias) == key:
                return Match("alias", city.name, city.slug)
            options.setdefault(norm_name(alias), (city.name, city.slug))
    return _close(name, options)


def match_unit(units: dict, name: str) -> Match:
    """The parastatal of one city a name is: short code, name, an "Other name", or nearest.
    `units`: {code: object with id, name, aliases (optional)}."""
    key = norm_name(name)
    if not key:
        return Match("none")
    options: dict[str, tuple[str, str]] = {}
    for u in units.values():
        for text in (u.id, getattr(u, "name", "")):
            if norm_name(text) == key:
                return Match("exact", u.id, u.id)
    for u in units.values():
        for alias in getattr(u, "aliases", []) or []:
            if norm_name(alias) == key:
                return Match("alias", u.id, u.id)
    for u in units.values():
        for text in (u.id, getattr(u, "name", ""), *(getattr(u, "aliases", []) or [])):
            if norm_name(text):
                options.setdefault(norm_name(text), (u.id, u.id))
    return _close(name, options)


@dataclass
class Resolution:
    """One name of an uploaded file, for the preview's "Cities and parastatals" table."""

    kind: str  # "city" | "parastatal"
    as_written: str
    city_as_written: str = ""
    match: Match = field(default_factory=lambda: Match("none"))
    type_from_file: str = ""  # the file's own Configuration sheet says (a type label, or "")
    rows: int = 0  # filled rows that carry this name
    remembered: Decision | None = None  # an earlier decision about the same spelling

    @property
    def needs_decision(self) -> bool:
        """An exact or alias match is placed without asking; anything else needs a choice."""
        return self.match.kind not in ("exact", "alias")

    def key(self) -> tuple[str, str, str]:
        city = norm_name(self.city_as_written) if self.kind == "parastatal" else ""
        return self.kind, city, norm_name(self.as_written)


def places_in_file(read) -> tuple[dict, dict]:
    """({city as written: rows}, {(city, parastatal) as written: rows}) of the rows that hold a
    score, an input or evidence, and the type labels the file's Configuration sheet gives."""
    from asics_agent.scoring.template_import import EVIDENCE_FIELDS

    cities: dict[str, int] = {}
    units: dict[tuple[str, str], int] = {}
    for row in read.rows:
        if not (
            row.score is not None or row.inputs or any(getattr(row, f) for f in EVIDENCE_FIELDS)
        ):
            continue
        city, who = _text(row.city), _text(row.parastatal)
        cities[city] = cities.get(city, 0) + 1
        if who:
            units[(city, who)] = units.get((city, who), 0) + 1
    return cities, units


def config_types(read) -> dict[tuple[str, str], str]:
    """{(city norm, parastatal norm): type label} from the file's Configuration table."""
    return {
        (norm_name(c.city), norm_name(c.parastatal)): c.parastatal_type
        for c in read.config
        if c.parastatal_type
    }


def resolve_file(settings, read, remembered: dict | None = None) -> list[Resolution]:
    """The names an uploaded file uses, each with its register match and any earlier decision."""
    from asics_agent.cities import load_register
    from asics_agent.scoring.compare_run import city_units

    register, _ = load_register(settings.city_register)
    remembered = remembered if remembered is not None else remembered_decisions(settings)
    types = config_types(read)
    cities, units = places_in_file(read)
    out: list[Resolution] = []
    city_match: dict[str, Match] = {}
    for city, rows in sorted(cities.items()):
        m = city_match[city] = match_city(register, city)
        out.append(
            Resolution("city", city, "", m, "", rows, remembered.get(("city", "", norm_name(city))))
        )
    if settings.unit == "ulg":
        return out
    by_slug = {c.slug: c for c in register.values()}
    unit_cache: dict[str, dict] = {}
    for (city, who), rows in sorted(units.items()):
        decision = remembered.get(("city", "", norm_name(city)))
        target = city_match[city]
        if decision is not None and decision.action == "map":
            target = Match("exact", slug=decision.city_slug)
        found: Match = Match("none")
        if target.kind in ("exact", "alias") and target.slug in by_slug:
            if target.slug not in unit_cache:
                unit_cache[target.slug] = city_units(settings, by_slug[target.slug])[0]
            found = match_unit(unit_cache[target.slug], who)
        out.append(
            Resolution(
                "parastatal",
                who,
                city,
                found,
                types.get((norm_name(city), norm_name(who)), ""),
                rows,
                remembered.get(("parastatal", norm_name(city), norm_name(who))),
            )
        )
    return out


def undecided(resolutions: list[Resolution], decisions: list[Decision]) -> list[Resolution]:
    """The names that still need a choice."""
    have = {d.key() for d in decisions}
    return [r for r in resolutions if r.needs_decision and r.key() not in have]


# -- placing a row at merge time -------------------------------------------------------------------
@dataclass
class Placement:
    city: str = ""
    unit: str = ""
    type_label: str = ""
    registered: bool = True  # the city and the parastatal are both in the register
    city_registered: bool = True
    skipped: bool = False
    why: str = ""
    state: str = ""
    ulg: str = ""


def _type_label(code_or_label: str) -> str:
    return type_label(canonical_type(code_or_label)) if known_type(code_or_label) else ""


class PlaceMap:
    """Places the rows of a file: the register's names where there is a match or a decision,
    its own place (flagged "Not in register") where there is not, and nothing dropped."""

    def __init__(self, settings, register, decisions: dict[tuple, Decision], file_types=None):
        from asics_agent.scoring.compare_run import city_units

        self.settings, self.register, self.decisions = settings, register, decisions
        self.file_types = file_types or {}
        self._units: dict[str, dict] = {}
        self._city_units = city_units
        self._by_slug = {c.slug: c for c in register.values()}
        self._first: dict[str, str] = {}  # norm -> the first spelling met, for unregistered names

    def _spelling(self, name: str, shown: str = "") -> str:
        return self._first.setdefault(norm_name(name), shown or _text(name))

    def _units_of(self, city):
        if city.slug not in self._units:
            self._units[city.slug] = self._city_units(self.settings, city)[0]
        return self._units[city.slug]

    def place(self, city_written: str, who_written: str) -> Placement:
        key_city = ("city", "", norm_name(city_written))
        d = self.decisions.get(key_city)
        city, new_state, new_ulg = None, "", ""
        if d is not None and d.action == "skip":
            return Placement(skipped=True, why=f"the city {city_written} was skipped")
        if d is not None and d.action == "map" and d.city_slug in self._by_slug:
            city = self._by_slug[d.city_slug]
        elif d is not None and d.action == "new":
            new_state, new_ulg = d.state, d.ulg
        else:
            m = match_city(self.register, city_written)
            if m.kind in ("exact", "alias"):
                city = self._by_slug[m.slug]
        if city is None:  # its own place: a new city (or a near spelling nobody confirmed)
            name = self._spelling(city_written)
            if self.settings.unit == "ulg":
                return Placement(name, "", "", False, False, state=new_state, ulg=new_ulg)
            return self._unregistered_unit(name, who_written, False, new_state, new_ulg)
        if self.settings.unit == "ulg":
            return Placement(city.name, "", "", True)
        return self._in_city(city, city_written, who_written)

    def _in_city(self, city, city_written: str, who_written: str) -> Placement:
        key = ("parastatal", norm_name(city_written), norm_name(who_written))
        d = self.decisions.get(key)
        units = self._units_of(city)
        if d is not None and d.action == "skip":
            return Placement(skipped=True, why=f"{who_written} ({city_written}) was skipped")
        if d is not None and d.action == "map" and d.parastatal_code in units:
            u = units[d.parastatal_code]
            return Placement(city.name, u.id, type_label(u.type), True)
        if d is None or d.action != "new":
            m = match_unit(units, who_written)
            if m.kind in ("exact", "alias"):
                u = units[m.slug]
                return Placement(city.name, u.id, type_label(u.type), True)
        return self._unregistered_unit(
            city.name,
            who_written,
            True,
            "",
            "",
            d.type if d is not None else "",
            d.parastatal_code if d is not None and d.action == "new" else "",
        )

    def _unregistered_unit(self, city, who, city_registered, state, ulg, decided_type="", code=""):
        code = code or self._spelling(f"{city}|{who}", _text(who)) or "UNKNOWN"
        kind = decided_type or self.file_types.get((norm_name(city), norm_name(who)), "")
        return Placement(
            city,
            code,
            _type_label(kind),
            False,
            city_registered,
            why=NOT_IN_REGISTER,
            state=state,
            ulg=ulg,
        )


def pseudo_city(name: str, units: list[dict], state: str = "", ulg: str = ""):
    """A CityConfig for a place only the people's files know (for the Scores page)."""
    from asics_agent.models import CityConfig, Parastatal

    return CityConfig(
        slug=slugify(name),
        name=name,
        state=state,
        ulg=ulg,
        parastatals=[
            Parastatal(
                id=u["parastatal"],
                name=u["parastatal"],
                type=canonical_type(u["type"]) if known_type(u.get("type", "")) else "other",
            )
            for u in units
        ],
    )
