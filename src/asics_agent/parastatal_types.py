"""The list of parastatal types, and the one place that reads the old type names.

Adding a type is one edit: add a `ParastatalTypeDef` to PARASTATAL_TYPES (and, if the team
wants questions to apply to it only, a rule in data/applicability_rules.yaml). Nothing else
in the code compares type strings by hand.

The ULG (the city's own municipal body) is a unit, not a parastatal type. The code still gives
the ULG unit a `Parastatal` object whose type is ULG_TYPE; that is the only name for it.
Older saved work (registers, Sources workbooks, answers files) used other names for the types;
`canonical_type` reads them and everything we write uses the new codes.
"""

from dataclasses import dataclass

from asics_agent.legacy_names import canonical_unit


@dataclass(frozen=True)
class ParastatalTypeDef:
    code: str  # what is stored and written to workbooks
    label: str  # what the team sees (register dropdown, Sources workbook)
    old_codes: tuple[str, ...] = ()  # earlier codes, read only
    old_labels: tuple[str, ...] = ()  # earlier labels, read only (any capitalisation)


PARASTATAL_TYPES: tuple[ParastatalTypeDef, ...] = (
    ParastatalTypeDef("development_authority", "Development Authority"),
    ParastatalTypeDef(
        "water_supply_entity",
        "Water Supply Entity",
        old_codes=("water_supply_board",),
        old_labels=("Water supply board",),
    ),
    ParastatalTypeDef(
        "public_bus_transport_operator",
        "Public Bus Transport Operator",
        old_codes=("transport_corporation",),
        old_labels=("Transport corporation",),
    ),
    ParastatalTypeDef("other", "Other"),
)

# The ULG unit is not a parastatal type; its Parastatal object carries this type.
ULG_TYPE = "ulg"
ULG_TYPE_LABEL = "City government"  # the label older ULG files carry in their Type column

TYPE_CODES = tuple(t.code for t in PARASTATAL_TYPES)
TYPE_LABELS_BY_CODE = {t.code: t.label for t in PARASTATAL_TYPES}
# label -> code for every type the team can choose (the register's dropdown)
LABEL_CODES = {t.label: t.code for t in PARASTATAL_TYPES}
FALLBACK_TYPE = "other"


def _key(text: str) -> str:
    return " ".join((text or "").replace("_", " ").casefold().split())


_LOOKUP: dict[str, str] = {}
for _t in PARASTATAL_TYPES:
    for _name in (_t.code, _t.label, *_t.old_codes, *_t.old_labels):
        _LOOKUP[_key(_name)] = _t.code
_LOOKUP[_key(ULG_TYPE)] = ULG_TYPE
_LOOKUP[_key(ULG_TYPE_LABEL)] = ULG_TYPE


def canonical_type(value: str) -> str:
    """The current code for a type written as a code or label, old or new.

    A value nobody recognises is returned unchanged (so the caller can report it)."""
    text = (value or "").strip()
    if not text:
        return text
    return _LOOKUP.get(_key(text)) or canonical_unit(text)


def known_type(value: str) -> bool:
    """True when `value` (code or label, old or new) names a parastatal type or the ULG."""
    return canonical_type(value) in {*TYPE_CODES, ULG_TYPE}


def type_label(code: str) -> str:
    """The label for a type code (the ULG's included, for files written for the ULG)."""
    code = canonical_type(code)
    return ULG_TYPE_LABEL if code == ULG_TYPE else TYPE_LABELS_BY_CODE.get(code, code)
